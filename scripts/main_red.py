#!/usr/bin/env python3
"""main 推送报警(issue #11/#35,04 §3.2/§4):main 上的 CI 失败自动开 issue。

两种挂法,报警逻辑只此一份:
- ci.yml checks job 内的失败步骤(GITHUB_JOB 自动指向 checks,只看该 job);
- main.yml alarm job(--all-jobs,#35):needs checks+benchmark 任一失败触发,
  收集本 run 全部 job 的失败步骤,步骤名带 job 前缀。

用 GITHUB_TOKEN 开带 main-red 标签的 issue:标题含 commit sha 与失败步骤;
同 commit(标题含短 sha)已有未关闭的同标签单则跳过,不同 commit 各开各单(#189)。
--dry-run 用模拟输入打印将开的内容、不访问网络。只依赖标准库。
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

try:
    from scripts import github_api
except ImportError:  # 以脚本直接执行时(scripts/ 在 sys.path[0])
    import github_api

MAIN_RED_LABEL = "main-red"
LABEL_COLOR = "d73a4a"
LABEL_DESCRIPTION = "main CI 红:30 分钟内 fix 或 revert(04 §3.2)"


@dataclass(frozen=True)
class AlertStyle:
    """报警 issue 的呈现口径(标签/标题前缀/正文首行)。默认 main CI;nightly 传自定义。"""

    label: str = MAIN_RED_LABEL
    title_prefix: str = "main 红"
    note: str = ""  # 空 = 默认 main CI 失败口径


MAIN_RED_STYLE = AlertStyle()


# ---------- 纯逻辑(供 tests/rules 单测) ----------


def failed_step_names(steps: list[dict]) -> list[str]:
    """steps 里 conclusion 为 failure 的步骤名(Actions runs/{id}/jobs 接口)。"""
    return [step["name"] for step in steps if step.get("conclusion") == "failure"]


def issue_title(sha: str, step_names: list[str], prefix: str = "main 红") -> str:
    return f"{prefix}:{sha[:12]} 失败步骤:{', '.join(step_names)}"


def issue_body(sha: str, step_names: list[str], run_url: str, note: str = "") -> str:
    scope = note or "main 上的 CI 失败(04 §3.2 第三道关卡,无分支保护的兜底报警)。"
    return (
        f"{scope}\n\n"
        f"- commit: {sha}\n"
        f"- 失败步骤: {', '.join(step_names)}\n"
        f"- 运行: {run_url}\n\n"
        "纪律:只允许 fix 或 revert PR,30 分钟内处理否则 revert(04 §3.2)。修复后关闭本 issue。"
    )


def alert(api, sha: str, run_id: str, job_name: str | None, run_url: str,
          style: AlertStyle = MAIN_RED_STYLE) -> None:
    """失败 → 开报警 issue;同 commit(标题含短 sha)已有未关闭的同标签单则跳过,
    不同 commit 各开各单(#189:按标签查重会把不同的红静默吞掉)。

    job_name 指定时只看该 job 的失败步骤(ci.yml 挂在 checks job 内的用法);
    None = 报警 job 模式(main.yml --all-jobs,#35):收集全部 job 的失败步骤,
    步骤名带 job 前缀(checks/ruff、benchmark/效率基准…)。
    style 供非 main 场景复用(nightly 流水线传 label=nightly-red)。
    """
    label = style.label
    jobs = (api.get(f"actions/runs/{run_id}/jobs?per_page=100") or {}).get("jobs", [])
    if job_name is None:
        names = [
            f"{job.get('name', '?')}/{name}"
            for job in jobs
            for name in failed_step_names(job.get("steps") or [])
        ]
    else:
        steps = next((job["steps"] for job in jobs if job.get("name") == job_name), [])
        names = failed_step_names(steps)
    if not names:
        print(f"{label}: 没有失败步骤(运行被取消或读不到),不开 issue")
        return
    existing = api.get(f"issues?state=open&labels={label}&per_page=100")
    if isinstance(existing, list) and any(
            sha[:12] in str(issue.get("title") or "") for issue in existing):
        # 标题存的是短形式(issue_title 的 sha[:12]),匹配必须同口径;拿全 sha 匹配会永远失配
        print(f"{label}: 同一 commit 的报警 issue 已存在,不重复开")
        return
    api.create_label(label, LABEL_COLOR, LABEL_DESCRIPTION)
    title = issue_title(sha, names, style.title_prefix)
    issue = api.create_issue(title, issue_body(sha, names, run_url, style.note), [label]) or {}
    print(f"{label}: 已开 issue #{issue.get('number', '?')}: {title}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="打印将开的 issue,不访问网络")
    parser.add_argument("--sha", default="", help="dry-run:模拟的 commit sha")
    parser.add_argument("--steps", default="", help="dry-run:逗号分隔的失败步骤名")
    parser.add_argument(
        "--all-jobs",
        action="store_true",
        help="报警 job 模式(main.yml alarm,#35):收集本 run 全部 job 的失败步骤",
    )
    parser.add_argument("--label", default=MAIN_RED_LABEL,
                        help="报警 issue 标签(默认 main-red;nightly 流水线传 nightly-red)")
    parser.add_argument("--title-prefix", default="main 红",
                        help="issue 标题前缀(默认 main 红)")
    parser.add_argument("--note", default="",
                        help="正文首行说明(默认 main CI 失败口径;nightly 传测量链路说明)")
    args = parser.parse_args()
    if args.dry_run:
        names = [name for name in args.steps.split(",") if name]
        sha = args.sha or "0" * 40
        print(f"DRY-RUN title: {issue_title(sha, names, args.title_prefix)}")
        print(issue_body(sha, names, "https://github.com/example/actions/runs/0", args.note))
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
        None if args.all_jobs else os.environ.get("GITHUB_JOB", "checks"),
        run_url,
        style=AlertStyle(label=args.label, title_prefix=args.title_prefix, note=args.note),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
