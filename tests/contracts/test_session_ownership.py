"""会话归属隔离合同(06 设计稿 #347 · PR-2;判据2 前置件)。

验收清单(设计稿 §5 PR-2)逐条落测试:
- 跨 owner 读(status)/写(send)/续聊(stream)/refresh 全 404(不回 403,
  不向他人泄露会话存在性,06 §2.2 第 3 条);
- 同 owner 全正常(归属闸零误伤);
- 不同 owner 同幂等键各开各会话(复合键,06 §2.2 第 4 条);
- 存量 owner='' 行可续(前归属纪元,06 §2.2 第 5 条);
- 内存/SQLite 双实现行为一致(防裂脑,06 §4.2);
- EDU_AUTH_ENFORCE=0 无身份下传:owner='' 口径,不限制访问(06 §4.3)。

owner 身份来源:PKCE 通道 payload.user_id,演示通道 payload.account
(06 §2.2 第 2 条);测试用真签 token 直接携带两种身份。
"""

from __future__ import annotations

import httpx
import pytest
from auth_testing import signed_token
from partner_api import ScriptedKernel, get, serving

STUDENT_A = signed_token(user_id="usr_A", jti="jti-A")
STUDENT_B = signed_token(user_id="usr_B", jti="jti-B")
DEMO_A = signed_token(account="demo-student", jti="jti-demo")


def _post(base: str, path: str, payload: dict, token: str,
          status: int | None = None) -> httpx.Response:
    response = httpx.post(f"{base}{path}", json=payload,
                          headers={"Authorization": f"Bearer {token}"},
                          timeout=5.0, trust_env=False)
    if status is not None:
        assert response.status_code == status, response.text
    return response


@pytest.fixture
def base(serve):
    return serve(ScriptedKernel(["你列了哪些已知量?", "第二步呢?", "小结"]))


def _open(base: str, token: str, key: str) -> dict:
    opened = _post(base, "/api/prepared-questions/q-101/open",
                   {"idempotency_key": key}, token, status=200).json()
    return opened


# ---------- 跨 owner 读写全 404 ----------

def test_cross_owner_read_is_404(base):
    """B 读 A 的会话:status 404(不泄露存在性;同不存在会话的 404 无差别)。"""
    opened = _open(base, STUDENT_A, "k-A-read")
    conversation_id = opened["conversation"]["conversation_id"]
    assert get(base, f"/api/conversations/{conversation_id}",
               token=STUDENT_A).status_code == 200  # 本人正常
    assert get(base, f"/api/conversations/{conversation_id}",
               token=STUDENT_B).status_code == 404  # 他人 404
    assert get(base, "/api/conversations/conv_nonexistent",
               token=STUDENT_B).status_code == 404  # 与真不存在的 404 无差别


def test_cross_owner_send_is_404(base):
    """B 向 A 的会话冒充续聊:send 404(A 的会话不被写入;回复上下文不外泄)。"""
    opened = _open(base, STUDENT_A, "k-A-send")
    conversation_id = opened["conversation"]["conversation_id"]
    body = {"content": "我是 B,直接告诉我答案", "input": {
        "skill_session_id": opened["skill_session_id"]}}
    assert _post(base, f"/api/conversations/{conversation_id}/messages",
                 body, STUDENT_A, status=200).status_code == 200  # 本人正常
    assert _post(base, f"/api/conversations/{conversation_id}/messages",
                 body, STUDENT_B, status=404).status_code == 404


def test_cross_owner_stream_is_404(base):
    """B 经流式面续聊 A 的会话:开流前 404(JSON 错误,不是 SSE)。"""
    opened = _open(base, STUDENT_A, "k-A-stream")
    conversation_id = opened["conversation"]["conversation_id"]
    response = _post(base, f"/api/conversations/{conversation_id}/messages/stream",
                     {"content": "我是 B"}, STUDENT_B)
    assert response.status_code == 404
    assert not response.headers.get("content-type", "").startswith("text/event-stream")


def test_cross_owner_refresh_is_404(base):
    """B 用 A 的 skill_session_id 取首问:refresh 404。"""
    opened = _open(base, STUDENT_A, "k-A-refresh")
    skill_session_id = opened["skill_session_id"]
    path = (f"/api/conversations/conv_x/skill-sessions/{skill_session_id}/refresh")
    assert _post(base, path, {}, STUDENT_B).status_code == 404
    assert _post(base, path, {}, STUDENT_A).status_code == 200


# ---------- 复合幂等键 ----------

