"""tests/teaching 共享工具:指向假上游的 tutor 角色 Gateway(02 §6:测护栏不测模型)。"""

from __future__ import annotations

from pathlib import Path

from edu_agent.gateway import Gateway, ModelConfig, ModelRegistry, ProviderConfig, RoleConfig


def tutor_gateway(base_url: str, facts_dir: Path) -> Gateway:
    """单 tutor 角色(json_strict false,不带 schema)指向假上游。"""
    providers = {"fake": ProviderConfig("fake", base_url, None, False)}
    models = {"m": ModelConfig("m", "fake", "fake-model")}
    role = RoleConfig(
        name="tutor", primary="m", fallback=None, json_strict=False,
        concurrency=2, first_token_timeout_s=2.0, total_timeout_s=5.0,
        max_attempts=2, backoff_base_ms=1, backoff_cap_ms=8,
    )
    return Gateway(ModelRegistry(providers=providers, models=models, roles={"tutor": role}), facts_dir)
