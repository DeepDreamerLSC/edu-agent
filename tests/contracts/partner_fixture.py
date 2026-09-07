"""partner 侧测试模拟器(02 §6 tests/fixtures 同类):RSA 密钥对、断言签名、PKCE。

签名/密钥用 cryptography 库(人批结构决策,与 identity 验签对偶,审查 P2);
PKCS#1 v1.5 此处为 RS256 签名方案(JWT 标准,非加密场景);RSA-1024 测试强度,
现场生成,联调/测试专用非生产凭据。
"""

from __future__ import annotations

import base64
import hashlib
import json

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def generate_key(bits: int = 1024):
    """partner 私钥对象(RSA-1024 测试强度,现场生成)。"""
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


def pkce_challenge(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode()).digest())
