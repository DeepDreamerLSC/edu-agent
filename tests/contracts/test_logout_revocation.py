"""logout 吊销面合同(06 设计稿 #347 · PR-1;#106 真登出)。

验收清单(设计稿 §5 PR-1)逐条落测试:
- 登出后旧 token 全接口 401(对话 GET/POST + files PUT 三面);
- 双次登出均 200;无 token 登出 200(幂等空操作,零破坏);
- 按 jti 精确吊销:未登出的另一枚 token 不受牵连;
- 登出写入时顺手回收过期条目(名单存活期 = 剩余 TTL,不积累);
- EDU_AUTH_ENFORCE=0 熔断跳过吊销检查(联调语义不变,06 §4.3);
- 演示通道 token 带 jti,同样可吊销(06 §2.1 第 4 条);
- 吊销面 SQLite 落盘 + 启动全量加载(06 §2.1 第 2 条):重启后吊销仍生效
  (§4.4「重启不复活已登出 token」;终审 #400 裁定的安全回归项已闭环)。
"""

from __future__ import annotations

import base64
import json
import time

import httpx
import pytest
from auth_testing import TEST_TOKEN, signed_token
from edu_agent.api import IdentityService
from edu_agent.store import SqliteStore
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


# ---------- SQLite 落盘(06 §2.1 第 2 条;终审 #400 裁定的安全回归项) ----------

def test_revocation_survives_identity_restart(tmp_path):
    """P1 核心验收:吊销 → 重启(identity 重建、库文件同一路径)→ 旧 token 仍 401。

    重启复现方式 = 同库文件再开一个 SqliteStore + IdentityService(进程重启的
    可测等价物:内存名单清零,只有库文件还在——与 test_sqlite_store 的重启
    复现同款)。另一枚未吊销 token 不受牵连(名单精确重放,非全量拉黑)。
    """
    db = SqliteStore(tmp_path / "edu-agent.db")
    revoked = signed_token(jti="jti-restart")
    survivor = signed_token(jti="jti-survivor")
    identity = IdentityService({"hmac_key": "test-hmac-key"}, revocation_store=db)
    assert identity.revoke(revoked) is True
    del identity, db  # 「重启」:identity 连同内存名单一起消失

    rebooted = IdentityService({"hmac_key": "test-hmac-key"},
                               revocation_store=SqliteStore(tmp_path / "edu-agent.db"))
    assert rebooted.verify_token(revoked) is False   # 重启不复活已登出 token(06 §4.4)
    assert rebooted.verify_token(survivor) is True   # 未吊销 token 不受牵连


def test_revocation_persists_across_process_restart_via_http(tmp_path, monkeypatch):
    """重启回归(HTTP 面,部署形态):logout → 整服务重启(同库文件)→ 旧 token 401。

    build_server(db=…) 注入即吊销落盘(生产装配 = serve_partner_api 同款);
    第二台服务 = 新 identity + 新内存名单,吊销状态只能来自库文件。"""
    db_path = tmp_path / "edu-agent.db"
    with serving(ScriptedKernel(["先看条件。"]),
                 identity=IdentityService(revocation_store=SqliteStore(db_path))) \
            as first:
        assert post(first, "/api/auth/logout", {}, status=200).json() == {"ok": True}
        assert get(first, "/api/conversations/conv_x").status_code == 401
    with serving(ScriptedKernel(["先看条件。"]),
                 identity=IdentityService(revocation_store=SqliteStore(db_path))) \
            as second:
        assert get(second, "/api/conversations/conv_x").status_code == 401  # 仍被拒
        assert get(second, "/api/conversations/conv_x",
                   token=signed_token(jti="other-after-reboot")).status_code == 404


def test_store_revoke_writes_row_and_cleans_expired(tmp_path):
    """store 面:吊销写行(jti+exp);写入时顺手清掉过期行(06 §2.1 第 6 条)。"""
    db = SqliteStore(tmp_path / "edu-agent.db")
    now = int(time.time())
    db.revoke_token("jti-old", now - 10)   # 直接写store:模拟「登出后时间流逝到过期」
    db.revoke_token("jti-new", now + 3600)
    assert db.load_revoked(now) == {"jti-new": now + 3600}  # 过期行已被顺手清


def test_revoke_db_failure_fails_closed(tmp_path):
    """写序先库后内存(06 §2.1 第 3 条):库已关(写必败)→ revoke 抛出且
    内存名单不被污染——宁可不吊销也不谎报成功(不静默降级纯内存档)。"""
    db = SqliteStore(tmp_path / "edu-agent.db")
    identity = IdentityService({"hmac_key": "test-hmac-key"}, revocation_store=db)
    db.close()
    token = signed_token(key="test-hmac-key", jti="jti-fail")
    with pytest.raises(Exception, match="Cannot operate on a closed database"):
        identity.revoke(token)
    assert identity.verify_token(token) is True  # 名单未被污染(未吊销成功)


def test_unwired_identity_keeps_in_memory_semantics():
    """未注入 store 的 IdentityService(纯测试/联调形态)仍是内存档:
    revoke 可用、verify 正常——既有调用方(显式传 identity 的测试)零破坏。"""
    identity = IdentityService({"hmac_key": "test-hmac-key"})
    token = signed_token(key="test-hmac-key", jti="jti-memory-only")
    assert identity.revoke(token) is True
    assert identity.verify_token(token) is False
