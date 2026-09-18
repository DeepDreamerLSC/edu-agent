#!/usr/bin/env python3
"""V1 首验重放(#333 task=v1-replay;PM 派单,裁定 c5717512971 跑前冻结评论 5727284505)。

4 案(answerhit_01/understanding_04/stuck_01/stuck_02)× KernelSubject 真 kernel
(零 monkeypatch,当前 main b7cb624=V1#358+property#360),enriched12 fixture,
本地模型,~30 calls 预算(硬顶 40)。判读口径=冻结评论:
①锚过=reveal 轮带 anchor_numbers;②拦住=answer_leak 照旧+锚不出 model 分支;
③92/93 硬门=make check 另跑(本盒)。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # 仓库根
ENRICHED12 = ROOT / "edu_agent/evals/datasets/small_lecturer_image_teaching_v2_enriched12.json"
# 裁 b 补验自有 fixture(PM 裁:enriched12 是分层抽样数据集不作宿主,字节还原 main)
FIXTURES_V1ANCHOR = Path(__file__).resolve().parent / "fixtures_v1anchor.json"
OUT = Path(__file__).resolve().parent / "out" / "v1"
FACTS = Path(__file__).resolve().parent / "out" / "facts"
MAX_CALLS = 40  # PM ~30 预算+裕量硬顶
PER_CASE_RESERVE = 9

CASE_IDS = [
    "image_v2_answerhit_01",    # elicit 线(终答命中面:answer_leak 应拦)
    "image_v2_understanding_04",  # elicit 线(理解信号)
    "image_v2_stuck_01",        # support 线(再次 stuck→V1 锚过应实证)
    "image_v2_stuck_02",        # support 线
    # 裁 b 补验(#333 5727499202 冻结):二次卡壳+数字步骤,中间值≠终答
    "image_v2_v1anchor_01",     # 12米剪1/3 剩(中间值4/终答8)
    "image_v2_v1anchor_02",     # 4分米剪1/4 剩(中间值1/终答3)
]


def main() -> None:
    case_ids = sys.argv[1:] or CASE_IDS  # 补验轮:可传子集只重跑目标案
    from edu_agent.evals.corpus_round import transcript_messages
    from edu_agent.evals.judge import judge_transcript
    from edu_agent.evals.kernel_subject import KernelSubject
    from edu_agent.gateway import Gateway
    from edu_agent.gateway.registry import load_registry

    OUT.mkdir(parents=True, exist_ok=True)
    cases = {}
    for src in (ENRICHED12, FIXTURES_V1ANCHOR):
        payload = json.loads(src.read_text(encoding="utf-8"))
        cases.update({c["id"]: c for c in payload["scenarios"]})

    gateway = Gateway(load_registry(ROOT / "configs/models.yaml"),
                      facts_dir=str(FACTS))
    w0 = gateway.writer.count
    subject = KernelSubject(gateway)

    results = []
    for cid in case_ids:
        used = gateway.writer.count - w0
        if used + PER_CASE_RESERVE > MAX_CALLS:
            print(f"[ABORT] 预算将越顶(已用 {used}+储备 {PER_CASE_RESERVE} > {MAX_CALLS}),停跑")
            sys.exit(2)
        transcript = subject.run_case(cases[cid])
        guard_events = transcript.get("guard_events") or []
        judge_out = judge_transcript(
            gateway,
            {"question": cases[cid].get("question", ""),
             "grade": cases[cid].get("grade", ""),
             "reference_answer": cases[cid].get("reference_answer", ""),
             "messages": transcript_messages(transcript)},
            role="judge")
        # 冻结判读①:授权锚轮(reveal+anchor_numbers)
        anchor_rounds = [e for e in guard_events
                         if e.get("branch") == "reveal" and "anchor_numbers" in e]
        # 冻结判读②:answer_leak 拦截照旧;锚不进 model 分支
        leak_rounds = [e for e in guard_events if e.get("guard") == "answer_leak"]
        anchor_on_model = [e for e in guard_events
                           if e.get("branch") != "reveal" and "anchor_numbers" in e]
        rec = {"case_id": cid, "arm": "kernel-v1",
               "transcript": transcript, "guard_events": guard_events,
               "judge": judge_out,
               "anchor_rounds": len(anchor_rounds),
               "anchor_details": [{k: e.get(k) for k in ("turn", "hint_level", "anchor_numbers")}
                                  for e in anchor_rounds],
               "leak_rounds": len(leak_rounds),
               "anchor_on_model_branch": len(anchor_on_model),
               "calls_used": gateway.writer.count - w0}
        (OUT / f"{cid}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{cid}] 轮数={len(transcript.get('turns') or [])} "
              f"anchor={len(anchor_rounds)} leak={len(leak_rounds)} "
              f"judge={judge_out.get('total')} calls累计={rec['calls_used']}")
        results.append(rec)

    total = gateway.writer.count - w0
    print(f"\nV1 重放完成:{len(results)} 案,calls 实计 {total}")
    (OUT / "v1-summary.json").write_text(
        json.dumps({"n": len(results), "calls": total,
                    "per_case": [{"case_id": r["case_id"],
                                  "anchor_rounds": r["anchor_rounds"],
                                  "leak_rounds": r["leak_rounds"],
                                  "anchor_on_model_branch": r["anchor_on_model_branch"],
                                  "final_state": r["transcript"].get("final_state")}
                                 for r in results]}, ensure_ascii=False, indent=2),
        encoding="utf-8")


if __name__ == "__main__":
    main()
