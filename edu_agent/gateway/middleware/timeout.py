"""总超时 + 首 token 超时(01 §3、§4):期限写进 ctx,由 provider 在 IO 边界检查。

期限从进入本中间件起算(在 ratelimit 内侧,排队时间不计,与 edu.queue_ms 分离)。
"""

from __future__ import annotations

import time
from collections.abc import Iterator

from ..errors import FailureType, GatewayError
from ..request import CallContext, Handler, ModelRequest, ModelResponse, StreamEvent, StreamHandler


def with_timeouts(first_token_s: float | None, total_s: float, *, stream: bool):
    """first_token_s 仅流式路径生效(01 §5:invoke 没有首 token 事件)。"""

    def wrap(inner: Handler | StreamHandler) -> Handler | StreamHandler:
        if not stream:

            def handler(request: ModelRequest, ctx: CallContext) -> ModelResponse:
                _arm(ctx, first_token_s, total_s)
                response = inner(request, ctx)
                _check_total(ctx)
                return response

            return handler

        def streaming(request: ModelRequest, ctx: CallContext) -> Iterator[StreamEvent]:
            _arm(ctx, first_token_s, total_s)
            for event in inner(request, ctx):
                yield event
            _check_total(ctx)

        return streaming

    return wrap


def _arm(ctx: CallContext, first_token_s: float | None, total_s: float) -> None:
    now = time.monotonic()
    ctx.total_deadline = now + total_s
    ctx.first_token_deadline = now + first_token_s if first_token_s is not None else None


def _check_total(ctx: CallContext) -> None:
    if ctx.total_deadline is not None and time.monotonic() > ctx.total_deadline:
        raise GatewayError(FailureType.TIMEOUT_TOTAL, "总时长超时")
