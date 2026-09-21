"""SQLite 持久化(M3 目标项:数据库存储)——一个库文件、两张 JSON blob 表。

`SqliteStore` 一个类实现两个既有接口(不另立抽象层,02 §2 store 包内 additive):
- `ConversationStore` 协议(conversations.py):会话表(对话)最小面;
- `FileSessionStore` 三操作(learner_sessions.py):LearnerSession(会话)本体存取。
外加 files 表两操作(文件元数据):`FileService(records_store=...)` 注入后,上传
元数据重启可续——此前 records 只在内存,进程重启后全部 file_id 404。

表结构 = 两张 JSON blob 表 + 3 个索引(字段照现有 JSON 结构,不加"以后可能用到"的列):
- ``records``:会话(``kind='session'``,id=session_id)与对话(``kind='conversation'``,
  id=conversation_id)共表;索引列即会话表的查找面(idempotency_key /
  skill_session_id / kernel_session_id),payload 是既有 JSON 形状的 blob。
- ``files``:file_id 主键 + payload(FileRecord 字段的 JSON)。
- ``revoked_jti``:登出吊销名单(jti 主键 + exp;06 §2.1 第 2 条)——
  identity 启动全量加载进内存,热路径不碰库;exp = 被吊销 token 的原 exp,
  写时顺手清过期,名单最长寿命 = token 剩余 TTL,不积累。

取舍(写在代码里,便于审查):
- **幂等合同下沉 DDL(决策 6)**:idempotency_key / skill_session_id 上
  **部分唯一索引**(空键不入索引)。服务层幂等(open 预查 + RLock)之外的第二
  道闸——并发/跨进程下重复键在库层面不存在,后到者撞索引回查返回既有。
  kernel_session_id **不设 UNIQUE**:服务层对它无唯一性保证(open/message 两处
  都校验幂等键与 skill_session 的归属,这个没有),不冒进。
- **单连接 + 单事务**(02 §5 禁自建连接池/worker 池):一个 sqlite3 连接 +
  ``threading.Lock`` 串行化(服务是 ThreadingHTTPServer,多线程);跨进程并发
  交给 WAL + ``busy_timeout=5000``(备份/迁移是第二进程,只读或短写)。
- **写路径 fail-closed**:任何 ``sqlite3.Error`` 原样抛出,绝不吞错——产品数据
  不静默丢;服务层把它映射 503(合同表)。
- **损坏拒启**:构造即 ``SELECT 1`` 探测,坏库直接抛 ``DatabaseError``——服务
  起不来、launchd 可见,不做降级只读(降级会掩盖库已坏的事实)。
- **PRAGMA user_version 归一次性迁移脚本**(migrate_json_to_sqlite.py)管,本类
  不碰:schema 用 ``CREATE TABLE IF NOT EXISTS``;两处都写 user_version 会互相踩。

PG 触发备选(决策 6,文档化,不是本单交付):出现**多实例**(一库多写者)、
**网络直连**(合作方/分析端要跨网读)、**重分析**(要窗口函数/并行查询)三选一
时再迁 PostgreSQL——当前单机单实例,SQLite + WAL 是最小答案。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
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
  owner TEXT NOT NULL DEFAULT '',
  payload TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_records_idempotency
  ON records(owner, idempotency_key)
  WHERE kind='conversation' AND idempotency_key IS NOT NULL AND idempotency_key != '';
CREATE UNIQUE INDEX IF NOT EXISTS uq_records_skill_session
  ON records(skill_session_id)
  WHERE kind='conversation' AND skill_session_id IS NOT NULL AND skill_session_id != '';
CREATE INDEX IF NOT EXISTS idx_records_kernel_session ON records(kernel_session_id);
CREATE TABLE IF NOT EXISTS files (
  file_id TEXT PRIMARY KEY,
  payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS revoked_jti (
  jti TEXT PRIMARY KEY,
  exp INTEGER NOT NULL
);
DROP INDEX IF EXISTS idx_records_idempotency;
DROP INDEX IF EXISTS idx_records_skill_session;
"""
_REVOKE_INSERT = "INSERT OR REPLACE INTO revoked_jti(jti, exp) VALUES(?, ?)"
_REVOKE_DELETE_EXPIRED = "DELETE FROM revoked_jti WHERE exp < ?"
_REVOKE_LOAD = "SELECT jti, exp FROM revoked_jti WHERE exp >= ?"
# 查找 SQL 全部字面量(列名不经拼接,S608);索引各对应一个查找面。幂等唯一索引
# 按 (owner, idempotency_key) 复合(06 §2.2 第 4 条)——不同 owner 同名键各开各的
# 会话;owner 列由一次性迁移脚本 ALTER 补上并回填 PRAGMA user_version(06 §2.2
# 第 1 条),新库由本 DDL 直建。两个唯一索引用新名 uq_*:同名 IF NOT EXISTS 在
# 存量库(旧普通索引)上会静默跳过,改名才真正建成;DROP 旧名清掉写放大。空键
# (NULL/'')被部分索引排除——脏历史行不至拒启。
_FIND_CONVERSATION = {
    "conversation_id": "SELECT payload FROM records WHERE kind='conversation' AND id=?",
    "idempotency_key": ("SELECT payload FROM records WHERE kind='conversation' "
                        "AND owner=? AND idempotency_key=? ORDER BY rowid LIMIT 1"),
    "skill_session_id": "SELECT payload FROM records WHERE kind='conversation' AND skill_session_id=?",
    "kernel_session_id": "SELECT payload FROM records WHERE kind='conversation' AND kernel_session_id=?",
}
_INSERT_CONVERSATION = (
    "INSERT INTO records"
    "(id, kind, idempotency_key, skill_session_id, kernel_session_id, owner, payload)"
    " VALUES(?, 'conversation', ?, ?, ?, ?, ?)")
