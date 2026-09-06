"""models.yaml 加载与角色解析(01 §2.6、§8):配置一份。

json_strict 声明:provider 层=服务端原生保证(grammar/json_object),mlx 无保证记
false;角色层=本角色接受结构化请求。#32/#34 定稿后 judge 主选 mlx 走路线 1
(schema 进 prompt + 本地校验 + schema_violation 一次修复重试),加载期不再按
provider 能力拒绝角色——"不静默穿透"由路线 1 的本地校验保证(不合规即显式失败),
provider 声明只反映一次通过率风险,由评测线量化(#32 10% 平行评分)。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


class RegistryError(Exception):
    """配置或角色解析错误(加载期/调用前发现,不属于九种调用失败)。"""


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key_env: str | None
    json_strict: bool


@dataclass(frozen=True)
class ModelConfig:
    id: str
    provider: str
    name: str  # 发给服务端的模型名


@dataclass(frozen=True)
class RoleConfig:
    name: str
    primary: str
    fallback: str | None
    json_strict: bool
    concurrency: int
    first_token_timeout_s: float
    total_timeout_s: float
    max_attempts: int
    backoff_base_ms: int
    backoff_cap_ms: int


@dataclass(frozen=True)
class ModelRegistry:
    """已加载校验的配置。类名避开 registry 模块名(macOS 大小写不敏感文件系统下
    from edu_agent.gateway import Registry 会被私有导入检查当作导入私有模块 registry.py)。
    """

    providers: dict[str, ProviderConfig]
    models: dict[str, ModelConfig]
    roles: dict[str, RoleConfig]

    def role(self, name: str) -> RoleConfig:
        try:
            return self.roles[name]
        except KeyError:
            raise RegistryError(f"未知角色 '{name}',models.yaml 中有: {sorted(self.roles)}") from None

    def model(self, model_id: str) -> ModelConfig:
        try:
            return self.models[model_id]
        except KeyError:
            raise RegistryError(f"未知模型条目 '{model_id}'") from None

    def provider(self, name: str) -> ProviderConfig:
        try:
            return self.providers[name]
        except KeyError:
            raise RegistryError(f"未知 provider '{name}'") from None


def _provider_entries(raw: dict) -> dict[str, ProviderConfig]:
    entries = {}
    for name, spec in raw.items():
        base_url = spec.get("base_url")
        if not base_url:
            raise RegistryError(f"provider '{name}' 缺 base_url")
        entries[name] = ProviderConfig(
            name=name,
            base_url=str(base_url),
            api_key_env=spec.get("api_key_env"),
            json_strict=bool(spec.get("json_strict", False)),
        )
    return entries


def _model_entries(raw: dict, providers: dict[str, ProviderConfig]) -> dict[str, ModelConfig]:
    entries = {}
    for model_id, spec in raw.items():
        provider = spec.get("provider")
        if provider not in providers:
            raise RegistryError(f"模型 '{model_id}' 引用了未知 provider '{provider}'")
        name = spec.get("name")
        if not name:
            raise RegistryError(f"模型 '{model_id}' 缺 name(发给服务端的模型名)")
        entries[model_id] = ModelConfig(id=model_id, provider=provider, name=str(name))
    return entries


def _role_field(spec: dict, role: str, key: str):
    if key not in spec:
        # 01 §4:重试/退避/备选策略必须按角色声明,不写死在代码里
        raise RegistryError(f"角色 '{role}' 缺必填字段 '{key}'")
    return spec[key]


def _positive(value, role: str, key: str) -> float:
    if not isinstance(value, (int, float)) or value <= 0:
        raise RegistryError(f"角色 '{role}' 的 '{key}' 必须为正数,得到 {value!r}")
    return float(value)


def _non_negative_int(spec: dict, role: str, key: str) -> int:
    value = _role_field(spec, role, key)
    if not isinstance(value, int) or value < 0:
        raise RegistryError(f"角色 '{role}' 的 '{key}' 必须为非负整数,得到 {value!r}")
    return value


def _role_entries(raw: dict, models: dict[str, ModelConfig]) -> dict[str, RoleConfig]:
    entries = {}
    for name, spec in raw.items():
        primary = _role_field(spec, name, "primary")
        if primary not in models:
            raise RegistryError(f"角色 '{name}' 的 primary 引用了未知模型 '{primary}'")
        fallback = spec.get("fallback")
        if fallback is not None and fallback not in models:
            raise RegistryError(f"角色 '{name}' 的 fallback 引用了未知模型 '{fallback}'")
        entries[name] = RoleConfig(
            name=name,
            primary=primary,
            fallback=fallback,
            json_strict=bool(spec.get("json_strict", False)),
            concurrency=int(_positive(_role_field(spec, name, "concurrency"), name, "concurrency")),
            first_token_timeout_s=_positive(
                _role_field(spec, name, "first_token_timeout_s"), name, "first_token_timeout_s"
            ),
            total_timeout_s=_positive(_role_field(spec, name, "total_timeout_s"), name, "total_timeout_s"),
            max_attempts=int(_positive(_role_field(spec, name, "max_attempts"), name, "max_attempts")),
            backoff_base_ms=_non_negative_int(spec, name, "backoff_base_ms"),
            backoff_cap_ms=_non_negative_int(spec, name, "backoff_cap_ms"),
        )
    return entries


def load_registry(path: Path | str) -> ModelRegistry:
    """加载并校验 models.yaml;任何结构性问题在这里失败,不带病运行。"""
    file = Path(path)
    try:
        raw = yaml.safe_load(file.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RegistryError(f"找不到模型配置 {file}") from exc
    except yaml.YAMLError as exc:
        raise RegistryError(f"模型配置不是合法 YAML:{exc}") from exc
    if not isinstance(raw, dict):
        raise RegistryError("模型配置顶层必须是映射")
    for section in ("providers", "models", "roles"):
        if not isinstance(raw.get(section), dict) or not raw[section]:
            raise RegistryError(f"模型配置缺非空 '{section}' 段")
    providers = _provider_entries(raw["providers"])
    models = _model_entries(raw["models"], providers)
    roles = _role_entries(raw["roles"], models)
    return ModelRegistry(providers=providers, models=models, roles=roles)
