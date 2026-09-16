#!/usr/bin/env python3
"""#256 旋钮频次分析(零模型调用;派单 2026-09-17,摘要 sha256=ee6c92c56f561fa1)。

对已入仓转录/数据做静态分析:kernel 确定性模板调用点在本仓证据面上各自触发过几次。
匹配口径 = 审查者复现清单(review-probe-rerun,#256 评论 5697507803):信号判定一律
import kernel 既有信号函数,不自造正则;轮级触发以 guard_events 埋点为权威
(branch=elicit/support/reveal/answer_collect + guard=premature_confirm/泄漏族)。

证据面(四层,来源各自记 sha):
  S1 数据集层  edu_agent/evals/datasets/small_lecturer_image_teaching_v1.json(8 案)
  S2 转录层    edu_agent/evals/artifacts/149-ready-gate/*/results/*.json(真实运行转录)
  S3 配对层    gepa-spike/paired-experiment/round-00|01.json(task/256-paired-experiment
               @ a014257;无转录——P1-① 已裁,只有分数与失效的 hit 验证)
  S4 探针层    gepa-spike/structural-probe/round-00.json(probe/structural-variant
               @ 6c68289;逐案首问 + 全转录空转扫描 idle 判定)

用法: .venv/bin/python analyze.py [--paired DIR] [--probe DIR]
输出: matches.json(逐案逐轮原始命中)+ stdout 汇总(knob-frequency.md 的数据源)。
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]

from edu_agent.agents.small_lecturer.kernel import (  # noqa: E402
    FINISH_EVIDENCE_TEXT,
    NEEDS_REVIEW_TEXT,
    _student_signals_completion,
    _student_signals_stuck,
    _student_signals_understanding,
)

OLD_ZERO_CALL_PREFIX = "是你自己讲下来的"  # #302 前的零调用模板骨架(149 工件为旧文案)
NEW_ZERO_CALL_PREFIX = "你自己讲了做法"  # #302 起的零调用模板骨架
BOTTOM_OUT_PREFIX = "这一步我们直接看结果:"  # 无终答 bottom-out 文案前缀(#185)

SIGNALS = (("understanding", _student_signals_understanding),
           ("stuck", _student_signals_stuck),
           ("completion", _student_signals_completion))


def scan_dataset(path: Path) -> dict:
    """S1:elicit 数据集逐案逐轮信号扫描(审查者复现清单同款口径)。"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    scenarios = payload.get("scenarios") or payload.get("cases") or []
    cases = []
    for scenario in scenarios:
        turns = [t for t in (scenario.get("student_turns")
                             or scenario.get("student_messages") or []) if isinstance(t, str)]
        hits = {name: [i for i, t in enumerate(turns) if fn(t)]
                for name, fn in SIGNALS}
        cases.append({"case_id": scenario.get("id"), "turns": len(turns),
                      "answer_status": scenario.get("answer_status"), "signal_turns": hits})
    # 复现清单原式逐字复算(口径对照锚点)
    reviewer_expr = sum(any(_student_signals_understanding(t) for t in
                            (c.get("student_turns") or c.get("student_messages") or [])
                            if isinstance(t, str)) for c in scenarios)
    return {"source": str(path), "cases": cases, "n_cases": len(cases),
            "reviewer_reproduction_understanding_cases": reviewer_expr}


def _event_knob(event: dict) -> str | None:
    """guard_events 单条 → 旋钮名(埋点键为 kernel 一手定义,键序即优先序)。"""
    branch = str(event.get("branch") or "")
    if branch in ("elicit", "support", "reveal", "answer_collect"):
        return branch
    if str(event.get("guard") or "") == "premature_confirm":
        return "premature_confirm"
    if (str(event.get("guard") or "") or event.get("soften") or event.get("dropped")
            or event.get("mode") or branch == "value_disclosure"):
        return "leak_guard"
    return None


def _classify_finish(state: str, summary: str) -> str:
    """finish 路径归类(零调用模板两代文案/needs_review/其他=模型总结)。"""
    if state == "completed" and (OLD_ZERO_CALL_PREFIX in summary
                                 or NEW_ZERO_CALL_PREFIX in summary):
        return "completed_zero_call"
    return "needs_review" if state == "needs_review" else "other"


