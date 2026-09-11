"""#142 定案回归钉:门指标按角色定——tutor.ttft 双峰不设门(只记不阻断,与 p95 同例),
judge.ttft 维持 10% 门;去掉阻断 ≠ 去掉指标(render/基线照记)。"""

from scripts.benchmark import GATED_CHECKS, ROLES, compare, render

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


def test_tutor_ttft_record_only_any_degradation_passes():
    """#142 定案:tutor.ttft 逐题双峰 + 缓存态整簇位移 → 任何幅度都不设门。夹具取 126
    (= 基线 43 的 +193%,#142 逐题表里的**单条最大值**,代表"慢簇整体位移"这一档;
    本机实跑那一档是 p50 102 = +137%),均不拦。"""
    current = {"tutor": {"ttft_p50_ms": 126}}
    assert compare(current, BASELINE) == []


def test_gated_checks_cover_every_role():
    """#142 审查 P2(变异 M6/M13):门表必须覆盖每个角色**且非空**——
    `GATED_CHECKS.get(role, ())` 对未列出的角色返回**空元组**,即该角色静默零门
    (fail-open),而报告与基线照写(看着有门其实没有)。加角色却忘了加门(M11/M12)、
    或列出角色却给了空元组(M13),这条钉都要红。
    (M6「默认值改回 fail-closed」不在本钉射程内;审查判定其可达路径已由本钉封住,
    故 `compare()` 的默认值保持最小写法。)"""
    assert set(ROLES) <= set(GATED_CHECKS) and all(GATED_CHECKS[r] for r in ROLES)


def test_judge_ttft_keeps_default_gate():
    """judge.ttft 单峰连续(p50 实测 348-644),门不陪绑:+11% 仍失败。"""
    current = {"judge": {"ttft_p50_ms": 493}}
    assert compare(current, BASELINE) == ["judge.ttft_p50_ms: 493 vs 基线 444(劣化 >10%)"]


def test_tutor_e2e_speed_still_block_real_regression():
    """#142 论证的兜底:tutor.ttft 不设门 ≠ 放弃检测——真回归仍由已含 TTFT 的 e2e_p50
    与 speed_p50 拦,10% 门不变(judge.ttft 见上一测试)。"""
    current = {"tutor": {"e2e_p50_ms": 927, "speed_p50": 79.0}}
    assert compare(current, BASELINE) == [
        "tutor.e2e_p50_ms: 927 vs 基线 835(劣化 >10%)",
        "tutor.speed_p50: 79.0 vs 基线 89.1(劣化 >10%)",
    ]


def test_tutor_ttft_still_recorded_in_report():
    """去掉阻断 ≠ 去掉指标:tutor.ttft 照进报告与基线(collect/render 不动)——
    render 的 TTFT 列仍输出该值,后人一眼可辨「只记不阻断」。"""
    current = {"tutor": {"ttft_p50_ms": 59, "ttft_p95_ms": 126, "e2e_p50_ms": 839}}
    report = render(current)
    assert "| tutor | 0 | 59 / 126" in report  # TTFT p50/p95 列照记
    assert "TTFT p50/p95 (ms)" in report
