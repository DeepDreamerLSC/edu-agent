#!/usr/bin/env python3
"""PR 元数据门(04 §3.1):分支年龄、PR 触碰顶层包数、large-pr 软标签、structural 主门。

只在有 PR 上下文(GITHUB_TOKEN/GH_TOKEN + PR 号 + GITHUB_REPOSITORY)时执行,本地跳过。
分支年龄检查对"引入本检查的 PR"自豁免(04 §3.1:M0 第一个 PR 豁免;判断方式为
base 分支上不存在 scripts/pr_gates.py)。structural 主门(02 §7,issue #4):触碰
四类结构路径或新增六包名单外的顶层包 → 打 structural 标签,描述缺
`structural-approval:` 一行即 pr-gates 失败。只依赖标准库,经 GitHub REST API 读写。
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from scripts import github_api
except ImportError:  # 以脚本直接执行时(scripts/ 在 sys.path[0])
    import github_api

MAX_BRANCH_AGE_DAYS = 2
MAX_PACKAGES_PER_PR = 2
LARGE_PR_LINES = 800
STALE_LABEL = "stale-branch"
LARGE_LABEL = "large-pr"
STRUCTURAL_LABEL = "structural"
APPROVAL_PREFIX = "structural-approval:"
LABEL_COLORS = {STALE_LABEL: "b60205", LARGE_LABEL: "fbca04", STRUCTURAL_LABEL: "5319e7"}

# 四类结构路径(issue #22 方案 A 通配制):目录以前缀匹配,文件在仓库根精确匹配;
# scripts/ 下全部 *.py 通配(执行机制整体,点名制会漏新脚本——#14 的 github_api.py
# 即缝隙先例)。新增顶层包无法用路径表达,按 02 §2 六包名单判定。
# AGENTS.md 与 docs/roles/ 是规则文件(#23 未经审查即合的教训,从严纳入)。
STRUCTURAL_PATHS = (
    "pyproject.toml",
    "uv.lock",
    "configs/",
    ".github/",
    ".importlinter",
    "docs/plan/",
    "docs/roles/",
    "Makefile",
    "AGENTS.md",
)
PLANNED_TOP_LEVEL_PACKAGES = frozenset(
    {"gateway", "evals", "agents", "contracts", "api", "store"}  # 02 §2
)


# ---------- 纯逻辑(供 tests/rules 单测) ----------


def is_stale(first_commit: datetime, now: datetime) -> bool:
    """分支首个提交距 now 超过 MAX_BRANCH_AGE_DAYS 天即为超龄。"""
    return now - first_commit > timedelta(days=MAX_BRANCH_AGE_DAYS)


def touched_packages(files: list[dict]) -> set[str]:
    """PR 触碰的 edu_agent 顶层包集合。

    触碰 = edu_agent/<包>/ 下有增删行的文件;空 __init__.py 骨架(0 增 0 删)不算,
    这样"执行机制 PR"建包骨架不会误触本门。范围约束的针对对象是代码改动(04 §3.1)。
    """
    packages = set()
    for entry in files:
        parts = Path(entry["filename"]).parts
        changed = entry["additions"] + entry["deletions"]
        if len(parts) >= 3 and parts[0] == "edu_agent" and changed > 0:
            packages.add(parts[1])
    return packages


def is_large_pr(additions: int) -> bool:
    """PR 行数是软信号:超 800 行打 large-pr 标签,不阻塞(04 §3.1)。"""
    return additions > LARGE_PR_LINES


def path_is_structural(name: str) -> bool:
    """命中结构路径:STRUCTURAL_PATHS 里目录前缀匹配,文件根路径精确匹配;
    scripts/ 下全部 *.py(issue #22 方案 A 通配,非 .py 不算)。"""
    if name.startswith("scripts/") and name.endswith(".py"):
        return True
    for pattern in STRUCTURAL_PATHS:
        if pattern.endswith("/"):
            if name.startswith(pattern):
                return True
        elif name == pattern:
            return True
    return False


def new_top_level_packages(files: list[dict]) -> set[str]:
    """名单外的 edu_agent/<名>/ 下有增删行的包(02 §7 第①类:新增顶层包)。

    六包名单内的包不算;判定与 touched_packages 同款(只看有增删行的文件)。
    """
    packages = set()
    for entry in files:
        parts = Path(entry["filename"]).parts
        changed = entry["additions"] + entry["deletions"]
        if (
            len(parts) >= 3
            and parts[0] == "edu_agent"
            and changed > 0
            and parts[1] not in PLANNED_TOP_LEVEL_PACKAGES
        ):
            packages.add(parts[1])
    return packages


def has_structural_approval(body: str) -> bool:
    """描述里有一行以 structural-approval: 开头(日期 + 一句批准理由,02 §7)。"""
    return any(line.lstrip().startswith(APPROVAL_PREFIX) for line in body.splitlines())


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


# ---------- GitHub API ----------

# REST 封装统一在 scripts/github_api.py(SSRF 边界只实现这一份,别处漂移即错)。


# ---------- 四道门 ----------


def branch_age_gate(api: GithubApi, number: int, commits: list, base_sha: str) -> list[str]:
    first_date = commits[0]["commit"]["committer"]["date"] if commits else None
    if first_date is None:
        return ["branch-age: 读不到 PR 提交,按超龄处理(04 §3.1)"]
    now = datetime.now(timezone.utc)
    age_days = (now - parse_iso(first_date)).total_seconds() / 86400
    if not is_stale(parse_iso(first_date), now):
        api.remove_label(number, STALE_LABEL)
        print(f"PR-GATE-OK branch-age: 分支年龄 {age_days:.1f} 天 ≤ {MAX_BRANCH_AGE_DAYS} 天")
        return []
    introduced_here = api.get(f"contents/scripts/pr_gates.py?ref={base_sha}") is None
    if introduced_here:
        print(
            f"PR-GATE-EXEMPT branch-age: 分支已 {age_days:.1f} 天,但本 PR 引入该检查,自豁免(04 §3.1)"
        )
        return []
    api.add_label(number, STALE_LABEL, LABEL_COLORS[STALE_LABEL])
    detail = f"分支首个提交距今 {age_days:.1f} 天 > {MAX_BRANCH_AGE_DAYS} 天,已打 {STALE_LABEL},需 rebase(04 §3.1)"
    return [f"branch-age: {detail}"]


def packages_gate(api: GithubApi, number: int, files: list) -> list[str]:
    packages = sorted(touched_packages(files))
    detail = f"触碰顶层包 {len(packages)} 个 {packages}(上限 {MAX_PACKAGES_PER_PR})"
    if len(packages) <= MAX_PACKAGES_PER_PR:
        print(f"PR-GATE-OK packages-touched: {detail}")
        return []
    return [f"packages-touched: {detail}(04 §3.1)"]


def large_pr_gate(api: GithubApi, number: int, additions: int) -> None:
    if is_large_pr(additions):
        api.add_label(number, LARGE_LABEL, LABEL_COLORS[LARGE_LABEL])
        print(
            f"PR-GATE-LABEL large-pr: +{additions} 行 > {LARGE_PR_LINES},已打软标签"
            "(不阻塞;描述里需写一句为什么必须一起合,04 §3.1)"
        )
    else:
        api.remove_label(number, LARGE_LABEL)
        print(f"PR-GATE-OK large-pr: +{additions} 行 ≤ {LARGE_PR_LINES}")


def structural_gate(api, number: int, files: list, body: str) -> list[str]:
    """structural 主门(02 §7):命中即打标签;描述缺批准行即失败。

    structural 标签是"强制亮到合并时刻"的标记,批准行存在也保留(不是墙,
    agent 可伪造批准行是已知边界,02 §7 单人模式第 1 条)。
    """
    touched = [entry["filename"] for entry in files if path_is_structural(entry["filename"])]
    new_packages = sorted(new_top_level_packages(files))
    if not touched and not new_packages:
        api.remove_label(number, STRUCTURAL_LABEL)
        print("PR-GATE-OK structural: 未触碰结构路径")
        return []
    api.add_label(number, STRUCTURAL_LABEL, LABEL_COLORS[STRUCTURAL_LABEL])
    reasons = []
    if touched:
        reasons.append(f"触碰结构路径 {touched}")
    if new_packages:
        reasons.append(f"新增顶层包 {new_packages}(不在 02 §2 六包名单)")
    if has_structural_approval(body):
        print(f"PR-GATE-OK structural: {'; '.join(reasons)};描述含 {APPROVAL_PREFIX} 行")
        return []
    detail = "; ".join(reasons)
    return [
        f"structural: {detail},描述缺 {APPROVAL_PREFIX} 行即失败(02 §7 主门,已打标签)"
    ]


def run_pr_gates(api: GithubApi, number: int) -> list[str]:
    pr = api.get(f"pulls/{number}")
    if not isinstance(pr, dict):
        return [f"pr-gates: 无法读取 PR #{number}"]
    base_sha = pr.get("base", {}).get("sha", "")
    commits = api.get_paged(f"pulls/{number}/commits")
    files = api.get_paged(f"pulls/{number}/files")
    failures = branch_age_gate(api, number, commits, base_sha)
    failures += packages_gate(api, number, files)
    failures += structural_gate(api, number, files, pr.get("body") or "")
    large_pr_gate(api, number, pr.get("additions", 0))
    return failures


def detect_pr_number() -> int | None:
    """PR 号:优先 PR_NUMBER 环境变量,否则从 GITHUB_REF_NAME(N/merge)解析。"""
    direct = os.environ.get("PR_NUMBER")
    if direct and direct.isdigit():
        return int(direct)
    head, _, tail = os.environ.get("GITHUB_REF_NAME", "").partition("/")
    if head.isdigit() and tail:
        return int(head)
    return None


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    number = detect_pr_number()
    if not (token and repo and number):
        print("pr-gates: 无 PR 上下文(缺 GITHUB_TOKEN/GITHUB_REPOSITORY/PR 号),跳过")
        return 0
    failures = run_pr_gates(github_api.GithubApi(token, repo), number)
    for failure in failures:
        print(f"PR-GATE-FAIL {failure}")
    if failures:
        return 1
    print("pr-gates: 全部通过(04 §3.1)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
