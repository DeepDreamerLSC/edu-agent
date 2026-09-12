"""CORS 合同(老系统语义移植):白名单 echo Origin、预检 204、白名单外拒。

老系统 FastAPI CORSMiddleware 行为对齐:EDU_AGENT_CORS_ALLOWED_ORIGINS 逗号
分隔白名单;allow_credentials=False;非白名单预检 400。
请求走 partner_api 的 SSRF 边界守卫(只允许 127.0.0.1 本地测试服务器)。
"""

from __future__ import annotations

import httpx
import pytest
from partner_api import ScriptedKernel, _assert_local_base, serving


@pytest.fixture
def base(monkeypatch):
    # CORS 白名单在 build_server 时读 env,须在 serving 之前注入
    monkeypatch.setenv("EDU_AGENT_CORS_ALLOWED_ORIGINS",
                       "https://school.k12m.cn,http://localhost:8888")
    with serving(ScriptedKernel([])) as url:
        yield url


def options(base: str, path: str, origin: str) -> httpx.Response:
    """OPTIONS 预检形态;SSRF 边界守卫与 post() 同款(partner_api)。"""
    _assert_local_base(base)
    return httpx.options(f"{base}{path}", headers={"Origin": origin},
                         timeout=5.0, trust_env=False)


def get(base: str, path: str, origin: str | None = None) -> httpx.Response:
    """GET 形态;SSRF 边界守卫与 post() 同款(partner_api)。"""
    _assert_local_base(base)
    headers = {"Origin": origin} if origin else {}
    return httpx.get(f"{base}{path}", headers=headers, timeout=5.0, trust_env=False)


def test_preflight_allowed_origin_gets_204_and_headers(base):
    response = options(base, "/api/conversations", "https://school.k12m.cn")
    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == "https://school.k12m.cn"
    assert response.headers["Access-Control-Allow-Methods"] == "*"


def test_preflight_disallowed_origin_is_rejected(base):
    response = options(base, "/api/conversations", "https://evil.example")
    assert response.status_code == 400
    assert "Access-Control-Allow-Origin" not in response.headers


def test_normal_response_carries_cors_header_for_allowed_origin(base):
    response = get(base, "/healthz", "http://localhost:8888")
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:8888"


def test_same_site_request_without_origin_gets_no_cors_header(base):
    """无 Origin(同源/非浏览器客户端)不加 CORS 头——非浏览器路径零影响。"""
    response = get(base, "/healthz")
    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response.headers
