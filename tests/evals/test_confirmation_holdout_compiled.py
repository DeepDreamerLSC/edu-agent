"""fresh confirmation holdout 编译件(终裁执行链⑦燃料)验收面:结构+溯源+judge 闸
+反污染(I7')+变换校验+dry-run。

六层全零真模型:
- 结构与规模:22 案(positive 16/negative 6[type866 0 如实报数])与头部互洽;
  低于对齐配比(#413 的 2 案)的 866 型须在 selection_funnel 带如实报数说明;
- 反污染(I7'):与 r3 已用 23 案、confirm 24 案零重叠;与 32 案 regression
  corpus(本 PR 另一资产,全部为已曝光案)零重叠;
- 溯源(不造数据):学生文本 ⊆ 源 student 轮原文、question 逐字;证据链 sha256;
- judge 闸(ER judge v2 冻结语义):positive said 恰在判定终答轮、negative
  剧本 said 永不置位且答案原值不入剧本轮;变换案 cut_before 轮=源终答轮;
- 变换标记:negative origin 二值(fresh_scan/transform),transform 案必带
  compile.transform.cut_before 记录;
- dry-run:FakeGateway 抽 2 条(正/负各一)线性照录逐字一致。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

from edu_agent.evals import DATASETS_DIR, KernelSubject, to_kernel_case

from teachkit import FakeGateway

COMPILED = DATASETS_DIR / "external_slices" / "socraticmath_confirmation_holdout_v1.json"
NORMALIZED = DATASETS_DIR / "external_normalized" / "socraticmath.jsonl"
R3_EXECUTABLE = DATASETS_DIR / "external_slices" / "socraticmath_executable_v1.json"
CONFIRMATION = DATASETS_DIR / "external_slices" / "socraticmath_confirmation_v1.json"
REGRESSION_CORPUS = (DATASETS_DIR /
                     "small_lecturer_completion_gate_regression_32_v1.json")
V1 = "small_lecturer_dialogue_scenario/v1"
SLICE_POS = "confirmation_positive_student_final_answer"
SLICE_NEG = "confirmation_negative_student_stops_short"
SLICE_866 = "confirmation_type866_answer_complete_extensible"

_JUDGE_PATH = (Path(__file__).resolve().parents[2]
               / "edu_agent" / "evals" / "artifacts" / "er-judge-v2" / "er_judge_v2.py")
_spec = importlib.util.spec_from_file_location("er_judge_v2", _JUDGE_PATH)
er_judge_v2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(er_judge_v2)


def _load() -> dict:
    return json.loads(COMPILED.read_text(encoding="utf-8"))


def _source_records(payload: dict) -> dict[str, dict]:
    ids = {s["compile"]["record_id"] for s in payload["scenarios"]}
    records = {}
    with NORMALIZED.open(encoding="utf-8") as handle:
        for line in handle:
            if not any(sid in line for sid in ids):
                continue
            record = json.loads(line)
            if record.get("id") in ids:
                records[record["id"]] = record
    return records


def _start(reply: str) -> dict:
    return {"acceptable": True, "transcription": "", "steps": [], "reply": reply}


def _tutor(reply: str) -> dict:
    return {"reason": "引导", "reply": reply, "ready_to_confirm": False,
            "cited_numbers": []}


def test_header_counts_match_scenarios_and_funnel():
    """22 案计数互洽;低于对齐配比的 slice 须带如实报数说明(不凑数纪律)。"""
    payload = _load()
    scenarios = payload["scenarios"]
    counts = payload["counts"]
    by_slice = {s: sum(1 for x in scenarios if x["compile"]["slice"] == s)
                for s in (SLICE_POS, SLICE_NEG, SLICE_866)}
    assert counts["positive"] == by_slice[SLICE_POS] == 16
    assert counts["negative"] == by_slice[SLICE_NEG] == 6
    assert counts["type866"] == by_slice[SLICE_866] == 0
    assert counts["total"] == len(scenarios) == 22
    assert counts["negative_natural"] + counts["negative_transform"] == 6
    # 866 型 0 案:如实报数说明必须在场
    assert "如实报数" in payload["selection_funnel"]["type866"]["note"]
    # 负向自然止步不足,变换补足的分层说明必须在场
    assert "origin_mix" in payload["selection_funnel"]["negative"]
    assert "留人审" in payload["selection_funnel"]["negative"]["note"]


def test_zero_overlap_with_all_exposure_lists():
    """I7' 反污染:与 r3 23 案、confirm 24 案、32 案 regression corpus 零重叠。"""
    payload = _load()
    ours = {s["id"] for s in payload["scenarios"]}
    r3_ids = {s["id"] for s in json.loads(
        R3_EXECUTABLE.read_text(encoding="utf-8"))["scenarios"]}
    confirm_ids = {s["id"] for s in json.loads(
        CONFIRMATION.read_text(encoding="utf-8"))["scenarios"]}
    assert len(r3_ids) == 23 and len(confirm_ids) == 24
    assert not (ours & r3_ids), f"与 r3 重叠:{sorted(ours & r3_ids)}"
    assert not (ours & confirm_ids), f"与 confirm 24 重叠:{sorted(ours & confirm_ids)}"
    assert set(payload["compiled_from"]["excluded_r3_used"]) == r3_ids
    assert set(payload["compiled_from"]["excluded_confirm_24"]) == confirm_ids
    # 与 32 案 regression corpus(已曝光案全集)零重叠——两资产分立铁律
    corpus_ids = {c["id"] for c in json.loads(
        REGRESSION_CORPUS.read_text(encoding="utf-8"))["cases"]}
    assert len(corpus_ids) == 32
    assert not (ours & corpus_ids), f"与 regression corpus 重叠:{sorted(ours & corpus_ids)}"
    # 负向三案(已曝光)显式不在场
    assert not (ours & {"socraticmath_train_2791", "socraticmath_train_5106",
                        "socraticmath_train_3490"})


