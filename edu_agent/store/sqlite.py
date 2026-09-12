"""SQLite 持久化(M3 目标项:数据库存储)——一个库文件、两张 JSON blob 表。

`SqliteStore` 一个类实现两个既有接口(不另立抽象层,02 §2 store 包内 additive):
- `ConversationStore` 协议(conversations.py):会话表(对话)最小面;
- `FileSessionStore` 三操作(learner_sessions.py):LearnerSession(会话)本体存取。
外加 files 表三操作(文件元数据):`FileService(records_store=...)` 注入后,上传
元数据重启可续——此前 records 只在内存,进程重启后全部 file_id 404。

表结构 = 两张 JSON blob 表 + 3 个索引(字段照现有 JSON 结构,不加"以后可能用到"的列):
- ``records``:会话(``kind='session'``,id=session_id)与对话(``kind='conversation'``,
  id=conversation_id)共表;三个索引列即会话表的三个查找面(idempotency_key /
  skill_session_id / kernel_session_id),payload 是既有 JSON 形状的 blob。
- ``files``:file_id 主键 + payload(FileRecord 字段的 JSON)。

取舍(写在代码里,便于审查):
- **单连接 + 单事务**(02 §5 禁自建连接池/worker 池):一个 sqlite3 连接 +
  ``threading.Lock`` 串行化(服务是 ThreadingHTTPServer,多线程);跨进程并发
  交给 WAL + ``busy_timeout=5000``(备份/迁移是第二进程,只读或短写)。
- **写路径 fail-closed**:任何 ``sqlite3.Error`` 原样抛出,绝不吞错——产品数据
  不静默丢;服务层把它映射 503(合同表)。
- **损坏拒启**:构造即 ``SELECT 1`` 探测,坏库直接抛 ``DatabaseError``——服务
  起不来、launchd 可见,不做降级只读(降级会掩盖库已坏的事实)。
- **PRAGMA user_version 归一次性迁移脚本**(migrate_json_to_sqlite.py)管,本类
  不碰:schema 用 ``CREATE TABLE IF NOT EXISTS``;两处都写 user_version 会互相踩。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict
from pathlib import Path

from edu_agent.agents.small_lecturer.session import LearnerSession

from .conversations import conversation_payload, conversation_restore
from .learner_sessions import restore_session

_SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  idempotency_key TEXT,
  skill_session_id TEXT,
  kernel_session_id TEXT,
  payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_records_idempotency ON records(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_records_skill_session ON records(skill_session_id);
CREATE INDEX IF NOT EXISTS idx_records_kernel_session ON records(kernel_session_id);
CREATE TABLE IF NOT EXISTS files (
  file_id TEXT PRIMARY KEY,
  payload TEXT NOT NULL
);
"""
# 查找 SQL 全部字面量(列名不经拼接,S608);三个索引各对应一个查找面。
_FIND_CONVERSATION = {
    "conversation_id": "SELECT payload FROM records WHERE kind='conversation' AND id=?",
    "idempotency_key": ("SELECT payload FROM records WHERE kind='conversation' "
                        "AND idempotency_key=? ORDER BY rowid LIMIT 1"),
    "skill_session_id": "SELECT payload FROM records WHERE kind='conversation' AND skill_session_id=?",
    "kernel_session_id": "SELECT payload FROM records WHERE kind='conversation' AND kernel_session_id=?",
}
_UPSERT_CONVERSATION = (
    "INSERT OR REPLACE INTO records"
    "(id, kind, idempotency_key, skill_session_id, kernel_session_id, payload)"
    " VALUES(?, 'conversation', ?, ?, ?, ?)")
_UPSERT_SESSION = (
    "INSERT OR REPLACE INTO records(id, kind, payload) VALUES(?, 'session', ?)")
_FIND_SESSION = "SELECT payload FROM records WHERE kind='session' AND id=?"
_ALL_SESSIONS = "SELECT payload FROM records WHERE kind='session' ORDER BY id"
_UPSERT_FILE = "INSERT OR REPLACE INTO files(file_id, payload) VALUES(?, ?)"
_FIND_FILE = "SELECT payload FROM files WHERE file_id=?"
_ALL_FILES = "SELECT payload FROM files ORDER BY file_id"
_STORED_KEY = "SELECT idempotency_key FROM records WHERE kind='conversation' AND id=?"


