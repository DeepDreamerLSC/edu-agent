"""M7-1 Identity Spine v0(#545)合同钉:三类 additive 身份字段的确定性、join 机械性、防篡改与兼容。

A 件:guard 事件被检对象身份(role/phase/subject_id/output_id/effect);
B 件:facts 行 join 脊柱(edu.turn;同 turn 多调用靠 edu.call_id + phase 区分,
不依赖 event_count == call_count);
C 件:run_case result 行 git_sha。
合同正本 = edu_agent/agents/small_lecturer/trace_spine.py
(Trace owns ordering and lineage, not the meaning or authority of facts)。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fake_openai import completion

from edu_agent.agents.small_lecturer import (
    FIRST_QUESTION_COLLECT,
    SAFE_FALLBACK_TEXT,
    LearnerSession,
    finish,
    reply,
    start,
)

from gwkit import facts_rows
from teachkit import FakeGateway, kernel_env, open_json, tutor_json

# choice_letter 声明面(完成门出证用;test_kernel_transition_gate 同款形态)
CHOICE_Q = {"text": "下面哪个数是质数? A.9 B.11 C.15 D.21", "answer": "B",
            "answer_spec": {"answer_type": "choice_letter",
                            "letter_choices": ["A", "B", "C", "D"]},
            "analysis": "", "knowledge_points": []}
EQUATION_Q = {"text": "解方程 2x+5=17。", "answer": "x=6",
              "analysis": "", "knowledge_points": []}
REPEAT_Q = {"text": "鸡和兔一共8只,26只脚,各多少?", "answer": "鸡3只兔5只",
            "analysis": "", "knowledge_points": []}


def _spine(event: dict) -> dict:
    """事件的脊柱投影(剔轮号/时间性键,确定性比对用)。"""
    return {k: v for k, v in event.items() if k != "turn"}


def _text_id(text: str) -> str:
    """合同口径独立重推导(不 import 生产实现):sha256(UTF-8 原字节)。"""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _const_id(name: str) -> str:
    return f"const:{name}"


# ---------- A 件:被检对象身份 ----------

def test_first_check_subject_pinned_to_exact_reply_bytes(tmp_path):
    """影子事件 subject_id = sha256(模型 reply 原字节):钉死 hash 口径(零归一化),
    篡改一字节即不匹配(防篡改负向 ②)。"""
    model_reply = "你打算从题目条件入手,一步步来。"
    with kernel_env(tmp_path, [completion(open_json("我们先看看这道题。")),
                               completion(tutor_json(model_reply))]) as (_fake, gateway):
        first = start(dict(EQUATION_Q), {"grade": "五年级", "answer_status": "incorrect"},
                      gateway=gateway)
        turn = reply(first.session, "我试试。", gateway=gateway)
    shadow = next(e for e in turn.session.guard_events if e.get("branch") == "model")
    assert shadow["phase"] == "model_reply_first_check"
    assert shadow["role"] == "tutor"
    assert shadow["subject_id"] == _text_id(model_reply)              # 精确字节
    assert shadow["subject_id"] != _text_id(model_reply + "。")       # 篡改 → 失配
    assert shadow["subject_id"] != _text_id(" " + model_reply)        # 无归一化空间


def test_safe_fallback_recheck_mechanically_distinct(tmp_path):
    """M7-0 M3 缺口(#545):safe_fallback 轮的常量复检影子事件与真实调用事件同形
    ——补 subject_id/phase 后,零代码知识即可判别它不对应任何模型调用;处置事件
    output_id=const:SAFE_FALLBACK_TEXT 且等于该轮学生可见文本。"""
    leak = tutor_json("答案是 x=06。")  # 前导零:检得出掩不掉 → 问句兜底(test_kernel_r6 同款)
    with kernel_env(tmp_path, [completion(open_json("我们来看看这道题。")),
                               completion(leak),
                               completion(tutor_json("你自己把做法讲清楚了。", ready=True)),
                               completion(tutor_json("好,我们收尾。"))]) as (_fake, gateway):
        first = start(dict(EQUATION_Q), {"grade": "五年级", "answer_status": "incorrect"},
                      gateway=gateway)
        turn = reply(first.session, "我算出来了。", gateway=gateway)
    events = [e for e in turn.session.guard_events if e.get("turn") == 1]
    shadows = [e for e in events if e.get("branch") == "model"]
    firsts = [e for e in shadows if e["phase"] == "model_reply_first_check"]
    rechecks = [e for e in shadows if e["phase"] == "fallback_constant_recheck"]
    dispositions = [e for e in events if e.get("guard") == "answer_leak"]
    assert len(firsts) == len(rechecks) == len(dispositions) == 1
    assert dispositions[0]["mode"] == "safe_fallback"
    assert firsts[0]["subject_id"].startswith("sha256:")            # 真实调用产物
    assert rechecks[0]["subject_id"] == _const_id("SAFE_FALLBACK_TEXT")  # 常量复检,零调用
    assert dispositions[0]["effect"] == "REPLACE"
    assert dispositions[0]["output_id"] == _const_id("SAFE_FALLBACK_TEXT")
    assert dispositions[0]["subject_id"] == firsts[0]["subject_id"]  # 被检对象=模型原文
    assert turn.text == SAFE_FALLBACK_TEXT                           # stage 输出=可见文本


# ---------- B 件:facts join 脊柱 ----------

def test_facts_rows_carry_turn_spine_through_finish(tmp_path):
    """edu.turn 全程在场:首问 0、reply 1、finish 总结 = 末轮+1(合同口径);
    同 session 各行 call_id 互异(调用唯一性不靠 turn)。"""
    with kernel_env(tmp_path, [
        completion(open_json("我们来看看这道题。")),
        completion(tutor_json("你把选择和理由都讲清楚了。", ready=True)),
        completion(json_summary()),
    ]) as (_fake, gateway):
        first = start(dict(CHOICE_Q), {"grade": "五年级", "answer_status": "incorrect"},
                      gateway=gateway)
        turn = reply(first.session, "答案是B。", gateway=gateway)
        summary = finish(first.session, gateway=gateway)
    rows = facts_rows(tmp_path)
    assert summary.status == "completed"
    assert [row["edu.turn"] for row in rows] == [0, 1, 2]      # join 脊柱(0 起)
    assert rows[0]["edu.session_id"] == rows[1]["edu.session_id"] == first.session.session_id
    assert len({row["edu.call_id"] for row in rows}) == 3
    shadow = next(e for e in turn.session.guard_events if e.get("branch") == "model")
    assert shadow["turn"] == 1 == rows[1]["edu.turn"]          # 事件↔调用同键 join
    assert "turn" not in _fake.requests[0]                     # E4:turn 不进 HTTP 体


def json_summary() -> str:
    import json
    return json.dumps({"summary": "你自己讲清了做法,完成。"}, ensure_ascii=False)


def test_same_turn_two_calls_join_by_phase_not_count(tmp_path):
    """同 turn 两次调用(复读重生成):非双射不靠计数猜——两行 facts 同 turn 不同
    call_id;事件面 first_check/repair_recheck 各自钉住被检文本。"""
    regen = "你想先从哪个条件入手,算出什么?"
    with kernel_env(tmp_path, [
        completion(open_json("我们来看看这道题。")),
        completion(tutor_json(FIRST_QUESTION_COLLECT)),   # 复读首问模板 → 重生成
        completion(tutor_json(regen)),
    ]) as (_fake, gateway):
        first = start(dict(REPEAT_Q), {"grade": "六年级", "answer_status": "incorrect"},
                      gateway=gateway)
        turn = reply(first.session, "嗯,我看看。", gateway=gateway)
    rows = [r for r in facts_rows(tmp_path) if r["edu.turn"] == 1]
    assert len(rows) == 2                                     # 主调用 + repair 调用
    assert len({r["edu.call_id"] for r in rows}) == 2         # 调用对象不碰撞
    events = [e for e in turn.session.guard_events if e.get("turn") == 1]
    shadows = [e for e in events if e.get("branch") == "model"]
    firsts = [e for e in shadows if e["phase"] == "model_reply_first_check"]
    repairs = [e for e in shadows if e["phase"] == "repair_recheck"]
    assert any(e.get("branch") == "repeat_regen" for e in events)    # 复读处置在案
    assert len(firsts) == len(repairs) == 1
    assert firsts[0]["subject_id"] == _text_id(FIRST_QUESTION_COLLECT)
    assert repairs[0]["subject_id"] == _text_id(regen)         # repair 调用的被检对象
    assert turn.text == regen                                 # 可见输出=repair 产物


def test_direct_gateway_call_keeps_null_turn(tmp_path):
    """非 Kernel 直调(gwkit 面):edu.turn=None(additive 缺省,旧行为)。"""
    from teachkit import tutor_env

    with tutor_env(tmp_path, [completion("好的。")]) as (_fake, gateway):
        from edu_agent.gateway import ModelRequest

        gateway.invoke(ModelRequest(role="tutor", messages=[{"role": "user", "content": "hi"}]))
    row = facts_rows(tmp_path)[0]
    assert row["edu.turn"] is None


# ---------- 确定性 ----------

def test_spine_deterministic_across_identical_runs(tmp_path):
    """同剧本两次运行:全部脊柱字段逐字段一致(session_id/call_id/ts 除外)。"""
    def run(root: Path) -> dict:
        with kernel_env(root, [completion(open_json("我们来看看这道题。")),
                               completion(tutor_json("答案是 x=06。")),
                               completion(tutor_json("好。"))]) as (_fake, gateway):
            first = start(dict(EQUATION_Q), {"grade": "五年级", "answer_status": "incorrect"},
                          gateway=gateway)
            reply(first.session, "我算出来了。", gateway=gateway)
            return {"events": [_spine(e) for e in first.session.guard_events]}

    assert run(tmp_path / "a") == run(tmp_path / "b")


# ---------- E5:旧形态事件兼容 ----------

def test_legacy_events_without_spine_still_flow(tmp_path):
    """无脊柱键的既有事件(旧工件/旧持久化)与新事件同流:_stamp_turn 只补轮号,
    不要求旧事件带新键;判定与可见输出不受影响。"""
    legacy = [{"branch": "model", "cited": [], "extracted": [6.0],
               "violation_sources": [], "gate": "observed"},
              {"guard": "answer_leak", "rule_ids": ["grounded_answer_disclosure"],
               "original": "答案是 x=6。", "regenerated": False, "mode": "blocked"}]
    gateway = FakeGateway([{"reply": "那下一步怎么算?", "ready_to_confirm": False,
                            "cited_numbers": [], "acceptable": True, "steps": []}])
    session = LearnerSession(question=dict(EQUATION_Q),
                             learner={"grade": "五年级", "answer_status": "incorrect"})
    session.guard_events = [dict(e) for e in legacy]
    session.first_question = FIRST_QUESTION_COLLECT
    turn = reply(session, "我试试移项。", gateway=gateway)
    for old, merged in zip(legacy, turn.session.guard_events[:2], strict=True):
        assert merged == {**old, "turn": 1}                     # 旧事件仅补 turn
    assert turn.text == "那下一步怎么算?"
