"""会话表(Conversation)的文件持久化(M3 WS2,00 §5.2 会话语义;02:仅 additive)。

`MemoryConversationStore` 是 v1(接口即持久化接口的最小面),本模块是同一接口的
文件实现:**一会话一 JSON**(`data/conversations/{conversation_id}.json`),
进程重启后 open→message→finish 仍可续(重启前 `_by_conversation` 丢空 →
`GET/POST /api/conversations/{id}` 全 404)。

三个取舍(都写在代码里,便于审查):
- **重启扫描建索引**:幂等键与 skill_session 两个索引不单独落索引文件,启动时
  扫一遍 JSON 重建——索引是派生态,``idempotency_key`` 随会话文件一起存即可,
  避免"索引文件与会话文件不一致"这类第二个真相源(马尾梯)。
- **内核会话对象不入本文件**:``extras["kernel_session"]`` 是 `LearnerSession`
  本体(非 JSON 可序列化),落盘时抽出为 ``extras["kernel_session_id"]``;
  本体由 `FileSessionStore` 单独存(一会话一文件),服务层读回时惰性 rehydrate。
  两份文件一份真相:session 文件是本体,conversation 文件只是路由与状态视图。
- **原子写**:tmp + ``os.replace``(#31/#FileSessionStore 同款),进程被杀不留半截 JSON;
  坏文件隔离跳过,不炸整个扫描。
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import fields
from pathlib import Path
from typing import Protocol

from .sessions import Conversation


class ConversationStore(Protocol):
    """会话表最小面(Memory/File 两实现共用;service 只依赖这五个操作)。"""

    def find_by_idempotency(self, idempotency_key: str) -> Conversation | None: ...
    def find_by_skill_session(self, skill_session_id: str) -> Conversation | None: ...
    def create(self, conversation: Conversation, idempotency_key: str) -> Conversation: ...
    def get(self, conversation_id: str) -> Conversation | None: ...
    def update(self, conversation: Conversation) -> None: ...


class FileConversationStore:
    """会话表 JSON 文件实现;启动扫描重建双索引,线程安全语义同内存版。"""

    def __init__(self, root: Path | str = "data/conversations") -> None:
        self.root = Path(root)
        self._lock = threading.Lock()
        self._by_conversation: dict[str, Conversation] = {}
        self._by_idempotency: dict[str, str] = {}
        self._by_skill_session: dict[str, str] = {}
        self._idempotency_of: dict[str, str] = {}  # conversation_id -> idempotency_key
        self._scan()

    # ---------- 启动扫描 ----------

    def _scan(self) -> None:
        """目录内全部会话恢复进内存索引;单文件损坏只跳过该文件。"""
        if not self.root.exists():
            return
        for path in sorted(self.root.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                conversation = Conversation(**{k: data[k] for k in (
                    "conversation_id", "question_id", "attempt_id", "skill_session_id",
                    "session_version", "state", "first_question", "summary") if k in data})
                conversation.extras = data.get("extras") or {}
            except (json.JSONDecodeError, OSError, TypeError, KeyError) as error:
                print(f"[store] 跳过损坏的会话文件:{path}({type(error).__name__})")
                continue
            self._index(conversation, str(data.get("idempotency_key") or ""))

    def _index(self, conversation: Conversation, idempotency_key: str) -> None:
        self._by_conversation[conversation.conversation_id] = conversation
        self._by_skill_session[conversation.skill_session_id] = conversation.conversation_id
        if idempotency_key:
            self._by_idempotency[idempotency_key] = conversation.conversation_id
            self._idempotency_of[conversation.conversation_id] = idempotency_key

    # ---------- 落盘 ----------

    def _write(self, conversation: Conversation) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{conversation.conversation_id}.json"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(self._payload(conversation), ensure_ascii=False),
                       encoding="utf-8")
        os.replace(tmp, path)

    def _payload(self, conversation: Conversation) -> dict:
        # 不能对 Conversation 用 dataclasses.asdict:它会**递归**把 extras 里的
        # LearnerSession 本体也转成 dict(AsdictVisitor),于是抽取 session_id 落空、
        # 重启后拿不到本体。逐字段取,extras 原样搬运再抽走本体。
        data = {f.name: getattr(conversation, f.name)
                for f in fields(conversation) if f.name != "extras"}
        extras = dict(conversation.extras or {})
        session = extras.pop("kernel_session", None)  # 本体由 FileSessionStore 存
        if session is not None:
            extras["kernel_session_id"] = getattr(session, "session_id", "")
        data["extras"] = extras
        key = self._idempotency_of.get(conversation.conversation_id)
        if key:
            data["idempotency_key"] = key
        return data

    # ---------- 会话表最小面(与 MemoryConversationStore 同语义) ----------

    def find_by_idempotency(self, idempotency_key: str) -> Conversation | None:
        with self._lock:
            conversation_id = self._by_idempotency.get(idempotency_key)
            return self._by_conversation.get(conversation_id) if conversation_id else None

    def find_by_skill_session(self, skill_session_id: str) -> Conversation | None:
        with self._lock:
            conversation_id = self._by_skill_session.get(skill_session_id)
            return self._by_conversation.get(conversation_id) if conversation_id else None

    def create(self, conversation: Conversation, idempotency_key: str) -> Conversation:
        with self._lock:
            existing = self._by_idempotency.get(idempotency_key)
            if existing:
                return self._by_conversation[existing]  # 同键幂等:返回既有会话
            self._index(conversation, idempotency_key)
            self._write(conversation)
            return conversation

    def get(self, conversation_id: str) -> Conversation | None:
        with self._lock:
            return self._by_conversation.get(conversation_id)

    def update(self, conversation: Conversation) -> None:
        with self._lock:
            self._by_conversation[conversation.conversation_id] = conversation
            self._by_skill_session[conversation.skill_session_id] = conversation.conversation_id
            self._write(conversation)