class SqliteStore:
    """一会话一库的 SQLite 实现:ConversationStore 协议 + 会话本体存取 + 文件元数据。

    同一实例可同时注入 ``build_service(store=…, sessions=…)`` 的两个位(一个类
    实现两个既有接口);``probe``/``probe_failures`` 供 healthz 的 SELECT 1 探针。
    """

    def __init__(self, path: Path | str = "data/edu-agent.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # RLock:公开方法持锁后还会调内部查找(create 内嵌幂等查)——同线程重入
        # 合法,跨线程仍是单连接串行。
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False,
                                     isolation_level=None)  # 单事务/操作(autocommit)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self.probe_failures = 0
        self._conn.execute("SELECT 1").fetchone()  # 损坏拒启:坏库构造即抛

    def close(self) -> None:
        """显式关闭(测试/演练用);此后任何读写抛 ProgrammingError(fail-closed)。"""
        with self._lock:
            self._conn.close()

    # ---------- healthz 探针 ----------

    def probe(self) -> bool:
        """SELECT 1 探针:成功 True;失败计数 +1 并返回 False(健康检查不该 500)。"""
        try:
            with self._lock:
                self._conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            self.probe_failures += 1
            return False

    # ---------- ConversationStore 协议(与 FileConversationStore 同语义) ----------

    def create(self, conversation, idempotency_key: str):
        with self._lock:
            existing = (self._conversation("idempotency_key", idempotency_key)
                        if idempotency_key else None)
            if existing is not None:
                return existing  # 同键幂等:返回既有会话
            self._write_conversation(conversation, idempotency_key)
            return conversation

    def get(self, conversation_id: str):
        return self._conversation("conversation_id", conversation_id)

    def update(self, conversation) -> None:
        with self._lock:
            row = self._conn.execute(_STORED_KEY,
                                     (conversation.conversation_id,)).fetchone()
            # 幂等键以库内已有值为准(update 不带键;单真相源在行上)
            self._write_conversation(conversation, row[0] if row else "")

    def find_by_idempotency(self, idempotency_key: str):
        return self._conversation("idempotency_key", idempotency_key)

    def find_by_skill_session(self, skill_session_id: str):
        return self._conversation("skill_session_id", skill_session_id)

    def find_by_kernel_session(self, kernel_session_id: str):
        """facts 归因(01 §7):edu.session_id = LearnerSession.session_id → 合作方会话。"""
        return self._conversation("kernel_session_id", kernel_session_id)

    def _conversation(self, column: str, value: str):
        if not value:
            return None
        with self._lock:
            row = self._conn.execute(_FIND_CONVERSATION[column], (value,)).fetchone()
        if row is None:
            return None
        conversation, _ = conversation_restore(json.loads(row[0]))
        return conversation

    def _write_conversation(self, conversation, idempotency_key: str) -> None:
        payload = conversation_payload(conversation, idempotency_key)
        kernel_session_id = str((payload["extras"] or {}).get("kernel_session_id") or "")
        self._conn.execute(_UPSERT_CONVERSATION, (
            conversation.conversation_id, idempotency_key or None,
            conversation.skill_session_id, kernel_session_id or None,
            json.dumps(payload, ensure_ascii=False)))

    # ---------- 会话本体(FileSessionStore 三操作同语义) ----------

    def save(self, session: LearnerSession) -> None:
        with self._lock:
            self._conn.execute(_UPSERT_SESSION, (
                session.session_id, json.dumps(asdict(session), ensure_ascii=False)))

    def load(self, session_id: str) -> LearnerSession | None:
        with self._lock:
            row = self._conn.execute(_FIND_SESSION, (session_id,)).fetchone()
        return restore_session(json.loads(row[0])) if row else None

    def load_all(self) -> list[LearnerSession]:
        """全部会话本体(id 序,稳定);单条坏记录跳过,不炸整个扫描(文件版同语义)。"""
        with self._lock:
            rows = self._conn.execute(_ALL_SESSIONS).fetchall()
        sessions = []
        for (text,) in rows:
            try:
                sessions.append(restore_session(json.loads(text)))
            except (json.JSONDecodeError, TypeError, KeyError) as error:
                print(f"[store] 跳过损坏的会话记录:({type(error).__name__}){error}")
        return sessions

    # ---------- 文件元数据(files 表;FileService 注入用,泛 JSON,不 import api) ----------

    def put_file(self, file_id: str, payload: dict) -> None:
        with self._lock:
            self._conn.execute(_UPSERT_FILE,
                               (file_id, json.dumps(payload, ensure_ascii=False)))

    def get_file(self, file_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(_FIND_FILE, (file_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def all_files(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(_ALL_FILES).fetchall()
        return [json.loads(text) for (text,) in rows]
