"""原生联合登录身份端点(00 §5.2、ADR-0004):合同来源 edu_agent/contracts/partner-sso.md。

全 stdlib 全内存;单 native_app 环境变量注册(验签公钥只进环境变量,不进库);
授权码单次消费+TTL;PKCE S256 常数时间比较;access_token HMAC 签发;
EXTERNAL_STUDENT_MAP 环境变量条目映射外部学生(扩容=加行)。失败路径错误码
与文案保持合同原文。v1 只支持单合作方。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key

CODE_TTL_S = 90  # partner-sso.md §3:授权码默认 90 秒,只能消费一次
TOKEN_TTL_S = 7200  # 访问令牌默认两小时,首版无刷新令牌
_VERIFIER_RE = re.compile(r"^[A-Za-z0-9\-._~]{43,128}$")
_CHALLENGE_RE = re.compile(r"^[A-Za-z0-9\-_]{43}$")


class IdentityError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.status_code = status_code
        self.code = code
        self.message = message


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())


def load_student_map(raw: str) -> dict[str, dict]:
    """EXTERNAL_STUDENT_MAP:external_id=user_id,display_name,tenant_id;…(扩容=加行)。"""
    students = {}
    for entry in filter(None, raw.split(";")):
        external_id, fields = entry.split("=", 1)
        user_id, display_name, tenant_id = (fields.split(",") + ["", ""])[:3]
        students[external_id.strip()] = {"user_id": user_id.strip(),
                                         "display_name": display_name.strip(),
                                         "tenant_id": tenant_id.strip()}
    return students


def _rs256_verify(pem: str, signed: bytes, signature: bytes) -> bool:
    """RS256(PKCS#1 v1.5 + SHA-256)验签(cryptography 库;人批结构决策,审查 P2)。"""
    try:
        load_pem_public_key(pem.encode()).verify(
            signature, signed, padding.PKCS1v15(), hashes.SHA256())
        return True
    except (InvalidSignature, ValueError):
        return False


def _decode_jwt(token: str, pem: str, kid: str, issuer: str, audience: str,
                now: int) -> dict:
    header_b64, payload_b64, signature_b64 = token.split(".")
    header = json.loads(_b64url_decode(header_b64))
    if header.get("alg") != "RS256" or header.get("kid") != kid:
        raise IdentityError(401, "NATIVE_IDENTITY_INVALID", "断言签名头不符合登记配置")
    if not _rs256_verify(pem, f"{header_b64}.{payload_b64}".encode(),
                         _b64url_decode(signature_b64)):
        raise IdentityError(401, "NATIVE_IDENTITY_INVALID", "断言签名验证失败")
    claims = json.loads(_b64url_decode(payload_b64))
    if (claims.get("iss") != issuer or claims.get("aud") != audience
            or claims.get("role") != "student"):
        raise IdentityError(401, "NATIVE_IDENTITY_INVALID", "断言身份字段不符合约定")
    if not all(isinstance(claims.get(k), int) for k in ("iat", "nbf", "exp")):
        raise IdentityError(401, "NATIVE_IDENTITY_INVALID", "断言时间字段缺失或非法")
    if now < claims["nbf"] or now > claims["exp"] or claims["exp"] <= claims["iat"]:
        raise IdentityError(401, "NATIVE_IDENTITY_INVALID", "断言已过期或尚未生效")
    if not claims.get("jti") or not claims.get("sub"):
        raise IdentityError(401, "NATIVE_IDENTITY_INVALID", "断言缺少 sub/jti")
    return claims


def _hmac_token(payload: dict, key: str) -> str:
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64url(hmac.new(key.encode(), body.encode(), hashlib.sha256).digest())
    return f"edu_native_{body}.{signature}"


DEMO_ACCOUNT_DEFAULT = "student1"
DEMO_LOGIN_TTL_S = 7200  # 演示登录与业务 token 同两小时口径


def demo_login(account: str, password: str, hmac_key: str,
               now: int | None = None) -> dict:
    """演示登录(DEMO_ACCOUNT/DEMO_PASSWORD 环境变量比对):账密对 → HMAC access_token。

    凭据只从环境变量读(缺省 account=student1;密码无 env 时不启用登录);
    演示用途,非合作方 PKCE 通道。失败语义照 #74 错误表:401 USER_LOGIN_FAILED。
    签名密钥 hmac_key 走 IDENTITY_TOKEN_HMAC_KEY(专职密钥),不得用演示密码
    充当(审查 P2:低熵密钥反模式+换密码作废 token)。
    """
    expected_account = os.environ.get("DEMO_ACCOUNT", DEMO_ACCOUNT_DEFAULT)
    expected_password = os.environ.get("DEMO_PASSWORD", "")
    account_ok = _constant_time_equals(account or "", expected_account)
    password_ok = bool(expected_password) and _constant_time_equals(password or "",
                                                                   expected_password)
    if not (account_ok and password_ok):
        raise IdentityError(401, "USER_LOGIN_FAILED", "账号或密码不正确")
    issued = now if now is not None else int(time.time())
    token = _hmac_token({"account": expected_account, "role": "student",
                         "exp": issued + DEMO_LOGIN_TTL_S}, hmac_key)
    return {"access_token": token, "token_type": "bearer",
            "expires_in": DEMO_LOGIN_TTL_S,
            "expires_at": datetime.fromtimestamp(issued + DEMO_LOGIN_TTL_S,
                                                 timezone.utc)
            .isoformat().replace("+00:00", "Z"),
            "user": {"user_id": expected_account, "role": "student"}}


class IdentityService:
    """单 native_app 的授权码与令牌签发;全内存,进程重启即失效(v1 语义)。"""

    def demo_login_body(self, body: dict) -> tuple[int, dict]:
        """HTTP 形态演示登录:{account, password} → 200 token / 401 USER_LOGIN_FAILED。

        签名密钥走 IDENTITY_TOKEN_HMAC_KEY 专职密钥(审查 P2:演示密码低熵,
        不得充当 HMAC 签名密钥);密钥未配置即 fail closed。
        """
        if not self.config["hmac_key"]:
            raise IdentityError(503, None, "IDENTITY_TOKEN_HMAC_KEY 未配置")
        payload = demo_login(str(body.get("account", "")), str(body.get("password", "")),
                             hmac_key=self.config["hmac_key"])
        return 200, payload

    def __init__(self, config: dict | None = None) -> None:
        env = os.environ
        self.config = config or {
            "native_app_id": env.get("IDENTITY_NATIVE_APP_ID", ""),
            "api_key": env.get("IDENTITY_PARTNER_API_KEY", ""),
            "verify_key_pem": env.get("IDENTITY_VERIFY_KEY_PEM", ""),
            "kid": env.get("IDENTITY_KID", ""),
            "issuer": env.get("IDENTITY_ISSUER", ""),
            "audience": env.get("IDENTITY_AUDIENCE", ""),
            "hmac_key": env.get("IDENTITY_TOKEN_HMAC_KEY", ""),
            "students": load_student_map(env.get("EXTERNAL_STUDENT_MAP", "")),
        }
        self.codes: dict[str, dict] = {}
        self.idempotency: dict[str, tuple[str, dict]] = {}

    def native_code(self, body: dict, headers: dict, now: int | None = None) -> tuple[int, dict]:
        """POST /api/openapi/v1/auth/native-codes:断言+PKCE challenge → 一次性授权码。"""
        api_key = headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not api_key or not _constant_time_equals(api_key, self.config["api_key"]):
            raise IdentityError(401, "OPENAPI_UNAUTHORIZED", "API Key 缺失、无效或已撤销")
        if body.get("native_app_id") != self.config["native_app_id"]:
            raise IdentityError(403, "NATIVE_APP_INVALID",
                                "native_app_id 未登记、已停用或不属于当前合作方")
        idempotency_key = headers.get("Idempotency-Key", "")
        if not 8 <= len(idempotency_key) <= 256:
            raise IdentityError(401, "OPENAPI_UNAUTHORIZED", "Idempotency-Key 长度 8 至 256")
        fingerprint = json.dumps(body, sort_keys=True, ensure_ascii=False)
        if idempotency_key in self.idempotency:
            seen_fingerprint, payload = self.idempotency[idempotency_key]
            if not _constant_time_equals(seen_fingerprint, fingerprint):
                raise IdentityError(409, "SSO_IDEMPOTENCY_CONFLICT",
                                    "幂等键已用于其他登录交换")
            return 200, payload

        challenge = str(body.get("code_challenge", ""))
        if (body.get("code_challenge_method") != "S256"
                or not _CHALLENGE_RE.fullmatch(challenge)):
            raise IdentityError(400, "NATIVE_PKCE_INVALID", "丢弃本次 PKCE,重新生成并申请授权码")
        external_id = str(body.get("external_student_id", ""))
        claims = _decode_jwt(str(body.get("assertion", "")), self.config["verify_key_pem"],
                             self.config["kid"], self.config["issuer"],
                             self.config["audience"],
                             now if now is not None else int(time.time()))
        if not _constant_time_equals(str(claims.get("external_student_id", "")), external_id):
            raise IdentityError(401, "NATIVE_IDENTITY_INVALID",
                                "external_student_id 与断言签名 Claim 不一致")
        student = self.config["students"].get(external_id)
        if student is None:
            raise IdentityError(401, "NATIVE_IDENTITY_INVALID",
                                "外部学生映射不存在或已停用")

        code = f"edu_ncode_{uuid.uuid4().hex}"
        issued = _epoch(now)
        payload = {"data": {"schema_version": "native_authorization_code/v1",
                            "authorization_code": code, "expires_in": CODE_TTL_S,
                            "expires_at": _iso(issued + CODE_TTL_S)}}
        self.codes[code] = {"student": student, "challenge": challenge,
                            "expires": issued + CODE_TTL_S, "consumed": False}
        self.idempotency[idempotency_key] = (fingerprint, payload)
        return 201, payload

    def native_token(self, body: dict, now: int | None = None) -> tuple[int, dict]:
        """POST /api/auth/native/token:授权码+code_verifier → 短期访问令牌。"""
        current = _epoch(now)
        code = str(body.get("authorization_code", ""))
        record = self.codes.get(code)
        if record is None:
            raise IdentityError(401, "NATIVE_AUTHORIZATION_CODE_INVALID", "重新申请授权码")
        if record["consumed"]:
            raise IdentityError(401, "NATIVE_AUTHORIZATION_CODE_CONSUMED",
                                "不重放旧码,重新申请授权码")
        if current > record["expires"]:
            raise IdentityError(401, "NATIVE_AUTHORIZATION_CODE_EXPIRED", "重新申请授权码")
        verifier = str(body.get("code_verifier", ""))
        if not _VERIFIER_RE.fullmatch(verifier) or not _constant_time_equals(
                _b64url(hashlib.sha256(verifier.encode()).digest()), record["challenge"]):
            raise IdentityError(400, "NATIVE_PKCE_INVALID", "丢弃本次 PKCE,重新生成并申请授权码")
        record["consumed"] = True  # 授权码消费与会话创建同一原子操作
        student = record["student"]
        expires = current + TOKEN_TTL_S
        token = _hmac_token({"user_id": student["user_id"], "tenant_id": student["tenant_id"],
                             "role": "student", "exp": expires, "jti": uuid.uuid4().hex},
                            self.config["hmac_key"])
        return 200, {
            "access_token": token, "token_type": "bearer", "expires_in": TOKEN_TTL_S,
            "expires_at": _iso(current + TOKEN_TTL_S),
            "user": {"user_id": student["user_id"], "role": "student",
                     "display_name": student["display_name"],
                     "tenant_id": student["tenant_id"]},
        }


def _epoch(now: int | None) -> int:
    return now if now is not None else int(time.time())


def _iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")
