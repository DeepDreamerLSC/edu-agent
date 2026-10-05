"""M7-2 Minimal Decision Events(#545)合同钉:D1 终述路由 + D2 ready 覆盖。

合同正本 = trace_spine.py(构造收口,零业务谓词重算);本文件钉行为:
- D1(T1/T2/T3):route 事件 exactly-1、字段面/turn 口径/subject 哈希、attempted→
  committed 语义、GatewayError 原子回滚后不残留 committed 假事实;
- D2(T4/T5):仅真实 True→False 记事件(三态钉:True→False 记 / False→False
  不记 / 无覆盖不记),from/to 机械可见;
- T6:零 kernel import 的消费面(_route_report/_ready_report,纯事件/facts 读取)
  回答三问:该轮为何无 reply 主调用 / close 是否 deterministic route / ready 是
  模型原值还是 Kernel 覆盖;
- T7:非干扰(调用数/可见文本/终态/rule_ids 逐字面钉);
- T8:旧事件流(无 decision)对消费面 = ABSENT,不反写。
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest
from fake_openai import completion

from edu_agent.agents.small_lecturer import LearnerSession, reply, start
from edu_agent.gateway import FailureType, GatewayError

from gwkit import facts_rows
from teachkit import FakeGateway, kernel_env, open_json, tutor_json

# Gate B 段 eligible 题(test_kernel_restate 同款:answer_spec 声明面在场,
# 终述句「所以答案是0.5m」为声明式 claim,当轮即 evidence)。
GATE_QUESTION = {"text": "一个球从高处落下,每次弹起的高度是下落高度的1/6。"
                         "该球从18m的高度落下,第二次弹起的高度是多少米?",
                 "answer": "0.5m", "answer_spec": {"answer_type": "numeric_with_unit"},
                 "analysis": "", "knowledge_points": []}
GATE_READY_TURN = "18除以6再除以6,我算出来了。"
GATE_FINAL_STATEMENT = "所以答案是0.5m"
CHICKEN_QUESTION = {"text": "鸡和兔一共 8 只,共有 26 只脚。鸡和兔各有多少只?说明思路。",
                    "answer": "鸡3只兔5只", "analysis": "", "knowledge_points": []}

D1_KEYS = {"branch", "role", "turn", "phase", "decision", "effect", "reason",
           "subject_id", "target", "outcome"}          # 闭集:零新增正文面
D2_KEYS = {"branch", "role", "turn", "phase", "decision", "effect", "reason",
           "from", "to"}


def _sha(text: str) -> str:
    """subject_id 口径独立重推导(不 import 生产实现)。"""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _open(reply_text: str) -> dict:
    return {"acceptable": True, "transcription": "", "steps": [], "reply": reply_text}


def _tutor(reply_text: str, ready: bool = False) -> dict:
    return {"reply": reply_text, "ready_to_confirm": ready, "cited_numbers": []}


def _decisions(events: list[dict], phase: str) -> list[dict]:
    return [e for e in events if e.get("branch") == "decision" and e.get("phase") == phase]


def _ready_session(gateway, question: dict, learner_status: str,
                   ready_turn: str = GATE_READY_TURN):
    first = start(dict(question), {"grade": "六年级", "answer_status": learner_status},
                  gateway=gateway)
    confirmed = reply(first.session, ready_turn, gateway=gateway)
    assert confirmed.state == "ready_to_confirm"
    return first.session


# ---------- T6 消费面(零 kernel import:纯事件/facts 读取,三问机械可答)----------

def route_report(events: list[dict], calls: list[dict], turn: int) -> dict:
    """三问①②:该 turn 为何没有/有下一次 tutor model call;close 是否 deterministic。"""
    in_turn = [e for e in events if e.get("turn") == turn]
    d1 = [e for e in in_turn if e.get("phase") == "final_statement_route"]
    calls_t = [c for c in calls if c.get("edu.turn") == turn]
    first_check = any(e.get("phase") == "model_reply_first_check" for e in in_turn)
    if d1:
        return {"route": "deterministic_final_statement_close",
                "reply_stage_model_call": first_check,   # 路由绕过 reply 主检查
                "calls_in_turn": [c.get("edu.call_id") for c in calls_t],
                "outcome": d1[0].get("outcome", "ABSENT")}
    return {"route": "model_path", "reply_stage_model_call": first_check,
            "calls_in_turn": [c.get("edu.call_id") for c in calls_t]}


def ready_report(events: list[dict], turn: int) -> dict:
    """三问③:committed ready 是模型原值还是 Kernel 覆盖。"""
    in_turn = [e for e in events if e.get("turn") == turn]
    d2 = [e for e in in_turn if e.get("phase") == "post_method_ready_override"]
    if d2:
        return {"ready_source": "kernel_override", "model_value": d2[0]["from"],
                "kernel_value": d2[0]["to"], "reason": d2[0]["reason"]}
    return {"ready_source": "model_original" if in_turn else "ABSENT"}


# ---------- D1:终述路由事件 ----------

def test_d1_route_event_once_with_contract_fields():
    """T1 正向:ready ∧ 终述 → decision 事件 exactly-1,字段面逐项=授权文;
    subject_id=独立重算哈希;turn=2(transcript 下标,与 guard/facts 同口径);
    可见输出/终态与既有合同一致(零调用模板收束,completed)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("你现在觉得鸡和兔各有多少只?"),
        _tutor("我们把思路理清楚了。", ready=True),
    ])
    session = _ready_session(gateway, GATE_QUESTION, "correct")
    calls_before = len(gateway.requests)
    turn = reply(session, GATE_FINAL_STATEMENT, gateway=gateway)
    events = _decisions(session.guard_events, "final_statement_route")
    assert len(events) == 1
    event = events[0]
    assert set(event) <= D1_KEYS
    assert event["role"] == "kernel" and event["decision"] == "close_on_final_statement"
    assert event["effect"] == "ROUTE" and event["target"] == "finish"
    assert event["reason"] == "ready_to_confirm_and_final_statement"
    assert event["subject_id"] == _sha(GATE_FINAL_STATEMENT)     # 精确 UTF-8 字节
    assert event["subject_id"] != _sha(GATE_FINAL_STATEMENT + " ")
    assert event["turn"] == 2 and event["outcome"] == "committed"
    # T7 非干扰:零模型调用、完成语义与 Product 合同逐字面一致
    assert len(gateway.requests) == calls_before
    assert turn.state == "completed" and session.finished
    assert "18" in turn.text and "0.5m" in turn.text             # 模板引学生原话


