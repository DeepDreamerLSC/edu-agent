#!/usr/bin/env python3
"""Trusted Completion Gate 32 案 regression corpus 编译器(C 段预备件,#414 §六)。

输入(全部仓内 tracked 语料,零模型调用,只读):
  - edu_agent/evals/datasets/external_slices/socraticmath_confirmation_v1.json(24 案,#413)
  - edu_agent/evals/datasets/external_slices/socraticmath_executable_v1.json(ablation 7 案,#398)
  - edu_agent/evals/datasets/small_lecturer_regression_shortboard_v1.json(十字绣 1 案,#333 复现件)
输出:edu_agent/evals/datasets/small_lecturer_completion_gate_regression_32_v1.json

组成(设计 v3.1 §六.1 的定义,以设计件为准):confirmation 全 24 案(负向三案 2791/5106/3490
即其 6 负向成员,不重复计)+ ablation 五臂 8 案(十字绣/2591/675/val_13 closure 4 +
3565/4402/3666/866 ER 4)= 32 案。PM 提案曾列 700m 回归案——incident-700m-replay 属
r3 26 案而非 ablation 八案,不在 §六 定义内,差异记入产物头部 pending_review。

每案带:输入轨迹(逐字嵌入源 scenario)、期望行为断言(哪轮该/不该 completed、
该/不该重问)、来源指纹(源文件 sha256 + scenario_id + 曝光史)。
gate_a_probe 为建议性探针(ADVISORY):以 A 段(#415)已合的 verify_completion 在
「建议 AnswerSpec」下逐轮计算 evidence 可构造性——AnswerSpec 组装本属 B/C 段组装方
契约,本探针只预登记确定性行为供审查,不构成规格裁定(pending_review)。

硬不变量(违者断言失败,不造数据):
  G1 计数互洽:confirmation 24 + ablation 8 = 32,id 唯一;
  G2 负向三案 2791/5106/3490 在册且期望 needs_review;5106 带 summary 代说消失旗;
  G3 正向四锚(2322/2960/3695/3138,§六.2)在册带 anchor 旗;
  G4 ablation 八案与五臂工件清单一致(闭式清单互证);
  G5 嵌入 scenario 与源文件逐字节一致(重放输入冻结);
  G6 探针可复算:probe 输出由本脚本在当前源上确定性重生产;
  G7 源文件 sha256 指纹入册(证据链)。
"""

from __future__ import annotations

import functools
import hashlib
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONFIRMATION = (REPO / "edu_agent/evals/datasets/external_slices/"
                "socraticmath_confirmation_v1.json")
EXECUTABLE = (REPO / "edu_agent/evals/datasets/external_slices/"
              "socraticmath_executable_v1.json")
SHORTBOARD = (REPO / "edu_agent/evals/datasets/"
              "small_lecturer_regression_shortboard_v1.json")
OUT = (REPO / "edu_agent/evals/datasets/"
       "small_lecturer_completion_gate_regression_32_v1.json")

SLICE_POS = "confirmation_positive_student_final_answer"
SLICE_NEG = "confirmation_negative_student_stops_short"
SLICE_866 = "confirmation_type866_answer_complete_extensible"

# ablation 五臂 8 案闭式清单(五臂工件 /tmp/wt-step7-ab/runs/ablation-{arm}/results/,
# 2026-09-22;仓内可查佐证 = er-judge-v2 REPORT.md 数据源节 + ablation-report.md §2)。
ABLATION_CLOSURE = ("repro-close-loop-cross-stitch", "socraticmath_train_2591",
                    "socraticmath_train_675", "socraticmath_val_13")
ABLATION_ER = ("socraticmath_train_3565", "socraticmath_train_4402",
               "socraticmath_train_3666", "socraticmath_train_866")

