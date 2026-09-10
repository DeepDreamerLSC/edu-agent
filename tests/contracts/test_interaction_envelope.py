"""skill_interaction/v1 运行时填充合同(M3 PR6;#48 schema 为规格)。

信封可选集合(attempt_state/confirmation/progress)全部从内核 session 直读,
不建状态机;本文件对每个字段断言类型与值,并对全部状态做 schema 校验。
零真实模型(假 gateway)。
"""

from __future__ import annotations

import json

import jsonschema

from edu_agent.agents.small_lecturer import LearnerSession
from edu_agent.api import Conversation, ConversationService, SmallLecturerKernel, build_service
from edu_agent.contracts import skill_interaction_schema


class FakeGateway:
    """确定性假 gateway:vision 三字段 / tutor 回合 JSON / 总结 JSON。"""

    def __init__(self, ready_at_call: int = 99):
        self.ready_at_call = ready_at_call
        self.tutor_calls = 0

    def invoke(self, request):
        if request.role == "vision":
            text = json.dumps({"acceptable": True, "reason": "单题清晰",
                               "transcription": ""})
        elif request.response_schema and "summary" in json.dumps(request.response_schema):
            text = json.dumps({"summary": "你完整讲清楚了这道题。"}, ensure_ascii=False)
        else:
            self.tutor_calls += 1
            text = json.dumps({"reply": f"第 {self.tutor_calls} 问?",
                               "ready_to_confirm": self.tutor_calls >= self.ready_at_call},
                              ensure_ascii=False)
        response = type("R", (), {})()
        response.text = text
        return response


def live_conversation(state: str, *, history: list | None = None,
                      summary: dict | None = None) -> Conversation:
    """带真内核 session 的会话(信封直读源);state/history 按用例定制。"""
    session = LearnerSession(question={"text": "解方程 3x+7=25"}, learner={"grade": "五年级"})
    session.state = state
    for message in (history or []):
        session.history.append(message)
    return Conversation(
        conversation_id="conv-env-1", question_id="q-1", attempt_id="attempt-1",
        skill_session_id="skill_session-env-1", session_version=3,
        state=state, summary=summary,
        extras={"kernel_session": session},
    )


def envelope_for(conversation: Conversation) -> dict:
    return ConversationService.interaction_envelope(conversation)


# ---------- schema 合法性(全状态) ----------

def test_envelope_validates_for_every_state():
    for state in ("preparing", "first_question_ready", "dialogue",
                  "ready_to_confirm", "needs_review", "completed", "failed"):
        envelope = envelope_for(live_conversation(state))
        jsonschema.validate(envelope, skill_interaction_schema())  # #48 全字段过 schema


# ---------- 信封字段逐个:类型与值 ----------

def test_envelope_required_fields():
    envelope = envelope_for(live_conversation("dialogue"))
    assert envelope["schema_version"] == "skill_interaction/v1"
    assert envelope["skill_session_id"] == "skill_session-env-1"
    assert envelope["skill_id"] == "small_lecturer_coaching"
    assert isinstance(envelope["skill_version"], str) and envelope["skill_version"]
    assert envelope["session_version"] == 3 and isinstance(envelope["session_version"], int)
    assert envelope["kind"] == "input_request"          # dialogue→input_request
    assert envelope["state"] == "dialogue"


def test_attempt_state_maps_kernel_state():
    """attempt_state = 内核 session.state 的 dict 映射(老系统词汇,#34 实录)。"""
    assert envelope_for(live_conversation("first_question_ready"))["attempt_state"] == {
        "state": "collecting_inputs"}
    assert envelope_for(live_conversation("dialogue"))["attempt_state"] == {
        "state": "collecting_inputs"}
    assert envelope_for(live_conversation("ready_to_confirm"))["attempt_state"] == {
        "state": "ready_to_confirm"}
    assert envelope_for(live_conversation("needs_review"))["attempt_state"] == {
        "state": "needs_review"}
    assert envelope_for(live_conversation("completed"))["attempt_state"] == {
        "state": "completed"}
    assert envelope_for(live_conversation("failed"))["attempt_state"] == {"state": "failed"}
    assert isinstance(envelope_for(live_conversation("dialogue"))["attempt_state"], dict)


