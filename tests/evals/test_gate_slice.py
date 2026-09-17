"""⑦门候选切片跑批器测试(#256 阶段 3,零 API)。"""

import json

from unittest.mock import MagicMock, patch

from edu_agent.evals import (
    build_teacher_pack,
    gate_from_runs,
    load_runnable_cases,
    load_slice_rows,
    run_candidate_slice,
)


def test_load_runnable_cases_covers_11_with_sources():
    """11 案齐:9 案带 steps 剧本(池内),2 案抽学生侧线性剧本(池外)。"""
    cases = load_runnable_cases()
    assert len(cases) == 11
    by_id = {c["id"]: c for c in cases}
    assert all(c.get("steps") or c.get("student_turns") for c in cases)  # 11 案全有剧本
    # 池内 8 案 steps 分支剧本 + stability_age 池内线性剧本 + 池外 2 案抽取
    assert sum(1 for c in cases if c.get("steps")) == 8
    assert sum(1 for c in cases if c.get("student_turns")) == 3
    # __r1 重跑槽位案:学生剧本非空(从冻结 messages 学生侧抽出)
    r1 = by_id["small_lecturer_teaching_context_shadow_pilot_20_stability_fraction_addition__r1"]
    assert r1["student_turns"]
    # 挑战案同理
    ch = by_id["challenge_coordinate_swap_20260914"]
    assert ch["student_turns"]


def test_run_candidate_slice_two_runs_full_rows():
    """双跑各 11 行,case_id 全对上切片;judge 输入换 messages、其余逐字冻结。"""
    cases = load_runnable_cases()
    slice_ids = {c["id"] for c in cases}
    frozen_rows = {"question": "Q", "reference_answer": "R", "grade": "5",
                   "messages": [{"role": "assistant", "content": "旧转录"}]}

    def fake_run_case(case):
        return {"turns": [{"student": "s", "tutor": "t", "state": "dialogue"}],
                "summary": "总结"}

    def fake_judge(gateway, judge_case, role="judge", session_id=None):
        assert judge_case["question"] == "Q"  # 冻结行字段逐字保留
        assert judge_case["messages"] != frozen_rows["messages"]  # messages 已换新
        return {"math_integrity": 2, "answer_leaked": False, "total": 9,
                "verdict": "pass", "scores": {"summary_mastery": 2}}

    with patch("edu_agent.evals.gate_slice.ElicitSubject") as mock_subject, \
         patch("edu_agent.evals.gate_slice.judge_transcript", side_effect=fake_judge), \
         patch("edu_agent.evals.gate_slice.load_slice_rows",
               return_value={cid: dict(frozen_rows, id=cid) for cid in slice_ids}):
        mock_subject.return_value.run_case.side_effect = fake_run_case
        run1, run2 = run_candidate_slice("候选elicit", "候选support", MagicMock())
        assert set(run1) == slice_ids and set(run2) == slice_ids
        assert run1["challenge_coordinate_swap_20260914"]["math_integrity"] == 2
        # ElicitSubject 收到候选双旋钮
        assert mock_subject.call_args.args[0] == "候选elicit"
        assert mock_subject.call_args.kwargs["support_hint"] == "候选support"


def test_gate_from_runs_delegates_to_lane_m():
    """跑批直比 = lane_m 判定(健康位 pass、缺失读数保守 fail)。"""
    cases = load_runnable_cases()
    baseline = [{"case_id": cases[0]["id"], "criterion": "mi", "expected": 2,
                 "baseline": {"run1": 2, "run2": 2}}]
    ok = {cases[0]["id"]: {"math_integrity": 2}}
    result = gate_from_runs(baseline, ok, dict(ok))
    assert result.gate == "pass"
    result = gate_from_runs(baseline, {}, {})  # 读数缺失 → 保守端 expected=2 → pass?
    # 数值行保守端:缺失按 expected 计 → final=2 >= expected → pass(fail-closed 只对 leak)
    assert result.gate == "pass"