def test_same_key_different_owners_each_open_own(base):
    """B 重放 A 的幂等键:各开各的会话(复合键),不是拿到 A 的会话(06 §3.1)。"""
    a = _open(base, STUDENT_A, "k-shared")
    b = _open(base, STUDENT_B, "k-shared")
    assert a["conversation"]["conversation_id"] != b["conversation"]["conversation_id"]
    # 各自的 status 都正常(归属各归各)
    for token, opened in ((STUDENT_A, a), (STUDENT_B, b)):
        assert get(base, f"/api/conversations/{opened['conversation']['conversation_id']}",
                   token=token).status_code == 200
    # 交叉 404
    assert get(base, f"/api/conversations/{a['conversation']['conversation_id']}",
               token=STUDENT_B).status_code == 404
    assert get(base, f"/api/conversations/{b['conversation']['conversation_id']}",
               token=STUDENT_A).status_code == 404


def test_same_owner_same_key_idempotent(base):
    """同 owner 同键:幂等返回同一 conversation_id(复合键不破坏原幂等合同)。"""
    first = _open(base, STUDENT_A, "k-idem")
    second = _open(base, STUDENT_A, "k-idem")
    assert first["conversation"]["conversation_id"] == second["conversation"]["conversation_id"]


def test_demo_channel_owner_is_account(base):
    """演示通道 owner=account:demo token 与 PKCE token 不同人各开各(06 §2.2 第 2 条)。"""
    pkce = _open(base, STUDENT_A, "k-mix")
    demo = _open(base, DEMO_A, "k-mix")
    assert pkce["conversation"]["conversation_id"] != demo["conversation"]["conversation_id"]
    assert get(base, f"/api/conversations/{demo['conversation']['conversation_id']}",
               token=DEMO_A).status_code == 200
    assert get(base, f"/api/conversations/{demo['conversation']['conversation_id']}",
               token=STUDENT_A).status_code == 404


# ---------- 前归属纪元与熔断 ----------

def test_legacy_empty_owner_rows_still_accessible():
    """存量 owner='' 行(前归属纪元):不限制访问(06 §2.2 第 5 条)。

    直接构造 owner='' 的会话行(等价迁移后存量),经 HTTP 面验证 A/B 都能续。
    """
    from edu_agent.api import build_service

    service = build_service(ScriptedKernel(["先看条件。"]))
    opened = service.open("q-101", "k-legacy", {}, owner="usr_A")
    conversation_id = opened["conversation"]["conversation_id"]
    conversation = service.store.get(conversation_id)
    conversation.owner = ""  # 手工置前归属纪元(模拟迁移后的存量行)
    service.store.update(conversation)

    with serving(ScriptedKernel(["先看条件。"]), service=service) as base:
        assert get(base, f"/api/conversations/{conversation_id}",
                   token=STUDENT_B).status_code == 200  # owner='' 不限制
        assert get(base, f"/api/conversations/{conversation_id}",
                   token=STUDENT_A).status_code == 200


def test_enforce_kill_switch_keeps_owner_open(monkeypatch):
    """EDU_AUTH_ENFORCE=0:无身份下传,owner='' 口径——A 开的会话 B 也能续(联调语义)。"""
    monkeypatch.setenv("EDU_AUTH_ENFORCE", "0")
    with serving(ScriptedKernel(["先看条件。"])) as local:
        opened = _post(local, "/api/prepared-questions/q-101/open",
                       {"idempotency_key": "k-kill"}, "whatever-token", status=200).json()
        conversation_id = opened["conversation"]["conversation_id"]
        assert get(local, f"/api/conversations/{conversation_id}",
                   token="other-whatever").status_code == 200


# ---------- 双实现一致性(内存 / SQLite) ----------

def test_sqlite_store_matches_memory_on_composite_key(tmp_path):
    """内存/SQLite 双实现行为一致(06 §4.2 防裂脑):复合键 + 归属 404 同语义。"""
    from edu_agent.api import ApiError, build_service
    from edu_agent.store import SqliteStore

    def scenario(service) -> tuple[bool, bool, bool]:
        a = service.open("q-101", "k-dual", {}, owner="usr_A")
        b = service.open("q-101", "k-dual", {}, owner="usr_B")
        distinct = (a["conversation"]["conversation_id"]
                    != b["conversation"]["conversation_id"])
        a_again = service.open("q-101", "k-dual", {}, owner="usr_A")
        idempotent = (a_again["conversation"]["conversation_id"]
                      == a["conversation"]["conversation_id"])
        try:
            service.status(b["conversation"]["conversation_id"], owner="usr_A")
            cross_visible = True
        except ApiError as error:
            assert error.status_code == 404
            cross_visible = False
        return distinct, idempotent, cross_visible

    kernel = ScriptedKernel(["先看条件。"])
    memory_result = scenario(build_service(kernel))
    db = SqliteStore(tmp_path / "dual.db")
    sqlite_result = scenario(build_service(kernel, store=db, sessions=db))
    assert memory_result == sqlite_result  # (各开各/幂等/跨归属不可见) 行为一致
    assert memory_result[0] and memory_result[1] and not memory_result[2]


