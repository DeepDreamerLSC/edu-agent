"""04 §3.1 PR 元数据门纯逻辑测试:分支年龄、触碰顶层包、large-pr 阈值、structural 主门。"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import scripts.pr_gates as pr_gates

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
APPROVAL = "structural-approval: 2026-09-06 人批,依据 issue #4 指派"


class StubApi:
    """模拟 GithubApi:只记录标签增删,structural_gate 对 api 的全部用法。"""

    def __init__(self):
        self.added = []
        self.removed = []

    def add_label(self, number, name, color):
        self.added.append(name)

    def remove_label(self, number, name):
        self.removed.append(name)


def test_branch_age_boundary():
    fresh = NOW - timedelta(days=pr_gates.MAX_BRANCH_AGE_DAYS) + timedelta(seconds=1)
    assert pr_gates.is_stale(fresh, NOW) is False
    stale = NOW - timedelta(days=pr_gates.MAX_BRANCH_AGE_DAYS) - timedelta(seconds=1)
    assert pr_gates.is_stale(stale, NOW) is True


def test_empty_skeleton_files_do_not_count_as_touched():
    """空 __init__.py 骨架(0 增 0 删)不算触碰:执行机制 PR 建包骨架不误触本门。"""
    files = [
        {"filename": "edu_agent/gateway/__init__.py", "additions": 0, "deletions": 0},
        {"filename": "edu_agent/agents/__init__.py", "additions": 0, "deletions": 0},
    ]
    assert pr_gates.touched_packages(files) == set()


def test_packages_over_limit_detected():
    files = [
        {"filename": "edu_agent/gateway/client.py", "additions": 10, "deletions": 0},
        {"filename": "edu_agent/agents/kernel.py", "additions": 10, "deletions": 0},
        {"filename": "edu_agent/evals/runner.py", "additions": 10, "deletions": 0},
        {"filename": "scripts/budget.py", "additions": 5, "deletions": 0},
        {"filename": "edu_agent/__init__.py", "additions": 1, "deletions": 0},
    ]
    assert pr_gates.touched_packages(files) == {"gateway", "agents", "evals"}


def test_pure_deletions_count_as_touched():
    files = [{"filename": "edu_agent/store/cache.py", "additions": 0, "deletions": 50}]
    assert pr_gates.touched_packages(files) == {"store"}


def test_large_pr_threshold():
    assert pr_gates.is_large_pr(pr_gates.LARGE_PR_LINES) is False
    assert pr_gates.is_large_pr(pr_gates.LARGE_PR_LINES + 1) is True


# ---------- structural 主门(issue #4,02 §7) ----------


def test_structural_hit_without_approval_fails():
    """触碰结构路径 + 描述缺批准行 → pr-gates 失败并打 structural 标签(红灯)。"""
    api = StubApi()
    files = [{"filename": ".github/workflows/ci.yml", "additions": 5, "deletions": 0}]
    failures = pr_gates.structural_gate(api, 1, files, "普通描述,没有批准行")
    assert failures and "structural-approval" in failures[0]
    assert api.added == ["structural"]


def test_structural_hit_with_approval_passes_but_stays_labelled():
    api = StubApi()
    files = [{"filename": "Makefile", "additions": 1, "deletions": 1}]
    assert pr_gates.structural_gate(api, 1, files, f"说明\n{APPROVAL}\n") == []
    assert api.added == ["structural"]  # 命中即亮标签,批准了也保留(02 §7:亮到合并时刻)


def test_non_structural_pr_passes():
    api = StubApi()
    files = [{"filename": "edu_agent/gateway/client.py", "additions": 10, "deletions": 0}]
    assert pr_gates.structural_gate(api, 1, files, "") == []
    assert api.added == []


def test_every_structural_path_pattern_matches():
    for pattern in pr_gates.STRUCTURAL_PATHS:
        name = (pattern + "x.yml") if pattern.endswith("/") else pattern
        assert pr_gates.path_is_structural(name) is True, pattern
    assert pr_gates.path_is_structural("edu_agent/gateway/x.py") is False
    assert pr_gates.path_is_structural("docs/README.md") is False  # docs/plan/ 之外不算
    assert pr_gates.path_is_structural("sub/Makefile") is False  # 文件只认仓库根


def test_new_top_level_package_outside_plan_hits():
    """六包名单外的 edu_agent/<名>/ 有增删行 = 新增顶层包(02 §7 第①类)。"""
    files = [{"filename": "edu_agent/plugins/core.py", "additions": 3, "deletions": 0}]
    assert pr_gates.new_top_level_packages(files) == {"plugins"}
    api = StubApi()
    assert pr_gates.structural_gate(api, 1, files, APPROVAL) == []
    assert api.added == ["structural"]


def test_planned_package_is_not_new():
    files = [{"filename": "edu_agent/store/cache.py", "additions": 9, "deletions": 1}]
    assert pr_gates.new_top_level_packages(files) == set()
    assert pr_gates.path_is_structural("edu_agent/store/cache.py") is False


def test_approval_must_start_the_line():
    """批准行必须独占一行;行中被提及不算(可伪造是已知边界,但格式不放松)。"""
    api = StubApi()
    files = [{"filename": "configs/models.yaml", "additions": 4, "deletions": 0}]
    body = "评审备注:请补一行 structural-approval: 2026-09-06 理由"
    assert pr_gates.structural_gate(api, 1, files, body) != []
    assert pr_gates.structural_gate(api, 1, files, f"  {APPROVAL}") == []  # 行首空白容忍


# ---------- scripts 通配与规则文件(issue #22 方案 A、#23 教训) ----------


def test_any_scripts_py_is_structural():
    """scripts/ 下全部 *.py 通配:点名制的缝隙先例是 #14 的 github_api.py。"""
    for name in ("scripts/github_api.py", "scripts/budget.py", "scripts/some_future_helper.py"):
        assert pr_gates.path_is_structural(name) is True, name


