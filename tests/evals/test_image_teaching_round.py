"""题图教学评测集 v1(#130 WP5)runner 入口纯逻辑单测:数据集门 + case 装配 + 报告。

不调模型:load_scenarios / to_cases / to_judge_cases / render_report 全是确定性函数,
judge 与收集的真实调用留给 Mac 侧跑批。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import scripts.image_teaching_round as round_entry
from edu_agent.evals import load_scenarios, to_cases


def _write_image(tmp_path: Path) -> tuple[str, str]:
    payload = b"\xff\xd8\xffimage-teaching-round"
    path = tmp_path / "pqfile_round.jpg"
    path.write_bytes(payload)
    return str(path), hashlib.sha256(payload).hexdigest()


def _scenario(tmp_path: Path, **overrides) -> dict:
    path, sha = _write_image(tmp_path)
    scenario = {
        "id": "image_v1_round_01",
        "title": "圆·半径",
        "grade": "六年级",
        "question": {"text": "池塘周长 62.8 米,求半径。",
                     "image": {"path": path, "sha256": sha}},
        "reference_answer": {"value": "10", "answer_type": "integer", "unit": "米"},
        "bucket": "circle_geometry",
        "visual_dependency": "required",
        "misconception_seed": "半径当直径",
        "student_turns": ["周长除以 3.14 吗?", "哦,还要除以 2。", "半径 10 米。"],
        "expected": {"outcome": "ready_to_record"},
        "source": {"question_id": "q001", "provider": "pujia_school_question_bank",
                   "lesson_name": "圆的周长"},
    }
    scenario.update(overrides)
    return scenario


def _dataset(tmp_path: Path, scenarios: list[dict], version: str | None = None) -> Path:
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps({
        "schema_version": version or "small_lecturer_image_teaching/v1",
        "scenarios": scenarios,
    }, ensure_ascii=False), encoding="utf-8")
    return path


def test_load_scenarios_passes_valid_dataset(tmp_path):
    scenarios = load_scenarios(_dataset(tmp_path, [_scenario(tmp_path)]))
    assert len(scenarios) == 1 and scenarios[0]["id"] == "image_v1_round_01"


def test_load_scenarios_rejects_wrong_schema_version(tmp_path):
    path = _dataset(tmp_path, [_scenario(tmp_path)], version="small_lecturer_image_teaching/v2")
    with pytest.raises(ValueError, match="schema_version 不符"):
        load_scenarios(path)


def test_load_scenarios_rejects_empty(tmp_path):
    with pytest.raises(ValueError, match="非空列表"):
        load_scenarios(_dataset(tmp_path, []))


def test_load_scenarios_surfaces_validation_errors(tmp_path):
    bad = _scenario(tmp_path, visual_dependency="partial")
    with pytest.raises(ValueError, match="visual_dependency 非法"):
        load_scenarios(_dataset(tmp_path, [bad]))


def test_to_cases_keeps_v1_question_dict(tmp_path):
    cases = to_cases([_scenario(tmp_path)])
    case = cases[0]
    assert case["id"] == "image_v1_round_01"
    assert case["question"]["text"].startswith("池塘周长")
    assert case["question"]["image"]["sha256"]
    assert case["student_turns"] and case["grade"] == "六年级"
    assert case["reference_answer"] == "10"


def test_to_judge_cases_builds_transcript_and_text_question(tmp_path):
    case = to_cases([_scenario(tmp_path)])[0]
    rows = [{
        "case_id": case["id"], "status": "ok",
        "transcript": {
            "turns": [{"student": "周长除以 3.14 吗?", "tutor": "先想想直径与半径的关系。"},
                      {"student": "", "tutor": "周长 = πd。"}],
            "summary": "半径 10 米。",
            "learner": {"grade": "六年级"},
        },
    }]
    judge_input = round_entry.to_judge_cases(rows, [case])
    assert len(judge_input) == 1
    entry = judge_input[0]
    assert entry["question"] == case["question"]["text"]  # judge 拿文本,不看图
    assert entry["reference_answer"] == "10"
    roles = [message["role"] for message in entry["messages"]]
    assert roles == ["user", "assistant", "assistant", "assistant"]


def test_to_judge_cases_skips_failed_rows(tmp_path):
    case = to_cases([_scenario(tmp_path)])[0]
    rows = [{"case_id": case["id"], "status": "failed", "transcript": {"turns": []}}]
    assert round_entry.to_judge_cases(rows, [case]) == []


def test_render_report_lists_dimensions_and_pass_count(tmp_path):
    cases = to_cases([_scenario(tmp_path)])
    scores = {cases[0]["id"]: {
        "scores": {dim: 2 for dim in round_entry.DIMENSIONS},
        "total": 12, "verdict": "pass",
    }}
    report = round_entry.render_report(cases, scores)
    assert "| 题 |" in report
    assert "first_question" in report
    assert "pass 1/1" in report


def test_render_report_marks_missing_case_failed(tmp_path):
    cases = to_cases([_scenario(tmp_path)])
    report = round_entry.render_report(cases, {})
    assert "FAIL" in report and "pass 0/1" in report