def test_d1_turn_joins_finish_call_and_bypasses_reply_check(tmp_path):
    """T1 join:incorrect 档 close 消费 finish 总结调用——decision turn=2 与该调用
    facts 行同键;该 turn 无 model_reply_first_check 影子(reply 主调用被路由绕过)。"""
    with kernel_env(tmp_path, [completion(open_json("我们先看这道题。")),
                               completion(tutor_json("我们把思路理清楚了。", ready=True)),
                               completion(json.dumps({"summary": "你自己讲清了思路。"},
                                                     ensure_ascii=False))]) as (_fake, gateway):
        first = start(dict(GATE_QUESTION), {"grade": "六年级", "answer_status": "incorrect"},
                      gateway=gateway)
        reply(first.session, GATE_READY_TURN, gateway=gateway)
        turn = reply(first.session, GATE_FINAL_STATEMENT, gateway=gateway)
    rows = facts_rows(tmp_path)
    assert [row["edu.turn"] for row in rows] == [0, 1, 2]        # join 脊柱(0 起)
    events = _decisions(turn.session.guard_events, "final_statement_route")
    assert len(events) == 1 and events[0]["turn"] == 2 == rows[2]["edu.turn"]
    report = route_report(turn.session.guard_events, rows, 2)   # T6 消费面三问①②
    assert report["route"] == "deterministic_final_statement_close"
    assert report["reply_stage_model_call"] is False
    assert report["outcome"] == "committed" and len(report["calls_in_turn"]) == 1


