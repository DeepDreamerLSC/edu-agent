#!/usr/bin/env python3
"""elicit 触发对补跑(#293 教师盲审材料;task=elicit-pair-topup,PM 直发)。

预注册:#293 评论 5713864212(判读口径跑前冻结,跑后不改)。
2 案(chicken_rabbit/equation_subtract)× 2 臂(长跑 best/kernel 默认),
评测路径自然跑(tutor+judge 本地,零 editor 零搜索零远程);≤30 calls 硬顶。

工件:out/<案>/<盲标A|B>.json(transcript+guard_events+判卷)+ mapping.json
(臂→盲标随机映射,只入仓不进教师材料)。
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # 仓库根
DATASET = ROOT / "edu_agent/evals/datasets/small_lecturer_dialogue_stability_20.json"
OUT = Path(__file__).resolve().parent / "out"
MAX_CALLS = 30  # PM 派单硬顶;超即停报
PER_EVAL_RESERVE = 8  # 单评测上界(tutor ~5 + judge 1 + 裕量),预算前置检查用

# 两臂(预注册逐字引用;来源见 #293 评论)
ARM_X = ("请复讲：先说核心思路，再写出第一步的具体算式或操作，最后给出明确结论。"
         "请用完整句子描述步骤与结果，以便确认掌握。")  # epoch-2(nets-main-02 正本)
ARM_Y = ("我们从头把思路串一遍——"
         "先说说你第一步算了什么、为什么这样算。")  # kernel _ELICIT_TEMPLATE 原文
CASE_IDS = ("stability_chicken_rabbit", "stability_equation_subtract")


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
                      facts_dir=str(OUT / "facts"))
    w0 = gateway.writer.count

    # 盲化:臂→A/B 随机(固定 seed,预注册口径);文件名只用盲标
    rng = random.Random(20260917)
    blind = {"X": "A", "Y": "B"}
    blind["X"], blind["Y"] = rng.sample(("A", "B"), 2)
    (OUT / "mapping.json").write_text(
        json.dumps({"arm_X": blind["X"], "arm_Y": blind["Y"],
                    "note": "臂→盲标随机映射(seed=20260917);"
                            "X=epoch-2(nets-main-02) Y=kernel默认,真实对应只存本件"},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    report = []
    for cid in CASE_IDS:
        case = cases[cid]
        for arm, tpl in (("X", ARM_X), ("Y", ARM_Y)):
            used = gateway.writer.count - w0
            if used + PER_EVAL_RESERVE > MAX_CALLS:
                print(f"[ABORT] 预算将越顶(已用 {used}+储备 {PER_EVAL_RESERVE}"
                      f">{MAX_CALLS}),按派单停跑——已产工件保留")
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
            rec = {"case_id": cid, "arm_blind": blind[arm],
                   "transcript": transcript, "guard_events": guard_events,
                   "judge": judge_out,
                   "calls_used": gateway.writer.count - w0}
            d = OUT / cid
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{blind[arm]}.json").write_text(
                json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            elicit_hits = sum(1 for e in guard_events
                              if e.get("branch") == "elicit")
            print(f"[{cid}/{blind[arm]}] 轮数={len(transcript.get('turns') or [])} "
                  f"elicit埋点={elicit_hits} judge_total={judge_out.get('total')} "
                  f"verdict={judge_out.get('verdict')} calls累计={rec['calls_used']}")
            report.append(rec)

    total_calls = gateway.writer.count - w0
    print(f"完成:2 案×2 臂,calls 实计 {total_calls}(硬顶 {MAX_CALLS})")
    (OUT / "run-summary.json").write_text(
        json.dumps({"calls": total_calls, "max_calls": MAX_CALLS,
                    "records": [{"case_id": r["case_id"],
                                 "arm_blind": r["arm_blind"],
                                 "judge_total": r["judge"].get("total"),
                                 "judge_verdict": r["judge"].get("verdict"),
                                 "elicit_hits": sum(1 for e in r["guard_events"]
                                                    if e.get("branch") == "elicit")}
                                for r in report]}, ensure_ascii=False, indent=2),
        encoding="utf-8")


if __name__ == "__main__":
    main()
