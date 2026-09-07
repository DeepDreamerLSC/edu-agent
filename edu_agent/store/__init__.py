"""store 包(02 §2 预定,M3 落地;内存会话表 + LearnerSession 文件持久化)。

MemoryConversationStore:幂等键/skill_session 双索引、线程安全,接口即持久化的
最小面;FileSessionStore(M3 PR6):LearnerSession 一会话一 JSON 文件,
additive-only(00 §5.2 上下文保留,不用数据库)。
"""

from .learner_sessions import FileSessionStore
from .sessions import Conversation, MemoryConversationStore

__all__ = ["Conversation", "FileSessionStore", "MemoryConversationStore"]
