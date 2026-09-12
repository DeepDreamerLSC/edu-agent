"""SqliteStore 合同(M3 DB 存储:一张库文件替 JSON 文件持久化)。

覆盖:两个既有接口(ConversationStore 协议 + FileSessionStore 三操作)的往返与
重启续跑(#166 同款用例)、三索引跨实例、文件元数据落库(FileService 注入)、
healthz SELECT 1 探针与失败计数、故障注入(损坏拒启/写失败 fail-closed 不丢数据/
只读拒绝)、多进程并发写(WAL + busy_timeout 的意图)。
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import threading
from dataclasses import dataclass

import httpx
import pytest

from edu_agent.agents.small_lecturer import LearnerSession, Summary
from edu_agent.api import FileService, build_server, build_service
from edu_agent.store import Conversation, SqliteStore


@dataclass
class StubTurn:
    text: str
    session: object = None
    ready_to_confirm: bool = False
    status: str = "completed"


class RecordingKernel:
    """记录 reply/finish 收到的 session 类型,推进真 LearnerSession(#166 用例同款)。"""

    def __init__(self) -> None:
        self.session = None
        self.seen: list[tuple[str, str]] = []

    def start(self, question: dict, learner: dict) -> StubTurn:
        self.session = LearnerSession(question=question, learner=learner)
        self.session.state = "first_question_ready"
        self.session.first_question = "先说说你打算怎么开始?"
        return StubTurn("先说说你打算怎么开始?", session=self.session)

    def reply(self, session: LearnerSession, student_message: str) -> StubTurn:
        self.seen.append(("reply", type(session).__name__))
        session.state = "dialogue"
        session.session_version += 1
        session.history.append({"role": "user", "content": student_message})
        return StubTurn("那下一步呢?", session=session)

    def finish(self, session: LearnerSession) -> StubTurn:
        self.seen.append(("finish", type(session).__name__))
        session.state = "completed"
        return StubTurn("你讲清楚了。", session=session, status="completed")


def _service(db_path, kernel):
    """一次"进程启动":store 实例全新,只共享库文件(重启复现的关键)。"""
    db = SqliteStore(db_path)
    return build_service(kernel, store=db, sessions=db), db


def _open_and_turn(service, idem="idem-1"):
    opened = service.open("q-1", idem, learner={"grade": "五年级"})
    conversation_id = opened["conversation"]["conversation_id"]
    service.send(conversation_id, {
        "content": "两边减 7。",
        "input": {"skill_session_id": opened["skill_session_id"],
                  "expected_session_version": opened["session_version"]}})
    return opened


def sample_session(**overrides) -> LearnerSession:
    session = LearnerSession(
        question={"text": "解方程 3x+7=25", "answer": "x=6"},
        learner={"grade": "五年级", "answer_status": "correct"},
        history=[{"role": "user", "content": "两边减 7。"},
                 {"role": "assistant", "content": "为什么两边能同时减?"}],
    )
    session.state = "ready_to_confirm"
    session.session_version = 4
    session.summary = Summary(text="你完整讲清楚了。", status="completed", session_version=4)
    for key, value in overrides.items():
        setattr(session, key, value)
    return session


# ---------- 两接口往返 ----------

def test_session_save_load_roundtrip(tmp_path):
    db = SqliteStore(tmp_path / "edu-agent.db")
    session = sample_session()
    db.save(session)
    assert db.load(session.session_id) == session  # dataclass 逐字段相等(含 Summary 重建)
    assert db.load_all() == [session]
    assert db.load("kernel_no_such") is None


def test_conversation_create_get_update_roundtrip(tmp_path):
    db = SqliteStore(tmp_path / "edu-agent.db")
    conversation = Conversation(conversation_id="conv_1", question_id="q-1",
                                attempt_id="attempt_1", skill_session_id="skill_1",
                                first_question="先想想?")
    assert db.create(conversation, "idem-1") is conversation
    assert db.get("conv_1") == conversation  # 恢复对象逐字段相等
    conversation.state = "dialogue"
    db.update(conversation)
    assert db.get("conv_1").state == "dialogue"


def test_create_idempotent_same_key_returns_existing(tmp_path):
    db = SqliteStore(tmp_path / "edu-agent.db")
    first = Conversation(conversation_id="conv_1", question_id="q-1", attempt_id="a",
                         skill_session_id="skill_1")
    second = Conversation(conversation_id="conv_2", question_id="q-1", attempt_id="b",
                          skill_session_id="skill_2")
    db.create(first, "idem-1")
    assert db.create(second, "idem-1").conversation_id == "conv_1"


# ---------- 三索引跨实例(#166 语义) ----------

def test_indexes_survive_restart(tmp_path):
    db = SqliteStore(tmp_path / "edu-agent.db")
    session = sample_session()
    conversation = Conversation(
        conversation_id="conv_1", question_id="q-1", attempt_id="a",
        skill_session_id="skill_1", extras={"kernel_session_id": session.session_id})
    db.create(conversation, "idem-1")
    db.save(session)

    reopened = SqliteStore(tmp_path / "edu-agent.db")  # 新进程,只共享库文件
    assert reopened.find_by_idempotency("idem-1").conversation_id == "conv_1"
    assert reopened.find_by_skill_session("skill_1").conversation_id == "conv_1"
    assert reopened.find_by_kernel_session(session.session_id).conversation_id == "conv_1"
    assert reopened.find_by_idempotency("no-such") is None


def test_restart_continuity_open_message_finish(tmp_path):
    """#166 的会话恢复用例换到 SQLite:重启后 open→message→finish 仍可续,
    内核仍收到 LearnerSession 本体(不是三键投影)。"""
    first = RecordingKernel()
    opened = _open_and_turn(_service(tmp_path / "edu-agent.db", first)[0], idem="idem-chain")
    conversation_id = opened["conversation"]["conversation_id"]

    kernel = RecordingKernel()  # 新进程
    service, _db = _service(tmp_path / "edu-agent.db", kernel)
    assert service.status(conversation_id)["state"] == "dialogue"
    assert service.status(conversation_id)["turn_count"] == 2
    body = service.send(conversation_id, {
        "content": "然后两边除以 3。",
        "input": {"skill_session_id": opened["skill_session_id"],
                  "expected_session_version": 2}})
    assert kernel.seen == [("reply", "LearnerSession")], kernel.seen
    assert body["session_version"] == 3
    finished = service._confirm(service._conversation_or_404(conversation_id))
    assert finished["ready_to_confirm"] is True and finished["status"] == "completed"
    assert finished["summary"] == {"status": "completed", "text": "你讲清楚了。"}


# ---------- 文件元数据落库 ----------

def test_file_service_records_survive_restart(tmp_path):
    db = SqliteStore(tmp_path / "edu-agent.db")
    files = FileService(storage_dir=tmp_path / "images", records_store=db)
    created = files.upload_request({"filename": "a.jpg", "content_type": "image/jpeg",
                                    "size_bytes": 10,
                                    "purpose": "micro_lesson_question_image"})
    file_id = created["file_id"]

    reopened = FileService(storage_dir=tmp_path / "images",
                           records_store=SqliteStore(tmp_path / "edu-agent.db"))
    record = reopened.records[file_id]  # 启动预载:此前 records 只在内存,重启即全 404
    assert record.filename == "a.jpg" and record.status == "requested"
    assert db.get_file(file_id)["purpose"] == "micro_lesson_question_image"


# ---------- healthz 探针 ----------

def test_healthz_probe_and_failure_count(tmp_path):
    db = SqliteStore(tmp_path / "edu-agent.db")
    server = build_server(build_service(RecordingKernel()), db=db)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        data = httpx.get(f"{base}/healthz", timeout=5.0, trust_env=False).json()
        assert data["store"] == {"ok": True, "probe_failures": 0}
        db.close()  # 模拟库失联:探针失败计数,健康检查不 500
        data = httpx.get(f"{base}/healthz", timeout=5.0, trust_env=False).json()
        assert data["store"] == {"ok": False, "probe_failures": 1}
    finally:
        server.shutdown()
        server.server_close()


def test_healthz_without_db_keeps_old_shape(tmp_path):
    server = build_server(build_service(RecordingKernel()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        data = httpx.get(
            f"http://127.0.0.1:{server.server_address[1]}/healthz",
            timeout=5.0, trust_env=False).json()
        assert "store" not in data  # 未注入 db 不加键(老形状不变)
    finally:
        server.shutdown()
        server.server_close()


# ---------- 故障注入:明确行为,不静默 ----------

def test_corrupt_db_refuses_to_start(tmp_path):
    """损坏 = 拒启:构造即探测,抛 DatabaseError(不做降级只读——那会掩盖事实)。"""
    path = tmp_path / "edu-agent.db"
    path.write_bytes(b"this is definitely not a sqlite database" * 10)
    with pytest.raises(sqlite3.DatabaseError):
        SqliteStore(path)


def test_write_after_close_fails_closed_and_keeps_data(tmp_path):
    """连接关闭后写入报错(fail-closed),且已写数据不丢(重开后仍在)。"""
    path = tmp_path / "edu-agent.db"
    db = SqliteStore(path)
    db.save(sample_session())
    db.close()
    with pytest.raises(sqlite3.Error):
        db.save(sample_session())
    assert SqliteStore(path).load_all() != []  # 此前写入仍在


@pytest.mark.skipif(os.geteuid() == 0, reason="root 绕过文件权限,只读注入用非 root 跑")
def test_readonly_db_write_fails_and_keeps_data(tmp_path):
    path = tmp_path / "edu-agent.db"
    db = SqliteStore(path)
    db.save(sample_session())
    db.close()
    os.chmod(path, 0o444)
    readonly = SqliteStore(path)  # 只读文件:打开与读成功
    assert readonly.load_all() != []
    with pytest.raises(sqlite3.Error):
        readonly.save(sample_session())  # 写入报错,不静默丢
    os.chmod(path, 0o644)


def test_db_path_is_directory_refuses_to_start(tmp_path):
    """库路径被目录占位 = 打不开,拒启(等效故障:root 下无法用 chmod 模拟只读)。"""
    path = tmp_path / "edu-agent.db"
    path.mkdir()
    with pytest.raises(sqlite3.OperationalError):
        SqliteStore(path)


# ---------- 多进程并发写(WAL + busy_timeout 的意图) ----------

_WORKER = """
import sys
from edu_agent.store import Conversation, SqliteStore

store = SqliteStore(sys.argv[1])
tag, count = sys.argv[2], int(sys.argv[3])
for i in range(count):
    store.create(Conversation(
        conversation_id=f"conv_{tag}_{i}", question_id="q", attempt_id="a",
        skill_session_id=f"skill_{tag}_{i}"), f"idem-{tag}-{i}")
print("ok")
"""


def test_multi_process_concurrent_writes_all_land(tmp_path):
    path = tmp_path / "edu-agent.db"
    SqliteStore(path).close()  # 建库建表
    workers = [subprocess.Popen(
        [sys.executable, "-c", _WORKER, str(path), tag, "20"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for tag in ("a", "b")]
    for worker in workers:
        out, err = worker.communicate(timeout=120)
        assert worker.returncode == 0, err or out
    with sqlite3.connect(path) as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM records WHERE kind='conversation'").fetchone()[0]
    assert total == 40  # 两进程 × 20 条,一条不丢
    assert SqliteStore(path).get("conv_a_0") is not None
    assert SqliteStore(path).get("conv_b_19") is not None


# ---------- 迁移标记不被运行时碰 ----------

def test_runtime_store_leaves_user_version_alone(tmp_path):
    path = tmp_path / "edu-agent.db"
    db = SqliteStore(path)
    db.save(sample_session())
    db.close()
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0  # 只归迁移脚本管


# ---------- 布局核对 ----------

def test_two_tables_and_three_indexes(tmp_path):
    path = tmp_path / "edu-agent.db"
    SqliteStore(path).close()
    with sqlite3.connect(path) as conn:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        indexes = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'")}
    assert {"records", "files"} <= tables  # 两张 JSON blob 表
    assert indexes == {"idx_records_idempotency", "idx_records_skill_session",
                       "idx_records_kernel_session"}  # 3 个索引


def test_wal_and_busy_timeout_and_foreign_keys(tmp_path):
    db = SqliteStore(tmp_path / "edu-agent.db")
    assert db._conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert db._conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert db._conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    db.close()