def scan_results(results_glob: str) -> dict:
    """S2:真实运行转录 → 埋点计数(branch/guard 双键全扫)+ finish 路径文本归类。"""
    knobs = {k: {"cases": set(), "turns": 0, "case_ids": []}
             for k in ("elicit", "support", "reveal", "answer_collect",
                       "premature_confirm", "leak_guard")}
    finish = {"completed_zero_call": {"cases": 0, "ids": []},
              "needs_review": {"cases": 0, "ids": []},
              "needs_review_text": Counter(), "other": {"cases": 0, "ids": []}}
    n_files = n_turns = 0
    arms = Counter()
    for path in sorted(REPO.glob(results_glob)):
        row = json.loads(path.read_text(encoding="utf-8"))
        transcript = row.get("transcript") or {}
        case_id = str(row.get("case_id") or path.stem)
        n_files += 1
        arms[path.relative_to(REPO).parts[4]] += 1
        for event in transcript.get("guard_events") or []:
            knob = _event_knob(event)
            if knob:
                knobs[knob]["turns"] += 1
                if case_id not in knobs[knob]["cases"]:
                    knobs[knob]["cases"].add(case_id)
                    knobs[knob]["case_ids"].append(case_id)
        n_turns += len(transcript.get("turns") or [])
        kind = _classify_finish(transcript.get("final_state"),
                                transcript.get("summary") or "")
        finish[kind]["cases"] += 1
        finish[kind]["ids"].append(case_id)
        if kind != "needs_review":
            continue
        for label, text in (("NEEDS_REVIEW_TEXT", NEEDS_REVIEW_TEXT),
                            ("FINISH_EVIDENCE_TEXT", FINISH_EVIDENCE_TEXT),
                            ("bottom_out", BOTTOM_OUT_PREFIX)):
            summary = transcript.get("summary") or ""
            if text in summary or summary.startswith(text):
                finish["needs_review_text"][label] += 1
                break
        else:
            finish["needs_review_text"]["other"] += 1
    for knob in knobs.values():
        knob["cases"] = len(knob["cases"])
    return {"results_glob": results_glob, "n_files": n_files, "n_turns": n_turns,
            "files_by_arm": dict(arms), "knobs": knobs, "finish": finish}


def scan_paired(directory: Path) -> dict:
    """S3:配对实验工件(无转录,P1-① 已裁)——只如实记录 hit 验证与 Δ 概览。"""
    if not directory.is_dir():
        return {"present": False}
    rounds = []
    for path in sorted(directory.glob("round-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        rounds.append({"file": path.name,
                       "template_hit_validation": data.get("template_hit_validation"),
                       "n_cases": len(data.get("paired_cases") or []),
                       "delta_zero_cases": sum(1 for c in data.get("paired_cases") or []
                                               if c.get("delta") == 0)})
    return {"present": True, "rounds": rounds}


def scan_probe(directory: Path) -> dict:
    """S4:结构探针工件(修复后)——逐案 idle 判定与首问模板检查。"""
    path = directory / "round-00.json"
    if not path.is_file():
        return {"present": False}
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("paired_cases") or []
    return {"present": True, "n_cases": len(cases),
            "idle_cases": sum(1 for c in cases if c.get("idle")),
            "template_in_first_question": sum(1 for c in cases
                                              if c.get("template_text_in_variant_first_question")),
            "first_questions_identical": sum(
                1 for c in cases
                if c.get("parent_first_question") == c.get("variant_first_question"))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--paired", type=Path, default=Path(), help="S3 配对工件目录")
    parser.add_argument("--probe", type=Path, default=Path(), help="S4 探针工件目录")
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "matches.json")
    args = parser.parse_args()

    result = {
        "zero_model_calls": True,
        "s1_dataset": scan_dataset(REPO / "edu_agent/evals/datasets"
                                   / "small_lecturer_image_teaching_v1.json"),
        "s2_results": scan_results(
        "edu_agent/evals/artifacts/149-ready-gate/**/results/*.json"),
        "s3_paired": scan_paired(args.paired),
        "s4_probe": scan_probe(args.probe),
    }
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    s1, s2 = result["s1_dataset"], result["s2_results"]
    print(f"S1 数据集层:{s1['n_cases']} 案;"
          f"复现清单原式(understanding 命中案数)={s1['reviewer_reproduction_understanding_cases']}")
    for name, _ in SIGNALS:
        n = sum(1 for c in s1["cases"] if c["signal_turns"][name])
        print(f"  {name}: 命中 {n}/{s1['n_cases']} 案")
    print(f"S2 转录层:{s2['n_files']} 件 / {s2['n_turns']} 轮")
    for knob, row in s2["knobs"].items():
        print(f"  {knob}: {row['cases']} 案 / {row['turns']} 轮")
    print(f"  finish: {json.dumps(s2['finish']['needs_review_text'], ensure_ascii=False)}"
          f" completed_zero_call={s2['finish']['completed_zero_call']['cases']}"
          f" needs_review={s2['finish']['needs_review']['cases']}"
          f" other={s2['finish']['other']['cases']}")
    print(f"S3 配对层:{json.dumps(result['s3_paired'], ensure_ascii=False)[:200]}")
    print(f"S4 探针层:{json.dumps(result['s4_probe'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
