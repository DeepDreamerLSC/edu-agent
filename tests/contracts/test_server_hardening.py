"""审查 P2 HTTP 三件套回归(#113):query string 路由、Content-Length 钳制、
请求头大小写不敏感。全部打本地 127.0.0.1 测试服务器,零真实模型。

三处均为 #113 实测复现的最小修复:
① 路由 regex `$` 锚定不剥 `?` → 带查询串请求全部 404/401;
② Content-Length 读前无上限(可 OOM)、非法值落 503 而非 400;
③ `dict(self.headers)` 固化请求头原始大小写 → 小写头误判 401。
"""

from __future__ import annotations

import http.client
import threading

import httpx

from edu_agent.api import IdentityService, build_server, build_service
from partner_api import ScriptedKernel, post
from auth_testing import TEST_TOKEN

_API_KEY = "test-api-key"
_NATIVE_APP = "partner_student_app"


def _serve(identity: IdentityService | None = None) -> tuple[str, object]:
    server = build_server(build_service(ScriptedKernel(["先看条件。"])), identity)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}", server


def _raw_post(base: str, path: str, headers: dict[str, str]) -> tuple[int, bytes]:
    """裸 http.client 发任意请求头(httpx 会规整/拒绝非法 Content-Length)。"""
    url = httpx.URL(base)
    conn = http.client.HTTPConnection(url.host, url.port, timeout=5.0)
    try:
        conn.putrequest("POST", path)
        for name, value in headers.items():
            conn.putheader(name, value)
        conn.endheaders()
        response = conn.getresponse()
        return response.status, response.read()
    finally:
        conn.close()


# ---------- ① query string 剥除 ----------


def test_query_string_healthz_still_200():
    base, server = _serve()
    try:
        response = httpx.get(f"{base}/healthz?foo=bar", timeout=5.0, trust_env=False)
        assert response.status_code == 200  # 修复前:healthz 锚定失配 → 401
    finally:
        server.shutdown()
        server.server_close()


def test_query_string_post_route_still_routes():
    base, server = _serve()
    try:
        response = post(base, "/api/conversations?foo=bar",
                        {"question_text": "小明有 12 本书,借出 5 本,还剩几本?",
                         "idempotency_key": "qs-001"})
        assert response.status_code == 201  # 修复前:`^/api/conversations$` 失配 → 404
        assert response.json()["first_question"]
    finally:
        server.shutdown()
        server.server_close()


def test_query_string_does_not_pollute_path_param():
    """带查询串的 GET 仍取到真 conversation_id(而非 "id?foo=bar" 查不到)。"""
    base, server = _serve()
    try:
        created = post(base, "/api/conversations",
                       {"question_text": "1+1 等于几?", "idempotency_key": "qs-002"})
        conversation_id = created.json()["conversation_id"]
        view = httpx.get(f"{base}/api/conversations/{conversation_id}?foo=bar",
                         headers={"Authorization": f"Bearer {TEST_TOKEN}"},
                         timeout=5.0, trust_env=False)
        assert view.status_code == 200
        assert view.json()["conversation_id"] == conversation_id
    finally:
        server.shutdown()
        server.server_close()


# ---------- ② Content-Length 钳制与 400 ----------


def test_non_integer_content_length_is_400():
    base, server = _serve()
    try:
        status, _ = _raw_post(base, "/api/conversations", {
            "Authorization": f"Bearer {TEST_TOKEN}", "Content-Length": "abc"})
        assert status == 400  # 修复前:int() 抛错落 503
    finally:
        server.shutdown()
        server.server_close()


def test_negative_content_length_is_400():
    base, server = _serve()
    try:
        status, _ = _raw_post(base, "/api/conversations", {
            "Authorization": f"Bearer {TEST_TOKEN}", "Content-Length": "-1"})
        assert status == 400  # 修复前:read(-1) 读到 EOF
    finally:
        server.shutdown()
        server.server_close()


# ---------- ③ 请求头大小写不敏感 ----------


def test_lowercase_auth_headers_are_read():
    """小写 authorization/idempotency-key 走通 API Key 与幂等键两道闸。

    修复前 `dict(self.headers)` 的键是原始小写 → 取 "Authorization" 得 None → 401。
    修复后两闸都过,停在 PKCE 校验(400 NATIVE_PKCE_INVALID)——证明两个头都按
    大小写不敏感读到。
    """
    base, server = _serve(IdentityService({"native_app_id": _NATIVE_APP, "api_key": _API_KEY}))
    try:
        response = httpx.post(f"{base}/api/openapi/v1/auth/native-codes",
                              headers={"authorization": f"Bearer {_API_KEY}",
                                       "idempotency-key": "login-001"},
                              json={"native_app_id": _NATIVE_APP},
                              timeout=5.0, trust_env=False)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "NATIVE_PKCE_INVALID"
    finally:
        server.shutdown()
        server.server_close()
