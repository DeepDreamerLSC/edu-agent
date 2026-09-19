#!/usr/bin/env python3
"""二阶段 b 补全 runner(#333 kernel-ablation-phase2b;协议=phase2-protocol-v1 §4/§5)。

①CREF 噪声底:C 同配置复跑判别切片 5 案;②bottomout_backboard 补 2 案
(上轮预算中止缺)。预算硬顶 55(本单独立;超停 exit 2 呈 PM)。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "phase2"
FACTS = HERE / "out" / "facts"
MAX_CALLS = 55  # PM 派单 2026-09-19 硬顶(phase2b 独立额度)
PER_CASE_RESERVE = 12

RUNS: list[tuple[str, frozenset[str], list[str]]] = [
    # (变体目录, off 集, 案)——CREF 全 5 案;bottomout_backboard 补缺 2 案
    ("CREF", frozenset(), [
        "no-progress-real-6a61aa32-replay",
        "image_v2_understanding_04",
        "no-progress-control-reasonable-review",
        "no-progress-control-thin-reasoning",
        "image_v2_stuck_02",
    ]),
    ("LOO-bottomout_backboard", frozenset({"bottomout_backboard"}), [
        "no-progress-control-thin-reasoning",
        "image_v2_stuck_02",
    ]),
]


def main() -> None:
    from edu_agent.agents.small_lecturer import kernel as K
    from edu_agent.agents.small_lecturer.ablation import set_phase2_off
    from edu_agent.evals.corpus_round import transcript_messages
    from edu_agent.evals.judge import judge_transcript
    from edu_agent.evals.kernel_subject import KernelSubject
    from edu_agent.gateway import Gateway
    from edu_agent.gateway.registry import load_registry
    from ablation_run import load_cases  # 同目录工件脚本(脚本态 sys.path[0])

    cases = load_cases()
    missing = [c for _, _, cs in RUNS for c in cs if c not in cases]
    if missing:
        raise SystemExit(f"[FAIL] 缺 fixture: {missing}")
    OUT.mkdir(parents=True, exist_ok=True)
    gateway = Gateway(load_registry(ROOT / "configs/models.yaml"),
                      facts_dir=str(FACTS))
    w0 = gateway.writer.count
    subject = KernelSubject(gateway)
    spent: dict[str, int] = {}
    for variant, off, case_ids in RUNS:
        K.set_ablation_arm("C")
        set_phase2_off(off)
        (OUT / variant).mkdir(parents=True, exist_ok=True)
        vw0 = gateway.writer.count
        for cid in case_ids:
            used = gateway.writer.count - w0
            if used + PER_CASE_RESERVE > MAX_CALLS:
                print(f"[ABORT] 预算将越顶(已用 {used}+储备 {PER_CASE_RESERVE} > "
                      f"{MAX_CALLS}),停跑于 {variant}/{cid}")
                set_phase2_off(())
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
            rec = {"case_id": cid, "variant": variant, "off": sorted(off),
                   "transcript": transcript, "guard_events": guard_events,
                   "judge": judge_out,
                   "calls_used": gateway.writer.count - vw0}
            (OUT / variant / f"{cid}.json").write_text(
                json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[{variant}/{cid}] 轮数={len(transcript.get('turns') or [])} "
                  f"guard={len(guard_events)} calls={gateway.writer.count - vw0}",
                  flush=True)
        spent[variant] = gateway.writer.count - vw0
        set_phase2_off(())
    K.set_ablation_arm("C")
    total = gateway.writer.count - w0
    meta_p = OUT / "run-meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    meta["phase2b"] = {"total_calls": total, "spent": spent, "max_calls": MAX_CALLS}
    meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"phase2b 完成:总 calls={total}(硬顶 {MAX_CALLS}),分项 {spent}")


if __name__ == "__main__":
    main()
