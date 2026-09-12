"""store 包(02 §2 预定,M3 落地;会话表 + LearnerSession 持久化)。

MemoryConversationStore:幂等键/skill_session 双索引、线程安全,接口即持久化的
最小面;FileConversationStore(M3 WS2):同一接口的文件实现,重启后会话可续;
FileSessionStore(M3 PR6):LearnerSession 一会话一 JSON 文件,additive-only
(00 §5.2 上下文保留);SqliteStore(M3 DB 存储):同一组接口的 SQLite 实现
(两张 JSON blob 表 + 3 索引;单连接 + 单事务,写路径 fail-closed),service
注入位不变,文件实现保留供回退与对照。
"""

from .conversations import ConversationStore, FileConversationStore
from .learner_sessions import FileSessionStore
from .sessions import Conversation, MemoryConversationStore
from .sqlite import SqliteStore

__all__ = ["Conversation", "ConversationStore", "FileConversationStore", "FileSessionStore",
           "MemoryConversationStore", "SqliteStore"]
