"""身份两端点 HTTP 接线合同(00 §5.2 身份行;#63 逻辑,#34 M3 全景 B1)。

PKCE 全舞步走 HTTP:native-codes(断言+challenge→一次性码)→ token(码+verifier→
短期令牌);幂等/错误码族/信封形态同 #48。断言上游 = 本地生成的 RSA 密钥对
(partner_fixture,联调专用非生产凭据);全部凭据运行时生成,零字面量。
"""

from __future__ import annotations

import secrets

import httpx
import pytest

from edu_agent.api import IdentityService

from partner_api import ScriptedKernel, serving
from partner_fixture import generate_key, identity_config, pkce_challenge, public_pem, sign_rs256
from auth_testing import signed_token

API_KEY = "test-" + secrets.token_hex(8)
HMAC_KEY = "test-" + secrets.token_hex(8)
VERIFIER = "test-verifier-" + secrets.token_hex(16)
CHALLENGE = pkce_challenge(VERIFIER)
EXTERNAL_ID = "student-001"


@pytest.fixture
def base_url():
    """完整对话服务(stub 内核 + 真身份):PKCE 舞步打的就是部署形态的 HTTP 面。"""
    config = dict(identity_config(API_KEY, HMAC_KEY), verify_key_pem="")
    key = generate_key(1024)
    config["verify_key_pem"] = public_pem(key)
    with serving(ScriptedKernel(["第一问"], start_text="第一问"),
                 identity=IdentityService(config)) as base:
        yield base, key


def _assertion(key, external_id=EXTERNAL_ID):
    import time

    return sign_rs256(key, {"alg": "RS256", "kid": "partner-key-2026-01"}, {
        "iss": "https://partner.example", "aud": "edu-agent", "role": "student",
        "sub": external_id, "external_student_id": external_id, "jti": "jti-1",
        "iat": int(time.time()), "nbf": int(time.time()) - 1, "exp": int(time.time()) + 300,
    })


def _native_codes(base, key, *, idem="login-001", api_key=API_KEY,
                  external_id=EXTERNAL_ID, assertion=None):
    headers = {"Authorization": f"Bearer {api_key}", "Idempotency-Key": idem}
    return httpx.post(f"{base}/api/openapi/v1/auth/native-codes", headers=headers, timeout=5.0,
                      trust_env=False,
                      json={"assertion": assertion or _assertion(key, external_id=external_id),
                            "external_student_id": external_id,
                            "native_app_id": "partner_student_app",
                            "code_challenge": CHALLENGE, "code_challenge_method": "S256"})


# ---------- PKCE 全舞步(经 HTTP) ----------

def test_pkce_full_dance_native_codes_then_token(base_url):
    base, key = base_url
    codes = _native_codes(base, key)
    assert codes.status_code == 201
    code = codes.json()["data"]["authorization_code"]
    token = httpx.post(f"{base}/api/auth/native/token", timeout=5.0, trust_env=False,
                       json={"native_app_id": "partner_student_app",
                             "authorization_code": code, "code_verifier": VERIFIER})
    assert token.status_code == 200
    body = token.json()
    assert body["token_type"] == "bearer" and body["access_token"].startswith("edu_native_")
    assert body["user"]["user_id"] == "usr_001"


def test_authorization_code_is_single_use(base_url):
    base, key = base_url
    code = _native_codes(base, key).json()["data"]["authorization_code"]
    payload = {"native_app_id": "partner_student_app", "authorization_code": code,
               "code_verifier": VERIFIER}
    first = httpx.post(f"{base}/api/auth/native/token", json=payload, timeout=5.0, trust_env=False)
    replay = httpx.post(f"{base}/api/auth/native/token", json=payload, timeout=5.0, trust_env=False)
    assert first.status_code == 200 and replay.status_code == 401
    assert replay.json()["error"]["code"] == "NATIVE_AUTHORIZATION_CODE_CONSUMED"


def test_wrong_verifier_rejected(base_url):
    base, key = base_url
    code = _native_codes(base, key).json()["data"]["authorization_code"]
    response = httpx.post(f"{base}/api/auth/native/token", timeout=5.0, trust_env=False,
                          json={"native_app_id": "partner_student_app",
                                "authorization_code": code,
                                "code_verifier": "wrong-" + secrets.token_hex(16)})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "NATIVE_PKCE_INVALID"


# ---------- 幂等与错误码族 ----------

def test_native_codes_idempotency_same_key_same_body(base_url):
    base, key = base_url
    # 幂等指纹是 body 的 json.dumps(含 assertion),而 assertion 内嵌 int(time.time()) 的
    # iat/nbf/exp——两次现签会跨秒变体,指纹不同被误判 409(CI 实测 flaky)。固定断言
    # 才是本用例要测的"同键同体"。#113 P2 分支 CI 首次暴露。
    assertion = _assertion(key)
    first = _native_codes(base, key, idem="login-idem-1", assertion=assertion)
    second = _native_codes(base, key, idem="login-idem-1", assertion=assertion)
    assert first.status_code == 201 and second.status_code == 200  # 首发Created/重放OK
    assert second.json() == first.json()  # 同键同体 → 同一授权码载荷(#63 语义)


def test_native_codes_idempotency_conflict_on_other_body(base_url):
    base, key = base_url
    _native_codes(base, key, idem="login-idem-c")
    conflict = _native_codes(base, key, idem="login-idem-c", external_id="student-002")
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "SSO_IDEMPOTENCY_CONFLICT"


def test_native_codes_wrong_api_key_is_401(base_url):
    base, key = base_url
    response = _native_codes(base, key, api_key="wrong-" + secrets.token_hex(8))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "OPENAPI_UNAUTHORIZED"


# ---------- 路由可达(对话面不受身份路由影响;healthz 并入) ----------

def test_dialogue_routes_reachable_after_identity_wiring(base_url):
    base, _ = base_url
    opened = open_session(base)
    assert opened["first_question_ready"] is True
    healthz = httpx.get(f"{base}/healthz", timeout=5.0, trust_env=False)
    assert healthz.status_code == 200  # healthz 并入对话服务(8300 一个服务全包)


def open_session(base: str) -> dict:
    """本文件专属:该服务用随机 HMAC 密钥(与全库 TEST_TOKEN 不同源),须现签。"""
    response = httpx.post(f"{base}/api/prepared-questions/q-1/open", timeout=5.0, trust_env=False,
                          json={"idempotency_key": "idem-" + secrets.token_hex(4)},
                          headers={"Authorization": f"Bearer {signed_token(key=HMAC_KEY)}"})
    assert response.status_code == 200
    return response.json()
