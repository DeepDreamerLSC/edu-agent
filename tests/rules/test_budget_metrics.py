"""02 §2 预算指标红灯测试:每个指标构造一次违规,budget.py 必须非零退出并点名指标。"""

from pathlib import Path

import scripts.budget as budget

from rulekit import run_py


def write_code_lines(path: Path, count: int) -> None:
    """写一个恰好 count 行非空非注释代码的 .py 文件。"""
    body = "\n".join(f"v{i} = {i}" for i in range(count))
    path.write_text(body + "\n", encoding="utf-8")


def test_baseline_green(base_repo):
    """夹具本身必须全绿,保证后续红灯来自目标违规。"""
    result = run_py("budget.py", "--root", str(base_repo))
    assert result.returncode == 0, result.stdout + result.stderr


def test_app_total_lines_over_limit(base_repo):
    write_code_lines(
        base_repo / "edu_agent" / "big.py", budget.LIMIT_APP_TOTAL_LINES + 1
    )
    result = run_py("budget.py", "--root", str(base_repo))
    assert result.returncode != 0
    assert "BUDGET-FAIL app-total-lines" in result.stdout


def test_single_file_lines_over_limit(base_repo):
    write_code_lines(
        base_repo / "edu_agent" / "large.py", budget.LIMIT_SINGLE_FILE_LINES + 1
    )
    result = run_py("budget.py", "--root", str(base_repo))
    assert result.returncode != 0
    assert "BUDGET-FAIL single-file-lines" in result.stdout


def test_top_level_packages_over_limit(base_repo):
    for name in ("a", "b", "c", "d", "e", "f", "g"):
        package = base_repo / "edu_agent" / name
        package.mkdir()
        (package / "__init__.py").touch()
    result = run_py("budget.py", "--root", str(base_repo))
    assert result.returncode != 0
    assert "BUDGET-FAIL top-level-packages" in result.stdout


def test_runtime_deps_over_limit(base_repo):
    pyproject = base_repo / "pyproject.toml"
    deps = ",\n".join(f'  "dep{i}"' for i in range(budget.LIMIT_RUNTIME_DEPS + 1))
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8").replace(
            "dependencies = []", f"dependencies = [\n{deps},\n]"
        ),
        encoding="utf-8",
    )
    result = run_py("budget.py", "--root", str(base_repo))
    assert result.returncode != 0
    assert "BUDGET-FAIL runtime-deps" in result.stdout


def test_config_files_over_limit(base_repo):
    configs = base_repo / "configs"
    configs.mkdir()
    for index in range(budget.LIMIT_CONFIG_FILES + 1):
        (configs / f"c{index}.yaml").touch()
    result = run_py("budget.py", "--root", str(base_repo))
    assert result.returncode != 0
    assert "BUDGET-FAIL config-files" in result.stdout


def test_deploy_script_lines_over_limit(base_repo):
    lines = "\n".join(f"echo {i}" for i in range(budget.LIMIT_DEPLOY_SCRIPT_LINES + 1))
    (base_repo / "scripts" / "deploy.sh").write_text(lines + "\n", encoding="utf-8")
    result = run_py("budget.py", "--root", str(base_repo))
    assert result.returncode != 0
    assert "BUDGET-FAIL deploy-script-lines" in result.stdout


def test_deploy_metric_passes_without_scripts(base_repo):
    """部署脚本指标先就位:无脚本时必须通过(02 §10)。"""
    result = run_py("budget.py", "--root", str(base_repo))
    assert result.returncode == 0
    assert "BUDGET-OK deploy-script-lines" in result.stdout


def test_suppressions_over_limit(base_repo):
    for index in range(budget.LIMIT_SUPPRESSIONS + 1):
        content = f"x{index} = {index}  # noqa: E501\n"
        (base_repo / "edu_agent" / f"m{index}.py").write_text(content, encoding="utf-8")
    result = run_py("budget.py", "--root", str(base_repo))
    assert result.returncode != 0
    assert "BUDGET-FAIL suppressions" in result.stdout


def test_test_ratio_report_only_in_m0(base_repo):
    """测试比超限在 M0–M1 只报告不阻塞(02 §2、§6)。"""
    write_code_lines(base_repo / "edu_agent" / "app.py", 10)
    (base_repo / "tests").mkdir()
    write_code_lines(base_repo / "tests" / "check_app.py", 30)
    result = run_py("budget.py", "--root", str(base_repo))
    assert result.returncode == 0, result.stdout
    assert "BUDGET-REPORT test-ratio" in result.stdout
    assert "3.00" in result.stdout


def test_test_ratio_blocks_when_strict(base_repo):
    """M2 起测试比阻塞:用环境变量模拟严格模式。"""
    write_code_lines(base_repo / "edu_agent" / "app.py", 10)
    (base_repo / "tests").mkdir()
    write_code_lines(base_repo / "tests" / "check_app.py", 30)
    result = run_py(
        "budget.py",
        "--root",
        str(base_repo),
        env_extra={"BUDGET_STRICT_TEST_RATIO": "1"},
    )
    assert result.returncode != 0
    assert "BUDGET-FAIL test-ratio" in result.stdout
