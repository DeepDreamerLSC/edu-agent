"""主选失败按策略切备选(01 §4):触发阈值见 errors.FALLBACK_AFTER_FAILURES。

本调用内粘住备选:外层 retry 重入时不再回到已判定失败的主选。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from ..errors import FALLBACK_AFTER_FAILURES, GatewayError
from ..registry import ModelConfig
from ..request import CallContext, Handler, ModelRequest, ModelResponse, StreamEvent, StreamHandler


def eligible(error: GatewayError, ctx: CallContext) -> bool:
    threshold = FALLBACK_AFTER_FAILURES.get(error.failure)
    if threshold is None:
        return False
    return ctx.model_attempts.get(ctx.current_model, 0) >= threshold


def _switch(ctx: CallContext, primary_id: str, fallback_id: str) -> None:
    ctx.fallback_from = primary_id
    ctx.fallback_to = fallback_id
    ctx.current_model = fallback_id


def with_fallback_invoke(primary: ModelConfig, fallback: ModelConfig,
                         make_handler: Callable[[ModelConfig], Handler]):
    fb_handler: Handler | None = None

    def _get_fb() -> Handler:
        # 惰性构造:主选失败切备选时才调 make_handler(否则缺云凭据的环境
        # 连本地主选调用都被装配期急切构造堵死——#113 P2)
        nonlocal fb_handler
        if fb_handler is None:
            fb_handler = make_handler(fallback)
        return fb_handler

    def wrap(inner: Handler) -> Handler:
        def handler(request: ModelRequest, ctx: CallContext) -> ModelResponse:
            current = inner if ctx.current_model == primary.id else _get_fb()
            try:
                return current(request, ctx)
            except GatewayError as error:
                if ctx.current_model != primary.id or not eligible(error, ctx):
                    raise
                _switch(ctx, primary.id, fallback.id)
                return _get_fb()(request, ctx)

        return handler

    return wrap


def with_fallback_stream(primary: ModelConfig, fallback: ModelConfig,
                         make_handler: Callable[[ModelConfig], StreamHandler]):
    fb_handler: StreamHandler | None = None

    def _get_fb() -> StreamHandler:
        # 惰性构造,理由同 with_fallback_invoke(#113 P2)
        nonlocal fb_handler
        if fb_handler is None:
            fb_handler = make_handler(fallback)
        return fb_handler

    def wrap(inner: StreamHandler) -> StreamHandler:
        def handler(request: ModelRequest, ctx: CallContext) -> Iterator[StreamEvent]:
            current = inner if ctx.current_model == primary.id else _get_fb()
            produced = False
            try:
                for event in current(request, ctx):
                    produced = True
                    yield event
                return
            except GatewayError as error:
                if produced or ctx.current_model != primary.id or not eligible(error, ctx):
                    raise
                _switch(ctx, primary.id, fallback.id)
                yield from _get_fb()(request, ctx)

        return handler

    return wrap
