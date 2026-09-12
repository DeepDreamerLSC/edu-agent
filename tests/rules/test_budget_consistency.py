"""02 §11.4 一致性红灯:文档表格数字与常量/pyproject 不一致必须失败,
解析不到某项同样按不一致处理,不允许静默跳过。"""

import tomllib

import scripts.budget as budget

from rulekit import REPO_ROOT, VALID_PYPROJECT, run_py


def edit_doc(base_repo, transform) -> None:
    doc = base_repo / "docs" / "plan" / "02-complexity-budget.md"
    doc.write_text(transform(doc.read_text(encoding="utf-8")), encoding="utf-8")


def test_doc_number_mismatch_fails(base_repo):
    """改了文档数字没改常量 → 红,并点名指标。"""
    edit_doc(base_repo, lambda text: text.replace("| 30 000 |", "| 29 000 |", 1))
    result = run_py("budget.py", "--root", str(base_repo))
    assert result.returncode != 0
    assert "BUDGET-FAIL doc-consistency(app-total-lines)" in result.stdout


def test_doc_missing_row_fails(base_repo):
    """表格删掉某行 → 按不一致处理,不允许静默跳过。"""
    edit_doc(
        base_repo,
        lambda text: "\n".join(
            line for line in text.splitlines() if not line.startswith("| 部署脚本行数 |")
        ),
    )
    result = run_py("budget.py", "--root", str(base_repo))
    assert result.returncode != 0
    assert "doc-consistency(deploy-script-lines)" in result.stdout
    assert "解析不到" in result.stdout


def test_doc_21_threshold_mismatch_fails(base_repo):
    """2.1 表阈值与常量/pyproject 不一致 → 红。"""
    edit_doc(
        base_repo,
        lambda text: text.replace(
            "| 函数语句数 | PLR0915 | 50 |", "| 函数语句数 | PLR0915 | 49 |", 1
        ),
    )
    result = run_py("budget.py", "--root", str(base_repo))
    assert result.returncode != 0
    assert "BUDGET-FAIL ruff-consistency" in result.stdout
    assert "PLR0915" in result.stdout


def test_pyproject_threshold_mismatch_fails(base_repo):
    """pyproject 阈值改了没同步文档/常量 → 红,并点名配置键。"""
    (base_repo / "pyproject.toml").write_text(
        VALID_PYPROJECT.replace("max-statements = 50", "max-statements = 49"),
        encoding="utf-8",
    )
    result = run_py("budget.py", "--root", str(base_repo))
    assert result.returncode != 0
    assert "BUDGET-FAIL ruff-consistency" in result.stdout
    assert "max-statements" in result.stdout


def test_pyproject_select_missing_code_fails(base_repo):
    """select 里删掉某条规则(规则被改坏/删除)→ 红。"""
    (base_repo / "pyproject.toml").write_text(
        VALID_PYPROJECT.replace('    "S102",\n', ""),
        encoding="utf-8",
    )
    result = run_py("budget.py", "--root", str(base_repo))
    assert result.returncode != 0
    assert "BUDGET-FAIL ruff-consistency" in result.stdout
    assert "S102" in result.stdout


def test_repo_doc_matches_repo_constants():
    """仓库自身的文档、常量、pyproject 三方必须一致(CI 也跑 budget,此处点名断言)。"""
    root = REPO_ROOT
    assert budget.check_doc_section2(root) == []
    assert budget.check_ruff_consistency(root) == []


def test_kernel_mechanisms_metric_not_silently_zero():
    """真树上 kernel-mechanisms 必须非零(#209 审查钉):reply() 改名/拆文件会让
    指标静默显示 0——正是本仓库反复出现的空转失效形态;改名时本钉变红。"""
    assert budget.kernel_mechanisms_if_count(REPO_ROOT) > 0


def test_fixture_pyproject_matches_repo_rules():
    """夹具 pyproject 必须与仓库真实 ruff 配置一致,防止夹具漂移造成假绿。"""
    repo = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    fixture = tomllib.loads(VALID_PYPROJECT)
    repo_lint = repo["tool"]["ruff"]["lint"]
    fixture_lint = fixture["tool"]["ruff"]["lint"]
    assert set(repo_lint["select"]) == set(fixture_lint["select"])
    assert repo_lint.get("pylint") == fixture_lint.get("pylint")
    assert repo_lint.get("mccabe") == fixture_lint.get("mccabe")
