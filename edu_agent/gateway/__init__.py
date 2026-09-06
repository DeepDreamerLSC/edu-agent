"""gateway 入口(01 §3):invoke / stream。

链序固定:registry → ratelimit → retry → fallback → timeout → provider,
响应侧 redact → record(内容经长度+哈希后才进事实记录)。
本 PR 落地 timeout/redact/record 与 provider;ratelimit/retry/fallback 见后续 PR,插入点即上序。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

import httpx

from .errors import FailureType, GatewayError
from .middleware.record import FactWriter, with_record_invoke, with_record_stream
from .middleware.timeout import with_timeouts
from .providers.openai_compatible import invoke_handler, stream_handler
from .registry import (
    ModelConfig,
    ModelRegistry,
    ProviderConfig,
    RegistryError,
    RoleConfig,
    load_registry,
)
from .request import (
    CallContext,
    ModelRequest,
    ModelResponse,
    StreamEvent,
)

__all__ = [
    "FailureType",
    "FactWriter",
    "Gateway",
    "GatewayError",
    "ModelConfig",
    "ModelRequest",
    "ModelResponse",
    "ProviderConfig",
    "ModelRegistry",
    "RegistryError",
    "RoleConfig",
    "StreamEvent",
    "invoke",
    "load_registry",
    "stream",
]

_REPO_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "models.yaml"


class Gateway:
    """按 01 §3 组装调用链;一个实例可跨调用复用(线程安全)。"""

    def __init__(self, registry: ModelRegistry, facts_dir: Path | str = "facts") -> None:
        self.registry = registry
        self.writer = FactWriter(facts_dir)
        self._clients: dict[str, httpx.Client] = {}

    def close(self) -> None:
        for client in self._clients.values():
            client.close()
        self._clients.clear()

    def _client(self, provider: ProviderConfig) -> httpx.Client:
        client = self._clients.get(provider.name)
        if client is None:
            client = httpx.Client()
            self._clients[provider.name] = client
        return client

    def _api_key(self, provider: ProviderConfig) -> str | None:
        if provider.api_key_env is None:
            return None
        key = os.environ.get(provider.api_key_env)
        if not key:
            # 凭据只走环境变量(01 §10/issue #3):缺失即快速失败,不降级、不进日志
            raise RegistryError(f"环境变量 {provider.api_key_env} 未设置(provider {provider.name})")
        return key

    def _prepare(self, request: ModelRequest) -> tuple[RoleConfig, ModelConfig, CallContext]:
        role = self.registry.role(request.role)
        if request.response_schema is not None and not role.json_strict:
            raise RegistryError(f"角色 '{role.name}' 未声明 json_strict,不接受带 schema 的请求(01 §8)")
        model = self.registry.model(role.primary)
        provider = self.registry.provider(model.provider)
        ctx = CallContext(
            provider_name=provider.name,
            request_model=model.id,
            model_name=model.name,
            current_model=model.id,
        )
        return role, model, ctx

    def invoke(self, request: ModelRequest) -> ModelResponse:
        role, model, ctx = self._prepare(request)
        provider = self.registry.provider(model.provider)
        handler = invoke_handler(self._client(provider), provider.base_url, self._api_key(provider), model.name)
        handler = with_timeouts(None, role.total_timeout_s, stream=False)(handler)
        handler = with_record_invoke(self.writer)(handler)
        return handler(request, ctx)

    def stream(self, request: ModelRequest) -> Iterator[StreamEvent]:
        role, model, ctx = self._prepare(request)
        provider = self.registry.provider(model.provider)
        handler = stream_handler(self._client(provider), provider.base_url, self._api_key(provider), model.name)
        handler = with_timeouts(role.first_token_timeout_s, role.total_timeout_s, stream=True)(handler)
        handler = with_record_stream(self.writer)(handler)
        return handler(request, ctx)


@lru_cache(maxsize=1)
def default_gateway() -> Gateway:
    """模块级入口的默认实例:配置与事实目录可用环境变量覆盖。"""
    config = os.environ.get("EDU_MODELS_YAML") or str(_REPO_CONFIG)
    facts = os.environ.get("EDU_FACTS_DIR") or "facts"
    return Gateway(load_registry(Path(config)), facts)


def invoke(request: ModelRequest) -> ModelResponse:
    return default_gateway().invoke(request)


def stream(request: ModelRequest) -> Iterator[StreamEvent]:
    return default_gateway().stream(request)
