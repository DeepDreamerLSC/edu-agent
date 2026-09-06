"""OpenAI 兼容 provider(01 §2.2):唯一必需协议;含流式 SSE、usage、九种失败映射与路线 1 校验。"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator

import httpx
import jsonschema

from ..errors import FailureType, GatewayError
from ..request import CallContext, Handler, ModelRequest, ModelResponse, StreamEvent, StreamHandler

_DONE = "[DONE]"
_SCHEMA_INSTRUCTION = "只输出一个 JSON 对象,不要围栏、不要解释,严格遵守以下 JSON Schema:\n{schema}"
_REPAIR_HINT = (
    "你的上一条输出不符合要求的 JSON Schema。错误:{errors}\n"
    "请重新输出:只输出一个符合该 Schema 的 JSON 对象,不要围栏、不要解释:\n{schema}"
)


def _headers(api_key: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def build_messages(request: ModelRequest, repair: GatewayError | None) -> list[dict]:
    """路线 1(issue #8):schema 附进 prompt;修复重试时附上违规原文与修复提示。"""
    if request.response_schema is None:
        return request.messages
    schema_text = json.dumps(request.response_schema, ensure_ascii=False)
    if repair is None:
        instruction = _SCHEMA_INSTRUCTION.format(schema=schema_text)
        return [*request.messages, {"role": "user", "content": instruction}]
    hint = _REPAIR_HINT.format(errors=repair.detail, schema=schema_text)
    return [
        *request.messages,
        {"role": "assistant", "content": repair.output or ""},
        {"role": "user", "content": hint},
    ]


def validate_schema(schema: dict, text: str) -> None:
    """路线 1 的本地校验(01 §8/issue #8):不合规抛 schema_violation;detail 不含输出原文。"""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GatewayError(
            FailureType.SCHEMA_VIOLATION, f"输出不是合法 JSON({exc.msg})", output=text
        ) from exc
    validator = jsonschema.validators.validator_for(schema)(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.path))
    if errors:
        summary = "; ".join(
            f"{'/'.join(str(p) for p in err.path) or '<root>'} {err.validator}" for err in errors[:5]
        )
        raise GatewayError(FailureType.SCHEMA_VIOLATION, summary, output=text)


def _body(request: ModelRequest, ctx: CallContext, model_name: str, stream: bool) -> dict:
    body: dict = {
        "model": model_name,
        "messages": build_messages(request, ctx.repair),
        "stream": stream,
    }
    if stream:
        body["stream_options"] = {"include_usage": True}
    if request.max_tokens is not None:
        body["max_tokens"] = request.max_tokens
    if request.temperature is not None:
        body["temperature"] = request.temperature
    return body


def _http_timeout(ctx: CallContext, stream: bool) -> httpx.Timeout:
    """读超时 = 剩余总预算;流式在首 token 前按首 token 窗口收口,其余边界由期限检查兜底。"""
    now = time.monotonic()
    remaining = (ctx.total_deadline - now) if ctx.total_deadline else 300.0
    read = remaining
    if stream and ctx.first_token_deadline:
        read = max(ctx.first_token_deadline - now, 0.05)
    return httpx.Timeout(read, connect=10.0, write=10.0, pool=10.0)


def check_deadlines(ctx: CallContext, *, first_token: bool) -> None:
    """在 IO 边界检查期限(01 §3 timeout:总超时 + 首 token 超时)。"""
    now = time.monotonic()
    if (
        first_token
        and ctx.ttft_ms is None
        and ctx.first_token_deadline is not None
        and now > ctx.first_token_deadline
    ):
        raise GatewayError(FailureType.TIMEOUT_FIRST_TOKEN, "首 token 超时")
    if ctx.total_deadline is not None and now > ctx.total_deadline:
        raise GatewayError(FailureType.TIMEOUT_TOTAL, "总时长超时")


def _map_transport_error(exc: Exception, ctx: CallContext, stream: bool) -> GatewayError:
    if isinstance(exc, httpx.ConnectTimeout):
        return GatewayError(FailureType.CONNECTION, "连接超时")
    if isinstance(exc, httpx.ReadTimeout):
        kind = (
            FailureType.TIMEOUT_FIRST_TOKEN
            if stream and ctx.ttft_ms is None
            else FailureType.TIMEOUT_TOTAL
        )
        return GatewayError(kind, "读超时")
    if isinstance(exc, httpx.TimeoutException):
        return GatewayError(FailureType.CONNECTION, "发送/池超时")
    return GatewayError(FailureType.CONNECTION, f"连接中断({type(exc).__name__})")


def _retry_after(headers) -> float | None:
    value = headers.get("Retry-After")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _status_error(status: int, headers) -> GatewayError:
    if status == 429:
        return GatewayError(
            FailureType.RATE_LIMITED, "HTTP 429", status=429, retry_after=_retry_after(headers)
        )
    if status >= 500:
        return GatewayError(FailureType.UPSTREAM_5XX, f"HTTP {status}", status=status)
    return GatewayError(FailureType.UPSTREAM_4XX, f"HTTP {status}", status=status)


