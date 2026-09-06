"""model_call 事实记录(01 §7):每次调用一条 JSONL,按 UTC 天切分。

字段对齐 OTel GenAI 语义约定,约定未覆盖的以 edu.* 标明;不记录就等于没发生。
记录在调用自然结束或失败时写入;学生内容经 redact(长度+哈希)后才进记录。
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from ..errors import GatewayError
from ..request import CallContext, Handler, ModelRequest, ModelResponse, StreamEvent, StreamHandler
from .redact import redact_messages, redact_text


class FactWriter:
    """JSONL 追加写,按 UTC 天切分文件。"""

    # ponytail: 进程内一把锁;多进程部署时再换文件锁,单机单进程是 v1 部署形态
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self._lock = threading.Lock()

    def write(self, payload: dict) -> None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        target = self.root / f"model_calls-{day}.jsonl"
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as handle:
                handle.write(line)


def _ms_since(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def build_payload(
    request: ModelRequest,
    ctx: CallContext,
    *,
    response: ModelResponse | None = None,
    error: GatewayError | None = None,
    total_ms: int | None = None,
) -> dict:
    """§7 全字段:键固定、次序固定;内容只以长度+哈希进入 edu.redacted。"""
    redacted = redact_messages(request.messages)
    if response is not None:
        redacted.append({"role": "assistant", **redact_text(response.text)})
    payload = {
        "edu.call_id": uuid.uuid4().hex,
        "edu.ts": datetime.now(timezone.utc).isoformat(),
        "edu.role": request.role,
        "edu.attempt": ctx.attempt,
        "edu.outcome": "ok" if error is None else error.failure.value,
        "edu.session_id": request.session_id,
        "edu.fallback_from": ctx.fallback_from,
        "edu.fallback_to": ctx.fallback_to,
        "edu.redacted": redacted,
        "edu.trace_id": request.trace_id,
        "edu.queue_ms": ctx.queue_ms,
        "edu.error_detail": None if error is None else error.detail,
        "gen_ai.provider.name": ctx.provider_name,
        "gen_ai.request.model": ctx.request_model,
        "gen_ai.response.model": response.model if response else None,
        "gen_ai.usage.input_tokens": response.input_tokens if response else None,
        "gen_ai.usage.output_tokens": response.output_tokens if response else None,
        "gen_ai.usage.cache_read.input_tokens": response.cache_read_input_tokens if response else None,
        "gen_ai.response.finish_reasons": [response.finish_reason] if response and response.finish_reason else None,
        "gen_ai.server.time_to_first_token": ctx.ttft_ms,
        "edu.total_ms": total_ms,
    }
    return payload


def with_record_invoke(writer: FactWriter):
    def wrap(inner: Handler) -> Handler:
        def handler(request: ModelRequest, ctx: CallContext) -> ModelResponse:
            start = time.monotonic()
            try:
                response = inner(request, ctx)
            except GatewayError as error:
                writer.write(build_payload(request, ctx, error=error, total_ms=_ms_since(start)))
                raise
            writer.write(build_payload(request, ctx, response=response, total_ms=_ms_since(start)))
            return response

        return handler

    return wrap


def with_record_stream(writer: FactWriter):
    def wrap(inner: StreamHandler) -> StreamHandler:
        def handler(request: ModelRequest, ctx: CallContext) -> Iterator[StreamEvent]:
            start = time.monotonic()
            response = None
            try:
                for event in inner(request, ctx):
                    if event.kind == "done" and event.response is not None:
                        response = event.response
                    yield event
            except GatewayError as error:
                writer.write(build_payload(request, ctx, error=error, total_ms=_ms_since(start)))
                raise
            writer.write(build_payload(request, ctx, response=response, total_ms=_ms_since(start)))

        return handler

    return wrap
