"""messages 语义补齐合同(00 §5.2;#34 M3 全景 B4):action 路由、SSE 六型帧、
消息幂等、skill_id 校验、refresh 信封(agent_run 恒 completed——同步架构)。

零真实模型:确定性假内核(ScriptedKernel / FlakyKernel),走 HTTP 打本地服务。
"""

from __future__ import annotations

import json
import threading

import httpx
import pytest

from edu_agent.api import ApiError, build_server, build_service
from test_api_service import ScriptedKernel
from auth_testing import TEST_TOKEN

REPLIES = ["你列了哪些已知量?", "很好,继续。", "结论对。", "总结:方法你讲清了。",
           "第五轮。", "第六轮。", "第七轮。", "第八轮。"]


def _serve(kernel) -> tuple[str, object]:
    server = build_server(build_service(kernel))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}", server


def _post(base: str, path: str, payload: dict | None = None):
    return httpx.post(f"{base}{path}", json=payload, timeout=5.0, trust_env=False,
                      headers={"Authorization": f"Bearer {TEST_TOKEN}"})


def open_session(base: str, question_id: str = "q-1") -> dict:
    response = _post(base, f"/api/prepared-questions/{question_id}/open",
                     {"idempotency_key": "idem-" + question_id})
    assert response.status_code == 200
    return response.json()


def parse_sse(raw: bytes) -> list[tuple[str, dict]]:
    frames = []
    for block in raw.decode("utf-8").strip().split("\n\n"):
        lines = block.split("\n")
        frames.append((lines[0].removeprefix("event: "),
                       json.loads(lines[1].removeprefix("data: "))))
    return frames


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
    base, server = _serve(kernel)
    yield base, kernel, server
    server.shutdown()
    server.server_close()


# ---------- interaction_action 路由(仅 confirm + 普通对话) ----------

@pytest.mark.parametrize("action", [
    "activate", "submit_inputs", "diagnose", "pause",
    "resume", "restart", "cancel", "refresh",
])
def test_unsupported_actions_rejected_with_contract_code(api, action):
    """老通用面的 action 明确拒收:400 UNSUPPORTED_ACTION(一个 if/else 非工作流引擎)。"""
    base, _, _ = api
    opened = open_session(base, question_id="q-act")
    response = _post(base, f"/api/conversations/{opened['conversation']['conversation_id']}/messages",
                     {"content": "任意内容",
                      "input": {"skill_session_id": opened["skill_session_id"],
                                "interaction_action": action}})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_ACTION"


def test_null_action_is_normal_dialogue(api):
    base, kernel, _ = api
    opened = open_session(base, question_id="q-null")
    response = _post(base, f"/api/conversations/{opened['conversation']['conversation_id']}/messages",
                     {"content": "我先列已知条件。",
                      "input": {"skill_session_id": opened["skill_session_id"],
                                "expected_session_version": 1}})
    assert response.status_code == 200
    assert kernel.reply_calls == 1


# ---------- skill_id 校验(一个比较) ----------

def test_wrong_skill_id_is_403(api):
    base, _, _ = api
    opened = open_session(base, question_id="q-skill")
    response = _post(base, f"/api/conversations/{opened['conversation']['conversation_id']}/messages",
                     {"content": "内容", "skill_id": "some_other_skill",
                      "input": {"skill_session_id": opened["skill_session_id"]}})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "SKILL_ID_INVALID"


# ---------- SSE 六型帧(status/error 补齐,M3 全景 B4) ----------

def test_sse_success_frame_order_status_first(api):
    base, _, _ = api
    opened = open_session(base, question_id="q-sse")
    response = _post(base, f"/api/conversations/{opened['conversation']['conversation_id']}/messages/stream",
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


class FlakyKernel:
    """start 正常、reply 抛 503 语义错误的内核(in-band error 帧的触发器)。"""

    name = "flaky"
    start_calls = 0

    def start(self, question, learner):
        self.start_calls += 1
        return type("T", (), {"text": "第一问"})()

    def reply(self, session, student_message):
        raise ApiError(503, None, "讲解服务暂时不可用,请稍后重试。")

    def finish(self, session):
        return type("S", (), {"text": "小结", "status": "needs_review"})()


def test_sse_kernel_error_frame_in_band():
    """内核异常(503 族)→ 流内 error 帧:友好文案+错误码(流已开,in-band)。"""
    server = build_server(build_service(FlakyKernel()))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    opened = open_session(base, question_id="q-err")
    response = _post(base, f"/api/conversations/{opened['conversation']['conversation_id']}/messages/stream",
                     {"content": "触发内核异常",
                      "input": {"skill_session_id": opened["skill_session_id"],
                                "expected_session_version": 1}})
    frames = parse_sse(response.content)
    server.shutdown()
    server.server_close()
    assert response.status_code == 200  # 流已开,错误 in-band
    assert frames[-1][0] == "error"
    error = frames[-1][1]
    assert error["code"] and "稍后重试" in error["message"]  # 错误码+友好文案


# ---------- 消息幂等(message_idempotency_key) ----------

def test_idempotent_resend_returns_same_turn_without_advance(api):
    base, kernel, _ = api
    opened = open_session(base, question_id="q-idem")
    conversation_id = opened["conversation"]["conversation_id"]
    body = {"content": "第一轮回答", "message_idempotency_key": "idem-msg-1",
            "input": {"skill_session_id": opened["skill_session_id"],
                      "expected_session_version": 1}}
    first = _post(base, f"/api/conversations/{conversation_id}/messages", body)
    second = _post(base, f"/api/conversations/{conversation_id}/messages", body)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()  # 同键同响应:不重调模型、不 version++
    assert kernel.reply_calls == 1        # 幂等重发不再调内核


def test_different_keys_are_different_turns(api):
    base, kernel, _ = api
    opened = open_session(base, question_id="q-idem2")
    conversation_id = opened["conversation"]["conversation_id"]
    first = _post(base, f"/api/conversations/{conversation_id}/messages",
                  {"content": "第一轮", "message_idempotency_key": "idem-a",
                   "input": {"skill_session_id": opened["skill_session_id"],
                             "expected_session_version": 1}})
    second = _post(base, f"/api/conversations/{conversation_id}/messages",
                   {"content": "第二轮", "message_idempotency_key": "idem-b",
                    "input": {"skill_session_id": opened["skill_session_id"],
                              "expected_session_version": 2}})
    assert first.json()["session_version"] == 2
    assert second.json()["session_version"] == 3  # 不同键正常推进


# ---------- refresh 信封补齐(M3 全景 B3) ----------

def test_refresh_returns_full_envelope_with_agent_run(api):
    base, _, _ = api
    opened = open_session(base, question_id="q-refresh")
    response = _post(
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
