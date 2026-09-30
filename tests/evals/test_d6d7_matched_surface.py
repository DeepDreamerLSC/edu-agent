"""matched-surface renderer/runner 机械测试:格式行/锚框架/暴露检测/泄漏门/执行附录。

不触网零模型;用合成 mini-pack(一 plain 案 + 一 dict 题面含 answer 案)走
parse → render → build → assert 全链,并锚 P0-1 系统级执行附录的前缀完整性。
"""

from __future__ import annotations

import hashlib
import json
import sys

import pytest

import d6d7_gold_consume as gc  # scripts/(conftest 挂载)
import d6d7_matched_surface as ms
from edu_agent.evals import (
    ResumeMismatch,
    file_sha256,
    git_head_sha,
    head_sha256,
)

MINI_PACK = """# 包头
---
## P1-01
**题面**:47本书每6本装一盒，至少需要多少个盒子？

逐轮原文:
- [轮0·学生] (无学生输入)
- [轮0·Tutor] 你好同学,这道题你的答案是什么呀?
- [轮1·学生] 47除以6等于7余5。
- [轮1·Tutor] ▶ **判定锚** 那剩下的5本书还需要再加一个盒子吗?

**P1-01 标注**:S2a=____ S2b=____
---
## P1-02
**题面**:{'text': '一个圆的直径是 10 厘米,半径是多少?', 'answer': '5厘米'}
**年级**:六年级

逐轮原文:
- [轮0·学生] (无学生输入)
- [轮0·Tutor] 你好同学,这道题你的答案是什么呀?
- [轮1·学生] 半径是 5 厘米。
- [轮1·Tutor] ▶ **判定锚** 说得对。

**P1-02 标注**:S2a=____ S2b=____
"""

GOLD = {"cases": [
    {"blind_id": "P1-01", "s2a": "NO", "s2b": "NO"},
    {"blind_id": "P1-02", "s2a": "NO", "s2b": "YES"},
]}


def test_render_format_and_anchor():
    cases = ms.parse_pack(MINI_PACK)
    prompt = ms.render_user_prompt(cases["P1-01"])
    lines = prompt.splitlines()
    assert lines[0] == "【题面】47本书每6本装一盒，至少需要多少个盒子？"
    assert "【年级】" not in prompt  # 无年级行不渲染
    assert "学生(轮1):47除以6等于7余5。" in lines
    assert "小讲师(轮1):那剩下的5本书还需要再加一个盒子吗?" in lines
    assert any(line.startswith("【判定锚】判定对象 = 小讲师(轮1)") for line in lines)
    assert prompt.count("【判定锚】") == 1
    # 引擎尾部输出要求逐字共享(renderer 模块引用的 _USER_INSTRUCTIONS)
    assert lines[-2:] == ms._USER_INSTRUCTIONS


def test_grade_line_and_exposure():
    cases = ms.parse_pack(MINI_PACK)
    prompt = ms.render_user_prompt(cases["P1-02"])
    assert "【年级】六年级" in prompt.splitlines()
    assert ms.answer_exposed(cases["P1-02"]["question"]) is True
    assert ms.answer_exposed(cases["P1-01"]["question"]) is False


def test_build_rows_and_leak_gate():
    rows = ms.build_rows(ms.parse_pack(MINI_PACK), GOLD)
    assert [row["case_id"] for row in rows] == ["P1-01", "P1-02"]
    assert rows[0]["answer_exposed"] is False
    assert rows[1]["answer_exposed"] is True
    assert rows[1]["gold"] == {"s2a": "NO", "s2b": "YES"}
    ms.assert_surface(rows)  # 泄漏门零命中
    # gold 标签不进 user_prompt(P1-2 防火墙镜像;合成案内容不含 YES 字样)
    assert "YES" not in rows[1]["user_prompt"]


def test_missing_anchor_refused():
    cases = ms.parse_pack(MINI_PACK)
    cases["P1-01"]["turns"] = [t for t in cases["P1-01"]["turns"] if not t[3]]
    try:
        ms.render_user_prompt(cases["P1-01"])
    except AssertionError:
        return
    raise SystemExit("缺锚案应拒绝渲染")


