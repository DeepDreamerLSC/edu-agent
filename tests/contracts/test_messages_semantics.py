"""messages 语义补齐合同(00 §5.2;#34 M3 全景 B4):action 路由、SSE 六型帧、
消息幂等、skill_id 校验、refresh 信封(agent_run 恒 completed——同步架构)。

零真实模型:确定性假内核(ScriptedKernel / FlakyKernel),走 HTTP 打本地服务。
"""

from __future__ import annotations

import pytest

from edu_agent.api import ApiError
from partner_api import ScriptedKernel, open_session, parse_sse, post, serving

REPLIES = ["你列了哪些已知量?", "很好,继续。", "结论对。", "总结:方法你讲清了。",
           "第五轮。", "第六轮。", "第七轮。", "第八轮。"]


class FlakyKernel:
    """start 正常、reply 抛 503 语义错误的内核(in-band error 帧的触发器)。"""

    name = "flaky"

    def start(self, question, learner):
        return type("T", (), {"text": "第一问"})()

    def reply(self, session, student_message):
        raise ApiError(503, None, "讲解服务暂时不可用,请稍后重试。")

    def finish(self, session):
        return type("S", (), {"text": "小结", "status": "needs_review"})()


@pytest.fixture
def api():
    kernel = ScriptedKernel(replies=list(REPLIES), ready_at=99)  # 本文件不测判停
    with serving(kernel) as base:
        yield base, kernel


# ---------- interaction_action 路由(仅 confirm + 普通对话) ----------

@pytest.mark.parametrize("action", [
    "activate", "submit_inputs", "diagnose", "pause",
    "resume", "restart", "cancel", "refresh",
])
def test_unsupported_actions_rejected_with_contract_code(api, action):
    """老通用面的 action 明确拒收:400 UNSUPPORTED_ACTION(一个 if/else 非工作流引擎)。"""
    base, _ = api
    opened = open_session(base, question_id="q-act")
    response = post(base, f"/api/conversations/{opened['conversation']['conversation_id']}/messages",
                    {"content": "任意内容",
                     "input": {"skill_session_id": opened["skill_session_id"],
                               "interaction_action": action}})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_ACTION"


def test_null_action_is_normal_dialogue(api):
    base, kernel = api
    opened = open_session(base, question_id="q-null")
    response = post(base, f"/api/conversations/{opened['conversation']['conversation_id']}/messages",
                    {"content": "我先列已知条件。",
                     "input": {"skill_session_id": opened["skill_session_id"],
                               "expected_session_version": 1}})
    assert response.status_code == 200
    assert kernel.reply_calls == 1


# ---------- skill_id 校验(一个比较) ----------

def test_wrong_skill_id_is_403(api):
    base, _ = api
    opened = open_session(base, question_id="q-skill")
    response = post(base, f"/api/conversations/{opened['conversation']['conversation_id']}/messages",
                    {"content": "内容", "skill_id": "some_other_skill",
                     "input": {"skill_session_id": opened["skill_session_id"]}})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "SKILL_ID_INVALID"


# ---------- SSE 六型帧(status/error 补齐,M3 全景 B4) ----------

def test_sse_success_frame_order_status_first(api):
    base, _ = api
    opened = open_session(base, question_id="q-sse")
    response = post(base, f"/api/conversations/{opened['conversation']['conversation_id']}/messages/stream",
                    {"content": "第一轮回答",
                     "input": {"skill_session_id": opened["skill_session_id"],
                               "expected_session_version": 1}})
    assert response.status_code == 200
    frames = parse_sse(response.content)
    assert [event for event, _ in frames] == ["status", "start", "interaction", "delta", "done"]
    by_event = dict(frames)
    assert by_event["status"] == {"state": "dialogue", "session_version": 2}  # 会话元信息
    assert by_event["interaction"]["schema_version"] == "skill_interaction/v1"
    assert by_event["done"]["assistant_message"]["content"]


def test_sse_kernel_error_frame_in_band():
    """内核异常(503 族)→ 流内 error 帧:友好文案+错误码(流已开,in-band)。"""
    with serving(FlakyKernel()) as base:
        opened = open_session(base, question_id="q-err")
        response = post(base,
                        f"/api/conversations/{opened['conversation']['conversation_id']}/messages/stream",
                        {"content": "触发内核异常",
                         "input": {"skill_session_id": opened["skill_session_id"],
                                   "expected_session_version": 1}})
        frames = parse_sse(response.content)
        assert response.status_code == 200  # 流已开,错误 in-band
        assert frames[-1][0] == "error"
        error = frames[-1][1]
        assert error["code"] and "稍后重试" in error["message"]  # 错误码+友好文案


# ---------- 消息幂等(message_idempotency_key) ----------

def test_idempotent_resend_returns_same_turn_without_advance(api):
    base, kernel = api
    opened = open_session(base, question_id="q-idem")
    conversation_id = opened["conversation"]["conversation_id"]
    body = {"content": "第一轮回答", "message_idempotency_key": "idem-msg-1",
            "input": {"skill_session_id": opened["skill_session_id"],
                      "expected_session_version": 1}}
    first = post(base, f"/api/conversations/{conversation_id}/messages", body)
    second = post(base, f"/api/conversations/{conversation_id}/messages", body)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()  # 同键同响应:不重调模型、不 version++
    assert kernel.reply_calls == 1        # 幂等重发不再调内核


def test_different_keys_are_different_turns(api):
    base, kernel = api
    opened = open_session(base, question_id="q-idem2")
    conversation_id = opened["conversation"]["conversation_id"]
    first = post(base, f"/api/conversations/{conversation_id}/messages",
                 {"content": "第一轮", "message_idempotency_key": "idem-a",
                  "input": {"skill_session_id": opened["skill_session_id"],
                            "expected_session_version": 1}})
    second = post(base, f"/api/conversations/{conversation_id}/messages",
                  {"content": "第二轮", "message_idempotency_key": "idem-b",
                   "input": {"skill_session_id": opened["skill_session_id"],
                             "expected_session_version": 2}})
    assert first.json()["session_version"] == 2
    assert second.json()["session_version"] == 3  # 不同键正常推进


# ---------- refresh 信封补齐(M3 全景 B3) ----------

def test_refresh_returns_full_envelope_with_agent_run(api):
    base, _ = api
    opened = open_session(base, question_id="q-refresh")
    response = post(
        base,
        f"/api/conversations/{opened['conversation']['conversation_id']}"
        f"/skill-sessions/{opened['skill_session_id']}/refresh")
    assert response.status_code == 200
    body = response.json()
    assert body["assistant_message"]["content"]          # 首问就绪时非空
    interaction = body["skill_interaction"]
    assert interaction["schema_version"] == "skill_interaction/v1"
    assert interaction["skill_session_id"] == opened["skill_session_id"]
    assert body["agent_run"]["status"] == "completed"    # 同步架构,恒 completed
    assert body["agent_run"]["id"]
