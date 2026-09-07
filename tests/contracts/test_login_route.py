"""login 路由合同(M3 收官 A1):演示账密 → HMAC token;GET 会话状态复用 #76。

凭据全走环境变量(DEMO_ACCOUNT/DEMO_PASSWORD),测试内运行时生成无字面量。
"""

from __future__ import annotations

import httpx
import pytest
from test_api_service import ScriptedKernel, _serve, post

from edu_agent.api import demo_login


@pytest.fixture
def base(monkeypatch):
    monkeypatch.setenv("DEMO_ACCOUNT", "student1")
    monkeypatch.setenv("DEMO_PASSWORD", "night-pass-4f1a")
    url, server = _serve(ScriptedKernel(["先看条件。"]))
    yield url
    server.shutdown()


def test_login_success_returns_hmac_token(base):
    response = post(base, "/api/auth/login",
                    {"account": "student1", "password": "night-pass-4f1a",
                     "role": "student"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"].startswith("edu_native_")
    assert payload["token_type"] == "bearer" and payload["expires_in"] == 7200
    assert payload["user"]["role"] == "student"


def test_login_wrong_password_is_401(base):
    response = post(base, "/api/auth/login",
                    {"account": "student1", "password": "wrong-pass"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "USER_LOGIN_FAILED"


def test_login_missing_env_password_disables_login(base, monkeypatch):
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    response = post(base, "/api/auth/login",
                    {"account": "student1", "password": "anything"})
    assert response.status_code == 401


def test_get_conversation_roundtrip_after_login(base):
    login = post(base, "/api/auth/login",
                 {"account": "student1", "password": "night-pass-4f1a"})
    token = login.json()["access_token"]
    created = httpx.post(f"{base}/api/conversations", json={
        "question_id": "equation_subtract", "idempotency_key": "a1-001",
    }, headers={"Authorization": f"Bearer {token}"}, timeout=5.0, trust_env=False)
    assert created.status_code == 201
    conversation_id = created.json()["conversation_id"]

    view = httpx.get(f"{base}/api/conversations/{conversation_id}",
                     headers={"Authorization": f"Bearer {token}"},
                     timeout=5.0, trust_env=False)
    assert view.status_code == 200
    body = view.json()
    assert body["conversation_id"] == conversation_id
    assert body["state"] == "first_question_ready"
    assert body["question_id"] == "equation_subtract"
    assert body["turn_count"] == 0
    assert body["session_version"] == 1


def test_get_unknown_conversation_is_404(base):
    login = post(base, "/api/auth/login",
                 {"account": "student1", "password": "night-pass-4f1a"})
    token = login.json()["access_token"]
    response = httpx.get(f"{base}/api/conversations/conv_missing",
                         headers={"Authorization": f"Bearer {token}"},
                         timeout=5.0, trust_env=False)
    assert response.status_code == 404
    assert "error" in response.json()


def test_get_without_token_is_401(base):
    response = httpx.get(f"{base}/api/conversations/conv_x", timeout=5.0,
                         trust_env=False)
    assert response.status_code == 401
