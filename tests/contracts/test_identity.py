"""身份端点合同(00 §5.2、partner-sso.md):PKCE 全舞步 + 样例回放 + 错误码族。

fixtures 内嵌 RSA-1024 测试密钥对(现场生成,联调专用非生产凭据);
断言格式照 partner-sso.md §4.2/#48 快照样例字段,不发明。
凭据全部运行时生成,无字面量(Mimosa 判例)。
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading

import pytest

from edu_agent.api import IdentityError, IdentityService
from partner_fixture import public_pem, sign_rs256

API_KEY = "test-" + secrets.token_hex(8)
HMAC_KEY = "test-" + secrets.token_hex(8)
CONFIG = {
    "native_app_id": "partner_student_app",
    "api_key": API_KEY,
    "kid": "partner-key-2026-01",
    "issuer": "https://partner.example",
    "audience": "edu-agent",
    "hmac_key": HMAC_KEY,
    "students": {"student-001": {"user_id": "usr_001", "display_name": "张同学",
                                 "tenant_id": "school_001"}},
}


@pytest.fixture
def key_pair() -> tuple[str, object]:
    """(验签用 PEM, 签名用私钥对象)。"""
    from partner_fixture import generate_key, public_pem
    key = generate_key(1024)
    return public_pem(key), key


def make_service(key_pem: str) -> IdentityService:
    return IdentityService(dict(CONFIG, verify_key_pem=key_pem))


def assertion(private_key, **overrides) -> str:
    import time
    external_id = overrides.get("external_id", "student-001")
    expired = overrides.get("expired", False)
    stamp = (overrides.get("now") or int(time.time())) - (3600 if expired else 0)
    return sign_rs256(
        private_key,
        {"alg": "RS256", "kid": overrides.get("kid", "partner-key-2026-01"), "typ": "JWT"},
        {"iss": overrides.get("issuer", "https://partner.example"), "sub": external_id,
         "aud": overrides.get("audience", "edu-agent"), "iat": stamp,
         "nbf": stamp, "exp": stamp + 60, "jti": "jti-" + external_id + str(stamp),
         "external_tenant_id": "partner-school-001", "external_student_id": external_id,
         "role": "student", "display_name": "张同学"})


def code_request(private_key, **overrides) -> tuple[dict, dict]:
    claim_overrides = {k: overrides[k] for k in
                       ("external_id", "expired", "audience", "issuer", "kid") if k in overrides}
    body = {
        "assertion": overrides.get("assertion_override")
        or assertion(private_key, **claim_overrides),
        "external_student_id": overrides.get("external_student_id", "student-001"),
        "native_app_id": overrides.get("native_app_id", "partner_student_app"),
        "code_challenge": overrides.get(
            "code_challenge",
            base64.urlsafe_b64encode(hashlib.sha256(b"v" * 48).digest()).rstrip(b"=").decode()),
        "code_challenge_method": "S256",
    }
    headers = {"Authorization": f"Bearer {overrides.get('api_key', API_KEY)}",
               "Idempotency-Key": overrides.get("idempotency_key", "dev-key-0001")}
    return body, headers


def partner_challenge(verifier: str) -> str:
    from partner_fixture import pkce_challenge
    return pkce_challenge(verifier)


def test_pkce_full_dance(key_pair):
    """样例回放(#48/postman 字段):断言+challenge → 201 code → verifier → 200 token。"""
    pem, private_key = key_pair
    service = make_service(pem)
    verifier = base64.urlsafe_b64encode(hashlib.sha256(b"the-verifier").digest()).rstrip(b"=").decode()
    body, headers = code_request(private_key, code_challenge=partner_challenge(verifier))
    status, payload = service.native_code(body, headers)
    assert status == 201
    data = payload["data"]
    assert data["schema_version"] == "native_authorization_code/v1"
    assert data["authorization_code"].startswith("edu_ncode_")
    assert data["expires_in"] == 90

    status, token = service.native_token({
        "native_app_id": "partner_student_app",
        "authorization_code": data["authorization_code"],
        "code_verifier": verifier,
    })
    assert status == 200
    assert token["token_type"] == "bearer" and token["access_token"].startswith("edu_native_")
    assert token["user"] == {"user_id": "usr_001", "role": "student",
                             "display_name": "张同学", "tenant_id": "school_001"}


def test_pkce_wrong_verifier_rejected_then_code_still_valid(key_pair):
    pem, private_key = key_pair
    service = make_service(pem)
    verifier = base64.urlsafe_b64encode(hashlib.sha256(b"right").digest()).rstrip(b"=").decode()
    body, headers = code_request(private_key, code_challenge=partner_challenge(verifier))
    _, payload = service.native_code(body, headers)
    code = payload["data"]["authorization_code"]
    with pytest.raises(IdentityError) as excinfo:
        service.native_token({"native_app_id": "partner_student_app",
                              "authorization_code": code, "code_verifier": "w" * 48})
    assert (excinfo.value.status_code, excinfo.value.code) == (400, "NATIVE_PKCE_INVALID")
    # 错 verifier 不消费授权码:正确 verifier 仍可兑换
    _, token = service.native_token({"native_app_id": "partner_student_app",
                                     "authorization_code": code, "code_verifier": verifier})
    assert token["access_token"]


def test_code_single_use_and_expiry(key_pair):
    pem, private_key = key_pair
    service = make_service(pem)
    verifier = base64.urlsafe_b64encode(hashlib.sha256(b"v").digest()).rstrip(b"=").decode()
    body, headers = code_request(private_key, code_challenge=partner_challenge(verifier))
    _, payload = service.native_code(body, headers)
    code = payload["data"]["authorization_code"]
    token_body = {"native_app_id": "partner_student_app", "authorization_code": code,
                  "code_verifier": verifier}
    service.native_token(token_body)
    with pytest.raises(IdentityError) as consumed:
        service.native_token(token_body)
    assert (consumed.value.status_code, consumed.value.code) == \
        (401, "NATIVE_AUTHORIZATION_CODE_CONSUMED")

    # 过期:直接向服务注入一条已过期的码
    service.codes["edu_ncode_expired"] = {
        "student": CONFIG["students"]["student-001"],
        "challenge": partner_challenge(verifier), "expires": 1, "consumed": False}
    with pytest.raises(IdentityError) as expired:
        service.native_token({"native_app_id": "partner_student_app",
                              "authorization_code": "edu_ncode_expired",
                              "code_verifier": verifier})
    assert (expired.value.status_code, expired.value.code) == \
        (401, "NATIVE_AUTHORIZATION_CODE_EXPIRED")


def test_code_concurrent_consume_only_one_succeeds(key_pair):
    """P1-3 回归:同码并发兑换,"单次消费"必须只有一个线程成功
    (无锁时 consumed 检查与置位之间的 check-then-act 窗口会双发 token)。"""
    pem, private_key = key_pair
    service = make_service(pem)
    verifier = base64.urlsafe_b64encode(hashlib.sha256(b"c").digest()).rstrip(b"=").decode()
    body, headers = code_request(private_key, code_challenge=partner_challenge(verifier))
    _, payload = service.native_code(body, headers)
    token_body = {"native_app_id": "partner_student_app",
                  "authorization_code": payload["data"]["authorization_code"],
                  "code_verifier": verifier}

    results: list[tuple[str, int]] = []
    barrier = threading.Barrier(20)

    def redeem() -> None:
        barrier.wait()
        try:
            status, _ = service.native_token(token_body)
            results.append(("ok", status))
        except IdentityError as error:
            results.append(("err", error.status_code))

    threads = [threading.Thread(target=redeem) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert [r for r in results if r[0] == "ok"] == [("ok", 200)]
    assert sum(1 for r in results if r == ("err", 401)) == 19


def test_assertion_errors_follow_contract(key_pair):
    pem, private_key = key_pair
    service = make_service(pem)
    for overrides in (
        {"expired": True},                     # 断言过期
        {"kid": "someone-else"},               # 未登记的 kid
        {"audience": "other"},                 # 受众不符
    ):
        body, headers = code_request(private_key, **overrides)
        with pytest.raises(IdentityError) as excinfo:
            service.native_code(body, headers)
        assert (excinfo.value.status_code, excinfo.value.code) == (401, "NATIVE_IDENTITY_INVALID")

    tampered = assertion(private_key)[:-6] + "AAAAAA"  # 篡改签名
    body, headers = code_request(private_key, assertion_override=tampered)
    with pytest.raises(IdentityError) as excinfo:
        service.native_code(body, headers)
    assert excinfo.value.code == "NATIVE_IDENTITY_INVALID"

    unknown = assertion(private_key, external_id="student-404")
    body, headers = code_request(private_key, assertion_override=unknown,
                                 external_student_id="student-404")
    with pytest.raises(IdentityError) as excinfo:
        service.native_code(body, headers)
    assert excinfo.value.code == "NATIVE_IDENTITY_INVALID"  # 映射不存在 fail closed


def test_idempotency_same_key_replays_and_conflicts(key_pair):
    pem, private_key = key_pair
    service = make_service(pem)
    body, headers = code_request(private_key)
    status, payload = service.native_code(body, headers)
    assert status == 201
    # 同键同参:返回仍有效的原授权码合同
    replay_status, replay = service.native_code(body, headers)
    assert (replay_status, replay["data"]["authorization_code"]) == \
        (200, payload["data"]["authorization_code"])
    # 同键异参:409
    body2, headers2 = code_request(private_key, idempotency_key=headers["Idempotency-Key"])
    body2["code_challenge"] = "a" * 43
    with pytest.raises(IdentityError) as excinfo:
        service.native_code(body2, headers2)
    assert (excinfo.value.status_code, excinfo.value.code) == \
        (409, "SSO_IDEMPOTENCY_CONFLICT")


def test_error_family_follows_contract(key_pair):
    pem, private_key = key_pair
    service = make_service(pem)
    body, headers = code_request(private_key, api_key="also-" + secrets.token_hex(8))
    with pytest.raises(IdentityError) as unauthorized:
        service.native_code(body, headers)
    assert (unauthorized.value.status_code, unauthorized.value.code) == \
        (401, "OPENAPI_UNAUTHORIZED")

    body, headers = code_request(private_key, native_app_id="unknown_app")
    with pytest.raises(IdentityError) as forbidden:
        service.native_code(body, headers)
    assert (forbidden.value.status_code, forbidden.value.code) == \
        (403, "NATIVE_APP_INVALID")

    body, headers = code_request(private_key, code_challenge="short")
    with pytest.raises(IdentityError) as pkce:
        service.native_code(body, headers)
    assert (pkce.value.status_code, pkce.value.code) == (400, "NATIVE_PKCE_INVALID")
