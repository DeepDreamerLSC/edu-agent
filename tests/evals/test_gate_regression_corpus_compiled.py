"""32 案 Trusted Completion Gate regression corpus(C 段预备件)验收面:
组成+断言+溯源指纹+探针一致性+dry-run。

五层全零真模型:
- 组成与设计件一致(§六.1):confirmation 全 24(负向三案为其负向成员)+ ablation
  五臂 8 = 32;负向七案(confirmation 负 6 + val_13)期望 needs_review;5106 带
  summary 代说消失旗;正向四锚(§六.2)在册;
- 期望行为断言完备:每案 final_state/no_reask/evidence 轮位成形;张力案
  (A 段建议规格下无可构造轮)逐案带 tension 旗——预登记,防 C 段判读时静默重释;
- 溯源指纹:嵌入 replay_input 与源 scenario 逐字一致;source_files sha256
  与仓内文件一致(证据链);
- gate_a_probe 一致性:抽验探针可由 A 段 verify_completion 复算(建议规格);
- dry-run:FakeGateway 抽 1 条线性照录;编译可复算。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from edu_agent.agents.small_lecturer import AnswerSpec, verify_completion
from edu_agent.evals import DATASETS_DIR, KernelSubject, to_kernel_case

from teachkit import FakeGateway

CORPUS = (DATASETS_DIR /
          "small_lecturer_completion_gate_regression_32_v1.json")
CONFIRMATION = DATASETS_DIR / "external_slices" / "socraticmath_confirmation_v1.json"
EXECUTABLE = DATASETS_DIR / "external_slices" / "socraticmath_executable_v1.json"
SHORTBOARD = DATASETS_DIR / "small_lecturer_regression_shortboard_v1.json"

NEGATIVE_THREE = ("socraticmath_train_2791", "socraticmath_train_5106",
                  "socraticmath_train_3490")
ANCHOR_FOUR = ("socraticmath_train_2322", "socraticmath_train_2960",
               "socraticmath_train_3695", "socraticmath_train_3138")
ABLATION_CLOSURE = ("repro-close-loop-cross-stitch", "socraticmath_train_2591",
                    "socraticmath_train_675", "socraticmath_val_13")
ABLATION_ER = ("socraticmath_train_3565", "socraticmath_train_4402",
               "socraticmath_train_3666", "socraticmath_train_866")


def _load() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def test_composition_matches_design_section_six():
    """§六.1:24+8=32;负向三案/四锚/五臂清单全在册。"""
    payload = _load()
    cases = payload["cases"]
    by_id = {c["id"]: c for c in cases}
    assert len(cases) == 32 and len(by_id) == 32
    assert payload["counts"] == {"confirmation_24": 24, "ablation_8": 8,
                                 "negative_must_disappear": 7,
                                 "anchor_four": 4, "total": 32}
    for sid in NEGATIVE_THREE:  # 负向三案=confirmation 负向成员,不重复计
        assert sid in by_id
        assert by_id[sid]["group"] == "confirmation_24"
        assert by_id[sid]["expected"]["final_state"] == "needs_review"
    assert by_id["socraticmath_train_5106"]["expected"]["summary_no_answer_speak"] is True
    for sid in ANCHOR_FOUR:
        assert by_id[sid]["expected"].get("anchor") is True, f"四锚缺席:{sid}"
    got_abl = {c["id"] for c in cases if c["group"] == "ablation_8"}
    assert got_abl == set(ABLATION_CLOSURE) | set(ABLATION_ER)
    # val_13 假收束防线旗(§六.1 负向:五臂 AB-old completed(假) 实证)
    assert "false_closure_must_disappear" in by_id["socraticmath_val_13"]["expected"]["flags"]


def test_expected_assertions_wellformed_and_tensions_flagged():
    """期望断言完备;张力案(A 段建议规格无 evidence 轮)逐案预登记。"""
    payload = _load()
    tension = 0
    for case in payload["cases"]:
        expected = case["expected"]
        assert expected["final_state"] in ("completed", "needs_review")
        assert isinstance(expected["no_reask_after_evidence"], bool)
        assert expected["design_refs"], f"{case['id']} 缺设计引用"
        assert isinstance(expected["flags"], list)
        probe = case["gate_a_probe"]
        assert probe.get("note", "").startswith("ADVISORY") or \
            "ADVISORY" in probe.get("note", ""), f"{case['id']} 探针缺 ADVISORY 标记"
        if any("tension" in f or "unexpected" in f for f in expected["flags"]):
            tension += 1
            if expected["final_state"] == "completed":
                has_ev = bool(probe.get("evidence_turns")
                              or probe.get("any_evidence"))
                assert not has_ev, \
                    f"{case['id']} tension 旗与探针结果矛盾"
    # 预登记张力面非空(§三 precision-first 白名单 vs §六.1 不劣化)——冻结在案
    assert tension >= 10, "张力案预登记面异常缩水(判读依据丢失)"
    # pending_review 头部含 700m 差异记录(设计件优先原则的执行凭证)
    assert any("700m" in note for note in payload["pending_review"])


def test_provenance_fingerprints_and_verbatim_embedding():
    """嵌入 replay_input 与源 scenario 逐字一致;源文件 sha256 指纹一致。"""
    payload = _load()
    for rel, digest in payload["source_files"].items():
        assert hashlib.sha256((Path(__file__).resolve().parents[2] / rel)
                              .read_bytes()).hexdigest() == digest, \
            f"证据链断裂:{rel}"
    conf = {s["id"]: s for s in json.loads(
        CONFIRMATION.read_text(encoding="utf-8"))["scenarios"]}
    exec_ = {s["id"]: s for s in json.loads(
        EXECUTABLE.read_text(encoding="utf-8"))["scenarios"]}
    for case in payload["cases"]:
        sid = case["id"]
        if case["group"] == "confirmation_24":
            assert case["replay_input"] == conf[sid], f"{sid} 嵌入与源不一致"
        elif sid in exec_:
            assert case["replay_input"] == exec_[sid], f"{sid} 嵌入与源不一致"
        else:
            assert sid == "repro-close-loop-cross-stitch"
            board = {s["id"]: s for s in json.loads(
                SHORTBOARD.read_text(encoding="utf-8"))["scenarios"]}
            src = board[sid]
            out = case["replay_input"]
            assert out["question"] == src["question"]
            assert out["student_turns"] == src["student_turns"]
            assert out["expect"] == src["expect"]
            assert "fake_model" not in out  # Gate 重放不消费 fake_model 面


def test_gate_probe_spot_check_with_merged_verifier():
    """抽验探针可由 A 段 verify_completion(建议规格)复算:正/负/张力各一。"""
    payload = _load()
    by_id = {c["id"]: c for c in payload["cases"]}
    # 正向可构造:4402 equation_form
    case = by_id["socraticmath_train_4402"]
    spec = case["gate_a_probe"]["spec"]
    a_spec = AnswerSpec(answer_type=spec["answer_type"],
                        ground_truth=spec["ground_truth"])
    turn = case["replay_input"]["student_turns"][3]
    assert verify_completion(a_spec, turn, 3) is not None, "4402 探针不可复算"
    # 负向零构造:5106(数值 1)全轮 None
    case = by_id["socraticmath_train_5106"]
    spec = case["gate_a_probe"]["spec"]
    a_spec = AnswerSpec(answer_type=spec["answer_type"],
                        ground_truth=spec["ground_truth"])
    for i, turn in enumerate(case["replay_input"]["student_turns"]):
        assert verify_completion(a_spec, turn, i) is None, \
            f"5106 负向案第 {i} 轮出现可构造 evidence"
    # 张力案:2322(结果是52,非白名单模板)全轮 None
    case = by_id["socraticmath_train_2322"]
    assert not case["gate_a_probe"]["evidence_turns"]
    assert any("tension" in f for f in case["expected"]["flags"])


def test_dry_run_linear_replay_verbatim():
    """dry-run 抽 1 条(confirmation 嵌入件):线性照录逐字一致。"""
    payload = _load()
    scenario = next(c["replay_input"] for c in payload["cases"]
                    if c["id"] == "socraticmath_train_930")
    gateway = FakeGateway(tutor_payloads=[
        {"acceptable": True, "transcription": "", "steps": [],
         "reply": "我们来看这道题。操场上跑步、跳绳、打羽毛球的各有多少人呢?"},
        {"reason": "引导", "reply": "很好。那一共有多少人该怎么算呢?",
         "ready_to_confirm": False, "cited_numbers": []},
        {"reason": "确认", "reply": "完全正确,你算出了操场上一共有49人。"
                                     "你自己完整说一遍结论吧。",
         "ready_to_confirm": True, "cited_numbers": []}])
    transcript = KernelSubject(gateway).run_case(to_kernel_case(scenario))
    assert [t["student"] for t in transcript["turns"][1:]] == \
        scenario["student_turns"]
    assert len(gateway.requests) == 1 + len(scenario["student_turns"])


def test_compiler_script_is_reproducible():
    """编译脚本在当前源上重放结果与入库件逐字一致(编译可复算)。"""
    script = (Path(__file__).resolve().parents[2]
              / "scripts" / "gate_regression_corpus_compile.py")
    result = subprocess.run([sys.executable, str(script)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert _load() == json.loads(CORPUS.read_text(encoding="utf-8"))
