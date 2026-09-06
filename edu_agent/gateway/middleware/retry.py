"""按失败类型重试(01 §4):指数退避+抖动;rate_limited 读 Retry-After;schema_violation 恰一次修复重试。

流式仅在未向调用方吐出任何事件时可重试(已吐出后重试会重复输出)。
"""

from __future__ import annotations

import random
import time
from collections.abc import Iterator

from ..errors import RETRYABLE, FailureType, GatewayError
from ..registry import RoleConfig
from ..request import CallContext, Handler, ModelRequest, ModelResponse, StreamEvent, StreamHandler


def _retryable(error: GatewayError, ctx: CallContext, role: RoleConfig) -> bool:
    if error.failure not in RETRYABLE:
        return False
    if error.failure is FailureType.SCHEMA_VIOLATION:
        # 修复重试恰一次(01 §4/issue #8),次数由文档定,不受 max_attempts 影响
        return ctx.repair is None
    return ctx.attempt < role.max_attempts


def _sleep_s(error: GatewayError, ctx: CallContext, role: RoleConfig) -> float:
    if error.failure is FailureType.RATE_LIMITED and error.retry_after is not None:
        return error.retry_after
    failures = ctx.model_attempts.get(ctx.current_model, 1)
    base = role.backoff_base_ms / 1000
    capped = min(base * (2 ** (failures - 1)), role.backoff_cap_ms / 1000)
    return capped + random.uniform(0, base)


def _note_repair(error: GatewayError, ctx: CallContext) -> None:
    if error.failure is FailureType.SCHEMA_VIOLATION:
        ctx.repair = error


def with_retry_invoke(role: RoleConfig):
    def wrap(inner: Handler) -> Handler:
        def handler(request: ModelRequest, ctx: CallContext) -> ModelResponse:
            while True:
                try:
                    return inner(request, ctx)
                except GatewayError as error:
                    if not _retryable(error, ctx, role):
                        raise
                    time.sleep(_sleep_s(error, ctx, role))
                    _note_repair(error, ctx)

        return handler

    return wrap


def with_retry_stream(role: RoleConfig):
    def wrap(inner: StreamHandler) -> StreamHandler:
        def handler(request: ModelRequest, ctx: CallContext) -> Iterator[StreamEvent]:
            while True:
                produced = False
                try:
                    for event in inner(request, ctx):
                        produced = True
                        yield event
                    return
                except GatewayError as error:
                    if produced or not _retryable(error, ctx, role):
                        raise
                    time.sleep(_sleep_s(error, ctx, role))
                    _note_repair(error, ctx)

        return handler

    return wrap
