#!/usr/bin/env python3
"""main 推送报警(issue #11,04 §3.2/§4):push 到 main 的 CI 失败自动开 issue。

GitHub Free 私有仓库无分支保护,main 红了只有邮件通知;本脚本挂在 ci.yml checks
job 的失败步骤上(push 事件才触发),用 GITHUB_TOKEN 开带 main-red 标签的 issue:
标题含 commit sha 与失败步骤,已有未关闭的 main-red issue 不重复开(按标签查重)。
--dry-run 用模拟输入打印将开的内容、不访问网络,是开 issue 逻辑的本地验证方式。
只依赖标准库。
"""

from __future__ import annotations

import argparse
import os
import sys

try:
    from scripts import github_api
except ImportError:  # 以脚本直接执行时(scripts/ 在 sys.path[0])
    import github_api

MAIN_RED_LABEL = "main-red"
LABEL_COLOR = "d73a4a"
LABEL_DESCRIPTION = "main CI 红:30 分钟内 fix 或 revert(04 §3.2)"


# ---------- 纯逻辑(供 tests/rules 单测) ----------


def failed_step_names(steps: list[dict]) -> list[str]:
    """steps 里 conclusion 为 failure 的步骤名(Actions runs/{id}/jobs 接口)。"""
    return [step["name"] for step in steps if step.get("conclusion") == "failure"]


def issue_title(sha: str, step_names: list[str]) -> str:
    return f"main 红:{sha[:12]} 失败步骤:{', '.join(step_names)}"


def issue_body(sha: str, step_names: list[str], run_url: str) -> str:
    return (
        "main 上的 CI 失败(04 §3.2 第三道关卡,无分支保护的兜底报警)。\n\n"
        f"- commit: {sha}\n"
        f"- 失败步骤: {', '.join(step_names)}\n"
        f"- 运行: {run_url}\n\n"
        "纪律:只允许 fix 或 revert PR,30 分钟内处理否则 revert(04 §3.2)。修复后关闭本 issue。"
    )


def alert(api, sha: str, run_id: str, job_name: str, run_url: str) -> None:
    """checks 失败 → 开 main-red issue;已有未关闭的同标签 issue 则跳过。"""
    data = api.get(f"actions/runs/{run_id}/jobs?per_page=100")
    steps = next(
        (job["steps"] for job in (data or {}).get("jobs", []) if job.get("name") == job_name),
        [],
    )
    names = failed_step_names(steps)
    if not names:
        print("main-red: 没有失败步骤(运行被取消或读不到),不开 issue")
        return
    existing = api.get(f"issues?state=open&labels={MAIN_RED_LABEL}&per_page=100")
    if isinstance(existing, list) and existing:
        print(f"main-red: 已有未关闭的报警 issue #{existing[0]['number']},不重复开")
        return
    api.create_label(MAIN_RED_LABEL, LABEL_COLOR, LABEL_DESCRIPTION)
    title = issue_title(sha, names)
    issue = api.create_issue(title, issue_body(sha, names, run_url), [MAIN_RED_LABEL]) or {}
    print(f"main-red: 已开 issue #{issue.get('number', '?')}: {title}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="打印将开的 issue,不访问网络")
    parser.add_argument("--sha", default="", help="dry-run:模拟的 commit sha")
    parser.add_argument("--steps", default="", help="dry-run:逗号分隔的失败步骤名")
    args = parser.parse_args()
    if args.dry_run:
        names = [name for name in args.steps.split(",") if name]
        sha = args.sha or "0" * 40
        print(f"DRY-RUN title: {issue_title(sha, names)}")
        print(issue_body(sha, names, "https://github.com/example/actions/runs/0"))
        return 0
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not (token and repo and run_id.isdigit()):
        print("main-red: 缺 GITHUB_TOKEN/GITHUB_REPOSITORY/GITHUB_RUN_ID,跳过")
        return 0
    run_url = (
        f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}"
        f"/{repo}/actions/runs/{run_id}"
    )
    api = github_api.GithubApi(token, repo)
    alert(
        api,
        os.environ.get("GITHUB_SHA", ""),
        run_id,
        os.environ.get("GITHUB_JOB", "checks"),
        run_url,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