def test_scripts_non_py_not_structural():
    """非 .py 不算(deploy.sh 由 04 §4 的行数预算管,不进四类)。"""
    assert pr_gates.path_is_structural("scripts/deploy.sh") is False
    assert pr_gates.path_is_structural("scripts/README.md") is False


def test_rule_files_are_structural():
    """AGENTS.md 与 docs/roles/ 是规则文件(#23 未经审即合的教训)。"""
    for name in ("AGENTS.md", "docs/roles/reviewer.md", "docs/roles/new_role.md"):
        assert pr_gates.path_is_structural(name) is True, name
    assert pr_gates.path_is_structural("docs/other/notes.md") is False


def test_gate_runs_main_version_in_ci():
    """issue #24:门必须以 main 版本执行——ci.yml 的 pr-gates job 含替换步骤,
    删掉这个步骤(回到分支自带门、堆叠可绕过)本测试变红。"""
    workflow = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    gate_section = workflow.split("pr-gates:")[1]
    assert "git ls-tree FETCH_HEAD --name-only scripts/pr_gates.py" in gate_section
    assert "git checkout FETCH_HEAD -- scripts/" in gate_section


def test_stacked_branch_cannot_smuggle_structural_change():
    """堆叠场景(issue #24 复现的单元化):门(本仓库版本=main 立场)对
    '分支上同时带旧门与新配置'的 PR 数据,结构触碰必须照样命中。"""
    api = StubApi()
    files = [
        {"filename": "scripts/pr_gates.py", "additions": 2, "deletions": 1},  # 分支上的旧门
        {"filename": "configs/models.yaml", "additions": 4, "deletions": 0},  # 偷渡目标
    ]
    failures = pr_gates.structural_gate(api, 1, files, "无批准行")
    assert failures and "configs/models.yaml" in failures[0]
    assert api.added == ["structural"]