def test_d1_negative_no_event_on_non_ready_or_non_final():
    """T2 负向:ready 但非终述(附和/问句)与终述形但非 ready → 均零 decision
    事件,走模型路径(原执行不变)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("你现在觉得鸡和兔各有多少只?"),
        _tutor("我们把思路理清楚了。", ready=True),
        _tutor("我们再确认一遍。"),
        _tutor("你想再试试吗?"),
        _tutor("我们继续。"),
        _tutor("说说你的第一步。"),
    ])
    session = _ready_session(gateway, GATE_QUESTION, "incorrect")
    ack = reply(session, "是的,我真棒。", gateway=gateway)        # 附和:无焦点数字
    guess = reply(session, "答案是0.5米吗?", gateway=gateway)     # 问句≠终述
    assert ack.state != "completed" and guess.state != "completed"
    early_gateway = FakeGateway(tutor_payloads=[                 # 终述形但非 ready 态
        _open("你先说说你的想法。"), _tutor("我们先看脚数。")])
    fresh = start(dict(CHICKEN_QUESTION),
                  {"grade": "六年级", "answer_status": "incorrect"}, gateway=early_gateway)
    early = reply(fresh.session, "鸡有3只,兔有5只。", gateway=early_gateway)
    assert early.state != "completed"                            # 非 ready:模型路径
    for turn in (ack, guess, early):
        assert _decisions(turn.session.guard_events, "final_statement_route") == []


class _ExplodingGateway(FakeGateway):
    """按调用序号注入 GatewayError(收束轮 finish 的模型总结失败)。"""

    def __init__(self, tutor_payloads, fail_indices: set[int]):
        super().__init__(tutor_payloads)
        self.fail_indices = fail_indices

    def invoke(self, request):
        if len(self.requests) in self.fail_indices:
            self.requests.append({"role": request.role, "messages": request.messages})
            raise GatewayError(FailureType.UPSTREAM_5XX, "服务暂不可用")
        return super().invoke(request)


def _snapshot(session) -> dict:
    return {"history": deepcopy(session.history), "state": session.state,
            "summary": deepcopy(session.summary),
            "session_version": session.session_version,
            "hint_level": session.hint_level}


def test_d1_gateway_error_atomicity_and_attempted_semantics():
    """T3 失败/回滚:GatewayError → session 逐字段回到调用前(原子性合同不退化);
    decision 事件保留且 outcome=attempted(路由已决未成,不冒充 commit truth、
    不冒充 commit truth、不制造 completed 假事实);同句重试成功后第二条 committed,第一条不动。"""
    gateway = _ExplodingGateway(tutor_payloads=[
        _open("你现在觉得鸡和兔各有多少只?"),
        _tutor("我们把思路理清楚了。", ready=True),
        {"summary": "你自己讲清了思路。"},
    ], fail_indices={2})
    session = _ready_session(gateway, GATE_QUESTION, "incorrect")
    before = _snapshot(session)
    with pytest.raises(GatewayError):
        reply(session, GATE_FINAL_STATEMENT, gateway=gateway)
    assert _snapshot(session) == before                          # 原子回滚逐字段
    events = _decisions(session.guard_events, "final_statement_route")
    assert len(events) == 1 and events[0]["outcome"] == "attempted"
    assert not session.finished and session.summary is None      # 零 completed 假事实
    turn = reply(session, GATE_FINAL_STATEMENT, gateway=gateway)  # 同句重试
    events = _decisions(session.guard_events, "final_statement_route")
    assert [e["outcome"] for e in events] == ["attempted", "committed"]
    assert events[0]["turn"] == events[1]["turn"] == 2           # 同轮两次路由尝试
    assert turn.state == "completed" and session.finished
    student = [m["content"] for m in session.history if m["role"] == "user"]
    assert student.count(GATE_FINAL_STATEMENT) == 1              # 终述零重复


# ---------- D2:feeds_method ready 覆盖事件 ----------

def test_d2_override_recorded_only_on_true_to_false():
    """T4 正向:模型 ready=True ∧ 代喂命中 ∧ 学生未陈述终答 → 覆盖事件 exactly-1
    (from=true/to=false 机械可见);既有 feeds_method 处置事件保持;终态/可见
    文本与既有合同一致(dialogue、脱敏文本)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("你先说说题目给了哪些条件?"),
        _tutor("你用的是假设法,对吧?", ready=True),
    ])
    first = start(dict(CHICKEN_QUESTION), {"grade": "六年级"}, gateway=gateway)
    turn = reply(first.session, "我先说说我的想法。", gateway=gateway)
    events = _decisions(turn.session.guard_events, "post_method_ready_override")
    assert len(events) == 1
    event = events[0]
    assert set(event) <= D2_KEYS
    assert event["decision"] == "ready_to_confirm_override"
    assert event["effect"] == "STATE_TRANSITION"
    assert event["reason"] == "student_answer_not_stated"
    assert event["from"] is True and event["to"] is False        # model 原值→kernel 终值
    assert event["turn"] == 1                                    # 与同轮 guard 事件同键
    feeds = [e for e in turn.session.guard_events if e.get("guard") == "feeds_method"]
    assert feeds and feeds[-1]["mode"] == "masked"               # 既有事件保持
    shadow = [e for e in turn.session.guard_events if e.get("branch") == "model"]
    assert shadow and shadow[0]["turn"] == 1                     # 同 turn 主检查
    assert turn.text == "你用的是这种方法,对吧?" and "假设法" not in turn.text
    assert turn.ready_to_confirm is False and turn.state == "dialogue"
    report = ready_report(turn.session.guard_events, 1)          # T6 消费面三问③
    assert report == {"ready_source": "kernel_override", "model_value": True,
                      "kernel_value": False, "reason": "student_answer_not_stated"}