# 五臂终态冻结(ablation-report.md §2 对照表;工件树临时,正本冻结于本 corpus)
FIVE_ARM = {
    "repro-close-loop-cross-stitch": {"baseline": "needs_review", "a_only": "completed",
                                      "b_old": "needs_review", "b_new": "completed",
                                      "ab_old": "completed"},
    "socraticmath_train_2591": {"baseline": "needs_review", "a_only": "completed",
                                "b_old": "needs_review", "b_new": "completed",
                                "ab_old": "completed"},
    "socraticmath_train_675": {"baseline": "needs_review", "a_only": "completed",
                               "b_old": "needs_review", "b_new": "completed",
                               "ab_old": "completed"},
    "socraticmath_val_13": {"baseline": "needs_review", "a_only": "needs_review",
                            "b_old": "needs_review", "b_new": "needs_review",
                            "ab_old": "completed(假)"},
    "socraticmath_train_3565": {"baseline": "completed", "a_only": "completed",
                                "b_old": "completed", "b_new": "completed",
                                "ab_old": "completed"},
    "socraticmath_train_4402": {"baseline": "completed", "a_only": "completed",
                                "b_old": "completed", "b_new": "completed",
                                "ab_old": "completed"},
    "socraticmath_train_3666": {"baseline": "completed", "a_only": "completed",
                                "b_old": "completed", "b_new": "completed",
                                "ab_old": "completed"},
    "socraticmath_train_866": {"baseline": "completed", "a_only": "completed",
                               "b_old": "completed", "b_new": "completed",
                               "ab_old": "completed"},
}

NEGATIVE_THREE = ("socraticmath_train_2791", "socraticmath_train_5106",
                  "socraticmath_train_3490")
ANCHOR_FOUR = ("socraticmath_train_2322", "socraticmath_train_2960",
               "socraticmath_train_3695", "socraticmath_train_3138")


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── Gate A 段探针(ADVISORY:建议 AnswerSpec 下逐轮 evidence 可构造性)─────────
from edu_agent.agents.small_lecturer import (  # noqa: E402
    AnswerSpec,
    verify_completion,
)


def _clean_answer(answer: str) -> str:
    """确定性清洗:剥「（答案不唯一）」标注/尾点/选项前缀「B.」。"""
    cleaned = re.sub(r"[，,]?\s*[（(]答案不唯一[）)]\.?$", "", (answer or "").strip())
    return re.sub(r"^[A-D][.、．]\s*", "", cleaned).rstrip(".。").strip()


def _face_of(question_text: str, cleaned: str) -> tuple[str, str]:
    """窄面判定:(answer_type, note);note 非空=§三红线条目。"""
    note = ""
    digit_first = re.fullmatch(r"(\d+(?:\.\d+)?(?:/\d+)?)(.*)", cleaned)
    if re.search(r"或|还是", cleaned):
        face, note = "composite", "多候选答案:§三红线,六窄面整体不判定"
    elif (len({m for m in re.findall(r"\d+(?:\.\d+)?", cleaned)}) >= 2
          and "=" not in cleaned):
        face, note = "composite", "≥2 数值 token(非算式):§三多槽红线,整体不判定"
    elif re.fullmatch(r"[A-D]", cleaned) and re.search(r"[ABCD][.、．]", question_text):
        face = "choice_letter"
    elif "=" in cleaned or "＝" in cleaned:
        face = ("equation_form" if re.search(r"[a-zA-Z]", cleaned)
                else "ratio_or_expression")
    elif "：" in cleaned or ":" in cleaned:
        face = "ratio_or_expression"
    elif digit_first and (re.fullmatch(r"[a-zA-Z]", digit_first.group(2))
                          or re.search(r"[+\-×÷*/]", digit_first.group(2))):
        face = "ratio_or_expression"
    elif digit_first or re.search(r"\d", cleaned):
        face = "numeric_with_unit"
    else:
        face = "short_text_exact"
    return face, note