def test_confirmation_follows_ready_and_completed():
    """confirmation = ready_to_confirm / completed(逐值)。"""
    assert envelope_for(live_conversation("dialogue"))["confirmation"] is None
    confirming = envelope_for(live_conversation("ready_to_confirm"))["confirmation"]
    assert confirming == {"ready_to_confirm": True, "completed": False}
    done = envelope_for(live_conversation("completed"))["confirmation"]
    assert done == {"ready_to_confirm": True, "completed": True}


def test_progress_counts_student_rounds():
    """progress = 当前轮次(学生轮数,内核 history 直读)/ 预期轮次。"""
    turns = [{"role": "user", "content": "一"}, {"role": "assistant", "content": "问?"},
             {"role": "user", "content": "二"}, {"role": "assistant", "content": "好"}]
    envelope = envelope_for(live_conversation("dialogue", history=turns))
    assert envelope["progress"] == {"current_round": 2, "expected_rounds": 5}


def test_empty_collections_and_result():
    """无多步输入流:inputs/requirements/missing_input_ids 恒空载;result 承载 summary。"""
    summary = {"status": "completed"}
    envelope = envelope_for(live_conversation("completed", summary=summary))
    assert envelope["inputs"] == [] and isinstance(envelope["inputs"], list)
    assert envelope["requirements"] == [] and isinstance(envelope["requirements"], list)
    assert envelope["missing_input_ids"] == [] and isinstance(envelope["missing_input_ids"], list)
    assert envelope["result"] == summary


# ---------- 夹具内核回退与真内核端到端 ----------

def test_envelope_falls_back_without_kernel_session():
    """夹具内核(无 session 对象):回退 conversation 状态与 extras history。"""
    conversation = Conversation(
        conversation_id="conv-fx-1", question_id="q-1", attempt_id="attempt-1",
        skill_session_id="skill_session-fx-1", session_version=2,
        state="ready_to_confirm",
        extras={"history": [{"role": "user", "content": "回答"}]},
    )
    envelope = envelope_for(conversation)
    jsonschema.validate(envelope, skill_interaction_schema())
    assert envelope["state"] == "ready_to_confirm" and envelope["kind"] == "confirmation"
    assert envelope["attempt_state"] == {"state": "ready_to_confirm"}
    assert envelope["progress"] == {"current_round": 1, "expected_rounds": 5}


def test_live_flow_envelope_fills_from_kernel_session():
    """端到端:真内核 service 流转中,信封 attempt_state/progress 直读内核 session。

    P1-6 后 confirm 两路都走 kernel.finish,completed 后内核 attempt 同步进
    completed(切片 result 的 attempt_state 与响应面 state 一致)。"""
    service = build_service(SmallLecturerKernel(FakeGateway(ready_at_call=2)))
    opened = service.open("q-1", "idem-env-1", learner={})
    conversation = service._conversation_or_404(opened["conversation"]["conversation_id"])
    first = service.interaction_envelope(conversation)
    assert first["state"] == "first_question_ready"
    assert first["attempt_state"] == {"state": "collecting_inputs"}
    service.send(conversation.conversation_id, {
        "content": "两边同时减 7。",
        "input": {"skill_session_id": opened["skill_session_id"],
                  "expected_session_version": opened["session_version"]}})
    ready = service.interaction_envelope(conversation)
    assert ready["state"] == "ready_to_confirm" and ready["kind"] == "confirmation"
    assert ready["confirmation"] == {"ready_to_confirm": True, "completed": False}
    assert ready["attempt_state"] == {"state": "ready_to_confirm"}
    assert ready["progress"]["current_round"] == 1
    service.send(conversation.conversation_id, {
        "content": "确认",
        "input": {"interaction_action": "confirm",
                  "skill_session_id": opened["skill_session_id"]}})
    done = service.interaction_envelope(conversation)
    assert done["kind"] == "result" and done["state"] == "completed"
    assert done["confirmation"] == {"ready_to_confirm": True, "completed": True}
    assert done["attempt_state"] == {"state": "completed"}  # confirm 走完 finish,内核尝试同步终态
    jsonschema.validate(done, skill_interaction_schema())
