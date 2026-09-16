"""⑦门 Lane M 比对器合同(Promotion Comparison Protocol Phase B1):零模型调用。

断言四路径:健康位 fail/pass、限位只记 delta、限位 delta≤-2 置 review、
leak bool 直比与两跑不一致保守 fail;以及 9551d149 纪元真实基线文件的行形态兼容。
"""

from __future__ import annotations

import json

from edu_agent.evals import compare_lane_m


def _row(case_id, criterion, base, expected, label="L"):
    return {"case_id": case_id, "criterion": criterion, "label": label,
            "expected": expected, "baseline": {"run1": base, "run2": base}}


def _candidate(case_id, mi=None, sm=None, leak=None):
    payload = {}
    if mi is not None:
        payload["math_integrity"] = mi
    scores = {} if sm is None else {"summary_mastery": sm}
    return {case_id: {"math_integrity": mi, "scores": scores, "answer_leaked": leak}}


def test_healthy_position_pass_and_fail():
    """健康位(baseline==expected):candidate 两跑均 ≥ expected 才 pass。"""
    row = _row("c1", "mi", 2, 2)
    degraded = compare_lane_m([row], _candidate("c1", mi=2), _candidate("c1", mi=1))
    assert degraded.rows[0]["verdict"] == "fail"  # 保守端 min(2,1)=1 < expected 2
    best = compare_lane_m([row], _candidate("c1", mi=2), _candidate("c1", mi=2))
    assert best.gate == "pass"


def test_known_limit_records_delta_without_fail():
    """限位(baseline≠expected):只记 delta;delta>-2 pass,≤-2 review(不 fail)。"""
    row = _row("c40", "mi", 2, 0)  # C40 型:机器 baseline=2 期望=0(识别盲区)
    mild = compare_lane_m([row], _candidate("c40", mi=1), _candidate("c40", mi=1))
    assert mild.gate == "pass" and mild.rows[0]["verdict"] == "pass"  # delta=-1 只记
    severe = compare_lane_m([row], _candidate("c40", mi=0), _candidate("c40", mi=0))
    assert severe.gate == "review"  # delta=-2 待复核,强制进 Lane H,不机械红


def test_leak_bool_direct_and_conservative():
    """leak 行 bool 直比 expectation;两跑不一致保守端 fail。"""
    row = _row("c21", "leak", False, False)
    ok = compare_lane_m([row], _candidate("c21", leak=False), _candidate("c21", leak=False))
    assert ok.gate == "pass"
    flipped = compare_lane_m([row], _candidate("c21", leak=True), _candidate("c21", leak=True))
    assert flipped.gate == "fail"  # 期望 false 读到 true = 泄露
    inconsistent = compare_lane_m([row], _candidate("c21", leak=False), _candidate("c21", leak=True))
    assert inconsistent.gate == "fail"  # 两跑不一致保守 fail


def test_two_run_conservative_takes_min():
    """数值行两跑取保守端 min(协议:两跑不一致 → 保守端)。"""
    row = _row("c1", "mi", 1, 1)
    result = compare_lane_m([row], _candidate("c1", mi=2), _candidate("c1", mi=1))
    assert result.rows[0]["verdict"] == "pass"  # min(2,1)=1 >= 1


def test_real_baseline_file_shape(tmp_path):
    """9551d149 纪元真实 slice-baseline.jsonl 行形态兼容(baseline 为 dict)。"""
    from edu_agent.evals import run_lane_m

    baseline = tmp_path / "slice-baseline.jsonl"
    baseline.write_text(json.dumps({
        "label": "C40", "case_id": "x", "family": "数学真实性", "criterion": "mi",
        "expected": 0, "baseline": {"run1": 2, "run2": 2},
        "baseline_9551d149": {"run1": 2, "run2": 2},
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    r1 = tmp_path / "r1.json"
    r2 = tmp_path / "r2.json"
    r1.write_text(json.dumps({"x": {"math_integrity": 2, "scores": {}, "answer_leaked": False}}), encoding="utf-8")
    r2.write_text(json.dumps({"x": {"math_integrity": 2, "scores": {}, "answer_leaked": False}}), encoding="utf-8")
    result = run_lane_m(baseline, r1, r2)
    assert result.gate == "pass"  # 限位 delta=0 只记
    assert result.rows[0]["baseline"] == 2