def propose_spec(question_text: str, answer: str, sid: str = "") -> dict | None:
    """建议 AnswerSpec(组装契约属 B/C 段,此处仅预登记;pending_review)。

    清洗规则(确定性,逐条可审)见 _clean_answer;窄面判定见 _face_of:
    单字母+题面选项→choice_letter;含 =/比例号→equation/ratio(含变量字母为
    equation);「或」多候选或 ≥2 数值 token→composite(§三红线,调度即 None);
    纯数值→numeric_with_unit;其余→short_text_exact。aliases 仅来自
    EXPLICIT_ALIASES 逐案人批例外(见其注记:禁推广,回指绑定本题)。
    """
    cleaned = _clean_answer(answer)
    if not cleaned:
        return None
    face, note = _face_of(question_text, cleaned)
    spec: dict = {"answer_type": face, "ground_truth": cleaned}
    if note:
        spec["note"] = note
    aliases = EXPLICIT_ALIASES.get(sid, ())
    if aliases:
        spec["aliases"] = list(aliases)
        spec["aliases_note"] = ALIASES_NOTE
    if face == "choice_letter":
        spec["letter_choices"] = sorted(
            set(re.findall(r"([ABCD])[.、．]", question_text)))
    return spec


def _probe_turns(question_text: str, answer: str, turns: list[str],
                 sid: str = "") -> dict:
    spec = propose_spec(question_text, answer, sid)
    if spec is None:
        return {"spec": None, "evidence_turns": [],
                "note": "ADVISORY:无答案/空答案,不可组装 spec"}
    probe = dict(spec)
    evidence: list[int] = []
    if spec["answer_type"] == "composite":
        probe["probe_result"] = "调度即 None(§三红线)"
        return {"spec": probe, "evidence_turns": [],
                "note": "ADVISORY:" + spec["note"]
                        + ";spec 组装契约属 B/C 段(pending_review)"}
    kw: dict = {}
    if "letter_choices" in spec:
        kw["letter_choices"] = tuple(spec["letter_choices"])
    if spec.get("aliases"):
        kw["aliases"] = tuple(spec["aliases"])
    a_spec = AnswerSpec(answer_type=spec["answer_type"],
                        ground_truth=spec["ground_truth"], **kw)
    for idx, text in enumerate(turns):
        if verify_completion(a_spec, text, idx) is not None:
            evidence.append(idx)
    return {"spec": probe, "evidence_turns": evidence,
            "note": "ADVISORY:建议规格下 A 段 verify_completion 逐轮探针;"
                    "spec 组装契约属 B/C 段(pending_review)"}


def probe_scenario(question_text: str, answer: str, scenario: dict) -> dict:
    """线性案逐轮探;分支案逐 branch 探(重放走径由 tutor 文本路由,条件性记录)。"""
    sid = str(scenario.get("id") or "")
    if "student_turns" in scenario:
        return _probe_turns(question_text, answer, scenario["student_turns"], sid)
    branches = {}
    any_evidence = False
    for step in scenario.get("steps") or []:
        for branch in step.get("branches") or []:
            result = _probe_turns(question_text, answer,
                                  [branch["student_response"]], sid)
            branches[f"{step['id']}/{branch['id']}"] = bool(result["evidence_turns"])
            any_evidence = any_evidence or bool(result["evidence_turns"])
    spec = propose_spec(question_text, answer, sid) or {}
    return {"spec": spec, "evidence_branches": branches,
            "any_evidence": any_evidence,
            "note": "分支案:evidence 条件于实际走径(哪条 branch 被路由);"
                    "ADVISORY,spec 组装契约属 B/C 段(pending_review)"}


# ── 期望行为断言(设计 §四/§五/§六 推导;来源事实入 prior_facts)──────────────