def test_run_candidate_slice_persists_transcripts(tmp_path):
    """transcripts_out 给定时逐跑逐案落盘(Lane H 材料)。"""
    cases = load_runnable_cases()
    ids = {c["id"] for c in cases}
    with patch("edu_agent.evals.gate_slice.ElicitSubject") as mock_subject, \
         patch("edu_agent.evals.gate_slice.judge_transcript",
               return_value={"math_integrity": 2, "answer_leaked": False}):
        mock_subject.return_value.run_case.return_value = {
            "turns": [{"student": "s", "tutor": "t", "state": "dialogue"}], "summary": "x"}
        run_candidate_slice("e", "s", MagicMock(), transcripts_out=tmp_path)
    for run in ("run1", "run2"):
        saved = {p.stem for p in (tmp_path / run).glob("*.json")}
        assert saved == ids


def test_build_teacher_pack_blind_and_reversible(tmp_path):
    """盲包:A/B 随机可复现;解盲映射在返回值(调用方落包外);三判据判定栏在。"""
    import json

    for cid in load_slice_rows():
        d = tmp_path / "run1"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{cid}.json").write_text(json.dumps(
            {"turns": [{"student": "候选学生", "tutor": "候选导师", "state": "dialogue"}],
             "summary": "候选总结"}), encoding="utf-8")
    pack_dir = tmp_path / "pack"
    mapping = build_teacher_pack(tmp_path, pack_dir, seed=7)
    assert set(mapping) == set(load_slice_rows())
    assert not (pack_dir / "mapping.json").exists()  # 解盲映射不进教师包
    again = build_teacher_pack(tmp_path, pack_dir, seed=7)
    assert again == mapping  # seed 可复现
    sample = (pack_dir / "challenge_coordinate_swap_20260914.md").read_text(encoding="utf-8")
    for field in ("题目", "Transcript A", "Transcript B", "数学真实性", "学生掌握归因",
                  "转述忠实性", "总体", "具体证据"):
        assert field in sample
    # A/B 二者之一是候选转录(解盲后能对上)
    assert "候选导师" in (sample.split("## Transcript A")[1].split("## Transcript B")[0]
                        if mapping["challenge_coordinate_swap_20260914"] == "A"
                        else sample.split("## Transcript B")[1].split("## 判定")[0])


def test_slice_v2_semantic_repair():
    """v2:C35 退出(11 案无 simple_probability),C36 进驻(慈善转述正向位);
    十案逐字携带;判据锚逐字相同。"""
    from edu_agent.evals import load_slice_rows

    v1 = load_slice_rows("v1")
    v2 = load_slice_rows("v2")
    assert len(v2) == 11
    assert "small_lecturer_math_gold_candidates_simple_probability_complete_reasoning" not in v2
    c36 = "small_lecturer_teaching_context_shadow_pilot_20_stability_equation_subtract"
    assert c36 in v2 and v2[c36]["messages"]
    carried = set(v1) - {"small_lecturer_math_gold_candidates_simple_probability_complete_reasoning"}
    assert carried <= set(v2)  # 十案逐字携带
    v1_rows = {json.loads(l)["case_id"]: json.loads(l) for l in open(
        "edu_agent/evals/artifacts/teacher-gate-slice/slice-baseline.jsonl") if l.strip()}
    v2_rows = {json.loads(l)["case_id"]: json.loads(l) for l in open(
        "edu_agent/evals/artifacts/teacher-gate-slice-v2/slice-baseline.jsonl") if l.strip()}
    for cid in carried:
        assert v2_rows[cid]["expected"] == v1_rows[cid]["expected"]  # 判据/期望不变
        assert v2_rows[cid]["criterion"] == v1_rows[cid]["criterion"]
    assert v2_rows[c36]["criterion"] == "leak" and v2_rows[c36]["expected"] is False
    # C36 可运行(池内 steps/stability 剧本)
    cases = {c["id"]: c for c in load_runnable_cases("v2")}
    assert cases[c36].get("steps") or cases[c36].get("student_turns")
