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
    # 预登记张力面非空(§三 precision-first 白名单 vs §六.1 不劣化)——冻结在案。
    # #416 claim 边界校准(2026-09-24 人裁)后张力案 13→5(8 案经 B-1/B-5/
    # C-3b/维度表恢复 evidence 轮);2591 alias「它易变形」入库(2026-09-24 用户
    # 双重批准,题库显式声明面逐案例外,verifier 零改动)后 evidence 轮恢复,
    # 张力案 5→4(2591 出列)——再消失即红(须随重放登记面同步重新登记,防
    # 静默重释),新增即红(新保守拒判面,须呈报)。
    assert tension == 4, f"张力案登记面变化(alias 入库后=4,实测 {tension})"
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
    """抽验探针可由 A 段 verify_completion(建议规格)复算:正/负/校准恢复案各一。"""
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
    # 2322(#416 校准恢复案):t0「吧」问句整条拒,t2「结果是52」可构造
    # (B-1 结果是)——探针登记 [2] 可由合并 verifier 复算,张力旗已随
    # corpus 机械再生成移除
    case = by_id["socraticmath_train_2322"]
    spec = case["gate_a_probe"]["spec"]
    a_spec = AnswerSpec(answer_type=spec["answer_type"],
                        ground_truth=spec["ground_truth"])
    turns = case["replay_input"]["student_turns"]
    assert case["gate_a_probe"]["evidence_turns"] == [2]
    assert not any("tension" in f for f in case["expected"]["flags"])
    assert verify_completion(a_spec, turns[0], 0) is None   # 「吧」问句正确保守
    assert verify_completion(a_spec, turns[2], 2) is not None


def test_2591_explicit_alias_declaration_and_adversarial_rejection():
    """2591 题库显式 alias「它易变形」(2026-09-24 用户双重批准,语义裁决
    gold-adjudication-c25c46c51-2591-20260924.md §B;verifier 零改动):

    - 声明面:spec.aliases 逐案登记 + 禁推广注记(仅 alias/等价形态,回指
      绑定本题)——人批显式例外,非通用规则;
    - 行为面:终句「平行四边形的特性是它易变形。」alias 命中,溯源 gt_ref
      仍为 ground_truth「易变形」;其余学生轮(背景/疑问式候选/错误答案
      「稳定性」)与对抗三形态(否定/猜测/后缀「容易变形」)全拒——裁决
      实测口径:alias 只恢复终句 evidence,不打开新缝。"""
    payload = _load()
    case = next(c for c in payload["cases"] if c["id"] == "socraticmath_train_2591")
    spec = case["gate_a_probe"]["spec"]
    assert spec["aliases"] == ["它易变形"]
    assert "不得推广为通用规则" in spec["aliases_note"]
    assert "回指绑定本题" in spec["aliases_note"]
    a_spec = AnswerSpec(answer_type=spec["answer_type"],
                        ground_truth=spec["ground_truth"],
                        aliases=tuple(spec["aliases"]))
    turns = case["replay_input"]["student_turns"]
    # 仅终句命中(alias 尾匹配+左边界「是」),其余轮全拒
    for i, turn in enumerate(turns):
        evidence = verify_completion(a_spec, turn, i)
        if i == len(turns) - 1:
            assert evidence is not None, "2591 终句 alias 未命中(evidence 面未恢复)"
            assert evidence.provenance.ground_truth_ref == "易变形"
            assert evidence.provenance.matched_span == "它易变形"
        else:
            assert evidence is None, f"2591 第 {i} 轮因 alias 误收"
    # 对抗三形态(裁决实测口径):否定窗/猜测窗/左边界各自拦截
    adversarial = ("平行四边形的特性不是它易变形。",   # 否定:命中前 2 字「不是」
                   "我猜是它易变形。",                 # 猜测:命中前「猜是」
                   "这种形状容易变形。")               # 后缀:「容」非左边界,裸 substring 不收
    for text in adversarial:
        assert verify_completion(a_spec, text, 9) is None, f"对抗形态误收:{text}"


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
