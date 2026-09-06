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
