"""tests/gateway 公共工具:指向假上游的最小 models 配置与 Gateway 构造。

只导入公开入口 edu_agent.gateway(02 §6)。
"""

from __future__ import annotations

from pathlib import Path

from edu_agent.gateway import (
    Gateway,
    ModelConfig,
    ModelRegistry,
    ProviderConfig,
    RegistryError,
    RoleConfig,
    load_registry,
)

REPO_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "models.yaml"


def role_config(**overrides) -> RoleConfig:
    """tutor 角色默认参数;测试按需覆盖(timeout/max_attempts/concurrency/json_strict/fallback)。"""
    defaults: dict = {
        "name": "tutor", "primary": "m", "fallback": None, "json_strict": True,
        "concurrency": 4, "first_token_timeout_s": 1.0, "total_timeout_s": 2.0,
        "max_attempts": 3, "backoff_base_ms": 1, "backoff_cap_ms": 8,
    }
    return RoleConfig(**{**defaults, **overrides})


def registry_for(base_url: str, *, model_name: str = "fake-model",
                 fallback_url: str | None = None, **role_kwargs) -> ModelRegistry:
    """单角色最小配置;fallback_url 提供时角色带备选(可指向另一假上游或同一地址)。"""
    strict = role_kwargs.get("json_strict", True)
    providers = {"fake": ProviderConfig("fake", base_url, None, strict)}
    models = {"m": ModelConfig("m", "fake", model_name)}
    fallback = None
    if fallback_url is not None:
        providers["fake2"] = ProviderConfig("fake2", fallback_url, None, strict)
        models["b"] = ModelConfig("b", "fake2", model_name)
        fallback = "b"
    role = role_config(fallback=fallback, **role_kwargs)
    return ModelRegistry(providers=providers, models=models, roles={"tutor": role})


def gateway_for(base_url: str, facts_dir: Path, **kwargs) -> Gateway:
    return Gateway(registry_for(base_url, **kwargs), facts_dir)


def write_yaml(tmp_path: Path, text: str) -> Path:
    config = tmp_path / "models.yaml"
    config.write_text(text, encoding="utf-8")
    return config


def load(text_or_path: str | Path, tmp_path: Path | None = None):
    """yaml 文本或路径 → load_registry;文本写入 tmp_path 再加载。"""
    if isinstance(text_or_path, Path):
        return load_registry(text_or_path)
    assert tmp_path is not None
    return load_registry(write_yaml(tmp_path, text_or_path))


__all__ = ["REPO_CONFIG", "RegistryError", "gateway_for", "load", "registry_for", "write_yaml"]
