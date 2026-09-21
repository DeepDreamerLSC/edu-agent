"""标定金标集 v2 冻结合同(标定卡口①):52 案、gate 三档、蒸馏面不带 judge 分数。

数据文件是冻结产物:本测试钉对账口径(52 案/14 硬期望/6 已核/32 仅诊断、
C01–C52 全覆盖、case_id 唯一),任何再蒸馏或手工改动撞此门即红。
"""

from __future__ import annotations

import json
from pathlib import Path

GOLDEN = Path(__file__).resolve().parents[2] / "edu_agent" / "evals" / "datasets" / "golden" / "calibration_golden_v2.jsonl"


def load_golden() -> tuple[dict, list[dict]]:
    lines = [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line]
    header, cases = lines[0], lines[1:]
    assert header.get("_comment"), "首行必须是来源/时间头注释"
    return header, cases


def test_golden_case_count_and_gate_breakdown():
    """52 案对账:hard=14(点火门)/verified=6(PM 已核)/diagnostic=32(仅报告)。"""
    header, cases = load_golden()
    assert header["case_count"] == 52
    assert len(cases) == 52
    gates = {"hard": 0, "verified": 0, "diagnostic": 0}
    for case in cases:
        assert case["gate"] in gates
        gates[case["gate"]] += 1
    assert gates == {"hard": 14, "verified": 6, "diagnostic": 32}


def test_golden_case_ids_unique_and_c_coverage():
    """case_id 唯一;C01–C52 案号全覆盖(映射 50 + C15 挑战案 + C52 构造案)。"""
    _, cases = load_golden()
    ids = [case["case_id"] for case in cases]
    assert len(set(ids)) == 52
    assert sorted(case["case_no"] for case in cases) == [f"C{i:02d}" for i in range(1, 53)]


def test_golden_hard_rows_carry_expectation():
    """hard 档(点火门)每案必有期望:scores(summary_mastery 下限)或 hard 块
    (answer_leaked/math_integrity/verdict)至少其一;verified 档同样带定档期望
    (PM 已核的 sm=0/2 与 math_integrity=2 锚点);仅 diagnostic 档不设期望字段。"""
    _, cases = load_golden()
    for case in cases:
        if case["gate"] in {"hard", "verified"}:
            assert case.get("hard") or case.get("scores"), case["case_id"]
        else:
            assert "hard" not in case and "scores" not in case, case["case_id"]
        for dim, expected in case.get("scores", {}).items():
            assert dim == "summary_mastery"
            assert isinstance(expected, int) or (isinstance(expected, dict) and set(expected) == {">="})


def test_golden_distillation_carries_no_judge_scores():
    """双盲纪律:蒸馏面不得带 judge 分数(六维其他维度/total/六维人均不出现在任何行)。"""
    _, cases = load_golden()
    forbidden = {"first_question", "socratic_followup", "grade_fit", "pacing", "termination", "total"}
    for case in cases:
        assert not (set(case) & forbidden)
        assert not (set(case.get("scores", {})) & forbidden)
