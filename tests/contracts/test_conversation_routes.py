"""合作方会话入口与状态查询路由合同(M3 最后代码 PR;#48 Postman 集合入口形态)。

POST /api/conversations(创建,合同字段透传)→ GET /api/conversations/{id}(状态)。
请求走 test_api_service 的 SSRF 边界守卫(只允许 127.0.0.1 本地测试服务器)。
"""

from __future__ import annotations

import httpx
import pytest
from test_api_service import ScriptedKernel, _assert_local_base, _serve, post


@pytest.fixture
def base():
    url, server = _serve(ScriptedKernel(["先看条件。", "思路对。", "讲完了。"]))
    yield url
    server.shutdown()


def get(base: str, path: str) -> httpx.Response:
    """GET 形态;SSRF 边界守卫与 post() 同款(test_api_service)。"""
    _assert_local_base(base)
    headers = {"Authorization": "Bearer test-token"}
    return httpx.get(f"{base}{path}", headers=headers, timeout=5.0, trust_env=False)


def test_create_then_get_roundtrip(base):
    response = post(base, "/api/conversations", {
        "question_id": "equation_subtract",
        "idempotency_key": "route-001",
        "image_file_id": "seed-image_x",  # 合同字段透传 learner
    })
    assert response.status_code == 201
    payload = response.json()
    conversation_id = payload["conversation_id"]
    assert payload["skill_session_id"] and payload["session_version"] == 1
    assert payload["first_question_ready"] is True
    assert payload["first_question"]

    view = get(base, f"/api/conversations/{conversation_id}")
    assert view.status_code == 200
    body = view.json()
    assert body == {
        "conversation_id": conversation_id,
        "state": "first_question_ready",
        "session_version": 1,
        "question_id": "equation_subtract",
        "created_at": body["created_at"],  # 动态字段与自身比对保键存在
        "turn_count": 0,
    }
    assert body["created_at"]  # ISO 时间戳由 open 写入


def test_idempotent_retry_returns_same_conversation(base):
    body = {"question_id": "equation_subtract", "idempotency_key": "route-002"}
    first = post(base, "/api/conversations", body)
    second = post(base, "/api/conversations", body)
    assert first.status_code == second.status_code == 201
    assert first.json()["conversation_id"] == second.json()["conversation_id"]


def test_unknown_conversation_is_404(base):
    response = get(base, "/api/conversations/conv_missing")
    assert response.status_code == 404
    assert "error" in response.json()


def test_forbidden_client_fields_are_403(base):
    for field in ("answer", "analysis", "mastery_status"):
        response = post(base, "/api/conversations",
                        {"question_id": "q", "idempotency_key": f"route-{field}",
                         field: "客户端伪造"})
        assert response.status_code == 403, (field, response.text)
        assert "不得提交" in response.json()["error"]["message"]
    # 拦截在创建之前:未产生任何会话
    assert get(base, "/api/conversations/conv_x").status_code == 404


def test_missing_required_fields_are_422(base):
    missing_key = post(base, "/api/conversations", {"question_id": "q"})
    assert missing_key.status_code == 422
    assert "idempotency_key" in missing_key.json()["error"]["message"]
    missing_question = post(base, "/api/conversations", {"idempotency_key": "k"})
    assert missing_question.status_code == 422
    assert "question_id" in missing_question.json()["error"]["message"]
