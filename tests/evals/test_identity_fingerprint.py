"""#490 M0 审计表第③项合同:identity 指纹构造公共 helper + 消费者不复活卫队。

helper 合同全部经公开入口 edu_agent.evals 导入;消费者脚本经 tests/evals/
conftest.py 挂载 scripts/ 导入(与 test_s2_judge / test_d6d7_matched_surface
同款口径)。不复活卫队沿用 #490 M3 的 _resume_gate 卫队形式:重复机制已删,
局部副本回流即测试红。d6d7 gold 运行器已按 I6-C C2 处置矩阵退役,
卫队面收窄到现存消费者 s2_judge_battery。
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

import s2_judge_battery
from edu_agent.evals import file_sha256, git_head_sha, head_sha256

_REPO = Path(__file__).resolve().parents[2]


def test_file_sha256_is_byte_face_hash(tmp_path):
    target = tmp_path / "asset.yaml"
    target.write_bytes(b"l1\nl2\n")
    assert file_sha256(target) == hashlib.sha256(b"l1\nl2\n").hexdigest()


def test_head_sha256_excludes_freeze_marker_line(tmp_path):
    """head -n -1 口径:末行(冻结标记)改动不算漂移,其余字节改动必变指纹。"""
    target = tmp_path / "frozen.md"
    target.write_text("正文\n更多正文\n- 冻结标记行\n", encoding="utf-8")
    expected = hashlib.sha256("正文\n更多正文\n".encode()).hexdigest()
    assert head_sha256(target) == expected
    target.write_text("正文\n更多正文\n- 冻结标记行(补记)\n", encoding="utf-8")
    assert head_sha256(target) == expected
    target.write_text("正文改\n更多正文\n- 冻结标记行\n", encoding="utf-8")
    assert head_sha256(target) != expected


def test_git_head_sha_matches_rev_parse_in_this_repo():
    expected = subprocess.run(["git", "rev-parse", "HEAD"], cwd=_REPO,
                              capture_output=True, text=True,
                              check=True).stdout.strip()
    assert git_head_sha(_REPO) == expected


def test_git_head_sha_fails_closed_outside_repo(tmp_path):
    """非仓库目录 fail closed(CalledProcessError),不静默降级 None。"""
    with pytest.raises(subprocess.CalledProcessError):
        git_head_sha(tmp_path)


def test_fingerprint_construction_not_duplicated_in_consumers():
    """M0 表第③项收口卫队:现存消费者不再持有 _sha / rubric head sha 局部实现,
    也不再内联 rev-parse 子进程块(构造侧唯一实现在公共层)。d6d7 运行器随
    I6-C C2 退役,卫队面即现存 s2_judge_battery。"""
    for module in (s2_judge_battery,):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "rev-parse" not in source
    assert not hasattr(s2_judge_battery, "_sha")
    assert not hasattr(s2_judge_battery, "_rubric_freeze_sha")
