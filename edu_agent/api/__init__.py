"""api 包(00 §5.2 合作方接口面;03 §4 状态机的传输层)。

公开入口:build_service(store, kernel, source=None) / build_server(service) /
partner_service()——测试与评测线只从本入口取用。M3 前置起 api 经
kernel_adapter 桥接 agents.small_lecturer 真内核(02 §2.2 未禁 api→agents;
gateway 经构造注入,CI 用假 gateway 零真实模型)。identity/healthz 同在此包。
"""

from .identity import IdentityError, IdentityService
from .identity import IdentityService
from .kernel_adapter import SmallLecturerKernel
from .question_source import SeedQuestionSource, SnapshotQuestionSource, question_source
from .service import ApiError, ConversationService, Kernel
from .server import build_server
from edu_agent.store import MemoryConversationStore

__all__ = [
    "ApiError", "ConversationService", "SnapshotQuestionSource", "IdentityError",
    "IdentityService", "Kernel", "SeedQuestionSource", "SmallLecturerKernel",
    "build_server", "build_service", "question_source",
]


def build_service(kernel: Kernel, store: MemoryConversationStore | None = None,
                  source=None) -> ConversationService:
    return ConversationService(store or MemoryConversationStore(), kernel, source)


def partner_service() -> ConversationService:
    """可运行入口装配(M3 前置 PR1):真内核(default_gateway)+题源(EDU_QUESTION_SOURCE 切换)。"""
    from .kernel_adapter import SmallLecturerKernel
    from .question_source import question_source as _source

    return build_service(SmallLecturerKernel(), source=_source())
