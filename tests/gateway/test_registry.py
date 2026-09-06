"""registry 合同(01 §2.6、§8):models.yaml 加载、角色解析、json_strict 加载期校验。"""

from __future__ import annotations

import pytest

from edu_agent.gateway import RegistryError

from gwkit import REPO_CONFIG, load

VALID = """
providers:
  fake:
    base_url: http://127.0.0.1:9/v1
    json_strict: true
models:
  m:
    provider: fake
    name: fake-model
roles:
  tutor:
    primary: m
    json_strict: true
    concurrency: 2
    first_token_timeout_s: 5
    total_timeout_s: 60
    max_attempts: 3
    backoff_base_ms: 100
    backoff_cap_ms: 1000
"""


def test_repo_config_loads(tmp_path):
    registry = load(REPO_CONFIG)
    # 01 §10:一份 models.yaml,tutor/judge 各有主选与备选
    assert set(registry.roles) == {"tutor", "judge"}
    for role in registry.roles.values():
        assert role.fallback and role.fallback in registry.models
        assert role.primary in registry.models
    judge = registry.roles["judge"]
    assert judge.json_strict is True
    assert registry.providers["deepseek"].json_strict is True
    assert registry.providers["mlx_tutor"].json_strict is False
    assert registry.providers["deepseek"].api_key_env == "DEEPSEEK_API_KEY"


def test_json_strict_mismatch_fails_at_load(tmp_path):
    # 01 §8/issue #8:角色要求 json_strict 而 provider 未声明支持,加载即报错,不发请求
    bad = VALID.replace("json_strict: true", "json_strict: false", 1)
    with pytest.raises(RegistryError, match="json_strict.*fake"):
        load(bad, tmp_path)


def test_json_strict_checked_on_fallback_model_too(tmp_path):
    # 主选 provider 支持、备选不支持:同样加载即报错(备选也 receives 结构化请求)
    text = """
providers:
  ok:
    base_url: http://127.0.0.1:9/v1
    json_strict: true
  lax:
    base_url: http://127.0.0.1:9/v2
    json_strict: false
models:
  m:
    provider: ok
    name: a
  b:
    provider: lax
    name: b
roles:
  tutor:
    primary: m
    fallback: b
    json_strict: true
    concurrency: 2
    first_token_timeout_s: 5
    total_timeout_s: 60
    max_attempts: 3
    backoff_base_ms: 100
    backoff_cap_ms: 1000
"""
    with pytest.raises(RegistryError, match="json_strict.*lax"):
        load(text, tmp_path)


def test_missing_role_field_fails(tmp_path):
    bad = VALID.replace("    max_attempts: 3\n", "")
    with pytest.raises(RegistryError, match="max_attempts"):
        load(bad, tmp_path)


def test_unknown_primary_model_fails(tmp_path):
    bad = VALID.replace("primary: m", "primary: nope")
    with pytest.raises(RegistryError, match="nope"):
        load(bad, tmp_path)


def test_unknown_provider_on_model_fails(tmp_path):
    bad = VALID.replace("provider: fake", "provider: ghost")
    with pytest.raises(RegistryError, match="ghost"):
        load(bad, tmp_path)


def test_unknown_role_at_call_time(tmp_path):
    registry = load(VALID, tmp_path)
    with pytest.raises(RegistryError, match="未知角色"):
        registry.role("simulator")
