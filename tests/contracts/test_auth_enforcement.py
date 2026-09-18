"""P1-1 鉴权验签回归:任意非空 Authorization 头不再过闸。

决策 7 已人批:默认强制验签(HMAC 比签 + exp)、EDU_AUTH_ENFORCE=0 熔断、
空 HMAC 密钥 fail-closed。断言只打本地 127.0.0.1 测试服务器。
"""

from __future__ import annotations

import pytest

from partner_api import ScriptedKernel, get
from auth_testing import TEST_TOKEN, signed_token


@pytest.fixture
def base(serve):
    return serve(ScriptedKernel(["先看条件。"]))


def test_valid_signed_token_passes_gate(base):
    # 404(会话不存在)= 已过鉴权闸;401 才是被闸拦下
    assert get(base, "/api/conversations/conv_x", token=TEST_TOKEN).status_code == 404


@pytest.mark.parametrize("token", [
    "whatever",
    signed_token(exp=1),  # exp=1(1970 年):已过期
], ids=["test_fake_token_is_401", "test_expired_token_is_401"])
def test_unverified_tokens_are_401(base, token):
    """假签 / 过期 token 一律 401(任意非空 Authorization 头不再过闸)。"""
    assert get(base, "/api/conversations/conv_x", token=token).status_code == 401


def test_empty_hmac_key_fails_closed(serve, monkeypatch):
    # 空钥 fail-closed:即便是格式合法的真签 token 也拒(与签发侧同口径);
    # HMAC 密钥在 build_server 时读 env,须在 serving 之前摘除
    monkeypatch.delenv("IDENTITY_TOKEN_HMAC_KEY", raising=False)
    local = serve(ScriptedKernel(["先看条件。"]))
    assert get(local, "/api/conversations/conv_x", token=TEST_TOKEN).status_code == 401


def test_enforce_kill_switch_bypasses_verification(serve, monkeypatch):
    monkeypatch.setenv("EDU_AUTH_ENFORCE", "0")  # 开关在 build_server 时读 env
    local = serve(ScriptedKernel(["先看条件。"]))
    # 熔断(联调应急):跳过验签,仅要求非空 Authorization → 404 即已过闸
    assert get(local, "/api/conversations/conv_x", token="whatever").status_code == 404