def test_d2_three_states_only_true_to_false_records():
    """T5 负向三态钉:False→False(模型原判 false)不记;True→True(学生已陈述
    终答,确认语义保留)不记;无代喂命中(纯模型路径)不记——零 NO_OP 事件。"""
    gateway = FakeGateway(tutor_payloads=[                       # 模型原判 ready=False
        _open("你先说说题目给了哪些条件?"),
        _tutor("你用的是假设法,对吧?", ready=False),
    ])
    first = start(dict(CHICKEN_QUESTION), {"grade": "六年级"}, gateway=gateway)
    turn = reply(first.session, "我先说说我的想法。", gateway=gateway)
    assert _decisions(turn.session.guard_events, "post_method_ready_override") == []
    assert turn.ready_to_confirm is False and turn.state == "dialogue"  # 行为不变

    stated = FakeGateway(tutor_payloads=[                        # 学生已陈述 → True→True
        _open("你现在觉得鸡和兔各有多少只?"),
        _tutor("你算得完全对!你用的这个方法和等式性质是一回事。", ready=True),
    ])
    second = start(dict(CHICKEN_QUESTION), {"grade": "六年级"}, gateway=stated)
    kept = reply(second.session, "兔有10除以2等于5只,鸡有3只,验算26只脚。",
                 gateway=stated)
    assert _decisions(kept.session.guard_events, "post_method_ready_override") == []
    assert kept.ready_to_confirm is True and kept.state == "ready_to_confirm"

    plain = FakeGateway(tutor_payloads=[                         # 无代喂:纯模型原值
        _open("你先说说题目给了哪些条件?"),
        _tutor("我们把思路理清楚了。", ready=True),
    ])
    third = start(dict(CHICKEN_QUESTION), {"grade": "六年级"}, gateway=plain)
    model_truth = reply(third.session, "我先说说我的想法。", gateway=plain)
    assert _decisions(model_truth.session.guard_events, "post_method_ready_override") == []
    assert model_truth.ready_to_confirm is True                  # 模型原值直达
    assert ready_report(model_truth.session.guard_events, 1) == {
        "ready_source": "model_original"}                        # T6:原值可机械判


# ---------- T8 兼容 + 隐私 ----------

def test_legacy_events_report_absent_not_rewritten():
    """T8:旧工件事件流(无 decision、无脊柱键)——消费面对 decision 面 = ABSENT
    (不猜、不反写历史);_stamp_turn 只补轮号的既有行为不变。"""
    legacy = [{"branch": "model", "cited": [], "extracted": [6.0],
               "violation_sources": [], "gate": "observed"},
              {"guard": "answer_leak", "rule_ids": ["grounded_answer_disclosure"],
               "original": "答案是 x=6。", "regenerated": False, "mode": "blocked"}]
    report = ready_report(legacy, 1)
    assert report == {"ready_source": "ABSENT"}                  # 明确 ABSENT,不猜
    assert route_report(legacy, [], 1)["route"] == "model_path"  # 无 decision=未路由
    gateway = FakeGateway(tutor_payloads=[                       # 手工会话无 start:首弹即 reply
        _tutor("那下一步怎么算?"),
    ])
    session = LearnerSession(question=dict(CHICKEN_QUESTION), learner={"grade": "六年级"})
    session.guard_events = [dict(e) for e in legacy]
    session.first_question = "你先说说题目给了哪些条件?"
    merged = reply(session, "我先看看。", gateway=gateway)
    assert [e for e in merged.session.guard_events[:2] if "decision" in e] == []
    for old in legacy:
        assert not any(k in ("from", "to", "outcome", "target") for k in old)  # 旧事件零污染


def test_decision_events_deterministic_and_private():
    """确定性 + 隐私:同剧本两次运行 decision 事件逐字段一致;事件键面 ⊆ 闭集,
    零 prompt/学生正文/answer 面(subject 仅哈希)。"""
    def run() -> dict:
        gateway = FakeGateway(tutor_payloads=[
            _open("你先说说题目给了哪些条件?"),
            _tutor("你用的是假设法,对吧?", ready=True),
        ])
        first = start(dict(CHICKEN_QUESTION), {"grade": "六年级"}, gateway=gateway)
        reply(first.session, "我先说说我的想法。", gateway=gateway)
        d2 = _decisions(first.session.guard_events, "post_method_ready_override")
        assert len(d2) == 1
        return d2[0]

    assert run() == run()
    event = run()
    assert json.dumps(event, ensure_ascii=False)                 # 可序列化(工件面)
    assert "我先说说我的想法" not in json.dumps(event)            # 学生正文零泄漏