def test_gold_json_shape_matches_builder():
    # gold 真件字段形态(builder 消费面):cases[].blind_id/s2a/s2b
    for case in GOLD["cases"]:
        assert {"blind_id", "s2a", "s2b"} <= set(case)
    json.dumps(GOLD)  # 可序列化


def test_system_addendum_p0_1():
    """P0-1(#485 冻结审+复审):附录只桥接输入形态且只判锚轮,sha 可复算、前缀完整。"""
    assert gc._SYSTEM_ADDENDUM.startswith("【matched-surface 执行附录")
    # 只桥接输入形态,不做任何判据语义改写
    for banned in ("改为", "不适用", "忽略上述", "override", "以本附录为准"):
        assert banned not in gc._SYSTEM_ADDENDUM
    # 复审 5356022635 收紧:锚轮唯一判定对象,前轮仅上下文(聚合后门封死)
    assert "只判锚轮" in gc._SYSTEM_ADDENDUM
    assert "不得把前轮自身 failure 作为本案成立证据" in gc._SYSTEM_ADDENDUM
    assert gc._addendum_sha() == hashlib.sha256(
        gc._SYSTEM_ADDENDUM.encode()).hexdigest()
    # 系统消息 = 冻结件逐字前缀 + 附录(经 runner 自身的公开属性引用,不私有导入)
    content = gc._system_content()
    assert content.startswith(gc.SYSTEM_PROMPT)
    assert content.endswith(gc._SYSTEM_ADDENDUM)


def _make_rows(count: int, exposed: int) -> list[dict]:
    return [{"case_id": f"P1-{i:02d}", "answer_exposed": i < exposed}
            for i in range(count)]


def test_frozen_pinned_and_preflight_p0_2():
    """P0-2(#485 复审):代码钉死冻结 sha;preflight 恰 30/唯一/exposed 恰 5。"""
    assert gc.FROZEN_CASES_SHA256 == (
        "71069ca8dca305ef2ae0cb07153bbc1d478ae09dfa123a852870899cbbbe1437")
    assert gc._preflight(_make_rows(30, 5)) is None
    assert gc._preflight(_make_rows(29, 5)) is not None  # 29 案 ≠ 30
    assert gc._preflight(_make_rows(31, 5)) is not None  # 31 案 ≠ 30
    duplicated = _make_rows(30, 5)
    duplicated[1]["case_id"] = duplicated[0]["case_id"]
    assert gc._preflight(duplicated) is not None  # case_id 重复
    assert gc._preflight(_make_rows(30, 6)) is not None  # exposed 6 ≠ 5
    assert gc._preflight(_make_rows(30, 4)) is not None  # exposed 4 ≠ 5


def _fabricate_results(run_dir, judge_model, status="ok"):
    """伪造 30 案结果文件(judge_model 单值或 i=29 异值)。"""
    for i in range(30):
        model = judge_model if not isinstance(judge_model, tuple) else judge_model[i]
        record = {"case_id": f"P1-{i:02d}", "status": status,
                  "transcript": {"judge_model": model}}
        (run_dir / "results" / f"P1-{i:02d}.json").write_text(
            json.dumps(record), encoding="utf-8")


