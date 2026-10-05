"""M7-1 B 件钉:result 行 git_sha 来源指纹(#545)。

git_sha_or_none=git_head_sha 的跑批容错面:git 可用→与 HEAD 全等;不可用→None
不伪造(不建第二 truth)。
"""

from __future__ import annotations

from pathlib import Path

from edu_agent.evals import git_head_sha, git_sha_or_none

REPO = Path(__file__).resolve().parents[2]


def test_git_sha_or_none_matches_head_when_git_available():
    assert git_sha_or_none(REPO) == git_head_sha(REPO)


def test_git_sha_or_none_records_none_without_fabrication(tmp_path, monkeypatch):
    # git 不可用(非仓库目录)→ None,不伪造
    assert git_sha_or_none(tmp_path) is None