def test_provenance_no_fabrication():
    """I1/I4:学生文本⊆源 student 轮原文、question 逐字;证据链 sha256 核对。"""
    payload = _load()
    assert hashlib.sha256(NORMALIZED.read_bytes()).hexdigest() == \
        payload["compiled_from"]["normalized_sha256"], "证据链(normalized)断裂"
    records = _source_records(payload)
    assert len(records) == len(payload["scenarios"]) == 22
    for scenario in payload["scenarios"]:
        record = records[scenario["compile"]["record_id"]]
        student_texts = [t["text"] for t in record["reference_dialogue"]
                         if t["role"] == "student"]
        assert scenario["question"] == record["problem"]["text"], \
            f"{scenario['id']} I4 违例"
        for turn in scenario["student_turns"]:
            assert any(turn in text for text in student_texts), \
                f"{scenario['id']} 学生轮非源文子串(造数据红线)"
        evidence = payload["selection_evidence"][scenario["id"]]
        assert evidence["basis"] == scenario["compile"]["selection"]["basis"]
        assert evidence["slice"] == scenario["compile"]["slice"]
        assert evidence["basis"].strip(), f"{scenario['id']} 缺判定依据(审计凭证)"


def test_judge_gates_said_alignment_and_negative_no_leak():
    """I5/I6:ER judge v2 冻结语义下 said 与判定轮对齐/负向永不置位零原值;
    变换案 cut_before 轮经 judge 校验为源终答轮。"""
    payload = _load()
    records = _source_records(payload)
    for scenario in payload["scenarios"]:
        record = records[scenario["compile"]["record_id"]]
        case = {"question": {"text": record["problem"]["text"],
                             "answer": record["problem"].get("answer") or ""}}
        keys = er_judge_v2.answer_keys(case)
        compile_info = scenario["compile"]
        turns = scenario["student_turns"]
        if compile_info["slice"] in (SLICE_POS, SLICE_866):
            pos = compile_info["student_turn_dialogue_indexes"].index(
                compile_info["selection"]["hit_turn_index"])
            assert er_judge_v2.student_asserts_answer(case, turns[pos], keys), \
                f"{scenario['id']} said 未在判定轮置位"
            assert not any(er_judge_v2.student_asserts_answer(case, t, keys)
                           for t in turns[:pos]), \
                f"{scenario['id']} said 早于判定轮置位"
        else:
            assert not any(er_judge_v2.student_asserts_answer(case, t, keys)
                           for t in turns), \
                f"{scenario['id']} 负向剧本 said 置位"
            answer = record["problem"].get("answer") or ""
            tokens = {float(m) for m in re.findall(r"\d+(?:\.\d+)?", answer)}
            for turn in scenario["student_turns"]:
                in_turn = {float(m) for m in re.findall(r"\d+(?:\.\d+)?", turn)}
                assert not (tokens & in_turn), \
                    f"{scenario['id']} 答案原值泄露入负向剧本轮"
            origin = compile_info["origin"]
            assert origin in ("fresh_scan", "transform"), \
                f"{scenario['id']} origin 非法:{origin}"
            if origin == "transform":
                cut = compile_info["transform"]["cut_before"]
                source_turn = next(
                    t["text"] for t in record["reference_dialogue"]
                    if record["reference_dialogue"].index(t) == cut)
                assert er_judge_v2.student_asserts_answer(
                    case, source_turn, keys), \
                    f"{scenario['id']} 变换校验:cut_before 轮非源终答轮"


