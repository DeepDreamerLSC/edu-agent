"""store 包(02 §2 预定,M3 落地;v1 为内存实现)。

v1 内存会话表(MemoryConversationStore):幂等键/skill_session 双索引、线程安全;
接口即未来持久化的最小面(03 §4 状态的持久层载体,additive 迁移)。
"""

from .sessions import Conversation, MemoryConversationStore

__all__ = ["Conversation", "MemoryConversationStore"]