# update 用 ON CONFLICT(id) 而非 INSERT OR REPLACE:REPLACE 会**删除**任何唯一
# 约束的冲突行(包括新 UNIQUE 索引),把"幂等返回既有"变成"谁后写谁赢"。
_UPSERT_CONVERSATION = (
    "INSERT INTO records"
    "(id, kind, idempotency_key, skill_session_id, kernel_session_id, owner, payload)"
    " VALUES(?, 'conversation', ?, ?, ?, ?, ?)"
    " ON CONFLICT(id) DO UPDATE SET idempotency_key=excluded.idempotency_key,"
    " skill_session_id=excluded.skill_session_id,"
    " kernel_session_id=excluded.kernel_session_id, payload=excluded.payload")
_UPSERT_SESSION = (
    "INSERT OR REPLACE INTO records(id, kind, payload) VALUES(?, 'session', ?)")
_FIND_SESSION = "SELECT payload FROM records WHERE kind='session' AND id=?"
_ALL_SESSIONS = "SELECT payload FROM records WHERE kind='session' ORDER BY id"
_UPSERT_FILE = "INSERT OR REPLACE INTO files(file_id, payload) VALUES(?, ?)"
_ALL_FILES = "SELECT payload FROM files ORDER BY file_id"
_STORED_KEY = "SELECT idempotency_key, owner FROM records WHERE kind='conversation' AND id=?"


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
        # WAL 官方推荐组合:NORMAL = 应用崩溃不丢、断电最多丢最后数个已提交事务
        # (决策 6 指定;默认 FULL 每次提交都 fsync,慢一档,对本数据不值得)。
        self._conn.execute("PRAGMA synchronous=NORMAL")
        # 存量库自适应(06 §2.2 第 1 条):ALTER ADD COLUMN 只在缺列时补(owner=''
        # = 前归属纪元);新库由 _SCHEMA 直建。旧全局唯一索引的同名重建与 user_version
        # 标记归 scripts/migrate_records_owner.py(一次性迁移,惯例同 json 迁移);
        # 此处只保证列在,不碰 user_version(两处写会互相踩,模块头已述)。
        if self._table_exists("records") and not self._has_column("records", "owner"):
            self._conn.execute("ALTER TABLE records ADD COLUMN owner TEXT NOT NULL DEFAULT ''")
        # 存量库索引切换(06 §4.2):旧全局唯一索引与新复合索引同名,IF NOT EXISTS
        # 会静默跳过 → 裂脑(查找按复合、约束按全局)。列序不符即 DROP 重建;
        # 新库无此索引,直过。
        if self._index_columns("uq_records_idempotency") not in (None, ["owner", "idempotency_key"]):
            self._conn.execute("DROP INDEX uq_records_idempotency")
        self._conn.executescript(_SCHEMA)
        self.probe_failures = 0
        self._conn.execute("SELECT 1").fetchone()  # 损坏拒启:坏库构造即抛

    def close(self) -> None:
        """显式关闭(测试/演练用);此后任何读写抛 ProgrammingError(fail-closed)。"""
        with self._lock:
            self._conn.close()

    def _has_column(self, table: str, column: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM pragma_table_info(?) WHERE name=?", (table, column)).fetchone()
        return row is not None

    def _table_exists(self, table: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return row is not None

    def _index_columns(self, name: str) -> list[str] | None:
        """索引列序;索引不存在返回 None。"""
        rows = self._conn.execute(
            "SELECT name FROM pragma_index_info(?)", (name,)).fetchall()
        return [row[0] for row in rows] if rows else None

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

    def create(self, conversation, idempotency_key: str, owner: str = ""):
        with self._lock:
            existing = (self._conversation("idempotency_key", (owner, idempotency_key))
                        if idempotency_key else None)
            if existing is not None:
                return existing  # 同(归属,键)幂等:返回既有会话
            if owner:
                conversation.owner = owner  # 单真相源在行上(与 update 的键保容同口径)
            try:
                self._write_conversation(conversation, idempotency_key,
                                         _INSERT_CONVERSATION)
            except sqlite3.IntegrityError:
                # UNIQUE 兜底(幂等合同已下沉 DDL):预查与写入之间被并发插进
                # 同键行时,后到者撞索引 → 回查返回既有;非键冲突照旧 fail-closed。
                existing = (self._conversation("idempotency_key", (owner, idempotency_key))
                            if idempotency_key else None)
                if existing is not None:
                    return existing
                raise
            return conversation

    def get(self, conversation_id: str):
        return self._conversation("conversation_id", conversation_id)

    def update(self, conversation) -> None:
        with self._lock:
            row = self._conn.execute(_STORED_KEY,
                                     (conversation.conversation_id,)).fetchone()
            # 幂等键与 owner 以库内已有值为准(update 不带键;单真相源在行上)
            self._write_conversation(conversation, row[0] if row else "",
                                     _UPSERT_CONVERSATION,
                                     stored_owner=row[1] if row else None)

    def find_by_idempotency(self, idempotency_key: str, owner: str = ""):
        return self._conversation("idempotency_key", (owner, idempotency_key))

    def find_by_skill_session(self, skill_session_id: str):
        return self._conversation("skill_session_id", skill_session_id)

    def find_by_kernel_session(self, kernel_session_id: str):
        """facts 归因(01 §7):edu.session_id = LearnerSession.session_id → 合作方会话。"""
        return self._conversation("kernel_session_id", kernel_session_id)

    def _conversation(self, column: str, value):
        # 复合键 (owner, key):owner='' 是合法值(前归属纪元/无身份下传),只有
        # 查找值整体为空才短路返回 None。
        if value in ("", None) or value == ("", ""):
            return None
        with self._lock:
            row = self._conn.execute(_FIND_CONVERSATION[column],
                                     value if isinstance(value, tuple) else (value,)
                                     ).fetchone()
        if row is None:
            return None
        conversation, _ = conversation_restore(json.loads(row[0]))
        return conversation

    def _write_conversation(self, conversation, idempotency_key: str, sql: str,
                            stored_owner: str | None = None) -> None:
        payload = conversation_payload(conversation, idempotency_key)
        kernel_session_id = str((payload["extras"] or {}).get("kernel_session_id") or "")
        # owner:update 走库内已有值(键/归属的真相源都在行上);create 用行上值
        # (create 前调用方已把 owner 填进 conversation)。
        owner = conversation.owner if stored_owner is None else stored_owner
        self._conn.execute(sql, (
            conversation.conversation_id, idempotency_key or None,
            conversation.skill_session_id, kernel_session_id or None, owner,
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

    def all_files(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(_ALL_FILES).fetchall()
        return [json.loads(text) for (text,) in rows]

    # ---------- 吊销名单(revoked_jti 表;IdentityService 注入用,不 import api) ----------

    def revoke_token(self, jti: str, exp: int) -> None:
        """吊销一枚 jti,并顺手清理已过期条目(06 §2.1 第 6 条:写时清,不积累)。

        INSERT OR REPLACE:同一 jti 再次登出幂等(不撞主键)。任何 sqlite3.Error
        原样抛出(fail-closed,与写路径同口径)——identity 吊销序先库后内存,
        库写失败即登出整体失败,绝不假报 ok。
        """
        now = int(time.time())
        with self._lock:
            self._conn.execute(_REVOKE_INSERT, (jti, exp))
            self._conn.execute(_REVOKE_DELETE_EXPIRED, (now,))

    def load_revoked(self, now: int) -> dict[str, int]:
        """启动全量加载:jti -> exp(已过期条目不在返回面)。06 §2.1 第 2 条:
        热路径每请求只碰 identity 内存,不碰 SQLite。"""
        with self._lock:
            rows = self._conn.execute(_REVOKE_LOAD, (now,)).fetchall()
        return {jti: exp for jti, exp in rows}