def test_v1_shape_and_transform_records():
    """v1 同形;全线性;变换案必带 cut_before 与 origin 标记,自然案不得带。"""
    payload = _load()
    for scenario in payload["scenarios"]:
        assert scenario["schema_version"] == V1
        assert scenario["student_turns"] and all(
            isinstance(t, str) and t.strip() for t in scenario["student_turns"])
        assert scenario["expect"] == {"ready_to_record": True}
        assert "steps" not in scenario
        assert scenario["trajectory_tags"] == [scenario["compile"]["slice"]]
        compile_info = scenario["compile"]
        if compile_info["origin"] == "transform":
            assert compile_info["rule"] == "R1+T"
            assert compile_info["transform"]["kind"] == "cut_before_assertion"
            assert isinstance(compile_info["transform"]["cut_before"], int)
        else:
            assert compile_info["rule"] == "R1"
            assert "transform" not in compile_info


def test_dry_run_positive_and_negative_replay_verbatim():
    """dry-run 抽 2 条(正/负各一):学生轮按序原文回放,与剧本逐字一致。"""
    payload = _load()

    def _replay(scenario_id: str, replies: list[str]) -> list[str]:
        scenario = next(s for s in payload["scenarios"] if s["id"] == scenario_id)
        gateway = FakeGateway(
            tutor_payloads=[_start(replies[0])] + [_tutor(t) for t in replies[1:]])
        transcript = KernelSubject(gateway).run_case(to_kernel_case(scenario))
        assert [t["student"] for t in transcript["turns"][1:]] == \
            scenario["student_turns"]
        assert len(gateway.requests) == 1 + len(scenario["student_turns"])
        return [t["student"] for t in transcript["turns"][1:]]

    positive = _replay(
        "socraticmath_train_2804",
        ["我们来看这道题。三种球各买一个,总价该怎么算呢?",
         "很好。那篮球和足球先加起来是多少呢?",
         "不错。再加上排球的价格呢?",
         "非常好。那总共是多少元呢?",
         "完全正确,总共就是353元。你总结一下方法吧。"])
    assert positive[-1] == \
        "我需要做的就是把每一种球的价格相加，得到的结果就是他们的总价格。"
    negative = _replay(
        "socraticmath_train_5220",
        ["这是一道求除数的问题。你知道除法各部分的关系吗?",
         "很好。那被除数、除数、商和余数之间是什么关系呢?",
         "不错。那根据题目,420÷____=24…12,除数该怎么求呢?",
         "那我们来算一下 (420-12)÷24 的结果是多少呢?",
         "我们再看看,这个除数到底是多少呢?"])
    assert negative[-1] == \
        "根据除法规则，需要执行（420-12）÷24，就可以得到正确的答案。"


def test_compiler_script_is_reproducible():
    """编译脚本在当前源数据上重放结果与入库件逐字一致(编译可复算)。"""
    script = (Path(__file__).resolve().parents[2]
              / "scripts" / "confirmation_holdout_compile.py")
    result = subprocess.run([sys.executable, str(script)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert _load() == json.loads(COMPILED.read_text(encoding="utf-8"))
