"""调用数据类(01 §3):请求/响应/流事件,以及中间件链共享的调用上下文。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from .errors import GatewayError


@dataclass(slots=True)
class ModelRequest:
    """一次模型调用。messages 为 OpenAI chat 格式;response_schema 触发路线 1(issue #8)。"""

    role: str
    messages: list[dict]
    response_schema: dict | None = None
    session_id: str | None = None
    trace_id: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None


@dataclass(slots=True)
class ModelResponse:
    text: str
    model: str | None = None
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_input_tokens: int | None = None


@dataclass(slots=True)
class StreamEvent:
    """kind="token" 携带增量文本;kind="done" 携带完整响应(usage/finish_reason)。"""

    kind: str
    text: str = ""
    response: ModelResponse | None = None


@dataclass
class CallContext:
    """中间件链共享的调用上下文。

    attempt 与 model_attempts 由 provider 递增,计实际发出的 HTTP 调用数;
    edu.attempt==1 且 ok 即"首次成功"(01 §6 指标口径)。
    """

    provider_name: str
    request_model: str  # models.yaml 条目 id(事实记录里的请求模型)
    model_name: str     # 发给服务端的模型名
    current_model: str  # 当前条目 id,备选切换后变化(01 §3 fallback)
    attempt: int = 0
    model_attempts: dict[str, int] = field(default_factory=dict)
    queue_ms: int = 0
    fallback_from: str | None = None
    fallback_to: str | None = None
    ttft_ms: int | None = None
    request_sent_at: float | None = None
    first_token_deadline: float | None = None
    total_deadline: float | None = None
    repair: GatewayError | None = None  # 路线 1 修复重试携带上一次违规


Handler = Callable[[ModelRequest, CallContext], ModelResponse]
StreamHandler = Callable[[ModelRequest, CallContext], Iterator[StreamEvent]]
