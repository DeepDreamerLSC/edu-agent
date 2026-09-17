"""#142 定案回归钉:门指标按角色定——tutor.ttft 双峰不设门(只记不阻断,与 p95 同例),
judge.ttft 维持 10% 门;去掉阻断 ≠ 去掉指标(render/基线照记)。
#241 行1 门控钉:标志位让路语义(活标志 SKIPPED / 写基线两条通路拒绝 / 死 PID 放行 /
 目录残留不炸)——import 级注入,零模型调用(审查 P2-2)。"""

import argparse
import os
import subprocess
import sys

from scripts import benchmark
from scripts.benchmark import (
    GATED_CHECKS,
    ROLES,
    compare,
    gate_or_skip,
    live,
    render,
    ttft_strata,
)

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


# ---------- #338/#188:TTFT 前缀缓存分层诊断列(不设门,零判定逻辑) ----------


def test_render_shows_ttft_strata_columns():
    """分层表进报告:命中/未命中两行 + 空谷注计数;缺失 strata 的 metrics 不炸。"""
    current = {"tutor": {"n": 3, "ttft_p50_ms": 60, "ttft_p95_ms": 130, "e2e_p50_ms": 100,
                         "e2e_p95_ms": 200, "speed_p50": 30.0,
                         "ttft_strata": {"hit": {"n": 2, "ttft_p50_ms": 60, "ttft_p95_ms": 70},
                                         "miss": {"n": 1, "ttft_p50_ms": 130, "ttft_p95_ms": 130},
                                         "mid_n": 1}},
               "judge": {"n": 2, "ttft_p50_ms": 400, "ttft_p95_ms": 500}}
    report = render(current)
    assert "## TTFT 前缀缓存分层(#188 诊断列,不设门)" in report
    assert "| tutor | 命中(未缓存==1) | 2 | 60 | 70 |" in report
    assert "| tutor | 未命中(未缓存≥10) | 1 | 130 | 130 |" in report
    assert "| judge | 命中(未缓存==1) | 0 | - | - |" in report  # 缺 strata 的角色按零行渲染
    assert "空谷(2–9)计数(tutor / judge):1 / 0" in report


def test_ttft_strata_layering_by_uncached_tokens():
    """分层口径(#188):未缓存==1→命中,≥10→未命中,2–9 空谷;usage 缺失行不计入。"""
    rows = [
        {"gen_ai.usage.input_tokens": 1001, "gen_ai.usage.cache_read.input_tokens": 1000,
         "gen_ai.server.time_to_first_token": 60},                       # 未缓存 1 → 命中
        {"gen_ai.usage.input_tokens": 800, "gen_ai.usage.cache_read.input_tokens": 799,
         "gen_ai.server.time_to_first_token": 70},                       # 未缓存 1 → 命中
        {"gen_ai.usage.input_tokens": 500, "gen_ai.usage.cache_read.input_tokens": 0,
         "gen_ai.server.time_to_first_token": 130},                      # 未缓存 500 → 未命中
        {"gen_ai.usage.input_tokens": 10, "gen_ai.usage.cache_read.input_tokens": 2,
         "gen_ai.server.time_to_first_token": 90},                       # 未缓存 8 → 空谷
        {"gen_ai.server.time_to_first_token": 100},                      # usage 缺失 → 不计入
    ]
    strata = ttft_strata(rows)
    assert strata["hit"] == {"n": 2, "ttft_p50_ms": 65, "ttft_p95_ms": 70}   # 线性插值分位(69.5→70)
    assert strata["miss"] == {"n": 1, "ttft_p50_ms": 130, "ttft_p95_ms": 130}
    assert strata["mid_n"] == 1


def test_strata_never_gated():
    """纯诊断:分层键不进 GATED_CHECKS(门逻辑零改动,#246 原样)。"""
    for checks in GATED_CHECKS.values():
        for name, _ in checks:
            assert name != "ttft_strata"


# ---------- #241 行1:标志位让路门控(审查 P2-2 六探针落盘,import 级、零模型调用) ----------


def _dead_pid() -> int:
    """确定已退出的 pid(spawn + wait;测试窗口内 pid 复用概率视为零)。"""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def _gate(monkeypatch, tmp_path, flags=(), write_baseline=False, baseline_exists=True):
    """门控三路径(BATCH_DIR/BASELINE_PATH/REPORT_PATH)指向 tmp 并注册标志。"""
    batch = tmp_path / "batch"
    batch.mkdir()
    for name in flags:
        (batch / name).touch()
    monkeypatch.setattr(benchmark, "BATCH_DIR", batch)
    monkeypatch.setattr(benchmark, "REPORT_PATH", tmp_path / "report.md")
    baseline = tmp_path / "efficiency.json"
    if baseline_exists:
        baseline.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(benchmark, "BASELINE_PATH", baseline)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    return argparse.Namespace(write_baseline=write_baseline)


def test_dead_pid_flag_cleaned_and_gate_open(tmp_path, monkeypatch):
    """死 pid 标志(崩溃遗留)→ 顺手清 + 门放行——否则一次崩溃 = 门永久 SKIPPED
    的绿色静默瘫痪(设计稿 §4-3 语义)。"""
    args = _gate(monkeypatch, tmp_path)
    flag = tmp_path / "batch" / f"crash-leftover.{_dead_pid()}"
    flag.touch()
    assert live() == []
    assert not flag.exists()
    assert gate_or_skip(args) is None


def test_live_flag_skips_gate_with_dual_trace(tmp_path, monkeypatch):
    """活标志 → exit 0 + 报告 SKIPPED + step summary 双留痕(P3-3:绿而无实跑必须可审计)。"""
    args = _gate(monkeypatch, tmp_path, flags=[f"corpus-round.{os.getpid()}"])
    assert gate_or_skip(args) == 0
    assert "SKIPPED" in (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "benchmark SKIPPED" in (tmp_path / "summary.md").read_text(encoding="utf-8")


def test_write_baseline_refused_with_live_flag(tmp_path, monkeypatch):
    """--write-baseline 撞活标志 → exit 1,基线内容零改动(争用窗口重种 = 污染基线)。"""
    args = _gate(monkeypatch, tmp_path, flags=[f"x.{os.getpid()}"], write_baseline=True)
    assert gate_or_skip(args) == 1
    assert (tmp_path / "efficiency.json").read_text(encoding="utf-8") == "{}"


def test_missing_baseline_auto_reseed_refused_with_live_flag(tmp_path, monkeypatch):
    """基线缺失自动重种分支(审查 P2-1 语义:守卫不能只挂 --write-baseline)同样拒绝。"""
    args = _gate(monkeypatch, tmp_path, flags=[f"x.{os.getpid()}"], baseline_exists=False)
    assert gate_or_skip(args) == 1
    assert not (tmp_path / "efficiency.json").exists()


def test_no_flag_normal_run(tmp_path, monkeypatch):
    """无标志(目录空与目录不存在两态)→ None 正常开跑。"""
    args = _gate(monkeypatch, tmp_path)
    assert gate_or_skip(args) is None
    monkeypatch.setattr(benchmark, "BATCH_DIR", tmp_path / "nonexistent")
    assert live() == []
    assert gate_or_skip(args) is None


def test_directory_residue_does_not_crash(tmp_path, monkeypatch):
    """目录形态残留(审查 P2-1:unlink 不吞目录 → IsADirectoryError 在真红路径会
    打断证据块写入)→ 不炸、不算活、门放行。"""
    args = _gate(monkeypatch, tmp_path)
    (tmp_path / "batch" / f"residue.{_dead_pid()}").mkdir()
    assert live() == []
    assert gate_or_skip(args) is None
