"""CORS 合同(老系统语义移植):白名单 echo Origin、预检 204、白名单外拒。

老系统 FastAPI CORSMiddleware 行为对齐:EDU_AGENT_CORS_ALLOWED_ORIGINS 逗号
分隔白名单;allow_credentials=False;非白名单预检 400。
请求走 partner_api 的 SSRF 边界守卫(只允许 127.0.0.1 本地测试服务器)。
"""

from __future__ import annotations

import httpx
import pytest
from partner_api import ScriptedKernel, _assert_local_base


@pytest.fixture
def base(serve, monkeypatch):
    # CORS 白名单在 build_server 时读 env,须在 serving 之前注入
    monkeypatch.setenv("EDU_AGENT_CORS_ALLOWED_ORIGINS",
                       "https://school.k12m.cn,http://localhost:8888")
    return serve(ScriptedKernel([]))


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


# ---------- #103 归一化(老系统 _normalize_cors_origin 同款,双侧先归一再比对) ----------


def test_preflight_hash_route_whitelist_entry_is_normalized(monkeypatch, serve):
    """#103 红灯复现:白名单配 hash 路由(老系统 partner 用值)→ 归一化成裸 origin
    命中;旧精确匹配下这里是 400 静默失效(CORS 全挂、服务端零线索)。"""
    monkeypatch.setenv("EDU_AGENT_CORS_ALLOWED_ORIGINS", "https://school.k12m.cn/test/#/")
    url = serve(ScriptedKernel([]))
    response = options(url, "/api/conversations", "https://school.k12m.cn")
    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == "https://school.k12m.cn"


def test_preflight_case_and_trailing_slash_whitelist_is_normalized(monkeypatch, serve):
    """白名单大小写/尾斜杠不规范(老系统会静默归一化掉的形态)→ 同样命中。"""
    monkeypatch.setenv("EDU_AGENT_CORS_ALLOWED_ORIGINS",
                       "HTTPS://School.K12M.CN/,http://localhost:8888/")
    url = serve(ScriptedKernel([]))
    for origin in ("https://school.k12m.cn", "http://localhost:8888"):
        response = options(url, "/api/conversations", origin)
        assert response.status_code == 204, origin
        assert response.headers["Access-Control-Allow-Origin"] == origin, origin


@pytest.mark.parametrize("whitelist,origin,expected_status,expected_echo", [
    # 双侧归一化:Origin 侧带 path/hash(非浏览器形态)也按裸 origin 比对(echo=归一化值)
    ("https://school.k12m.cn", "https://school.k12m.cn/x#/y", 204, "https://school.k12m.cn"),
    # `*` 维持有意丢弃(#103 P3):通配条目不因归一化意外复活
    ("*", "https://school.k12m.cn", 400, None),
    # 归一化只放宽书写形态,不放宽白名单判定:不同 host 仍 400
    ("https://school.k12m.cn/test/#/", "https://evil.example", 400, None),
    # #228 审查 P3:显式默认端口白名单(:443)vs 浏览器裸 Origin(浏览器永不发默认端口)
    ("https://school.k12m.cn:443", "https://school.k12m.cn", 204, "https://school.k12m.cn"),
    # 剥端口只剥默认值:非默认端口(:8888)是不同 origin,裸形态不得放行
    ("http://localhost:8888", "http://localhost", 400, None),
], ids=["origin_side_normalized", "wildcard_stays_rejected",
        "different_host_still_rejected", "default_port_whitelist_matches",
        "non_default_port_stays_distinct"])
def test_cors_normalization_matrix(monkeypatch, serve, whitelist, origin,
                                   expected_status, expected_echo):
    """#103/#228 归一化判定矩阵(五场景合一):白名单书写形态先归一再比对,
    只放宽书写、不放宽判定。断言与拆分前逐条等价(echo=归一化后的 origin)。"""
    monkeypatch.setenv("EDU_AGENT_CORS_ALLOWED_ORIGINS", whitelist)
    url = serve(ScriptedKernel([]))
    response = options(url, "/api/conversations", origin)
    assert response.status_code == expected_status, origin
    if expected_echo is None:
        assert "Access-Control-Allow-Origin" not in response.headers
    else:
        assert response.headers["Access-Control-Allow-Origin"] == expected_echo