def test_model_gate_uses_common_comparison(tmp_path):
    """#490 M3:模型身份比较基础部分走公共 compare_models,四类读数同旧谓词;
    VOID 措辞、ok/total/exposed 计数与四条件结束门处置留本脚本。"""
    run_dir = tmp_path / "run"
    (run_dir / "results").mkdir(parents=True)
    rows = _make_rows(30, 5)
    identity = {"judge_primary_model": "primary-name"}
    _fabricate_results(run_dir, "primary-name")
    gate = gc._model_gate(run_dir, rows, identity)
    # 返回形状保持(#490 M3 迁移证明:消费面 ok/total/models/model_gate/
    # answer_exposed_ok 五键不增不减,VOID 措辞留本脚本)
    assert set(gate) == {"ok", "total", "models", "model_gate", "answer_exposed_ok"}
    assert gate["model_gate"] == "ok" and gate["models"] == ["primary-name"]
    assert (gate["ok"], gate["total"], gate["answer_exposed_ok"]) == (30, 30, 5)
    # 异值(29 案 primary + 1 案 fallback)→ 整轮 VOID,fallback 反例镜像
    _fabricate_results(run_dir, tuple(
        "primary-name" if i < 29 else "fallback-name" for i in range(30)))
    mixed = gc._model_gate(run_dir, rows, identity)
    assert mixed["model_gate"] == "VOID"
    assert mixed["models"] == ["fallback-name", "primary-name"]
    # 单值但不等预注册 → VOID
    _fabricate_results(run_dir, "other-name")
    wrong = gc._model_gate(run_dir, rows, identity)
    assert wrong["model_gate"] == "VOID" and wrong["models"] == ["other-name"]
    # 零 ok 案(全环境失败)→ 无观察 → VOID
    _fabricate_results(run_dir, "primary-name", status="environment")
    empty = gc._model_gate(run_dir, rows, identity)
    assert empty["model_gate"] == "VOID" and empty["models"] == []
    assert empty["ok"] == 0 and empty["answer_exposed_ok"] == 0


def test_resume_refusal_delegates_to_common_strict_gate(tmp_path, monkeypatch):
    """#490 M3:resume 门迁公共层——strict_identity=True 委托 + ResumeMismatch →
    CLI 非零退出;identity 字段全链(cases/addendum 在内)不丢;门语义本体由
    tests/evals/test_runner.py 持有。"""
    assert not hasattr(gc, "_resume_gate")  # 重复机制已删,不复活
    captured = {}

    class SpyRunner:
        def __init__(self, subject, config, runs_root):
            captured["subject"] = subject

        def run(self, dataset_path, cases, run_dir=None, identity=None,
                strict_identity=False):
            captured.update(run_dir=run_dir, identity=identity,
                            strict_identity=strict_identity)
            raise ResumeMismatch("spy:identity 不一致(字段 cases_sha 值变)")

    class DummyGateway:
        def __init__(self, *args, **kwargs):
            pass

        def close(self):
            pass

    cases = tmp_path / "cases.jsonl"
    cases.write_text("\n".join(json.dumps(row) for row in _make_rows(30, 5)) + "\n",
                     encoding="utf-8")
    # 冻结门钉死真件 sha(上方常量测试持有);wiring 测试对合成件放行同款比对
    monkeypatch.setattr(gc, "FROZEN_CASES_SHA256",
                        hashlib.sha256(cases.read_bytes()).hexdigest())
    monkeypatch.setattr(gc, "EvalRunner", SpyRunner)
    monkeypatch.setattr(gc, "Gateway", DummyGateway)
    resume_dir = tmp_path / "prior-run"
    monkeypatch.setattr(sys, "argv", [
        "d6d7-gold-consume", "--cases", str(cases),
        "--artifacts-root", str(tmp_path / "art"), "--run-dir", str(resume_dir)])
    with pytest.raises(SystemExit, match="resume 拒绝"):
        gc.main()
    assert captured["strict_identity"] is True and captured["run_dir"] == resume_dir
    # identity 字段全链不丢(#485:git/rubric/prompt/cases/addendum/models + 双字段)
    assert set(captured["identity"]) == {
        "git_sha", "rubric_freeze_sha", "prompt_asset_sha", "cases_sha",
        "addendum_sha256", "models_yaml_sha", "judge_primary_id",
        "judge_primary_model"}
    # 指纹口径与公共 helper 一致(#490 M0 表第③项:构造侧唯一实现)
    assert captured["identity"]["git_sha"] == git_head_sha(gc._REPO)
    assert captured["identity"]["rubric_freeze_sha"] == head_sha256(
        gc._REPO / "docs/evals/s2-judge-rubric-v0.1.md")
    assert captured["identity"]["cases_sha"] == file_sha256(cases)