def expected_for(sid: str, slice_name: str, scenario: dict, group: str) -> dict:
    flags: list[str] = []
    if group == "confirmation_24":
        hit = scenario["compile"]["selection"]["hit_turn_index"]
        if slice_name in (SLICE_POS, SLICE_866):
            pos = scenario["compile"]["student_turn_dialogue_indexes"].index(hit)
            exp = {
                "gate_evidence": {"student_turn_index": pos, "dialogue_index": hit},
                "final_state": "completed",
                "no_reask_after_evidence": True,
                "design_refs": ["§六.1 正向 completed 不劣化", "§五 verified 后不再就答案槽询问"],
            }
            if sid in ANCHOR_FOUR:
                exp["anchor"] = True
                exp["design_refs"].append("§六.2 Gate 正确放行锚")
        else:
            exp = {
                "gate_evidence": "none(全程无 CompletionEvidence)",
                "final_state": "needs_review",
                "no_reask_after_evidence": False,
                "design_refs": ["§六.1 负向 completed 必须消失", "§四 fail-closed"],
            }
            if sid == "socraticmath_train_5106":
                exp["summary_no_answer_speak"] = True
                exp["design_refs"].append("§六.1 5106 summary 代说必须消失")
        if slice_name == SLICE_866:
            flags.append("type866_延伸空间:verified 后可作非交互延伸,不得确认性重问")
        return exp | {"flags": flags}

    # ablation 8 案:五臂事实 + 设计方向
    if sid in ABLATION_CLOSURE and sid != "socraticmath_val_13":
        return {
            "gate_evidence": "student_final_answer_turn(见 gate_a_probe 逐轮结果)",
            "final_state": "completed",
            "no_reask_after_evidence": True,
            "design_refs": ["§六.1 正向 completed 不劣化(五臂 B-new/AB-old completed 实证)"],
            "flags": flags,
        }
    if sid == "socraticmath_val_13":
        return {
            "gate_evidence": "none(全程无 CompletionEvidence)",
            "final_state": "needs_review",
            "no_reask_after_evidence": False,
            "design_refs": ["§六.1 负向 completed 必须消失",
                            "五臂 AB-old completed(假) 实证 = val_13 型防线"],
            "flags": ["false_closure_must_disappear"],
        }
    return {
        "gate_evidence": "student_final_answer_turn(见 gate_a_probe 逐轮结果)",
        "final_state": "completed",
        "no_reask_after_evidence": True,
        "design_refs": ["§六.1 正向 completed 不劣化", "§五 ER 面:verified 后不得把已给答案当未知重问"],
        "flags": flags,
    }


def _probe_has_evidence(probe: dict) -> bool:
    if "evidence_turns" in probe:
        return bool(probe["evidence_turns"])
    return bool(probe.get("any_evidence"))


def _add_tension_flags(case: dict) -> None:
    """期望与 A 段探针的张力预登记:completed 期望但建议规格下无可构造轮,
    或 needs_review 期望但探针出现可构造轮——均留人审(C 段判读须区分
    结构性保守拒判(设计内)与行为回归(设计外))。"""
    expected_state = case["expected"]["final_state"]
    has_ev = _probe_has_evidence(case["gate_a_probe"])
    if expected_state == "completed" and not has_ev:
        case["expected"]["flags"].append(
            "probe_no_evidence_tension(pending_review):A 段白名单/单位面/复合红线"
            "下建议规格无 evidence 轮——§六.1 不劣化期望与 §三 precision-first "
            "保守拒判的结构张力,C 段判读须区分结构拒判与行为回归")
    if expected_state == "needs_review" and has_ev:
        case["expected"]["flags"].append(
            "probe_unexpected_evidence(pending_review):负向期望但探针出现可构造轮")