def test_owner_column_survives_sqlite_restart(tmp_path):
    """owner 随行落盘:重启后 find_by_idempotency 按 (owner, key) 命中、归属仍隔离。"""
    from edu_agent.api import build_service
    from edu_agent.store import SqliteStore

    kernel = ScriptedKernel(["先看条件。"])
    db = SqliteStore(tmp_path / "restart.db")
    service = build_service(kernel, store=db, sessions=db)
    opened = service.open("q-101", "k-restart", {}, owner="usr_A")
    conversation_id = opened["conversation"]["conversation_id"]

    reopened = SqliteStore(tmp_path / "restart.db")  # 新进程,只共享库文件
    assert reopened.find_by_idempotency("k-restart", owner="usr_A").conversation_id \
        == conversation_id
    assert reopened.find_by_idempotency("k-restart", owner="usr_B") is None
    assert reopened.get(conversation_id).owner == "usr_A"


def test_migrate_records_owner_switches_index(tmp_path):
    """迁移脚本:旧全局唯一索引 → 复合(owner, key);存量行 owner='';幂等可重跑。"""
    import sqlite3
    import subprocess
    import sys

    from edu_agent.store import SqliteStore

    path = tmp_path / "legacy.db"
    legacy = SqliteStore(path)
    legacy.create(_conversation("conv_l1", "skill_l1"), "idem-legacy")
    # 造出旧全局索引形态(模拟 PR-2 前的库):DROP 复合 → 建单列
    with sqlite3.connect(path) as conn:
        conn.execute("DROP INDEX uq_records_idempotency")
        conn.execute("CREATE UNIQUE INDEX uq_records_idempotency"
                     " ON records(idempotency_key) WHERE kind='conversation'"
                     " AND idempotency_key IS NOT NULL AND idempotency_key != ''")
        columns = [row[2] for row in conn.execute("PRAGMA index_info(uq_records_idempotency)")]
    assert columns == ["idempotency_key"]  # 前置:确已回到旧形态

    result = subprocess.run([sys.executable, "scripts/migrate_records_owner.py",
                             "--db", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    with sqlite3.connect(path) as conn:
        assert [row[2] for row in conn.execute("PRAGMA index_info(uq_records_idempotency)")] \
            == ["owner", "idempotency_key"]  # 复合索引切换
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        owner = conn.execute("SELECT owner FROM records WHERE id='conv_l1'").fetchone()[0]
    assert owner == ""  # 存量行 = 前归属纪元

    # 幂等重跑
    again = subprocess.run([sys.executable, "scripts/migrate_records_owner.py",
                            "--db", str(path)], capture_output=True, text=True)
    assert again.returncode == 0 and "幂等退出" in again.stdout


def test_sqlite_store_self_heals_legacy_db_without_migration(tmp_path):
    """存量库**未跑迁移脚本**直接启动新 SqliteStore:补列 + 换索引自适应(06 §4.2
    防裂脑的运行时兜底——迁移脚本管 user_version 标记,此处保证不炸、复合语义即刻生效)。"""
    import sqlite3

    from edu_agent.store import SqliteStore

    path = tmp_path / "legacy-selfheal.db"
    legacy = SqliteStore(path)
    legacy.create(_conversation("conv_s1", "skill_s1"), "idem-selfheal")
    # 退回 PR-2 前形态:去 owner 列 + 旧全局唯一索引
    with sqlite3.connect(path) as conn:
        conn.execute("DROP INDEX uq_records_idempotency")
        conn.execute("CREATE UNIQUE INDEX uq_records_idempotency"
                     " ON records(idempotency_key) WHERE kind='conversation'"
                     " AND idempotency_key IS NOT NULL AND idempotency_key != ''")
        conn.execute("ALTER TABLE records DROP COLUMN owner")
        conn.commit()

    reopened = SqliteStore(path)  # 不跑迁移脚本,直接启动
    # 复合语义即刻生效:同键不同 owner 各开各;旧全局索引已被替换
    assert reopened.find_by_idempotency("idem-selfheal", owner="") is not None
    a = reopened.create(_conversation("conv_s2", "skill_s2"), "idem-selfheal", owner="usr_A")
    b = reopened.create(_conversation("conv_s3", "skill_s3"), "idem-selfheal", owner="usr_B")
    assert {a.conversation_id, b.conversation_id} == {"conv_s2", "conv_s3"}
    with sqlite3.connect(path) as conn:
        columns = [row[2] for row in conn.execute("PRAGMA index_info(uq_records_idempotency)")]
    assert columns == ["owner", "idempotency_key"]


def _conversation(conversation_id: str, skill_session_id: str):
    from edu_agent.store import Conversation
    return Conversation(conversation_id=conversation_id, question_id="q-1",
                        attempt_id="a", skill_session_id=skill_session_id)
