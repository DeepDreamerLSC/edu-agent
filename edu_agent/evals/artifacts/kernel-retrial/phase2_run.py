#!/usr/bin/env python3
"""二阶段逐机制归因 runner(#333 kernel-ablation-phase2;协议=phase2-protocol-v1.md)。

LOO-from-C:7 机制变体 + CREF(C 同配置复跑,噪声底)× 5 判别案;本地零远程;
预算硬顶 250(将越顶 exit 2 停呈 PM)。臂恒 C,变体只动 off 集;臂间/变体间复位。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "phase2"
FACTS = HERE / "out" / "facts"  # 与一阶段同 facts 流(追加写)
MAX_CALLS = 250  # 协议 §4 硬顶
PER_CASE_RESERVE = 12

# 变体 → off 集(协议 §2 词表;CREF=空集=C 原样,仅作噪声底)
VARIANTS: dict[str, frozenset[str]] = {
    "LOO-repeat_regen": frozenset({"repeat_regen"}),
    "LOO-repeat_fallback": frozenset({"repeat_fallback"}),
    "LOO-reveal_ladder": frozenset({"reveal_ladder"}),
    "LOO-premature_confirm": frozenset({"premature_confirm"}),
    "LOO-confirm_rewrite": frozenset({"confirm_rewrite"}),
    "LOO-soften_step": frozenset({"soften_step"}),
    "LOO-bottomout_backboard": frozenset({"bottomout_backboard"}),
    "CREF": frozenset(),
}

CASE_IDS = [  # 协议 §3 判别切片(PM 派单指定)
    "no-progress-real-6a61aa32-replay",
    "image_v2_understanding_04",
    "no-progress-control-reasonable-review",
    "no-progress-control-thin-reasoning",
    "image_v2_stuck_02",
]


def main() -> None:
    from edu_agent.agents.small_lecturer import kernel as K
    from edu_agent.evals.corpus_round import transcript_messages
    from edu_agent.evals.judge import judge_transcript
    from edu_agent.evals.kernel_subject import KernelSubject
    from edu_agent.gateway import Gateway
    from edu_agent.gateway.registry import load_registry
    from ablation_run import load_cases  # 同目录工件脚本(脚本态 sys.path[0])

    cases = load_cases()
    missing = [c for c in CASE_IDS if c not in cases]
    if missing:
        raise SystemExit(f"[FAIL] 判别切片缺 fixture: {missing}")
    OUT.mkdir(parents=True, exist_ok=True)
    gateway = Gateway(load_registry(ROOT / "configs/models.yaml"),
                      facts_dir=str(FACTS))
    w0 = gateway.writer.count
    subject = KernelSubject(gateway)
    calls_by_variant: dict[str, int] = {}
    for variant, off in VARIANTS.items():
        K.set_ablation_arm("C")
        K.set_phase2_off(off)
        (OUT / variant).mkdir(parents=True, exist_ok=True)
        vw0 = gateway.writer.count
        for cid in CASE_IDS:
            used = gateway.writer.count - w0
            if used + PER_CASE_RESERVE > MAX_CALLS:
                print(f"[ABORT] 预算将越顶(已用 {used}+储备 {PER_CASE_RESERVE} > "
                      f"{MAX_CALLS}),停跑于 {variant}/{cid}")
                K.set_phase2_off(())
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
        calls_by_variant[variant] = gateway.writer.count - vw0
        K.set_phase2_off(())
    K.set_ablation_arm("C")
    total = gateway.writer.count - w0
    (OUT / "run-meta.json").write_text(json.dumps(
        {"total_calls": total, "calls_by_variant": calls_by_variant,
         "max_calls": MAX_CALLS, "variants": list(VARIANTS), "cases": CASE_IDS},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"二阶段完成:总 calls={total}(硬顶 {MAX_CALLS}),分变体 {calls_by_variant}")


if __name__ == "__main__":
    main()
