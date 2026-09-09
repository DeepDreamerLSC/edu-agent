"""P1-1 鉴权验签回归:任意非空 Authorization 头不再过闸。

决策 7 已人批:默认强制验签(HMAC 比签 + exp)、EDU_AUTH_ENFORCE=0 熔断、
空 HMAC 密钥 fail-closed。断言只打本地 127.0.0.1 测试服务器。
"""

from __future__ import annotations

import threading

import httpx
import pytest

from edu_agent.api import build_server, build_service
from test_api_service import ScriptedKernel, _assert_local_base
from auth_testing import TEST_TOKEN, signed_token


def _serve() -> tuple[str, object]:
    server = build_server(build_service(ScriptedKernel(["先看条件。"])))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}", server


def _get(base: str, token: str) -> httpx.Response:
    _assert_local_base(base)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.get(f"{base}/api/conversations/conv_x", headers=headers,
                     timeout=5.0, trust_env=False)


def test_valid_signed_token_passes_gate():
    base, server = _serve()
    try:
        # 404(会话不存在)= 已过鉴权闸;401 才是被闸拦下
        assert _get(base, TEST_TOKEN).status_code == 404
    finally:
        server.shutdown()
        server.server_close()


def test_fake_token_is_401():
    base, server = _serve()
    try:
        assert _get(base, "whatever").status_code == 401
    finally:
        server.shutdown()
        server.server_close()


def test_expired_token_is_401():
    base, server = _serve()
    try:
        assert _get(base, signed_token(exp=1)).status_code == 401  # exp 在 1970,已过期
    finally:
        server.shutdown()
        server.server_close()


def test_empty_hmac_key_fails_closed(monkeypatch):
    monkeypatch.delenv("IDENTITY_TOKEN_HMAC_KEY", raising=False)
    base, server = _serve()
    try:
        # 空钥 fail-closed:即便是格式合法的真签 token 也拒(与签发侧同口径)
        assert _get(base, TEST_TOKEN).status_code == 401
    finally:
        server.shutdown()
        server.server_close()


def test_enforce_kill_switch_bypasses_verification(monkeypatch):
    monkeypatch.setenv("EDU_AUTH_ENFORCE", "0")
    base, server = _serve()
    try:
        # 熔断(联调应急):跳过验签,仅要求非空 Authorization → 404 即已过闸
        assert _get(base, "whatever").status_code == 404
    finally:
        server.shutdown()
        server.server_close()