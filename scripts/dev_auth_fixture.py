#!/usr/bin/env python3
"""联调螺丝钉(身份端点):生成合法身份断言(RS256 JWT)+ PKCE 对。

密钥/签名用 cryptography 库(人批结构决策,与 identity 验签对偶);
RSA-1024 现场生成,联调专用非生产凭据。输出 n/e/d(hex)仅作调试展示。

用法:
  python scripts/dev_auth_fixture.py --native-app-id app --issuer iss --audience edu-agent \
      --external-student-id student-001 --kid partner-key-2026-01
  # 输出:IDENTITY_VERIFY_KEY_PEM、断言、PKCE 对、两个端点的请求体,可直接粘进 curl/Postman。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import time
import uuid

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def generate_key(bits: int = 1024):
    return rsa.generate_private_key(public_exponent=65537, key_size=bits)


def public_pem(private_key) -> str:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def sign_rs256(private_key, header: dict, payload: dict) -> str:
    signing = (_b64url(json_bytes(header)) + "." + _b64url(json_bytes(payload)))
    signature = private_key.sign(signing.encode(), padding.PKCS1v15(), hashes.SHA256())
    return signing + "." + _b64url(signature)


def json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode()


def pkce_pair() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(48))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-app-id", default="partner_student_app")
    parser.add_argument("--issuer", default="https://partner.example")
    parser.add_argument("--audience", default="edu-agent")
    parser.add_argument("--kid", default="partner-key-2026-01")
    parser.add_argument("--external-student-id", default="student-001")
    parser.add_argument("--external-tenant-id", default="partner-school-001")
    parser.add_argument("--display-name", default="张同学")
    parser.add_argument("--bits", type=int, default=1024)
    args = parser.parse_args()

    key = generate_key(args.bits)
    now = int(time.time())
    assertion = sign_rs256(
        key,
        {"alg": "RS256", "kid": args.kid, "typ": "JWT"},
        {"iss": args.issuer, "sub": args.external_student_id, "aud": args.audience,
         "iat": now, "nbf": now, "exp": now + 60, "jti": str(uuid.uuid4()),
         "external_tenant_id": args.external_tenant_id,
         "external_student_id": args.external_student_id,
         "role": "student", "display_name": args.display_name})
    verifier, challenge = pkce_pair()

    print("IDENTITY_VERIFY_KEY_PEM(环境变量值):")
    print(public_pem(key))
    print("\nnative-codes 请求头:")
    print("  Authorization: Bearer <IDENTITY_PARTNER_API_KEY>")
    print(f"  Idempotency-Key: dev-{uuid.uuid4()}")
    print("native-codes 请求体:")
    print(json.dumps({"assertion": assertion, "external_student_id": args.external_student_id,
                      "native_app_id": args.native_app_id, "code_challenge": challenge,
                      "code_challenge_method": "S256"}, ensure_ascii=False, indent=2))
    print("\ntoken 请求体(verifier 只在本输出出现一次):")
    print(json.dumps({"native_app_id": args.native_app_id,
                      "authorization_code": "<上一步响应的 authorization_code>",
                      "code_verifier": verifier}, ensure_ascii=False, indent=2))
    print("\nEXTERNAL_STUDENT_MAP 建议条目:")
    print(f"  {args.external_student_id}=<user_id>,{args.display_name},<tenant_id>")
    return 0


if __name__ == "__main__":
    main()
