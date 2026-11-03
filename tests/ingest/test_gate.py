"""golden 门禁测试:断言判定与 false_accepted 口径(08 §5)。"""

from __future__ import annotations

import json
from pathlib import Path

from edu_agent.ingest import run_gate

QUESTIONS = [
    {"version": "ingest_questions_v1", "run_id": "r", "page_no": 1, "question_no": 1,
     "target_block_ids": [0], "question_bbox": [1, 1, 9, 9], "excluded_block_ids": [], "status": "accepted"},
]
ELEMENTS = [
    {"version": "ingest_elements_v1", "run_id": "r", "engine": "t", "page_no": 1,
     "lines": [{"bbox": [1, 1, 9, 9], "text": "1.计算"}], "visual_blocks": []},
]


def _files(tmp_path: Path) -> tuple[Path, Path, Path]:
    q = tmp_path / "questions.jsonl"
    e = tmp_path / "elements.jsonl"
    c = tmp_path / "cases.jsonl"
    q.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in QUESTIONS) + "\n", encoding="utf-8")
    e.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in ELEMENTS) + "\n", encoding="utf-8")
    return c, q, e


def test_gate_passes_clean_case(tmp_path: Path) -> None:
    c, q, e = _files(tmp_path)
    c.write_text(json.dumps({"case_id": "c1", "page": 1, "question_no": 1, "tier": "blocking",
                             "expected_status": "accepted", "forbidden_target_text": []}) + "\n", encoding="utf-8")
    report = run_gate(c, q, e)
    assert report["gate_pass"] and report["passed"] == 1


def test_gate_flags_pollution_as_false_accepted(tmp_path: Path) -> None:
    ELEMENTS[0]["lines"][0]["text"] = "选择题每小题3分 1.计算"
    c, q, e = _files(tmp_path)
    c.write_text(json.dumps({"case_id": "c1", "page": 1, "question_no": 1, "tier": "blocking",
                             "expected_status": "accepted", "forbidden_target_text": ["选择题每小题3分"]}) + "\n", encoding="utf-8")
    report = run_gate(c, q, e)
    assert not report["gate_pass"]
    assert report["false_accepted"] == 1
    ELEMENTS[0]["lines"][0]["text"] = "1.计算"


def test_gate_missing_question_fails_blocking(tmp_path: Path) -> None:
    c, q, e = _files(tmp_path)
    c.write_text(json.dumps({"case_id": "c9", "page": 2, "question_no": 7, "tier": "blocking"}) + "\n", encoding="utf-8")
    report = run_gate(c, q, e)
    assert report["blocking_failure"] == 1 and not report["gate_pass"]
