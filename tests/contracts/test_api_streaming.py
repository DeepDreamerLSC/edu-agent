"""合作方接口信封与流式合同(00 §5.2 多轮流式行;#48 skill_interaction/v1 schema)。

信封全字段对 contracts schema 校验、SSE 帧序(start→interaction→delta→done)、
流式路径的会话语义(409 在开流前以 JSON 返回)。零真实模型(假内核)。
"""

from __future__ import annotations

import jsonschema
import pytest

from edu_agent.contracts import skill_interaction_schema

from partner_api import ScriptedKernel, _serve, open_session, parse_sse, post


@pytest.fixture
def api():
    kernel = ScriptedKernel(
        replies=["你列了哪些已知量?", "很好,那两个量之间是什么关系?", "你已经掌握了乘法意义。"],
        ready_at=3,
    )
    base, server = _serve(kernel)
    yield base, kernel
    server.shutdown()
    server.server_close()


def _messages_path(opened: dict) -> str:
    return f"/api/conversations/{opened['conversation']['conversation_id']}/messages"


def test_envelope_validates_against_contract_schema(api):
    base, _ = api
    opened = open_session(base)
    response = post(base, _messages_path(opened), {
        "content": "第一轮",
        "input": {"skill_session_id": opened["skill_session_id"], "expected_session_version": 1},
    })
    interaction = response.json()["skill_interaction"]
    jsonschema.validate(interaction, skill_interaction_schema())  # 全字段过 #48 schema
    assert interaction["kind"] == "input_request" and interaction["state"] == "dialogue"
    assert set(interaction) == {  # 全量字段集(schema properties 逐键在位;M3 PR6 填 attempt_state)
        "schema_version", "skill_session_id", "skill_id", "skill_version",
        "session_version", "kind", "state", "attempt_state", "inputs",
        "requirements", "missing_input_ids", "confirmation", "progress", "result",
    }


def test_envelope_kind_follows_session_state(api):
    base, _ = api
    opened = open_session(base)
    for expected in (1, 2, 3):
        response = post(base, _messages_path(opened), {
            "content": f"第{expected}轮",
            "input": {"skill_session_id": opened["skill_session_id"],
                      "expected_session_version": expected},
        })
    interaction = response.json()["skill_interaction"]
    assert interaction["kind"] == "confirmation"  # ready_to_confirm 状态映射


def test_stream_emits_contract_frame_order(api):
    base, _ = api
    opened = open_session(base)
    response = post(base, _messages_path(opened) + "/stream", {
        "content": "我先说说已知条件。",
        "input": {"skill_session_id": opened["skill_session_id"], "expected_session_version": 1},
    })
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = parse_sse(response.content)
    assert [event for event, _ in frames] == ["status", "start", "interaction", "delta", "done"]
    interaction = dict(frames)["interaction"]
    jsonschema.validate(interaction, skill_interaction_schema())
    delta = dict(frames)["delta"]
    done = dict(frames)["done"]
    assert delta["text"] == "你列了哪些已知量?"
    assert done["assistant_message"]["content"] == delta["text"]  # done 含完整响应
    assert done["session_version"] == 2


def test_stream_conflict_returns_json_error_before_opening_stream(api):
    base, _ = api
    opened = open_session(base)
    body = {"content": "x", "input": {"skill_session_id": opened["skill_session_id"],
                                      "expected_session_version": 99}}
    response = post(base, _messages_path(opened) + "/stream", body)
    assert response.status_code == 409  # 校验失败不开流,JSON 错误(信封形态)
    assert response.json()["error"]["code"] == "SKILL_SESSION_CONFLICT"
    assert not response.headers.get("content-type", "").startswith("text/event-stream")


def test_first_question_contract_fields_semantics(api):
    """00 §5.2 开会话行:first_question_ready/retry_after_ms 字段语义保留——
    新链路同步出首问(ready=true、retry=0),字段为合作方既有处理兼容而在。"""
    base, _ = api
    body = open_session(base)
    assert body["first_question_ready"] is True and body["retry_after_ms"] == 0
