"""logout 吊销面合同(06 设计稿 #347 · PR-1;#106 真登出)。

验收清单(设计稿 §5 PR-1)逐条落测试:
- 登出后旧 token 全接口 401(对话 GET/POST + files PUT 三面);
- 双次登出均 200;无 token 登出 200(幂等空操作,零破坏);
- 按 jti 精确吊销:未登出的另一枚 token 不受牵连;
- 登出写入时顺手回收过期条目(名单存活期 = 剩余 TTL,不积累);
- EDU_AUTH_ENFORCE=0 熔断跳过吊销检查(联调语义不变,06 §4.3);
- 演示通道 token 带 jti,同样可吊销(06 §2.1 第 4 条)。

实现为纯内存名单(设计稿偏差,见 PR 描述):设计稿 §2.1 第 2 条的 SQLite
落盘 + 启动全量加载未实现——重启后吊销状态丢失,是**已接受的窗口**而非静默
缩水;触发条件(重启)与缓解(剩余 TTL ≤2h)都有限,落盘与 PR-2 迁移同批走。
"""

from __future__ import annotations

import base64
import json
import time

import httpx
import pytest
from auth_testing import TEST_TOKEN, signed_token
from partner_api import ScriptedKernel, get, post, serving

AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture
def base(serve):
    return serve(ScriptedKernel(["先看条件。"]))


def test_logout_revokes_token_on_all_surfaces(base):
    """登出后旧 token 三面全 401:对话 GET、对话 POST、files PUT。"""
    opened = post(base, "/api/prepared-questions/q-101/open",
                  {"idempotency_key": "k-revoke-1"}, status=200).json()
    conversation_id = opened["conversation"]["conversation_id"]
    assert post(base, "/api/auth/logout", {}, status=200).json() == {"ok": True}
    # 对话 GET(status)
    assert get(base, f"/api/conversations/{conversation_id}").status_code == 401
    # 对话 POST(messages)
    response = httpx.post(f"{base}/api/conversations/{conversation_id}/messages",
                          json={"content": "还在吗"}, headers=AUTH,
                          timeout=5.0, trust_env=False)
    assert response.status_code == 401
    # files PUT(二进制上传面)
    response = httpx.put(f"{base}/api/files/f_revoke/content", content=b"x",
                         headers=AUTH, timeout=5.0, trust_env=False)
    assert response.status_code == 401


def test_logout_idempotent_double_logout(base):
    """双次登出均 200 ok(第二次 = 名单已含该 jti 的幂等空操作)。"""
    assert post(base, "/api/auth/logout", {}, status=200).json() == {"ok": True}
    assert post(base, "/api/auth/logout", {}, status=200).json() == {"ok": True}
    assert get(base, "/api/conversations/conv_x").status_code == 401


def test_logout_without_or_bad_token_is_noop_ok(base):
    """缺头 / 验签失败的登出:200 ok:true,不动名单(真 token 仍有效)。"""
    # 缺头
    response = httpx.post(f"{base}/api/auth/logout", json={}, timeout=5.0, trust_env=False)
    assert response.status_code == 200 and response.json() == {"ok": True}
    # 假签
    response = httpx.post(f"{base}/api/auth/logout", json={},
                          headers={"Authorization": "Bearer whatever"},
                          timeout=5.0, trust_env=False)
    assert response.status_code == 200 and response.json() == {"ok": True}
    # 名单未被污染:真 token 仍过闸(404 = 已过鉴权闸)
    assert get(base, "/api/conversations/conv_x").status_code == 404


def test_revocation_is_per_jti_not_global(base):
    """A 登出不吊销 B:未登出的另一枚 token(jti 不同)不受牵连。"""
    assert post(base, "/api/auth/logout", {}, status=200).json() == {"ok": True}
    assert get(base, "/api/conversations/conv_x").status_code == 401
    assert get(base, "/api/conversations/conv_x",
               token=signed_token(jti="other-jti")).status_code == 404


def test_revoke_cleans_expired_entries_on_write():
    """登出写入时顺手回收过期条目(名单存活期 = 剩余 TTL,不积累)。"""
    from edu_agent.api import IdentityService

    service = IdentityService({"hmac_key": "k"})
    expired = signed_token(key="k", jti="jti-expired", exp=1)  # 1970 年已过期
    assert service.revoke(expired) is False  # 验签都不过:不入名单
    # 模拟「登出后时间流逝到过期」的名单条目,再登出一枚新 token:
    # 过期条目应被顺手清掉。观察面 = 名单本身(内部状态,白盒断言一条)。
    with service._revoke_lock:
        service._revoked["jti-stale"] = int(time.time()) - 10
    live = signed_token(key="k", jti="jti-live")
    assert service.revoke(live) is True
    with service._revoke_lock:
        assert "jti-stale" not in service._revoked  # 写时回收
        assert "jti-live" in service._revoked


def test_enforce_kill_switch_skips_revocation(monkeypatch):
    """EDU_AUTH_ENFORCE=0:跳过验签 = 跳过吊销(联调语义不变,06 §4.3)。"""
    monkeypatch.setenv("EDU_AUTH_ENFORCE", "0")
    with serving(ScriptedKernel(["先看条件。"])) as local:
        assert post(local, "/api/auth/logout", {}, status=200).json() == {"ok": True}
        # 熔断下 whatever 都过闸(404 即已过闸)——吊销检查同样被跳过
        assert get(local, "/api/conversations/conv_x", token="whatever").status_code == 404


def test_demo_channel_token_carries_jti_and_revocable(monkeypatch):
    """演示通道 payload 补 jti(06 §2.1 第 4 条):demo 登录 → 登出 → 401。"""
    monkeypatch.setenv("DEMO_ACCOUNT", "student1")
    monkeypatch.setenv("DEMO_PASSWORD", "night-pass-4f1a")
    monkeypatch.setenv("IDENTITY_TOKEN_HMAC_KEY", "demo-key-" + str(time.time()))
    with serving(ScriptedKernel(["先看条件。"])) as local:
        login = httpx.post(f"{local}/api/auth/login",
                           json={"account": "student1", "password": "night-pass-4f1a"},
                           timeout=5.0, trust_env=False)
        assert login.status_code == 200
        token = login.json()["access_token"]
        body = token.partition(".")[0][len("edu_native_"):]
        claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        assert claims.get("jti")  # payload 带 jti,否则演示 token 无法吊销
        assert get(local, "/api/conversations/conv_x", token=token).status_code == 404
        response = httpx.post(f"{local}/api/auth/logout", json={},
                              headers={"Authorization": f"Bearer {token}"},
                              timeout=5.0, trust_env=False)
        assert response.status_code == 200 and response.json() == {"ok": True}
        assert get(local, "/api/conversations/conv_x", token=token).status_code == 401
