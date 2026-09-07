"""api 包(00 §5.2 合作方接口面;03 §4 状态机的传输层)。

公开入口:build_service(store=None, kernel) / build_server(service)——测试与
评测线只从本入口取用(C 线铁律:api 不 import agents 包,内核经 Kernel 协议
注入,真内核由 B 线提供,测试注入确定性假内核)。healthz(04 §2.2)同在此包。
"""

from .identity import IdentityError, IdentityService
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


def build_service(kernel: Kernel,
                  store: MemoryConversationStore | None = None) -> ConversationService:
    return ConversationService(store or MemoryConversationStore(), kernel)
