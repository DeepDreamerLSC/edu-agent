"""#142 逐指标劣化系数回归钉:tutor.ttft 单列宽松门,judge.ttft 维持原有 10% 门。"""

from scripts.benchmark import compare

BASELINE = {
    "roles": {
        "tutor": {"ttft_p50_ms": 43, "e2e_p50_ms": 835, "speed_p50": 89.1},
        "judge": {"ttft_p50_ms": 444, "e2e_p50_ms": 3860, "speed_p50": 27.5},
    }
}


def test_tutor_ttft_bimodal_band_passes():
    """双峰实测带(慢簇 49-59ms)+ 其余指标正常波动 → 不入 failures(#142 常红根因)。"""
    current = {
        "tutor": {"ttft_p50_ms": 59, "e2e_p50_ms": 839, "speed_p50": 88.6},
        "judge": {"ttft_p50_ms": 374, "e2e_p50_ms": 3403, "speed_p50": 30.0},
    }
    assert compare(current, BASELINE) == []


def test_tutor_ttft_real_regression_still_fails():
    """真回归(43→90,+109%)仍被拦 → 补上"纯退出"留下的检测盲区。"""
    current = {"tutor": {"ttft_p50_ms": 90}}
    assert compare(current, BASELINE) == ["tutor.ttft_p50_ms: 90 vs 基线 43(劣化 >100%)"]


def test_judge_ttft_keeps_default_gate():
    """judge.ttft 单峰(334-612),门不陪绑:+11% 仍失败。"""
    current = {"judge": {"ttft_p50_ms": 493}}
    assert compare(current, BASELINE) == ["judge.ttft_p50_ms: 493 vs 基线 444(劣化 >10%)"]


def test_other_metrics_keep_default_gate():
    """e2e/speed 未列系数 → 维持 10%(tutor.e2e +11% 失败、speed 掉 11% 失败)。"""
    current = {"tutor": {"e2e_p50_ms": 927, "speed_p50": 79.0}}
    assert compare(current, BASELINE) == [
        "tutor.e2e_p50_ms: 927 vs 基线 835(劣化 >10%)",
        "tutor.speed_p50: 79.0 vs 基线 89.1(劣化 >10%)",
    ]
