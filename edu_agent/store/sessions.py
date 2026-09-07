"""会话存储的 v1 内存实现(00 §5.2 会话语义;03 §4 状态的持久层载体)。

M3 才引入真持久化(02:store 是 M3 包,additive 迁移);v1 内存 dict 即够
评测与合同回放。幂等键 → 会话的唯一映射在 open 语义里由 service 层保证,
本模块只提供无歧义的存取原子操作。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class Conversation:
    conversation_id: str
    question_id: str
    attempt_id: str
    skill_session_id: str
    session_version: int = 1
    state: str = "preparing"          # 03 §4:preparing→first_question_ready→dialogue→…
    first_question: str | None = None
    summary: dict | None = None       # confirm 后写入,不可变(completed 终态)
    extras: dict = field(default_factory=dict)


class MemoryConversationStore:
    """线程安全的内存会话表;接口即未来持久化接口的最小面。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_conversation: dict[str, Conversation] = {}
        self._by_idempotency: dict[str, str] = {}  # idempotency_key -> conversation_id
        self._by_skill_session: dict[str, str] = {}  # skill_session_id -> conversation_id

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
            self._by_conversation[conversation.conversation_id] = conversation
            self._by_idempotency[idempotency_key] = conversation.conversation_id
            self._by_skill_session[conversation.skill_session_id] = conversation.conversation_id
            return conversation

    def get(self, conversation_id: str) -> Conversation | None:
        with self._lock:
            return self._by_conversation.get(conversation_id)

    def update(self, conversation: Conversation) -> None:
        with self._lock:
            self._by_conversation[conversation.conversation_id] = conversation
