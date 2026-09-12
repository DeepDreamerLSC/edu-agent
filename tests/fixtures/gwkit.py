"""tests/gateway 公共工具(02 §6 tests/fixtures:不计测试比分子)。

指向假上游的最小 models 配置与 Gateway 构造、事实记录读取助手
(facts_line/facts_rows)、假上游生命周期上下文(fake_gateway)与共享常量
(SECRET/SCHEMA/FACT_FIELDS)。原在 tests/gateway/gwkit.py,收拢进 fixtures
(与 partner_api.py 同款决策:共享助手下移出比值分子)。
只导入公开入口 edu_agent.gateway。

谁在用:tests/gateway 全目录、tests/evals 的 test_judge、
tests/e2e 的 test_golden_path(gateway_for/常量)。
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from fake_openai import FakeOpenAI

from edu_agent.gateway import (
    Gateway,
    ModelConfig,
    ModelRegistry,
    ProviderConfig,
    RoleConfig,
    load_registry,
)

REPO_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "models.yaml"

# 学生敏感内容样本(invoke/脱敏合同共用)
SECRET = "学生姓名是小明,就读三年级二班"
# 路线 1 本地校验用的最小 JSON Schema(issue #8)
SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}
# 01 §7 事实记录全字段(键与次序固定;invoke 的集合断言与 e2e 的逐字段断言共用一份)
FACT_FIELDS = (
    "edu.call_id", "edu.ts", "edu.role", "edu.attempt", "edu.outcome",
    "edu.session_id", "edu.fallback_from", "edu.fallback_to", "edu.redacted",
    "edu.trace_id", "edu.queue_ms", "edu.error_detail",
    "gen_ai.provider.name", "gen_ai.request.model", "gen_ai.response.model",
    "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
    "gen_ai.usage.cache_read.input_tokens", "gen_ai.response.finish_reasons",
    "gen_ai.server.time_to_first_token", "edu.total_ms",
)


def role_config(**overrides) -> RoleConfig:
    """tutor 角色默认参数;测试按需覆盖(timeout/max_attempts/concurrency/json_strict/fallback)。"""
    defaults: dict = {
        "name": "tutor", "primary": "m", "fallback": None, "json_strict": True,
        "concurrency": 4, "first_token_timeout_s": 1.0, "total_timeout_s": 2.0,
        "max_attempts": 3, "backoff_base_ms": 1, "backoff_cap_ms": 8,
    }
    return RoleConfig(**{**defaults, **overrides})


def registry_for(base_url: str, *, model_name: str = "fake-model",
                 fallback_url: str | None = None, role_name: str = "tutor",
                 provider_json_strict: bool | None = None,
                 **role_kwargs) -> ModelRegistry:
    """单角色最小配置;fallback_url 提供时角色带备选(可指向另一假上游或同一地址)。

    provider_json_strict 缺省跟随角色 json_strict;显式传入可构造
    「provider 无服务端保证 + 角色仍走路线 1」的 judge 形态(#32)。"""
    strict = role_kwargs.get("json_strict", True)
    provider_strict = strict if provider_json_strict is None else provider_json_strict
    providers = {"fake": ProviderConfig("fake", base_url, None, provider_strict)}
    models = {"m": ModelConfig("m", "fake", model_name)}
    fallback = None
    if fallback_url is not None:
        providers["fake2"] = ProviderConfig("fake2", fallback_url, None, provider_strict)
        models["b"] = ModelConfig("b", "fake2", model_name)
        fallback = "b"
    role = role_config(name=role_name, fallback=fallback, **role_kwargs)
    return ModelRegistry(providers=providers, models=models, roles={role_name: role})


def gateway_for(base_url: str, facts_dir: Path, **kwargs) -> Gateway:
    return Gateway(registry_for(base_url, **kwargs), facts_dir)


@contextmanager
def fake_gateway(tmp_path: Path, replies: list, **kwargs) -> Iterator[tuple[FakeOpenAI, Gateway]]:
    """FakeOpenAI(按 replies 剧本)+ gateway_for 的生命周期:进入即启动,
    退出先关 gateway 再停 fake(与既有测试的拆除顺序一致)。"""
    fake = FakeOpenAI(replies).start()
    gateway = gateway_for(fake.url, tmp_path, **kwargs)
    try:
        yield fake, gateway
    finally:
        gateway.close()
        fake.stop()


def facts_line(facts_dir) -> dict:
    """单次调用的唯一事实记录行。"""
    files = list(Path(facts_dir).glob("model_calls-*.jsonl"))
    assert len(files) == 1, "事实记录按天切分,单次调用应只有一个文件"
    lines = files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


def facts_rows(facts_dir) -> list[dict]:
    """事实记录全部行(并发/重试场景)。"""
    files = list(Path(facts_dir).glob("model_calls-*.jsonl"))
    return [json.loads(line)
            for line in files[0].read_text(encoding="utf-8").strip().splitlines()]


def load(text_or_path: str | Path, tmp_path: Path | None = None):
    """yaml 文本或路径 → load_registry;文本写入 tmp_path 再加载。"""
    if isinstance(text_or_path, Path):
        return load_registry(text_or_path)
    assert tmp_path is not None
    config = tmp_path / "models.yaml"
    config.write_text(text_or_path, encoding="utf-8")
    return load_registry(config)


__all__ = [
    "FACT_FIELDS", "REPO_CONFIG", "SCHEMA", "SECRET",
    "facts_line", "facts_rows", "fake_gateway", "gateway_for", "load", "registry_for",
]
