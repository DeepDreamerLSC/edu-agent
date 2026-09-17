#!/usr/bin/env python3
"""elicit 触发对 v3 · 第 1 步单臂筛(#293 预注册 v3,PM 派单 task=elicit-pair-topup-v3)。

8 案(静态候选表全量)× 默认臂(kernel _ELICIT_TEMPLATE 原文),只看 guard_events:
验证 elicit 分支真实触发(静态预判 vs 运行时偏差仲裁)。每案落盘转录+埋点+判卷。
硬顶 240 本地 calls(全程,筛段软顶 80);零 API 零 editor 零远程。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # 仓库根
DATASET = ROOT / "edu_agent/evals/datasets/small_lecturer_image_teaching_v2_enriched12.json"
OUT = Path(__file__).resolve().parent / "out" / "screen"
MAX_CALLS = 240  # PM 硬顶(全程:筛+配对)
SCREEN_SOFT_CAP = 80  # 筛段软顶(8 案×~6 calls+裕量)
PER_CASE_RESERVE = 9  # 单案上界(tutor ~5 + judge 1 + 裕量)

# 默认臂 = kernel _ELICIT_TEMPLATE 原文(main 08f2fdcd L90-92,逐字)
ARM_DEFAULT = ("我们从头把思路串一遍——"
               "先说说你第一步算了什么、为什么这样算。")

# 静态候选表(预注册 v3,按 Tier 排序)
SCREEN_IDS = [
    "image_v2_understanding_04",   # Tier1 实证(试跑案0)
    "image_v2_understanding_02",   # Tier1 实证(试跑案1)
    "image_v2_understanding_01",   # Tier2 待仲裁(试跑无感矛盾)
    "image_v2_understanding_03",   # Tier2
    "image_v2_answercollect_01",   # Tier3 路径B前提
    "image_v2_answercollect_02",   # Tier3
    "image_v2_answerhit_01",       # Tier3
    "image_v2_answerhit_02",       # Tier3
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
                      facts_dir=str(Path(__file__).resolve().parent / "out" / "facts"))
    w0 = gateway.writer.count

    print("[飞行前回显] 默认臂(kernel 原文,逐字):")
    print(f"  {ARM_DEFAULT!r}")

    results = []
    for cid in SCREEN_IDS:
        used = gateway.writer.count - w0
        if used + PER_CASE_RESERVE > min(MAX_CALLS, SCREEN_SOFT_CAP):
            print(f"[ABORT] 筛段预算将越顶(已用 {used}+储备 {PER_CASE_RESERVE}),停跑")
            sys.exit(2)
        case = cases[cid]
        subject = ElicitSubject(ARM_DEFAULT, gateway)
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
        rec = {"case_id": cid, "arm": "default",
               "transcript": transcript, "guard_events": guard_events,
               "judge": judge_out,
               "elicit_hits": len(elicit_hits),
               "calls_used": gateway.writer.count - w0}
        (OUT / f"{cid}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{cid}] 轮数={len(transcript.get('turns') or [])} "
              f"elicit={len(elicit_hits)} judge={judge_out.get('total')} "
              f"calls累计={rec['calls_used']}")
        results.append(rec)

    triggered = [r["case_id"] for r in results if r["elicit_hits"]]
    print(f"\n筛段完成:{len(results)} 案,elicit 触发 {len(triggered)} 案:{triggered}")
    print(f"calls 实计:{gateway.writer.count - w0}")
    (OUT / "screen-summary.json").write_text(
        json.dumps({"n_screened": len(results),
                    "triggered": triggered,
                    "per_case": [{"case_id": r["case_id"],
                                  "elicit_hits": r["elicit_hits"],
                                  "turns": len(r["transcript"].get("turns") or []),
                                  "judge_total": r["judge"].get("total")}
                                 for r in results],
                    "calls_used": gateway.writer.count - w0},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    if len(triggered) < 8:
        print("[REPORT] 触发数 <8,按预注册停跑报 PM")


if __name__ == "__main__":
    main()
