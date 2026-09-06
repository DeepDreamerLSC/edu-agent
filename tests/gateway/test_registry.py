"""registry 合同(01 §2.6、§8):models.yaml 加载与角色解析。

json_strict 加载期 provider 能力校验已随 #32/#34 定稿移除(judge 主选 mlx 走
路线 1,角色声明不再被 provider 声明否决)——"不静默穿透"由路线 1 本地校验
保证,断言变更理由见 judge 实现 PR 描述。
"""

from __future__ import annotations

import pytest

from edu_agent.gateway import RegistryError

from gwkit import REPO_CONFIG, load

VALID = """
providers:
  fake:
    base_url: http://127.0.0.1:9/v1
    json_strict: false
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
    # 01 §10:一份 models.yaml;#34 互换后 tutor/judge 各有主选与备选,
    # judge_independent 为 #32 独立性保险角色(无备选,不许降级到被审计模型)
    assert set(registry.roles) == {"tutor", "judge", "judge_independent"}
    for name in ("tutor", "judge"):
        role = registry.roles[name]
        assert role.fallback and role.fallback in registry.models
        assert role.primary in registry.models
        assert role.json_strict is True
    assert registry.roles["judge_independent"].fallback is None
    # #34:tutor 主选 llama(grammar 级),judge 主选 mlx(路线 1)
    assert registry.roles["tutor"].primary == "llama_9b"
    assert registry.roles["judge"].primary == "mlx_27b"
    assert registry.roles["judge"].fallback == "deepseek_chat"
    # provider 声明=服务端原生保证:mlx 无保证记 false(#32)
    assert registry.providers["mlx"].json_strict is False
    assert registry.providers["llama"].json_strict is True
    assert registry.providers["deepseek"].json_strict is True
    assert registry.providers["deepseek"].api_key_env == "DEEPSEEK_API_KEY"


def test_role_json_strict_not_gated_by_provider_flag(tmp_path):
    """#32/#34:角色 json_strict 与 provider 服务端保证解耦——judge 主选 mlx
    (无服务端保证)仍可声明接受结构化请求,路线 1 本地校验兜底。"""
    registry = load(VALID, tmp_path)  # provider json_strict: false + 角色 true
    assert registry.roles["tutor"].json_strict is True
    assert registry.providers["fake"].json_strict is False


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
