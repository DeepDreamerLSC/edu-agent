"""issue #11 main 推送报警纯逻辑测试:失败步骤提取、标题、开 issue 与按标签查重。"""

import scripts.main_red as main_red

SHA = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
RUN_ARGS = (SHA, "100", "checks", "https://example.com/runs/100")


class StubApi:
    """模拟 GithubApi:记录调用,返回预置的 job steps 与未关闭 issue 列表。"""

    def __init__(self, jobs: list, open_issues: list) -> None:
        self._jobs = jobs
        self._open_issues = open_issues
        self.created: list[tuple[str, str]] = []
        self.labels_created: list[tuple[str, str, str]] = []

    def get(self, path: str):
        if path.startswith("actions/runs/"):
            return {"total_count": len(self._jobs), "jobs": self._jobs}
        if path.startswith("issues?"):
            return self._open_issues
        return None

    def create_label(self, name: str, color: str, description: str | None = None) -> None:
        self.labels_created.append((name, color, description or ""))

    def create_issue(self, title: str, body: str, labels: list):
        assert labels == ["main-red"]
        self.created.append((title, body))
        return {"number": 7}


def checks_job(steps: list) -> dict:
    return {"name": "checks", "steps": steps}


def test_failed_step_names_filters_by_conclusion():
    steps = [
        {"name": "ruff", "conclusion": "failure"},
        {"name": "pytest", "conclusion": "success"},
        {"name": "main-red", "conclusion": "in_progress"},  # 报警步骤自身,未结束
    ]
    assert main_red.failed_step_names(steps) == ["ruff"]


def test_title_contains_sha_and_failed_steps():
    title = main_red.issue_title(SHA, ["ruff", "pytest"])
    assert SHA[:12] in title
    assert "ruff" in title and "pytest" in title


def test_body_carries_discipline_line():
    body = main_red.issue_body(SHA, ["budget"], "https://example.com/runs/100")
    assert "30 分钟" in body and "revert" in body and "budget" in body


def test_alert_opens_labelled_issue_on_failure():
    api = StubApi(
        jobs=[checks_job([{"name": "ruff", "conclusion": "failure"}])],
        open_issues=[],
    )
    main_red.alert(api, *RUN_ARGS)
    assert len(api.created) == 1
    title, body = api.created[0]
    assert SHA[:12] in title and "ruff" in title
    assert "ruff" in body and "30 分钟" in body
    assert api.labels_created and api.labels_created[0][0] == "main-red"


def test_alert_skips_when_open_main_red_issue_exists():
    api = StubApi(
        jobs=[checks_job([{"name": "ruff", "conclusion": "failure"}])],
        open_issues=[{"number": 3}],
    )
    main_red.alert(api, *RUN_ARGS)
    assert api.created == []


def test_alert_skips_when_no_failed_step():
    api = StubApi(
        jobs=[checks_job([{"name": "ruff", "conclusion": "success"}])],
        open_issues=[],
    )
    main_red.alert(api, *RUN_ARGS)
    assert api.created == []


def test_alert_ignores_other_jobs_steps():
    api = StubApi(
        jobs=[{"name": "pr-gates", "steps": [{"name": "ruff", "conclusion": "failure"}]}],
        open_issues=[],
    )
    main_red.alert(api, *RUN_ARGS)
    assert api.created == []


# ---------- 报警 job 模式(main.yml alarm,issue #35) ----------


def test_alert_all_jobs_mode_collects_every_job_failure():
    """--all-jobs:checks 与 benchmark 的失败步骤都进标题,带 job 前缀;alarm 自身不计。"""
    api = StubApi(
        jobs=[
            {"name": "checks", "steps": [
                {"name": "安装依赖", "conclusion": "failure"},
                {"name": "pytest", "conclusion": "skipped"},  # 上游红导致的跳过不算失败
            ]},
            {"name": "benchmark", "steps": [{"name": "效率基准", "conclusion": "failure"}]},
            {"name": "alarm", "steps": [{"name": "main 推送报警", "conclusion": None}]},
        ],
        open_issues=[],
    )
    main_red.alert(api, SHA, "100", None, "https://example.com/runs/100")
    assert len(api.created) == 1
    title, body = api.created[0]
    assert "checks/安装依赖" in title and "benchmark/效率基准" in title
    assert "main 推送报警" not in title  # alarm 自身步骤(alarm job 运行中,非失败)
    assert "checks/安装依赖" in body


def test_alert_all_jobs_mode_no_failure_opens_nothing():
    api = StubApi(
        jobs=[{"name": "checks", "steps": [{"name": "pytest", "conclusion": "success"}]}],
        open_issues=[],
    )
    main_red.alert(api, SHA, "100", None, "https://example.com/runs/100")
    assert api.created == []


# ---------- main.yml 接线守卫(issue #35:删掉任一项接线,本组测试变红) ----------


def _section(workflow: str, job: str) -> str:
    return workflow.split(f"  {job}:")[1].split("\n\n  ")[0]


def test_main_yml_alarm_job_wired():
    """alarm job:needs 双 job + failure() 触发 + 调 main_red --all-jobs(不复制报警逻辑)。"""
    workflow = (_repo_root() / ".github" / "workflows" / "main.yml").read_text(encoding="utf-8")
    alarm = _section(workflow, "alarm")
    assert "needs: [checks, benchmark]" in alarm
    assert "if: failure()" in alarm
    assert "scripts/main_red.py --all-jobs" in alarm
    assert "issues: write" in workflow  # 开 issue 的权限(#35)


def test_main_yml_jobs_have_timeouts():
    """两级超时(#35 PM 补充项):挂死在 N 分钟后变红,接上 alarm 才闭环。"""
    workflow = (_repo_root() / ".github" / "workflows" / "main.yml").read_text(encoding="utf-8")
    assert "timeout-minutes: 10" in _section(workflow, "checks")
    assert "timeout-minutes: 30" in _section(workflow, "benchmark")


def _repo_root():
    from pathlib import Path

    return Path(__file__).resolve().parents[2]
