#!/usr/bin/env python3
"""三臂消融 runner(#333 kernel-ablation-run;协议=ablation-protocol-v1.md,点火键已落)。

三臂 A(raw shadow)/B(thin safety)/C(main)×12 案,本地零远程;预算 ≈290 硬顶 360
(超顶即停 exit 2)。每臂串行设置(模块级臂无并发串臂),臂间 reset C。
判读不在本脚本(M1-M6=ablation_metrics.py);judge 全跑只作旁证(协议 §3)。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # 仓库根
HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "ablation"
FACTS = HERE / "out" / "facts"
MAX_CALLS = 360  # 协议 §4 硬顶
PER_CASE_RESERVE = 12

ARMS = ["A", "B", "C"]

DATASETS = [
    ROOT / "edu_agent/evals/datasets/small_lecturer_no_progress_controls_v1.json",
    ROOT / "edu_agent/evals/datasets/small_lecturer_image_teaching_v2_enriched12.json",
    ROOT / "edu_agent/evals/datasets/small_lecturer_no_progress_real_v1.json",
    HERE / "ablation-cases-probe.json",    # 换写变体案(R1 m1_probe_corpus 提取)
    HERE / "ablation-cases-comma.json",    # 千分位撞池案(冻结附录)
]

CASE_IDS = [
    # fluent×2(协议 §2)
    "no-progress-control-reasonable-review",
    "no-progress-control-thin-reasoning",
    # stuck×2
    "image_v2_stuck_01",
    "image_v2_stuck_02",
    # no-progress×2(方位长对+换写变体)
    "no-progress-real-6a61aa32-replay",
    "no-progress-real-paraphrase-probe",
    # leak-risk×2
    "image_v2_answerhit_01",
    "image_v2_answerhit_02",
    # anchor collision×1(千分位补案,冻结附录)
    "ablation-comma-collision-01",
    # image-production×2
    "image_v2_understanding_04",
    "image_v2_understanding_02",
]


def load_cases() -> dict:
    cases: dict = {}
    for src in DATASETS:
        payload = json.loads(src.read_text(encoding="utf-8"))
        cases.update({c["id"]: c for c in payload.get("scenarios") or []})
    missing = [c for c in CASE_IDS if c not in cases]
    if missing:
        raise SystemExit(f"[FAIL] slice 案缺 fixture: {missing}")
    return cases


def main() -> None:
    from edu_agent.agents.small_lecturer import kernel as K
    from edu_agent.evals.corpus_round import transcript_messages
    from edu_agent.evals.judge import judge_transcript
    from edu_agent.evals.kernel_subject import KernelSubject
    from edu_agent.gateway import Gateway
    from edu_agent.gateway.registry import load_registry

    cases = load_cases()
    OUT.mkdir(parents=True, exist_ok=True)
    gateway = Gateway(load_registry(ROOT / "configs/models.yaml"),
                      facts_dir=str(FACTS))
    w0 = gateway.writer.count
    subject = KernelSubject(gateway)
    calls_by_arm: dict[str, int] = {}
    for arm in ARMS:
        K.set_ablation_arm(arm)
        (OUT / arm).mkdir(parents=True, exist_ok=True)
        arm_w0 = gateway.writer.count
        for cid in CASE_IDS:
            used = gateway.writer.count - w0
            if used + PER_CASE_RESERVE > MAX_CALLS:
                print(f"[ABORT] 预算将越顶(已用 {used}+储备 {PER_CASE_RESERVE} > "
                      f"{MAX_CALLS}),停跑于 {arm}/{cid}")
                K.set_ablation_arm("C")
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
            rec = {"case_id": cid, "arm": arm,
                   "transcript": transcript, "guard_events": guard_events,
                   "judge": judge_out,
                   "calls_used": gateway.writer.count - arm_w0}
            (OUT / arm / f"{cid}.json").write_text(
                json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[{arm}/{cid}] 轮数={len(transcript.get('turns') or [])} "
                  f"guard={len(guard_events)} "
                  f"calls={gateway.writer.count - arm_w0}", flush=True)
        calls_by_arm[arm] = gateway.writer.count - arm_w0
        K.set_ablation_arm("C")
    total = gateway.writer.count - w0
    (OUT / "run-meta.json").write_text(json.dumps(
        {"total_calls": total, "calls_by_arm": calls_by_arm,
         "max_calls": MAX_CALLS, "arms": ARMS, "cases": CASE_IDS},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"三臂完成:总 calls={total}(硬顶 {MAX_CALLS}),分臂 {calls_by_arm}")


if __name__ == "__main__":
    main()
