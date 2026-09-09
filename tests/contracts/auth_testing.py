"""鉴权测试助手(P1-1):固定测试 HMAC 密钥 + 真签 token,替换散落各文件的占位串。

密钥在模块导入即写入环境变量(IdentityService 在 build_server 时读 env),故所有
经 build_server 起的服务器都用同一 test 密钥,签发的 token 可验签通过。
TEST_TOKEN 无 exp(永不过期),供合同回放类测试稳定复现。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

TEST_HMAC_KEY = "test-hmac-key"
os.environ.setdefault("IDENTITY_TOKEN_HMAC_KEY", TEST_HMAC_KEY)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def signed_token(key: str = TEST_HMAC_KEY, **claims) -> str:
    """签发与 _hmac_token 同格式的 edu_native_<body>.<sig> 令牌。"""
    payload = {"account": "student1", "role": "student", **claims}
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64url(hmac.new(key.encode(), body.encode(), hashlib.sha256).digest())
    return f"edu_native_{body}.{signature}"


TEST_TOKEN = signed_token()