"""04 §3.1 PR 元数据门纯逻辑测试:分支年龄、触碰顶层包、large-pr 阈值。"""

from datetime import datetime, timedelta, timezone

import scripts.pr_gates as pr_gates

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


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