def build() -> dict:
    confirmation = json.loads(CONFIRMATION.read_text(encoding="utf-8"))
    executable = json.loads(EXECUTABLE.read_text(encoding="utf-8"))
    shortboard = json.loads(SHORTBOARD.read_text(encoding="utf-8"))
    conf_scen = {s["id"]: s for s in confirmation["scenarios"]}
    exec_scen = {s["id"]: s for s in executable["scenarios"]}
    board_scen = {s["id"]: s for s in shortboard["scenarios"]}

    cases = []

    # ── confirmation 24(#413)──
    for sid, scenario in conf_scen.items():
        slice_name = scenario["compile"]["slice"]
        answer = scenario["compile"]["answer"]
        cases.append({
            "id": sid,
            "group": "confirmation_24",
            "slice": slice_name,
            "source": {
                "file": "edu_agent/evals/datasets/external_slices/"
                        "socraticmath_confirmation_v1.json",
                "scenario_id": sid,
                "origin_lists": ["#413 confirmation 24 案(含负向三案)",
                                 "confirm 双臂批次用案(confirm-baseline/confirm-candidate)"],
            },
            "replay_input": scenario,
            "prior_facts": {
                "slice_counts": confirmation["counts"],
                "selection_basis": scenario["compile"]["selection"]["basis"],
            },
            "expected": expected_for(sid, slice_name, scenario, "confirmation_24"),
            "gate_a_probe": probe_scenario(scenario["question"], answer, scenario),
        })

    # ── ablation 8(五臂)──
    for sid in (*ABLATION_CLOSURE, *ABLATION_ER):
        if sid == "repro-close-loop-cross-stitch":
            scenario = board_scen[sid]
            replay = {
                "schema_version": "small_lecturer_regression_shortboard/v1(摘录)",
                "id": sid, "title": scenario["title"],
                "question": scenario["question"],
                "answer_status": scenario["answer_status"],
                "grade": scenario["grade"],
                "student_turns": scenario["student_turns"],
                "expect": scenario["expect"],
                "note": "fake_model 面不进 Gate 重放(跑面=真实 tutor + student_turns,"
                        "同五臂口径);完整正本见 shortboard 文件(指纹见头部 source_files)",
            }
            question_text = scenario["question"]["text"]
            answer = scenario["question"]["answer"]
            basis = ("产线闭环死环复现案(#333,conv_2c8551ff8b52):学生终述轮"
                     "「妈妈第二周绣了6dm」;五臂 B-new/AB-old completed(优质 closure)")
        else:
            scenario = exec_scen[sid]
            replay = scenario
            record = _record_of(sid)
            question_text = record["problem"]["text"]
            answer = record["problem"].get("answer") or ""
            runtime = _runtime_answer(sid)
            if runtime and runtime != answer:
                answer = runtime
            basis = {
                "socraticmath_train_2591": "closure:学生 t3 声明句「平行四边形的特性是它易变形。」",
                "socraticmath_train_675": "closure:学生 fallback 支 t3「答案是A。」(五臂实走 fallback)",
                "socraticmath_val_13": "closure(假收束防线):学生全程无选项断言,五臂 AB-old completed(假)",
                "socraticmath_train_3565": "ER:学生第 3 轮「所以能分割成100个…」后被追问(form1)",
                "socraticmath_train_4402": "ER:学生第 4 轮「应该是x-21=35。」后被要求变形(form1,最强样本)",
                "socraticmath_train_3666": "ER:学生仅疑问形态「是不是…4：8=15：30？」「应该是30：15=8：4也可以吧？」(form1)",
                "socraticmath_train_866": "ER:学生第 5 轮「所以我觉得比例可以是12：4=6：2。」后被延伸追问(form1)",
            }[sid]
        cases.append({
            "id": sid,
            "group": "ablation_8",
            "slice": ("repro_close_loop" if sid == "repro-close-loop-cross-stitch"
                      else scenario["compile"]["form"]),
            "source": {
                "file": ("edu_agent/evals/datasets/small_lecturer_regression_shortboard_v1.json"
                         if sid == "repro-close-loop-cross-stitch" else
                         "edu_agent/evals/datasets/external_slices/"
                         "socraticmath_executable_v1.json"),
                "scenario_id": sid,
                "origin_lists": ["ablation 五臂 8 案(2026-09-22)",
                                 "r3 双臂 26 案(#398 编译)",
                                 "ER judge v2 DEV10 人审 10 案(7 案交集)"],
            },
            "replay_input": replay,
            "prior_facts": {
                "five_arm_final_states": FIVE_ARM[sid],
                "basis": basis,
                "provenance": "五臂工件 /tmp/wt-step7-ab/runs/ablation-*/results/(临时树);"
                              "仓内佐证=er-judge-v2 REPORT.md;终态冻结于本 corpus",
            },
            "expected": expected_for(sid, "", scenario, "ablation_8"),
            "gate_a_probe": probe_scenario(question_text, answer, replay),
        })

    for case in cases:
        _add_tension_flags(case)

    payload = {
        "schema": "edu_agent_gate_regression_corpus/v1",
        "corpus_version": "completion_gate_regression_32_v1",
        "status_note": (
            "Trusted Completion Gate C 段行为回归 corpus(预注册级资产,#414 设计 v3.1 "
            "§六.1 的 32 案 = 终裁 regression corpus):C 段(generation 只读消费)合入后"
            "全量重放,验证 Gate 全链行为不回归——负向:无终答不得 completed;"
            "正向:verified 后不确认性重问。与 Phase A boundary gold(六窄面输入语法边界,"
            "A 段单测合成案)分立,不得混用。"
        ),
        "design": {
            "doc": "docs/evals/trusted-completion-gate-design-v3.md",
            "section": "§六 验收设计(fresh confirmation 前置)",
            "composition": "confirmation 全 24 案(负向三案 2791/5106/3490 为其负向成员,"
                           "不重复计)+ ablation 五臂 8 案 = 32 案",
        },
        "source_files": {
            "edu_agent/evals/datasets/external_slices/socraticmath_confirmation_v1.json":
                sha256_of(CONFIRMATION),
            "edu_agent/evals/datasets/external_slices/socraticmath_executable_v1.json":
                sha256_of(EXECUTABLE),
            "edu_agent/evals/datasets/small_lecturer_regression_shortboard_v1.json":
                sha256_of(SHORTBOARD),
        },
        "anti_contamination": {
            "note": "本 corpus 是行为回归面(重放已曝光案),不需要未曝光;"
                    "曝光史逐案记录于 source.origin_lists。",
            "fresh_holdout": "fresh confirmation holdout(终裁执行链⑦燃料)分立于 "
                             "socraticmath_confirmation_holdout_v1.json,与本 corpus 零重叠。",
        },
        "replay_notes": (
            "重放基线由 C 段跑面自建(同 corpus 双臂:main 现行 vs main+Gate),"
            "本 corpus 不内嵌 confirm 批次输出作基线(预注册纪律);五臂终态仅为"
            "历史事实记录。gate_a_probe 为 ADVISORY 探针:A 段 verify_completion 在"
            "建议 AnswerSpec 下的确定性逐轮结果,spec 组装契约属 B/C 段。"
        ),
        "pending_review": [
            "PM 提案曾列 700m 回归案(incident-700m-replay):属 r3 26 案而非 ablation "
            "八案,不在设计 §六.1 的 32 案定义内,未纳入;如需扩为 33 案须人裁并修订设计件",
            "gate_a_probe 的 AnswerSpec 组装(清洗规则/answer_type 映射)属 B/C 段组装方"
            "契约,本件仅预登记建议规格",
            "2591 spec 的 aliases=[\"它易变形\"] 是题库显式 alias 的人批逐案例外"
            "(2026-09-24 用户双重批准,语义裁决 gold-adjudication-c25c46c51-2591-"
            "20260924.md §B):仅 alias/等价形态,不得推广为通用规则,回指绑定本题;"
            "清单见编译脚本 EXPLICIT_ALIASES(禁推广注记)",
            "探针与期望的张力案(结构保守拒判 vs §六.1 不劣化)逐案见 gate_a_probe.note "
            "与 cases[].expected.flags:C 段重放判读时须区分「结构性拒判(设计内)」与"
            "「行为回归(设计外)」——留人审",
        ],
        "counts": {
            "confirmation_24": sum(1 for c in cases if c["group"] == "confirmation_24"),
            "ablation_8": sum(1 for c in cases if c["group"] == "ablation_8"),
            "negative_must_disappear": 7,
            "anchor_four": 4,
            "total": len(cases),
        },
        "cases": cases,
    }
    return payload


