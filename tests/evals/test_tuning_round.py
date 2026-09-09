"""tuning_round 对照逻辑单测(#34 2026-09-09 人批容差口径 + 夜评溯源)。

容差规则(基线报告 §3 两轮方差 → 判定):
- 场景两轮分差 ≤1(测量稳定)→ 单值判:本轮 ≥ max(R1,R2) 才"达标",否则"低于基线";
- 场景两轮分差 ≥2(噪声主导)→ 区间判:本轮 ≥ min 即"不劣(噪声主导)",不判反超。

纯逻辑直测,不启动评测(真模型链路由 evals-nightly.yml 夜评覆盖)。
"""

from __future__ import annotations

import json

import pytest

import scripts.tuning_round as tuning_round


def test_baseline_two_round_values_cover_all_cases():
    """基线是 (R1, R2) 二元组,且与 11 场景一一对应(基线报告 §3 落盘快照)。"""
    assert len(tuning_round.BASELINE) == 11
    for r1, r2 in tuning_round.BASELINE.values():
        assert isinstance(r1, int) and isinstance(r2, int)
        assert 0 <= r1 <= 12 and 0 <= r2 <= 12


class TestToleranceVerdict:
    """#34 2026-09-09 人批容差:分差 ≤1 单值判,≥2 区间判。"""

    def test_stable_case_reaches_max_passes(self):
        # R1=R2=8(分差 0):单值判,达到 max=8 → 达标
        assert tuning_round.tolerance_verdict(8, 8, 8) == "达标"

    def test_stable_case_below_max_fails(self):
        # 分差 0,本轮 7 < max 8 → 低于基线(一分不让)
        assert tuning_round.tolerance_verdict(7, 8, 8) == "低于基线"

    def test_near_stable_case_uses_max(self):
        # 分差 1(3,4):仍单值判,本轮 ≥ 4 才达标
        assert tuning_round.tolerance_verdict(4, 3, 4) == "达标"
        assert tuning_round.tolerance_verdict(3, 3, 4) == "低于基线"

    def test_noisy_case_in_range_is_not_inferior(self):
        # word_problem 型(11,5,分差 6):区间判,本轮 6 ≥ min 5 → 不劣(噪声主导)
        assert tuning_round.tolerance_verdict(6, 11, 5) == "不劣(噪声主导)"

    def test_noisy_case_above_max_still_not_reported_as_win(self):
        # 噪声场景不判反超:13 分超 max 也只标"不劣"(双向防错)
        assert tuning_round.tolerance_verdict(12, 11, 5) == "不劣(噪声主导)"

    def test_noisy_case_below_range_fails(self):
        # 分差 6,本轮 4 < min 5 → 低于基线
        assert tuning_round.tolerance_verdict(4, 11, 5) == "低于基线"

    def test_real_baseline_rows(self):
        """真实基线行抽测:equation_complete(8,8)单值判;stability word_problem(11,5)区间判。"""
        b = tuning_round.BASELINE
        assert tuning_round.tolerance_verdict(8, *b[
            "small_lecturer_dialogue_scenarios_equation_complete_reasoning"]) == "达标"
        assert tuning_round.tolerance_verdict(
            6, *b["small_lecturer_dialogue_stability_20_stability_word_problem"]) == "不劣(噪声主导)"


def test_probe_reports_unreachable_port():
    """预检探针:不可达端口返回失败原因而非抛异常(流水线红灯由调用方收口)。"""
    result = tuning_round._probe("http://127.0.0.1:1")
    assert result.startswith("不可达:")


def test_nightly_preflight_writes_manifest(tmp_path, monkeypatch):
    """夜评溯源:manifest 落 git sha/models.yaml 哈希/探针结果;不可达 provider 退出 1。"""

    class _P:
        base_url = "http://127.0.0.1:1"  # 不可达 → 预检失败路径

    class _R:
        providers = {"broken": _P()}

    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    with pytest.raises(SystemExit) as exc:
        tuning_round.nightly_preflight(_R(), tmp_path)  # type: ignore[arg-type]
    assert exc.value.code == 1
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["git_sha"] == "a" * 40
    assert "models_yaml_sha256" in manifest
    assert manifest["provider_probes"]["broken"].startswith("不可达:")
