#!/usr/bin/env python3
"""B+X 加回实验 runner(#333 kernel-ablation-phase2bx;点火单 2026-09-19)。

调用制:每次进程跑一个变体(`python phase2bx_run.py <variant>`),因 B+X 变体
=各自 patch 分支上的 owner-layer kernel 代码态(BASE-C/BASE-B 跑基线分支,
B-<mech> 跑对应 patch 分支);out/ 工件跨 checkout 持续累积。预算硬顶 100
(整批跨进程账本=run-meta.json;超停 exit 2 呈 PM)。判读线见 phase2bx-design-v0.md
§3(点火单⑤:冻结后跑)。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "phase2bx"
FACTS = HERE / "out" / "facts"
MAX_CALLS = 100  # 点火单预算带硬顶(60-100 整批)
PER_CASE_RESERVE = 12

BASELINE = [  # ② parity 修正后基线(判别切片 5+leak-risk 2+comma 1)
    "no-progress-real-6a61aa32-replay",
    "image_v2_understanding_04",
    "no-progress-control-reasonable-review",
    "no-progress-control-thin-reasoning",
    "image_v2_stuck_02",
    "image_v2_answerhit_01",
    "image_v2_answerhit_02",
    "ablation-comma-collision-01",
]
RUNS: dict[str, tuple[str, list[str]]] = {  # 变体 → (arm, 案)
    "BASE-C": ("C", BASELINE),
    "BASE-B": ("B", BASELINE),
    "B-repeat_regen": ("B", [  # 2正:6a61aa32/stuck_02;2负:reasonable/thin
        "no-progress-real-6a61aa32-replay",
        "image_v2_stuck_02",
        "no-progress-control-reasonable-review",
        "no-progress-control-thin-reasoning",
    ]),
    "B-elicit": ("B", [  # 2正:stuck_02/comma;2负:u4/thin
        "image_v2_stuck_02",
        "ablation-comma-collision-01",
        "image_v2_understanding_04",
        "no-progress-control-thin-reasoning",
    ]),
    "B-reveal_ladder": ("B", [  # 2正:stuck_02/comma;2负:thin/reasonable
        "image_v2_stuck_02",
        "ablation-comma-collision-01",
        "no-progress-control-thin-reasoning",
        "no-progress-control-reasonable-review",
    ]),
}


def main() -> None:
    variant = sys.argv[1] if len(sys.argv) > 1 else ""
    if variant not in RUNS:
        raise SystemExit(f"用法: phase2bx_run.py <{'|'.join(RUNS)}>")
    arm, case_ids = RUNS[variant]
    from edu_agent.agents.small_lecturer import kernel as K
    from edu_agent.evals.corpus_round import transcript_messages
    from edu_agent.evals.judge import judge_transcript
    from edu_agent.evals.kernel_subject import KernelSubject
    from edu_agent.gateway import Gateway
    from edu_agent.gateway.registry import load_registry
    from ablation_run import load_cases  # 同目录工件脚本(脚本态 sys.path[0])

    cases = load_cases()
    missing = [c for c in case_ids if c not in cases]
    if missing:
        raise SystemExit(f"[FAIL] 缺 fixture: {missing}")
    OUT.mkdir(parents=True, exist_ok=True)
    meta_p = OUT / "run-meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    batch_used = int(meta.get("total_calls") or 0)
    gateway = Gateway(load_registry(ROOT / "configs/models.yaml"),
                      facts_dir=str(FACTS))
    subject = KernelSubject(gateway)
    K.set_ablation_arm(arm)
    (OUT / variant).mkdir(parents=True, exist_ok=True)
    vw0 = gateway.writer.count
    for cid in case_ids:
        if batch_used + (gateway.writer.count - vw0) + PER_CASE_RESERVE > MAX_CALLS:
            meta["total_calls"] = batch_used + gateway.writer.count - vw0
            meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                              encoding="utf-8")
            print(f"[ABORT] 预算将越顶(批已用 {meta['total_calls']}+储备 "
                  f"{PER_CASE_RESERVE} > {MAX_CALLS}),停跑于 {variant}/{cid}",
                  flush=True)
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
        rec = {"case_id": cid, "variant": variant, "arm": arm,
               "transcript": transcript, "guard_events": guard_events,
               "judge": judge_out,
               "calls_used": gateway.writer.count - vw0}
        (OUT / variant / f"{cid}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{variant}/{cid}] 轮数={len(transcript.get('turns') or [])} "
              f"guard={len(guard_events)} calls={gateway.writer.count - vw0}",
              flush=True)
    meta["total_calls"] = batch_used + gateway.writer.count - vw0
    meta.setdefault("variants", {})[variant] = {
        "calls": gateway.writer.count - vw0, "arm": arm}
    meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"{variant} 完成:本变体 calls={gateway.writer.count - vw0},"
          f"批累计 {meta['total_calls']}/{MAX_CALLS}")


if __name__ == "__main__":
    main()
