"""golden 门禁(08 §5):声明式断言 + 唯一 runner;blocking 层零容忍。

case 字段:case_id/pdf/page/tier(blocking|watch)/question_no/
expected_status/forbidden_target_text[]。报告含 false_accepted 计数(08 §5 容差口径)。
"""

from __future__ import annotations

import json
from typing import Any
from pathlib import Path

from edu_agent.ingest.artifacts import read_jsonl


def _target_text(question: dict[str, Any], elements_by_page: dict[int, dict[str, Any]]) -> str:
    page = elements_by_page.get(int(question["page_no"]), {})
    lines = page.get("lines", [])
    return "\n".join(str(lines[i]["text"]) for i in question["target_block_ids"] if i < len(lines))


def evaluate_case(case: dict[str, Any], questions: list[dict[str, Any]], elements_by_page: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """单 case 判定:定位题号 → expected_status / forbidden_target_text 两条断言。"""
    matched = [q for q in questions if int(q["page_no"]) == int(case["page"]) and str(q["question_no"]) == str(case["question_no"])]
    failures: list[str] = []
    if not matched:
        return {"case_id": case["case_id"], "tier": case.get("tier", "watch"), "passed": False, "failures": ["question_not_found"], "false_accepted": False}
    question = matched[0]
    if question["status"] != case.get("expected_status", "accepted"):
        failures.append(f"expected_status {case.get('expected_status')} != {question['status']}")
    text = _target_text(question, elements_by_page)
    leaked = [bad for bad in case.get("forbidden_target_text", []) if bad in text]
    if leaked:
        failures.append(f"forbidden_target_text leaked: {leaked}")
    return {
        "case_id": case["case_id"],
        "tier": case.get("tier", "watch"),
        "passed": not failures,
        "failures": failures,
        "false_accepted": bool(leaked) and question["status"] == "accepted",
    }


def run_gate(cases_path: Path, questions_jsonl: Path, elements_jsonl: Path) -> dict[str, Any]:
    """跑全部 case 出报告;blocking_failure 必须为 0(08 §5 零容忍)。"""
    cases = [json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    questions = list(read_jsonl(questions_jsonl))
    elements_by_page = {int(record["page_no"]): record for record in read_jsonl(elements_jsonl)}
    results = [evaluate_case(case, questions, elements_by_page) for case in cases]
    report = {
        "case_count": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "blocking_failure": sum(1 for r in results if not r["passed"] and r["tier"] == "blocking"),
        "false_accepted": sum(1 for r in results if r["false_accepted"]),
        "cases": results,
    }
    report["gate_pass"] = report["blocking_failure"] == 0
    return report