@functools.cache
def _all_records() -> dict[str, dict]:
    normalized = (REPO / "edu_agent/evals/datasets/external_normalized/"
                  "socraticmath.jsonl")
    records: dict[str, dict] = {}
    for line in normalized.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            records[rec["id"]] = rec
    return records


def _record_of(sid: str) -> dict:
    return _all_records()[sid]


# r3 运行时 answer 冻结记录(675/val_13 记录层 problem.answer 为空,运行时
# cases.jsonl 为判分补值;工件树 /tmp/wt-step7-ab 2026-09-22 冻结,此处内置防树失)
RUNTIME_ANSWERS = {
    "socraticmath_train_675": "A",
    "socraticmath_val_13": "B",
}


def _runtime_answer(sid: str) -> str | None:
    return RUNTIME_ANSWERS.get(sid)


# 题库显式 alias 声明(逐案,B/C 段 spec 组装面的人批显式例外;2026-09-24 用户
# 双重批准入库)。题库声明面编译器 compile_answer_spec 的「aliases=[] 显式空,
# 不扩病例短语表是终裁红线」管的是 external_normalized 题库面;本表是 regression
# corpus 逐案例外,每条须带语义裁决依据,**不得推广为通用规则**:
#   2591「它易变形」=句内回指代词「它」(先行词=平行四边形)+ground_truth
#   「易变形」的等价形态:题面问特性谓词、参考答案唯一「易变形」、学生终句为
#   同一命题的回指表达且源导师终轮确认(语义裁决 gold-adjudication-c25c46c51-
#   2591-20260924.md §B,用户 2026-09-24 双重批准)。
ALIASES_NOTE = ("仅 alias/等价形态,不得推广为通用规则;回指绑定本题"
                "(用户 2026-09-24 禁推广注记)")
