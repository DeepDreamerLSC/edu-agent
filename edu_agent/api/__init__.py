"""api 包(00 §5.2 合作方接口面;03 §4 状态机的传输层)。

公开入口:build_service(store, kernel, source=None, sessions=None) / build_server(service)
/ partner_service()——测试与评测线只从本入口取用。M3 前置起 api 经 kernel_adapter
桥接 agents.small_lecturer 真内核(02 §2.2 未禁 api→agents;gateway 经构造注入,
CI 用假 gateway 零真实模型)。store 类型经本入口再导出(便捷面;store 自 02 §7
结构性改动后已是测试公开入口,测试可直连 edu_agent.store)。identity/healthz 同在此包。
"""

from .identity import IdentityError, IdentityService, demo_login
from .files import FileService
from .identity import IdentityService
from .kernel_adapter import SmallLecturerKernel
from .question_source import SeedQuestionSource, SnapshotQuestionSource, question_source
from .service import ApiError, ConversationService, Kernel
from .server import build_server
from edu_agent.store import Conversation, FileSessionStore, MemoryConversationStore

__all__ = [
    "ApiError", "Conversation", "ConversationService", "FileService", "FileSessionStore",
    "SnapshotQuestionSource", "IdentityError", "IdentityService", "Kernel", "demo_login",
    "MemoryConversationStore", "SeedQuestionSource", "SmallLecturerKernel",
    "build_server", "build_service", "question_source",
]


def build_service(kernel: Kernel, store: MemoryConversationStore | None = None,
                  source=None, sessions: FileSessionStore | None = None,
                  image_resolver=None) -> ConversationService:
    """source 注入题源(PR1);sessions 注入即开启上下文保留(M3 PR6:内核会话回合后落盘)。

    image_resolver 注入题图解析(file_id → data URL;生产装配传 FileService.data_url,
    未注入时题图引用原样透传——测试/评测假网关路径不依赖文件存储)。"""
    return ConversationService(store or MemoryConversationStore(), kernel,
                               source=source, sessions=sessions,
                               image_resolver=image_resolver)


def partner_service() -> ConversationService:
    """可运行入口装配(M3 前置 PR1):真内核(default_gateway)+题源(EDU_QUESTION_SOURCE 切换)。"""
    from .kernel_adapter import SmallLecturerKernel
    from .question_source import question_source as _source

    return build_service(SmallLecturerKernel(), source=_source())
