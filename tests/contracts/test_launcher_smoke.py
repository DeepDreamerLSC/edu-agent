"""启动器冒烟(#72 P1 回归钉):env 配置下经启动器 build() 装配,身份面必须返回
结构化鉴权错误(非 503/KeyError)——封堵「测试注入正确 config、启动器接错 env」
的缝隙。进程内起线程(零命令注入面),零真实模型。"""

from __future__ import annotations

import secrets
import sys
import threading
from pathlib import Path

import httpx
import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import serve_partner_api  # noqa: E402
from auth_testing import signed_token


def test_launcher_smoke_identity_wiring(monkeypatch):
    """P1 回归:启动器经 env→config 转换构造身份服务;鉴权层返回结构化 401。"""
    monkeypatch.setenv("EDU_PARTNER_API_PORT", "0")  # 随机端口,不碰部署位
    monkeypatch.setenv("IDENTITY_NATIVE_APP_ID", "smoke_student_app")
    monkeypatch.setenv("IDENTITY_PARTNER_API_KEY", "smoke-" + secrets.token_hex(8))
    smoke_key = "smoke-" + secrets.token_hex(8)
    monkeypatch.setenv("IDENTITY_TOKEN_HMAC_KEY", smoke_key)
    monkeypatch.setenv("IDENTITY_KID", "smoke-key")
    monkeypatch.setenv("IDENTITY_ISSUER", "https://smoke.example")
    monkeypatch.setenv("IDENTITY_AUDIENCE", "edu-agent")
    monkeypatch.setenv("IDENTITY_VERIFY_KEY_PEM", "")  # 缺 API Key 在验签前就被 401 挡下
    monkeypatch.setenv("EXTERNAL_STUDENT_MAP", "")
    server = serve_partner_api.build()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        healthz = httpx.get(f"{base}/healthz", timeout=2.0, trust_env=False)
        assert healthz.status_code == 200  # 服务就绪
        # 鉴权层工作的证据:缺 API Key → 身份层自己的 401 信封(带码),
        # 而非配置转换被绕过时的 KeyError→503(#72 P1 的症状)
        response = httpx.post(f"{base}/api/openapi/v1/auth/native-codes",
                              json={"assertion": "x"}, timeout=2.0, trust_env=False)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "OPENAPI_UNAUTHORIZED"
        # 对话面亦在线(真内核经注入;回合语义由 #55/#74 合同测试覆盖)
        dialogue = httpx.post(f"{base}/api/conversations/none/messages",
                              json={"content": "x"}, timeout=2.0, trust_env=False,
                              headers={"Authorization": f"Bearer {signed_token(key=smoke_key)}"})
        assert dialogue.status_code == 404  # 会话不存在 → 路由与存储层在线
    finally:
        server.shutdown()
        thread.join(timeout=5)
