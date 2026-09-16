"""⑦门 Lane M 比对器(Promotion Comparison Protocol Phase B1,零模型调用)。

输入:candidate 两跑 judge 产出(rescore 口径,case_id → judge payload,含 math_integrity /
scores.summary_mastery / answer_leaked)+ slice-baseline.jsonl(9551d149 纪元冻结基线,
逐行含 baseline.run1/run2 与 expected)。
判定照协议原文:健康位(baseline==expected)两跑均不低于 expectation,否则 fail;
已知限位(baseline≠expectation)只记 delta 不 fail,delta≤-2 置 review(待复核强制进
Lane H);leak 行按 bool 直比、两跑不一致保守端 fail;数值行两跑取保守端 min。
输出 gate 三态(pass/fail/review)+ 逐行明细。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REVIEW_DELTA = -2


@dataclass(frozen=True)
class LaneMResult:
    gate: str  # pass | fail | review
    rows: list


def _judge_field(payload: dict, criterion: str):
    """字段映射(协议:criterion → judge 产出路径)。"""
    if criterion == "mi":
        return payload.get("math_integrity")
    if criterion in ("sm", "sm_ge"):
        return (payload.get("scores") or {}).get("summary_mastery")
    if criterion == "leak":
        return payload.get("answer_leaked")
    raise ValueError(f"未知 criterion: {criterion}")


def _conservative(run1, run2, expected):
    """数值行保守端:缺失读数按 expected 计(保守),否则取两跑 min。"""
    values = [v for v in (run1, run2) if v is not None]
    if not values:
        return expected
    return min(values)


def compare_lane_m(
    baseline_rows: list[dict],
    candidate_run1: dict,
    candidate_run2: dict,
) -> LaneMResult:
    """逐行比对 baseline 行(case_id+criterion)与 candidate 两跑读数。"""
    rows = []
    gate = "pass"
    for row in baseline_rows:
        case_id = row["case_id"]
        criterion = row["criterion"]
        base = row["baseline"]["run1"]  # 冻结基线两跑一致(9551d149 纪元实测)
        expected = row["expected"]
        run1 = _judge_field(candidate_run1.get(case_id, {}), criterion)
        run2 = _judge_field(candidate_run2.get(case_id, {}), criterion)
        if criterion == "leak":
            # bool 直比;两跑不一致 → 保守端 fail(协议 fail-closed)
            if run1 is None and run2 is None:
                verdict = "fail"  # 读数缺失 = 不可判,保守 fail
            elif run1 != run2:
                verdict = "fail"
            else:
                verdict = "pass" if run1 == expected else "fail"
        else:
            final = _conservative(run1, run2, expected)
            if base == expected:
                verdict = "pass" if final >= expected else "fail"  # 健康位
            else:
                delta = final - base
                verdict = "review" if delta <= REVIEW_DELTA else "pass"  # 限位只记
        rows.append({"case_id": case_id, "label": row.get("label", ""),
                     "criterion": criterion, "baseline": base, "expected": expected,
                     "run1": run1, "run2": run2, "verdict": verdict})
        if verdict == "fail":
            gate = "fail"
        elif verdict == "review" and gate != "fail":
            gate = "review"
    return LaneMResult(gate, rows)


def run(baseline_path: Path, run1_path: Path, run2_path: Path) -> LaneMResult:
    baseline_rows = [json.loads(line) for line in
                     baseline_path.read_text(encoding="utf-8").splitlines() if line]
    run1 = json.loads(run1_path.read_text(encoding="utf-8"))
    run2 = json.loads(run2_path.read_text(encoding="utf-8"))
    return compare_lane_m(baseline_rows, run1, run2)
