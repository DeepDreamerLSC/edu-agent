#!/usr/bin/env python3
"""elicit 触发对 v3 · 第 2 步两臂配对(#293 预注册 v3;PM 放行用户裁 a:接受 4 对)。

4 触发案(筛段实证)× 两臂(X=nets-main-02 epoch-2 全角正本 / Y=kernel 默认),
每案转录+guard_events 落盘,盲化 mapping(臂→A/B 随机,只入仓)。
预算口径:本单全程 ≤240(筛段已耗 35,本段软顶 205,预期 ~56);零 API 零远程。
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # 仓库根
DATASET = ROOT / "edu_agent/evals/datasets/small_lecturer_image_teaching_v2_enriched12.json"
OUT = Path(__file__).resolve().parent / "out" / "pairs"
FACTS = Path(__file__).resolve().parent / "out" / "facts"

BUDGET_TOTAL = 240  # PM 硬顶(v3 全程:筛段+配对)
SPENT_SCREEN = 35   # 筛段实计(独立进程,台账口径并入)
SOFT_CAP = BUDGET_TOTAL - SPENT_SCREEN  # 本段软顶 205
PER_EVAL_RESERVE = 9

# 臂 X = gepa-nets-main-02/checkpoint.json best 逐字全角正本(epoch-2)
ARM_X = ("请复讲：先说核心思路，再写出第一步的具体算式或操作，最后给出明确结论。"
         "请用完整句子描述步骤与结果，以便确认掌握。")
# 臂 Y = kernel _ELICIT_TEMPLATE 原文(main 08f2fdcd L90-92)
ARM_Y = ("我们从头把思路串一遍——"
         "先说说你第一步算了什么、为什么这样算。")

CASE_IDS = [
    "image_v2_understanding_04",   # Tier1(试跑案0 复现)
    "image_v2_understanding_02",   # Tier1(试跑案1 复现)
    "image_v2_answerhit_01",       # 筛段意外触发(路径 B)
    "image_v2_answerhit_02",       # 筛段意外触发(路径 B)
]


def main() -> None:
    from edu_agent.evals.corpus_round import transcript_messages
    from edu_agent.evals.gepa import ElicitSubject
    from edu_agent.evals.judge import judge_transcript
    from edu_agent.gateway import Gateway
    from edu_agent.gateway.registry import load_registry

    OUT.mkdir(parents=True, exist_ok=True)
    payload = json.loads(DATASET.read_text(encoding="utf-8"))
    scenarios = payload["scenarios"] if isinstance(payload, dict) else payload
    cases = {c["id"]: c for c in scenarios}

    gateway = Gateway(load_registry(ROOT / "configs/models.yaml"),
                      facts_dir=str(FACTS))
    w0 = gateway.writer.count

    rng = random.Random(20260918)  # v3 配对段独立 seed(预注册 v3 盲化口径)
    blind = {"X": "A", "Y": "B"}
    blind["X"], blind["Y"] = rng.sample(("A", "B"), 2)
    (OUT / "mapping.json").write_text(
        json.dumps({"arm_X": blind["X"], "arm_Y": blind["Y"],
                    "note": "臂→盲标随机映射(seed=20260918);"
                            "X=nets-main-02 epoch-2 正本,Y=kernel 默认;"
                            "真实对应只存本件,不进教师材料"},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    print("[飞行前回显] 两臂模板原文(逐字):")
    print(f"  X(nets-main-02 epoch-2): {ARM_X!r}")
    print(f"  Y(kernel 默认):         {ARM_Y!r}")
    print(f"  盲化: X→{blind['X']}, Y→{blind['Y']}")

    records = []
    for cid in CASE_IDS:
        case = cases[cid]
        for arm, tpl in (("X", ARM_X), ("Y", ARM_Y)):
            used = gateway.writer.count - w0
            if used + PER_EVAL_RESERVE > SOFT_CAP:
                print(f"[ABORT] 本段预算将越顶(已用 {used}+储备 {PER_EVAL_RESERVE}"
                      f">{SOFT_CAP}),停跑")
                sys.exit(2)
            subject = ElicitSubject(tpl, gateway)
            transcript = subject.run_case(case)
            guard_events = transcript.get("guard_events") or []
            judge_out = judge_transcript(
                gateway,
                {"question": case.get("question", ""),
                 "grade": case.get("grade", ""),
                 "reference_answer": case.get("reference_answer", ""),
                 "messages": transcript_messages(transcript)},
                role="judge")
            elicit_hits = [e for e in guard_events if e.get("branch") == "elicit"]
            rec = {"case_id": cid, "arm": arm, "arm_blind": blind[arm],
                   "template": tpl,
                   "transcript": transcript, "guard_events": guard_events,
                   "judge": judge_out,
                   "elicit_hits": len(elicit_hits),
                   "calls_used_this_run": gateway.writer.count - w0}
            d = OUT / cid
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{blind[arm]}.json").write_text(
                json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[{cid}/{blind[arm]}(臂{arm})] 轮数={len(transcript.get('turns') or [])} "
                  f"elicit={len(elicit_hits)} judge={judge_out.get('total')}/"
                  f"{judge_out.get('verdict')} 本段calls={rec['calls_used_this_run']}")
            records.append(rec)

    seg = gateway.writer.count - w0
    print(f"\n配对段完成:4 案×2 臂,本段 calls={seg},全程(含筛段 {SPENT_SCREEN})"
          f"={seg + SPENT_SCREEN}(硬顶 {BUDGET_TOTAL})")
    (OUT / "pairs-summary.json").write_text(
        json.dumps({"segment_calls": seg, "screen_spent": SPENT_SCREEN,
                    "total_calls": seg + SPENT_SCREEN, "budget": BUDGET_TOTAL,
                    "per_eval": [{"case_id": r["case_id"], "arm": r["arm"],
                                  "arm_blind": r["arm_blind"],
                                  "elicit_hits": r["elicit_hits"],
                                  "judge_total": r["judge"].get("total"),
                                  "judge_verdict": r["judge"].get("verdict")}
                                 for r in records]}, ensure_ascii=False, indent=2),
        encoding="utf-8")


if __name__ == "__main__":
    main()
