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


# ---------- comparison.md 自述四行(2026-09-10 PM 马尾辫审查)----------

_WORD_PROBLEM = "small_lecturer_dialogue_stability_20_stability_word_problem"
_EQUATION = "small_lecturer_dialogue_scenarios_equation_complete_reasoning"


def _fake_scores() -> dict:
    return {_EQUATION: {"scores": {dim: 2 for dim in tuning_round.DIMENSIONS},
                        "total": 12, "verdict": "pass"}}


def _fake_rows() -> list[dict]:
    """word_problem 剧本 4 轮、第 2 学生轮后 ready_to_confirm 判停(夜评帧实况的最小化)。"""
    turns = [{"student": "", "tutor": "q", "state": "first_question_ready"},
             {"student": "s1", "tutor": "a1", "state": "dialogue"},
             {"student": "s2", "tutor": "a2", "state": "ready_to_confirm"}]
    return [{"case_id": _WORD_PROBLEM, "status": "ok", "transcript": {"turns": turns}}]


def _fake_cases() -> list[dict]:
    return [
        {"id": _EQUATION, "student_turns": ["a", "b"]},
        {"id": _WORD_PROBLEM, "student_turns": ["a", "b", "c", "d"], "answer_status": "correct"},
    ]


def _legacy_inline_lines(scores: dict) -> list[str]:
    """改动前 main() 的内联构造(git 历史逐字拷贝)——既有行逐字节对照的基准。"""
    report = ["# 调优轮对照(vs 基线 R1×R2,#34 容差口径:分差≤1 单值判/≥2 区间判)", "",
              "| 场景 | R1 | R2 | 本轮 | 判定 |", "|---|---:|---:|---:|---|"]
    deltas = []
    for case_id, (r1, r2) in tuning_round.BASELINE.items():
        got = scores.get(case_id, {}).get("total")
        if got is None:
            report.append(f"| {case_id} | {r1} | {r2} | 失败 | FAIL |")
            continue
        deltas.append(got - (r1 + r2) / 2)
        report.append(f"| {case_id} | {r1} | {r2} | {got} | "
                      f"{tuning_round.tolerance_verdict(got, r1, r2)} |")
    report += ["", f"逐维均分:见 judge-scores.json;对两轮均值差:{sum(deltas) / len(deltas):+.2f}"]
    return report


class TestComparisonSelfDescribe:
    """自述四行纯增量;既有行(标题/主表/均值差指针行)逐字节不变(只加信息不改测量)。"""

    def test_existing_lines_byte_identical(self):
        scores = _fake_scores()
        new = tuning_round.comparison_report(scores, _fake_rows(), _fake_cases())
        old = _legacy_inline_lines(scores)
        assert new[:2] == old[:2]                 # 标题 + 空行
        assert new[-(len(old) - 2):] == old[2:]   # 主表 + 均值差行:逐字节相同
        assert len(new) > len(old)                # 且确有自述增量

    def test_self_describe_block_contents(self):
        block = "\n".join(tuning_round.comparison_report(
            _fake_scores(), _fake_rows(), _fake_cases()))
        assert "P(gate 冻结 wiring)" in block                       # ① 口径名
        assert 'hint 注入:1/2 场景带 `answer_status="correct"`' in block
        assert f"| {_WORD_PROBLEM} | 2/4 ⚠ |" in block              # ② 截断(判停信号)
        assert f"| {_EQUATION} | 失败 |" in block                   # 无结果行如实标注
        assert "逐维均分(0-2):首问质量 2.00" in block               # ③ DIM_LABELS 渲染
        assert "追问引导 2.00" in block
        assert "护栏模式:**无答案**" in block                        # ④ 护栏模式

    def test_render_from_roundtrip(self, tmp_path):
        """--render-from:离线重渲染生成自述块;jfp 段承接原文不改编。"""
        run = tmp_path / "run"
        results = run / "collect" / "cases-20260910T000000Z-x" / "results"
        results.mkdir(parents=True)
        (run / "cases.jsonl").write_text(
            "\n".join(json.dumps(c, ensure_ascii=False) for c in _fake_cases()) + "\n",
            encoding="utf-8")
        (results / "case.json").write_text(
            json.dumps(_fake_rows()[0], ensure_ascii=False), encoding="utf-8")
        (run / "judge-scores.json").write_text(
            json.dumps(_fake_scores(), ensure_ascii=False), encoding="utf-8")
        (run / "comparison.md").write_text(
            "# 旧\n\n## json_first_pass(01 §6 结构化输出合规率)\n\n旧段原文\n", encoding="utf-8")

        assert tuning_round.render_from(run) == 0
        text = (run / "comparison.md").read_text(encoding="utf-8")
        assert "剧本截断" in text and "2/4 ⚠" in text               # 自述块已生成
        assert "承接原 comparison.md、未重算" in text               # 承接段显式标注(#154 审查观察 2)
        assert "## json_first_pass(01 §6 结构化输出合规率)\n\n旧段原文" in text
        assert text.index("对两轮均值差") < text.index("承接原 comparison.md")
        assert text.index("承接原 comparison.md") < text.index("## json_first_pass")
