"""corpus_round 纯逻辑测试(#216):零模型——过滤/撞名/跨轮 diff/报告渲染。

批跑面(KernelSubject+EvalRunner+judge)与 tuning_round 同口径,不在单测里重复
(#216 边界:真模型不进 CI);这里只钉数据的分诊与对照语义。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from edu_agent.evals import (
    check_rows,
    diff_checks,
    real_model_scenarios,
    render_report,
)


def _scenario(sid: str, *, fake_model: bool = False, checks: bool = True) -> dict:
    scenario = {
        "id": sid,
        "status": "guarded",
        "question": {"text": "鸡和兔一共有8只，共有26只脚。鸡和兔各有多少只？说明思路。",
                     "answer": "鸡3只，兔5只"},
        "student_turns": ["我不会做。"],
        "grade": "六年级",
        "source": {"issue": 197},
    }
    if fake_model:
        scenario["fake_model"] = [{"json": {"reply": "罐头"}}]
    if checks:
        scenario["expect"] = {"checks": [{"name": "finish_status", "status": "completed"}]}
    return scenario


def _write_corpus(tmp_path: Path, name: str, scenarios: list[dict]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({"schema_version": "small_lecturer_shadow_pilot_corpus/v1",
                                "scenarios": scenarios}, ensure_ascii=False), encoding="utf-8")
    return path


def test_real_model_filter_keeps_only_no_fake_model(tmp_path):
    """确定性口径(带 fake_model)不进本面(#216 边界);真模型口径全保留。"""
    path = _write_corpus(tmp_path, "pilot_a.json", [
        _scenario("s1"), _scenario("s2", fake_model=True)])
    scenarios = real_model_scenarios([path])
    assert list(scenarios) == ["pilot_a_s1"]


def test_case_id_prefixes_dataset_and_rejects_collision(tmp_path):
    """case id 加数据集前缀(报告行自带溯源);前缀后仍撞名 = 写错,即刻红。"""
    path_a = _write_corpus(tmp_path, "pilot_a.json", [_scenario("s1")])
    path_b = _write_corpus(tmp_path, "pilot_b.json", [_scenario("s1")])
    scenarios = real_model_scenarios([path_a, path_b])
    assert sorted(scenarios) == ["pilot_a_s1", "pilot_b_s1"]
    # 同一文件传两遍(重复 --corpus 参数)→ 前缀后仍撞名 = 写错,即刻红
    with pytest.raises(ValueError, match="撞名"):
        real_model_scenarios([path_a, path_a])


def test_check_rows_distinguishes_undeclared_from_all_green():
    """未声明 checks(adaptive 形态)记 declared=False,不冒充全绿。"""
    scenarios = {"x_s1": _scenario("s1"), "x_s2": _scenario("s2", checks=False)}
    results = [
        {"case_id": "x_s1", "status": "ok", "transcript": {"final_state": "completed", "turns": []}},
        {"case_id": "x_s2", "status": "ok", "transcript": {"final_state": "needs_review", "turns": []}},
        {"case_id": "x_s3", "status": "environment", "transcript": None},
    ]
    # x_s3 无场景声明 → check_rows 按缺失场景容错?不:scenario 查找必须命中,先补声明
    scenarios["x_s3"] = _scenario("s3")
    rows = check_rows(scenarios, results)
    assert rows["x_s1"] == {"status": "ok", "declared": True, "final_state": "completed", "failures": []}
    assert rows["x_s2"]["declared"] is False and rows["x_s2"]["failures"] is None
    assert rows["x_s3"]["status"] == "environment"


def test_diff_checks_classifies_new_red_and_flip():
    """绿→红 = 新增红(回归信号);红→绿 = 翻绿;首轮红无前科也是新增红。"""
    current = {
        "a": {"status": "ok", "declared": True, "failures": [{"check": "c", "detail": "d"}], "final_state": ""},
        "b": {"status": "ok", "declared": True, "failures": [], "final_state": ""},
        "c": {"status": "ok", "declared": True, "failures": [], "final_state": ""},
    }
    previous = {
        "a": {"status": "ok", "declared": True, "failures": [], "final_state": ""},
        "b": {"status": "ok", "declared": True, "failures": [{"check": "c", "detail": "d"}], "final_state": ""},
    }
    verdicts = diff_checks(current, previous)
    assert verdicts == {"a": "新增红", "b": "翻绿", "c": "绿"}


def test_render_report_marks_undeclared_and_counts_new_red():
    checks = {
        "x_s1": {"status": "ok", "declared": True, "failures": [], "final_state": "completed"},
        "x_s2": {"status": "ok", "declared": False, "failures": None, "final_state": "needs_review"},
    }
    scores = {"x_s1": {"total": 10, "verdict": "pass", "scores": {"socratic_followup": 2}}}
    report = render_report(Path("/tmp/out"), checks, scores,
                           {"from": "prev/run", "verdicts": {"x_s1": "绿", "x_s2": "新增红"}})
    assert "新增红:1" in report and "无声明" in report and "全绿" in report
    assert "追问=2" in report


def test_render_report_shows_previous_judge_total():
    """审查 P3:有上轮 judge 分(按轮留存)时 judge 列给「上轮→本轮」,噪声对比可复算。"""
    checks = {"x_s1": {"status": "ok", "declared": True, "failures": [], "final_state": "completed"}}
    scores = {"x_s1": {"total": 8, "verdict": "review", "scores": {"socratic_followup": 1}}}
    report = render_report(Path("/tmp/out"), checks, scores,
                           {"from": "prev/run", "verdicts": {"x_s1": "绿"},
                            "prev_scores": {"x_s1": {"total": 12}}})
    assert "total=12→8" in report
