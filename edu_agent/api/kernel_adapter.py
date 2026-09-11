"""真内核适配器(M3 前置 PR1):把 agents.small_lecturer 三函数包装成 api 的 Kernel 协议。

api→agents 方向未受限(02 §2.2 只禁 gateway→agents 与 agents→api/store);
gateway 经构造注入(CI 用假 gateway,零真实模型);错误按 #34 映射表落合同码:
网关失败(超时/断连/5xx/限流/内容违规)→ 503;版本冲突/终态语义 → 409。
"""

from __future__ import annotations

from edu_agent.agents.small_lecturer import finish as kernel_finish
from edu_agent.agents.small_lecturer import reply as kernel_reply
from edu_agent.agents.small_lecturer import start as kernel_start
from edu_agent.agents.small_lecturer.session import (
    SessionVersionConflict,
    TerminalStateError,
)
from edu_agent.gateway import Gateway, GatewayError

from .service import ApiError


class SmallLecturerKernel:
    """Kernel 协议实现:题面 dict(含 text/image)+ learner → 真内核三函数。"""

    name = "small_lecturer_kernel"

    def __init__(self, gateway: Gateway | None = None) -> None:
        self.gateway = gateway

    def start(self, question: dict, learner: dict) -> object:
        try:
            return kernel_start(question, learner, gateway=self.gateway)
        except ApiError:
            raise
        except Exception as error:
            raise self._map(error) from error

    def reply(self, session: object, student_message: str) -> object:
        try:
            return kernel_reply(session, student_message, gateway=self.gateway)
        except ApiError:
            raise
        except SessionVersionConflict as error:
            raise ApiError(409, "SKILL_SESSION_CONFLICT",
                           f"会话版本过期,读取最新 interaction 后由学生决定是否重发:{error}") from error
        except TerminalStateError as error:
            # 审查 P2:vision fail-closed 后追问等"终态后操作"是 409(客户端可自愈),
            # 不是 503 基础设施故障
            raise ApiError(409, "SKILL_SESSION_CONFLICT", f"会话已终态:{error}") from error
        except Exception as error:
            raise self._map(error) from error

    def finish(self, session: object) -> object:
        try:
            return kernel_finish(session, gateway=self.gateway)
        except ApiError:
            raise
        except TerminalStateError as error:
            raise ApiError(409, "SKILL_SESSION_CONFLICT", f"会话已终态:{error}") from error
        except Exception as error:
            raise self._map(error) from error

    @staticmethod
    def _map(error: Exception) -> ApiError:
        """网关失败按失败类型映射合同错误码表(#34 / A 线 §8.5):模型基础设施
        故障 → 503。GatewayError(connection/timeout 族等九型)是显式分支:消息带
        失败类型值(01 §4 枚举),可观测不发明——九型统一 503,不做逐型细分。"""
        if isinstance(error, GatewayError):
            return ApiError(503, None, f"服务暂不可用:{error.failure.value}")
        return ApiError(503, None, f"服务暂不可用:{type(error).__name__}")
