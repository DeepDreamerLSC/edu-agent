"""合同回放激活(#48 留桩;00 §5.2 对话面)——Postman 请求体样例打本地真服务。

本地起服务(stub 内核,零真实模型),把 test_partner_contract_snapshot.py 尾部
留桩的四类回放逐条接上:全流程、幂等同 Attempt、409 重放、401 结构。
身份两步(native-codes/token)是 M3 对齐件(00 §5.2 身份行:v1 单合作方),
本阶段不回放、显式登记;通用对话面端点(/api/conversations)同理——新合同以
prepared-questions 专用流程取代「建会话+激活」两步(00 §5.2 开会话行语义)。
"""

from __future__ import annotations

import json
import re

import pytest

from edu_agent.contracts import partner_endpoints, postman_dir

from partner_api import ScriptedKernel, _serve, post

_BARE_PLACEHOLDER = re.compile(r":\s*\{\{\w+\}\}")  # 裸值占位("k": {{v}})非合法 JSON


@pytest.fixture
def api():
    kernel = ScriptedKernel(
        replies=["题目要我们求什么?", "你已经用了哪个条件?", "很好,乘法就是几个几相加。", "你已经掌握了。"],
        ready_at=4,
    )
    base, server = _serve(kernel)
    yield base, kernel
    server.shutdown()
    server.server_close()


def _postman_bodies() -> dict[str, dict | None]:
    """Postman 集合各请求的请求体(裸值占位归一为 null,字符串占位原样保留)。"""
    collection = json.loads(
        (postman_dir() / "small-lecturer-partner-pilot.postman_collection.json").read_text(encoding="utf-8")
    )
    bodies = {}
    for item in collection["item"]:
        raw = item.get("request", {}).get("body", {}).get("raw")
        if not raw:
            bodies[item["name"]] = None
            continue
        normalized = _BARE_PLACEHOLDER.sub(": null", raw)
        bodies[item["name"]] = json.loads(normalized)
    return bodies


def _fill(template: dict, values: dict) -> dict:
    """按回放上下文回填请求体(模拟 Postman 环境变量求值):input 里的 null 位
    (原裸占位)与 "{{...}}" 字符串占位都填入上一响应的值。"""
    payload = json.loads(json.dumps(template))
    inner = payload.get("input") or {}
    for key, value in values.items():
        if inner.get(key) is None and key in inner:
            inner[key] = value
        elif isinstance(inner.get(key), str):
            inner[key] = inner[key].replace("{{" + key + "}}", str(value))
    payload["input"] = inner
    return payload


def test_partner_full_flow_replay_with_postman_bodies(api):
    """对话面全流程:open → refresh → messages(Postman 第 6 步请求体)→ stream → confirm。"""
    base, _ = api
    bodies = _postman_bodies()

    opened = post(base, "/api/prepared-questions/q-9001/open",
                  {"idempotency_key": "replay-open-1"}).json()
    sid = opened["skill_session_id"]
    conversation_id = opened["conversation"]["conversation_id"]

    refresh = post(base, f"/api/conversations/{conversation_id}/skill-sessions/{sid}/refresh")
    # R6 后 refresh 返回全信封(M3 全景 B3):assistant_message + skill_interaction + agent_run
    refreshed = refresh.json()
    assert refreshed["assistant_message"]["content"] == "我们先看已知条件,题目要我们求什么?"
    assert refreshed["skill_interaction"]["schema_version"] == "skill_interaction/v1"
    assert refreshed["agent_run"]["status"] == "completed"

    # Postman「6. 提交一轮学生回答」请求体,占位符替换为回放上下文
    turn = post(base, f"/api/conversations/{conversation_id}/messages", _fill(
        bodies["6. 提交一轮学生回答"],
        {"skill_session_id": sid, "expected_session_version": 1},
    ))
    assert turn.status_code == 200
    assert turn.json()["assistant_message"]["content"] == "题目要我们求什么?"

    streamed = post(base, f"/api/conversations/{conversation_id}/messages/stream", _fill(
        bodies["6. 提交一轮学生回答"],
        {"skill_session_id": sid, "expected_session_version": 2},
    ))
    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("text/event-stream")

    for expected in (3, 4):
        post(base, f"/api/conversations/{conversation_id}/messages", _fill(
            bodies["6. 提交一轮学生回答"],
            {"skill_session_id": sid, "expected_session_version": expected},
        ))
    confirm = post(base, f"/api/conversations/{conversation_id}/messages", {
        "content": "确认结束", "skill_id": "small_lecturer_coaching",
        "input": {"interaction_action": "confirm", "skill_session_id": sid},
    })
    assert confirm.json()["status"] == "completed"


def test_idempotent_open_returns_same_attempt(api):
    """留桩激活:幂等键开会话,同键重试不创建第二个会话(00 §5.2 约定 1)。"""
    base, _ = api
    first = post(base, "/api/prepared-questions/q-1/open", {"idempotency_key": "replay-idem"})
    again = post(base, "/api/prepared-questions/q-1/open", {"idempotency_key": "replay-idem"})
    assert again.json() == first.json()
    assert first.json()["conversation"]["attempt_id"] == again.json()["conversation"]["attempt_id"]


def test_stale_version_replay_returns_conflict_envelope(api):
    """留桩激活:以过期 expected_session_version 重放 → 409 + 合同错误结构。"""
    base, _ = api
    bodies = _postman_bodies()
    opened = post(base, "/api/prepared-questions/q-2/open", {"idempotency_key": "replay-409"}).json()
    sid = opened["skill_session_id"]
    conversation_id = opened["conversation"]["conversation_id"]
    post(base, f"/api/conversations/{conversation_id}/messages", _fill(
        bodies["6. 提交一轮学生回答"], {"skill_session_id": sid, "expected_session_version": 1}))
    stale = post(base, f"/api/conversations/{conversation_id}/messages", _fill(
        bodies["6. 提交一轮学生回答"], {"skill_session_id": sid, "expected_session_version": 1}))
    assert stale.status_code == 409
    error = stale.json()["error"]
    assert error["code"] == "SKILL_SESSION_CONFLICT"
    assert set(error) == {"code", "message", "request_id", "details"}


def test_unauthorized_replay_error_structure(api):
    """留桩激活:无令牌请求 → 401 且错误结构与合同一致。"""
    base, _ = api
    response = post(base, "/api/prepared-questions/q/open", {"idempotency_key": "k"}, auth=False)
    assert response.status_code == 401
    body = response.json()["error"]
    assert body["code"] is None and body["message"]


def test_identity_endpoints_registered_for_m3_alignment():
    """身份两步在合同在册、服务端属 M3 对齐件——显式登记,不留假绿。"""
    endpoints = {(row["method"], row["path"]) for row in partner_endpoints()["endpoints"]}
    assert ("POST", "/api/openapi/v1/auth/native-codes") in endpoints
    assert ("POST", "/api/auth/native/token") in endpoints


def test_postman_request_fields_replayable_on_new_contract():
    """Postman 对话面请求体的字段在新合同端点全部可表达(结构对账,零发明):
    content/skill_id/input.skill_session_id/expected_session_version/student_response。"""
    bodies = _postman_bodies()
    dialogue = bodies["6. 提交一轮学生回答"]
    assert dialogue["skill_id"] == "small_lecturer_coaching"
    assert set(dialogue["input"]) >= {"skill_session_id", "expected_session_version"}
    assert dialogue["content"] == dialogue["input"]["student_response"]