EXPLICIT_ALIASES = {
    "socraticmath_train_2591": ("它易变形",),
}


def verify_invariants(payload: dict, confirmation: dict, executable: dict,
                      shortboard: dict) -> None:
    cases = payload["cases"]
    ids = [c["id"] for c in cases]
    # G1
    assert len(cases) == 32 and len(set(ids)) == 32, "G1:计数/唯一性违例"
    assert payload["counts"]["confirmation_24"] == 24
    assert payload["counts"]["ablation_8"] == 8
    # G2 负向三案
    by_id = {c["id"]: c for c in cases}
    for sid in NEGATIVE_THREE:
        assert sid in by_id, f"G2:负向案 {sid} 缺席"
        assert by_id[sid]["expected"]["final_state"] == "needs_review"
    assert by_id["socraticmath_train_5106"]["expected"].get("summary_no_answer_speak") is True
    # G3 正向四锚
    for sid in ANCHOR_FOUR:
        assert sid in by_id and by_id[sid]["expected"].get("anchor") is True, f"G3:{sid}"
    # G4 ablation 闭式清单
    expected_abl = set(ABLATION_CLOSURE) | set(ABLATION_ER)
    got_abl = {c["id"] for c in cases if c["group"] == "ablation_8"}
    assert got_abl == expected_abl, f"G4:ablation 清单不符:{got_abl ^ expected_abl}"
    # G5 嵌入逐字一致
    for c in cases:
        sid = c["id"]
        if c["group"] == "confirmation_24":
            src = next(s for s in confirmation["scenarios"] if s["id"] == sid)
        elif sid == "repro-close-loop-cross-stitch":
            continue  # 摘录件(摘录范围有 note),指纹核对在 G7
        else:
            src = next(s for s in executable["scenarios"] if s["id"] == sid)
        assert c["replay_input"] == src, f"G5:{sid} 嵌入与源不一致"
        assert c["source"]["scenario_id"] == sid
    # G7 源文件存在且指纹与产物一致(逐字节)
    for path, digest in payload["source_files"].items():
        assert sha256_of(REPO / path) == digest, f"G7:{path} 指纹断裂"


def main() -> int:
    confirmation = json.loads(CONFIRMATION.read_text(encoding="utf-8"))
    executable = json.loads(EXECUTABLE.read_text(encoding="utf-8"))
    shortboard = json.loads(SHORTBOARD.read_text(encoding="utf-8"))
    payload = build()
    verify_invariants(payload, confirmation, executable, shortboard)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    pos = sum(1 for c in payload["cases"]
              if c["expected"]["final_state"] == "completed")
    neg = sum(1 for c in payload["cases"]
              if c["expected"]["final_state"] == "needs_review")
    print(f"corpus=32 (confirmation_24=24, ablation_8=8; "
          f"expected completed={pos}, needs_review={neg})")
    print(f"written: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
