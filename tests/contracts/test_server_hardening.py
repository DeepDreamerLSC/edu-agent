"""审查 P2 HTTP 三件套回归(#113):query string 路由、Content-Length 钳制、
请求头大小写不敏感。全部打本地 127.0.0.1 测试服务器,零真实模型。

三处均为 #113 实测复现的最小修复:
① 路由 regex `$` 锚定不剥 `?` → 带查询串请求全部 404/401;
② Content-Length 读前无上限(可 OOM)、非法值落 503 而非 400;
③ `dict(self.headers)` 固化请求头原始大小写 → 小写头误判 401。
"""

from __future__ import annotations

import http.client
import secrets

import httpx
import pytest

from edu_agent.api import IdentityService
from partner_api import ScriptedKernel, post
from auth_testing import TEST_TOKEN

_API_KEY = "test-" + secrets.token_hex(8)  # 运行时生成(测试假凭据,零字面量)
_NATIVE_APP = "partner_student_app"


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


def test_query_string_is_stripped_before_routing(serve):
    """query string 剥除族(① 三路由合一,断言等价):healthz GET 锚定、POST 建
    会话路由、GET 路径参数不被 ? 污染。修复前三处分别 401/404/查不到。"""
    base = serve(ScriptedKernel(["先看条件。"]))
    assert httpx.get(f"{base}/healthz?foo=bar", timeout=5.0, trust_env=False).status_code == 200
    created = post(base, "/api/conversations?foo=bar",
                   {"question_text": "小明有 12 本书,借出 5 本,还剩几本?",
                    "idempotency_key": "qs-001"})
    assert created.status_code == 201 and created.json()["first_question"]
    conversation_id = created.json()["conversation_id"]
    view = httpx.get(f"{base}/api/conversations/{conversation_id}?foo=bar",
                     headers={"Authorization": f"Bearer {TEST_TOKEN}"},
                     timeout=5.0, trust_env=False)
    assert view.status_code == 200
    assert view.json()["conversation_id"] == conversation_id


# ---------- ② Content-Length 钳制与 400 ----------

@pytest.mark.parametrize("content_length", [
    "abc",  # 修复前:int() 抛错落 503
    "-1",   # 修复前:read(-1) 读到 EOF
], ids=["test_non_integer_content_length_is_400", "test_negative_content_length_is_400"])
def test_malformed_content_length_is_400(serve, content_length):
    base = serve(ScriptedKernel(["先看条件。"]))
    status, _ = _raw_post(base, "/api/conversations", {
        "Authorization": f"Bearer {TEST_TOKEN}", "Content-Length": content_length})
    assert status == 400


# ---------- ③ 请求头大小写不敏感 ----------

def test_lowercase_auth_headers_are_read(serve):
    """小写 authorization/idempotency-key 走通 API Key 与幂等键两道闸。

    修复前 `dict(self.headers)` 的键是原始小写 → 取 "Authorization" 得 None → 401。
    修复后两闸都过,停在 PKCE 校验(400 NATIVE_PKCE_INVALID)——证明两个头都按
    大小写不敏感读到。
    """
    identity = IdentityService({"native_app_id": _NATIVE_APP, "api_key": _API_KEY})
    base = serve(ScriptedKernel(["先看条件。"]), identity=identity)
    response = httpx.post(f"{base}/api/openapi/v1/auth/native-codes",
                          headers={"authorization": f"Bearer {_API_KEY}",
                                   "idempotency-key": "login-001"},
                          json={"native_app_id": _NATIVE_APP},
                          timeout=5.0, trust_env=False)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "NATIVE_PKCE_INVALID"
