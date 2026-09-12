"""store 包(02 §2 预定,M3 落地;会话表 + LearnerSession 持久化)。

SqliteStore(M3 DB 存储,PR #196 起为生产装配):一个类实现 ConversationStore
协议 + FileSessionStore 三操作 + files 表(文件元数据);两张 JSON blob 表,
幂等键/skill_session 下沉 UNIQUE 索引,单连接 + 单事务,写路径 fail-closed。
文件三实现退役为对照与回退:FileConversationStore(FileSessionStore 同款降级,
兼作迁移源——data/ 下 JSON 原件保留到人工确认清理)、MemoryConversationStore
(幂等键/skill_session 双索引、线程安全,接口即持久化的最小面)。
"""

from .conversations import ConversationStore, FileConversationStore
from .learner_sessions import FileSessionStore
from .sessions import Conversation, MemoryConversationStore
from .sqlite import SqliteStore

__all__ = ["Conversation", "ConversationStore", "FileConversationStore", "FileSessionStore",
           "MemoryConversationStore", "SqliteStore"]
