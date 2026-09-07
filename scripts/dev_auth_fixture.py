#!/usr/bin/env python3
"""联调螺丝钉(阶段 4/身份端点):生成合法身份断言(RS256 JWT)+ PKCE 对。

全 stdlib:RSA 密钥对用 Miller-Rabin 现场生成(测试/联调专用,不作生产凭据);
签名即 PKCS#1 v1.5 + SHA-256,与 edu_agent/api/identity.py 的验签互为镜像。

用法:
  python scripts/dev_auth_fixture.py --native-app-id app --issuer iss --audience edu-agent \
      --external-student-id student-001 --kid partner-key-2026-01
  # 输出:n/e/d(hex,配 IDENTITY_VERIFY_KEY_PEM 用环境变量口径)、断言、PKCE 对、
  #       两个端点的请求体(JSON),可直接粘进 curl/Postman。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import time
import uuid


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _der_len(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    raw = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(raw)]) + raw


def _der_int(value: int) -> bytes:
    raw = value.to_bytes((value.bit_length() + 7) // 8 or 1, "big")
    if raw[0] & 0x80:
        raw = b"\x00" + raw
    return bytes([0x02]) + _der_len(len(raw)) + raw


def _der_seq(*parts: bytes) -> bytes:
    body = b"".join(parts)
    return bytes([0x30]) + _der_len(len(body)) + body


def _is_prime(candidate: int) -> bool:
    if candidate < 2:
        return False
    for witness in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if candidate % witness == 0:
            return candidate == witness
    d, rounds = candidate - 1, 0
    while d % 2 == 0:
        d, rounds = d // 2, rounds + 1
    for _ in range(16):
        x = pow(secrets.randbelow(candidate - 3) + 2, d, candidate)
        if x in (1, candidate - 1):
            continue
        for _ in range(rounds - 1):
            x = pow(x, 2, candidate)
            if x == candidate - 1:
                break
        else:
            return False
    return True


def _prime(bits_count: int) -> int:
    while True:
        candidate = secrets.randbits(bits_count) | (1 << (bits_count - 1)) | 1
        if _is_prime(candidate):
            return candidate


def generate_rsa_key(bits: int = 1024) -> tuple[int, int, int]:
    """返回 (n, e, d)。Miller-Rabin 现场生成;联调专用强度与用途,不作生产凭据。"""
    half = bits // 2
    p = _prime(half)
    q = _prime(bits - half)
    while q == p:
        q = _prime(bits - half)
    e = 65537
    return p * q, e, pow(e, -1, (p - 1) * (q - 1))


def public_pem(n: int, e: int) -> str:
    """SubjectPublicKeyInfo PEM(标准 base64 字母表,与 identity 验签对偶)。"""
    rsa_key = _der_seq(_der_int(n), _der_int(e))
    algorithm = bytes.fromhex("300d06092a864886f70d0101010500")  # rsaEncryption
    spki = _der_seq(algorithm, bytes([0x03]) + _der_len(len(rsa_key) + 1) + b"\x00" + rsa_key)
    body = base64.b64encode(spki).decode()
    lines = [body[i:i + 64] for i in range(0, len(body), 64)]
    return "-----BEGIN PUBLIC KEY-----\n" + "\n".join(lines) + "\n-----END PUBLIC KEY-----\n"


def sign_rs256(header: dict, payload: dict, n: int, d: int) -> str:
    signing = (_b64url(json.dumps(header, separators=(",", ":")).encode()) + "."
               + _b64url(json.dumps(payload, separators=(",", ":")).encode()))
    digest = hashlib.sha256(signing.encode()).digest()
    k = (n.bit_length() + 7) // 8
    padded = b"\x00\x01" + b"\xff" * (k - len(digest) - 3) + b"\x00" + digest
    signature = pow(int.from_bytes(padded, "big"), d, n).to_bytes(k, "big")
    return signing + "." + _b64url(signature)


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

    n, e, d = generate_rsa_key(args.bits)
    now = int(time.time())
    assertion = sign_rs256(
        {"alg": "RS256", "kid": args.kid, "typ": "JWT"},
        {"iss": args.issuer, "sub": args.external_student_id, "aud": args.audience,
         "iat": now, "nbf": now, "exp": now + 60, "jti": str(uuid.uuid4()),
         "external_tenant_id": args.external_tenant_id,
         "external_student_id": args.external_student_id,
         "role": "student", "display_name": args.display_name},
        n, d)
    verifier, challenge = pkce_pair()

    print("IDENTITY_VERIFY_KEY_PEM(环境变量值,单行转义见下):")
    print(public_pem(n, e))
    print("PEM 单行(n 分隔符已含):见上;签名参数 hex:n={}\ne={}\nd={}".format(
        hex(n), hex(e), hex(d)))
    print("\nnative-codes 请求头:")
    print(f'  Authorization: Bearer <IDENTITY_PARTNER_API_KEY>')
    print(f'  Idempotency-Key: dev-{uuid.uuid4()}')
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
