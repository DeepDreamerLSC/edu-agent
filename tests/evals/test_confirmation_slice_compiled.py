"""confirmation 三 slice 编译件(#412 prereg §三)验收面:结构+溯源+judge 闸+dry-run。

五层全零真模型:
- 结构与规模:24 案三 slice 计数与头部互洽;低于 prereg 区间的 slice(负向 6/8-12、
  866 型 2/3-5)须在 selection_funnel 带如实报数说明(不凑数纪律的可审计面);
- 排除核对:与 r3 已用 23 案零重叠(prereg §三排除条款,I7);
- 溯源(不造数据):每条学生文本 ⊆ 源记录 student 轮原文、question 与源
  problem.text 逐字一致(回连 normalized 层,sha256 与编译头核对);
- judge 闸(ER judge v2 冻结语义,按路径加载同 tests/evals/test_er_judge_v2.py
  先例):positive/type866 的 said 恰在判定终答轮置位(正向门分母成立)、
  negative 剧本 said 永不置位且答案原值不入剧本轮(premature 信号不漏);
- dry-run:FakeGateway 驱动 KernelSubject 抽 2 条(正向/负向各一)——线性照录
  逐字一致(本批无 R3 分支,无路由面)。
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

COMPILED = DATASETS_DIR / "external_slices" / "socraticmath_confirmation_v1.json"
NORMALIZED = DATASETS_DIR / "external_normalized" / "socraticmath.jsonl"
R3_EXECUTABLE = DATASETS_DIR / "external_slices" / "socraticmath_executable_v1.json"
V1 = "small_lecturer_dialogue_scenario/v1"
SLICE_POS = "confirmation_positive_student_final_answer"
SLICE_NEG = "confirmation_negative_student_stops_short"
SLICE_866 = "confirmation_type866_answer_complete_extensible"

_JUDGE_PATH = (
    Path(__file__).resolve().parents[2]
    / "edu_agent" / "evals" / "artifacts" / "er-judge-v2" / "er_judge_v2.py"
)
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


def test_header_counts_match_scenarios_and_prereg_bands():
    """24 案三 slice 计数互洽;区间内/低于区间均须与 funnel 报数一致。"""
    payload = _load()
    scenarios = payload["scenarios"]
    counts = payload["counts"]
    by_slice = {s: sum(1 for x in scenarios if x["compile"]["slice"] == s)
                for s in (SLICE_POS, SLICE_NEG, SLICE_866)}
    short = {SLICE_POS: "positive", SLICE_NEG: "negative", SLICE_866: "type866"}
    assert counts == {**{short[k]: v for k, v in by_slice.items()},
                      "total": len(scenarios)}
    assert 12 <= by_slice[SLICE_POS] <= 16          # prereg §三:正向 12-16
    assert by_slice[SLICE_NEG] == payload["selection_funnel"]["negative"]["final"]
    assert by_slice[SLICE_866] == payload["selection_funnel"]["type866"]["final"]
    # 低于 prereg 区间的 slice 必须带如实报数说明(不凑数纪律)
    if by_slice[SLICE_NEG] < 8:
        assert "如实报数" in payload["selection_funnel"]["negative"]["note"]
    if by_slice[SLICE_866] < 3:
        assert "如实报数" in payload["selection_funnel"]["type866"]["note"]


def test_zero_overlap_with_r3_used_23():
    """prereg §三排除条款:与 r3 已用 23 案零重叠(I7)。"""
    payload = _load()
    r3_ids = {s["id"] for s in json.loads(
        R3_EXECUTABLE.read_text(encoding="utf-8"))["scenarios"]}
    assert len(r3_ids) == 23
    ours = {s["id"] for s in payload["scenarios"]}
    assert not (ours & r3_ids), f"与 r3 重叠:{sorted(ours & r3_ids)}"
    assert set(payload["compiled_from"]["excluded_r3_used"]) == r3_ids


def test_provenance_no_fabrication():
    """I1/I4:学生文本⊆源 student 轮原文、question 逐字;证据链 sha256 核对。"""
    payload = _load()
    assert hashlib.sha256(NORMALIZED.read_bytes()).hexdigest() == \
        payload["compiled_from"]["normalized_sha256"], "证据链(normalized)断裂"
    records = _source_records(payload)
    assert len(records) == len(payload["scenarios"]) == 24
    for scenario in payload["scenarios"]:
        record = records[scenario["compile"]["record_id"]]
        student_texts = [t["text"] for t in record["reference_dialogue"]
                         if t["role"] == "student"]
        assert scenario["question"] == record["problem"]["text"], \
            f"{scenario['id']} I4 违例"
        for turn in scenario["student_turns"]:
            assert any(turn in text for text in student_texts), \
                f"{scenario['id']} 学生轮非源文子串(造数据红线)"
        # 逐案判定依据在头部 selection_evidence 与 compile.selection 双登记
        evidence = payload["selection_evidence"][scenario["id"]]
        assert evidence["basis"] == scenario["compile"]["selection"]["basis"]
        assert evidence["slice"] == scenario["compile"]["slice"]
        assert evidence["basis"].strip(), f"{scenario['id']} 缺判定依据(审计凭证)"


def test_judge_gates_said_alignment_and_negative_no_leak():
    """I5/I6:ER judge v2 冻结语义下 said 与判定轮对齐/负向永不置位零原值。"""
    payload = _load()
    records = _source_records(payload)
    for scenario in payload["scenarios"]:
        record = records[scenario["compile"]["record_id"]]
        case = {"question": {"text": record["problem"]["text"],
                             "answer": record["problem"].get("answer") or ""}}
        keys = er_judge_v2.answer_keys(case)
        said_index = None
        for turn, dialogue_index in zip(
                scenario["student_turns"],
                scenario["compile"]["student_turn_dialogue_indexes"], strict=True):
            if er_judge_v2.student_asserts_answer(case, turn, keys):
                said_index = dialogue_index
                break
        compile_info = scenario["compile"]
        if compile_info["slice"] in (SLICE_POS, SLICE_866):
            assert said_index == compile_info["selection"]["hit_turn_index"], \
                f"{scenario['id']} said 轮 {said_index} != 判定轮"
        else:
            assert said_index is None, \
                f"{scenario['id']} 负向剧本 said 置位(轮 {said_index})"
            answer = record["problem"].get("answer") or ""
            tokens = {float(m) for m in re.findall(r"\d+(?:\.\d+)?", answer)}
            for turn in scenario["student_turns"]:
                in_turn = {float(m)
                           for m in re.findall(r"\d+(?:\.\d+)?", turn)}
                assert not (tokens & in_turn), \
                    f"{scenario['id']} 答案原值泄露入负向剧本轮"


def test_v1_shape_matches_dialogue_scenario_v1_convention():
    """v1 子集与 dialogue_scenario/v1 既有件同形;全 R1 线性、无分支剧本。"""
    payload = _load()
    for scenario in payload["scenarios"]:
        assert scenario["schema_version"] == V1
        assert scenario["id"] and scenario["title"]
        assert isinstance(scenario["question"], str) and scenario["question"].strip()
        assert scenario["student_turns"] and all(
            isinstance(t, str) and t.strip() for t in scenario["student_turns"])
        assert scenario["expect"] == {"ready_to_record": True}
        assert scenario["compile"]["rule"] == "R1"
        assert "steps" not in scenario and scenario["trajectory_tags"] == [
            scenario["compile"]["slice"]]


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
        "socraticmath_train_2322",
        ["我们来看这道题。首先,减数增加、被减数减少时,差会怎么变化呢?",
         "嗯,你的思路有了。那你算出来差是多少呢?",
         "这个结果我们再检查一下,你确定吗?",
         "完全正确,差就是52。"])
    assert positive[-1] == "应该是74减去6再减去16，结果是52。"
    negative = _replay(
        "socraticmath_train_5181",
        ["这是一道求平均速度的问题。你知道速度怎么求吗?",
         "很好。那往返的总路程是多少呢?",
         "不错。那总时间怎么算呢?",
         "非常好。那平均速度是多少呢?",
         "我们再看看,平均速度到底是多少?"])
    assert negative[-1] == \
        "飞机的平均速度是3600千米除以我刚算出来的总时间450分钟。"


def test_compiler_script_is_reproducible():
    """编译脚本在当前源数据上重放结果与入库件逐字一致(编译可复算)。"""
    script = (Path(__file__).resolve().parents[2]
              / "scripts" / "confirmation_slice_compile.py")
    result = subprocess.run([sys.executable, str(script)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert _load() == json.loads(COMPILED.read_text(encoding="utf-8"))