def _usage_fields(usage: dict) -> tuple[int | None, int | None, int | None]:
    cache_read = (usage.get("prompt_tokens_details") or {}).get("cache_read_input_tokens")
    if cache_read is None:
        cache_read = usage.get("prompt_cache_hit_tokens")  # DeepSeek 命名(issue #3)
    return usage.get("prompt_tokens"), usage.get("completion_tokens"), cache_read


def _parse_completion(payload: dict) -> ModelResponse:
    choice = payload["choices"][0]
    input_tokens, output_tokens, cache_read = _usage_fields(payload.get("usage") or {})
    return ModelResponse(
        text=choice.get("message", {}).get("content") or "",
        model=payload.get("model"),
        finish_reason=choice.get("finish_reason"),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=cache_read,
    )


def _finish_reason_error(response: ModelResponse) -> GatewayError | None:
    if response.finish_reason == "length":
        return GatewayError(FailureType.TRUNCATED, "finish_reason=length")
    if response.finish_reason == "content_filter":
        return GatewayError(FailureType.CONTENT_FILTERED, "finish_reason=content_filter")
    return None


def _begin_attempt(ctx: CallContext) -> None:
    ctx.attempt += 1
    ctx.model_attempts[ctx.current_model] = ctx.model_attempts.get(ctx.current_model, 0) + 1


def invoke_handler(client: httpx.Client, base_url: str, api_key: str | None,
                   model_name: str) -> Handler:
    """最内层处理器:一次非流式 chat completion。"""

    def handler(request: ModelRequest, ctx: CallContext) -> ModelResponse:
        _begin_attempt(ctx)
        check_deadlines(ctx, first_token=False)
        ctx.request_sent_at = time.monotonic()
        try:
            resp = client.post(
                f"{base_url}/chat/completions",
                json=_body(request, ctx, model_name, stream=False),
                headers=_headers(api_key),
                timeout=_http_timeout(ctx, stream=False),
            )
        except httpx.TransportError as exc:
            raise _map_transport_error(exc, ctx, stream=False) from exc
        if resp.status_code != 200:
            raise _status_error(resp.status_code, resp.headers)
        try:
            response = _parse_completion(resp.json())
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise GatewayError(FailureType.UPSTREAM_5XX, "响应不是合法的 chat completion") from exc
        if error := _finish_reason_error(response):
            raise error
        if request.response_schema is not None:
            validate_schema(request.response_schema, response.text)
        return response

    return handler


def stream_handler(client: httpx.Client, base_url: str, api_key: str | None,
                   model_name: str) -> StreamHandler:
    """最内层流式处理器:SSE 逐行解析,首 token 记 TTFT,结尾做 finish_reason 与 schema 校验。"""

    def handler(request: ModelRequest, ctx: CallContext) -> Iterator[StreamEvent]:
        _begin_attempt(ctx)
        check_deadlines(ctx, first_token=True)
        ctx.request_sent_at = time.monotonic()
        try:
            with client.stream(
                "POST",
                f"{base_url}/chat/completions",
                json=_body(request, ctx, model_name, stream=True),
                headers=_headers(api_key),
                timeout=_http_timeout(ctx, stream=True),
            ) as resp:
                if resp.status_code != 200:
                    resp.read()
                    raise _status_error(resp.status_code, resp.headers)
                yield from _iterate_sse(resp, request, ctx)
        except httpx.TransportError as exc:
            raise _map_transport_error(exc, ctx, stream=True) from exc

    return handler


def _iterate_sse(resp: httpx.Response, request: ModelRequest,
                 ctx: CallContext) -> Iterator[StreamEvent]:
    parts: list[str] = []
    finish_reason = None
    usage: dict = {}
    model = None
    done_seen = False
    for line in resp.iter_lines():
        check_deadlines(ctx, first_token=True)
        if not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if data == _DONE:
            done_seen = True
            break
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError as exc:
            raise GatewayError(FailureType.UPSTREAM_5XX, "SSE chunk 非法 JSON") from exc
        model = chunk.get("model") or model
        usage = chunk.get("usage") or usage
        choices = chunk.get("choices") or []
        if not choices:
            continue
        finish_reason = choices[0].get("finish_reason") or finish_reason
        text = (choices[0].get("delta") or {}).get("content") or ""
        if not text:
            continue
        if ctx.ttft_ms is None and ctx.request_sent_at is not None:
            # 01 §5/issue #3:TTFT = 请求发出到首个含 content 的 chunk
            ctx.ttft_ms = int((time.monotonic() - ctx.request_sent_at) * 1000)
        parts.append(text)
        yield StreamEvent(kind="token", text=text)
    if not done_seen:
        raise GatewayError(FailureType.CONNECTION, "流式中断(未收到 [DONE])")
    input_tokens, output_tokens, cache_read = _usage_fields(usage)
    response = ModelResponse(
        text="".join(parts),
        model=model,
        finish_reason=finish_reason,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=cache_read,
    )
    if error := _finish_reason_error(response):
        raise error
    if request.response_schema is not None:
        validate_schema(request.response_schema, response.text)
    yield StreamEvent(kind="done", response=response)
