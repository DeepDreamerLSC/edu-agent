#!/usr/bin/env python3
"""二阶段逐机制贡献表 v2(#333 kernel-ablation-phase2;协议 §5 预注册)。

零模型 calls:读 out/phase2/<variant>/<case>.json + 一阶段 out/ablation/C/<case>.json
(主对照),复用一阶段 ablation_metrics 的 M1-M6 函数(同口径 by construction),
落 phase2-summary.json:逐机制×指标×案贡献表 + CREF 噪声带 + 三分类判定。
"""

from __future__ import annotations

import json
from pathlib import Path

from ablation_metrics import (m1_grounding, m2_requestion, m3_overcollect,
                              m4_answer_in_question, m5_turns_to_closure,
                              m6_interventions, _tutor_turns)

HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "phase2"
P1C = HERE / "out" / "ablation" / "C"  # 一阶段 C = 主对照(协议附录 B)

# 协议 §5 判定线的指标面
METRICS = ("m1", "m2", "m4", "rate", "judge")
M2_EARNER_CASES = ("no-progress-real-6a61aa32-replay", "image_v2_stuck_02")
FLUENT_CASES = ("image_v2_understanding_04", "no-progress-control-reasonable-review",
                "no-progress-control-thin-reasoning")
M2_EARNER_THRESHOLD = 2   # Δm2 ≥ +2 vs 一阶段 C → 真消费者方向
EARNER_MECHS = {"repeat_regen", "repeat_fallback", "reveal_ladder"}
SABOTEUR_MECHS = {"premature_confirm", "confirm_rewrite", "soften_step",
                  "bottomout_backboard"}


def _row(rec: dict, answer: str) -> dict:
    tr, ge = rec["transcript"], rec["guard_events"]
    m6 = m6_interventions(ge, tr)
    return {"m1": m1_grounding(tr), "m2": m2_requestion(tr),
            "m3": m3_overcollect(tr), "m4": m4_answer_in_question(tr, answer),
            "m5": m5_turns_to_closure(tr), "rate": m6["rate"],
            "state": tr.get("final_state"),
            "judge": (rec.get("judge") or {}).get("total"),
            "turns": len(_tutor_turns(tr))}


def _load(root: Path, key: str, cid: str) -> dict | None:
    f = root / key / f"{cid}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def main() -> None:
    from ablation_run import load_cases  # 同目录(脚本态 sys.path[0])
    cases = load_cases()

    variants = sorted(p.name for p in OUT.iterdir() if p.is_dir())
    case_ids = sorted({p.stem for v in variants for p in (OUT / v).glob("*.json")})

    table: dict[str, dict[str, dict]] = {}
    noise: dict[str, dict] = {}
    answers = {cid: str((cases.get(cid, {}).get("question") or {}).get("answer") or "")
               for cid in case_ids}
    for cid in case_ids:
        table[cid] = {}
        for v in variants:
            rec = _load(OUT, v, cid)
            if rec is not None:
                table[cid][v] = _row(rec, answers[cid])
        p1 = _load(P1C.parent, "C", cid)  # P1C 已含尾段 C;root=ablation,key=C
        if p1 is not None:
            table[cid]["P1-C"] = _row(p1, answers[cid])
        # 噪声带 = |CREF − P1-C| 逐指标
        if "CREF" in table[cid] and "P1-C" in table[cid]:
            noise[cid] = {m: abs(table[cid]["CREF"][m] - table[cid]["P1-C"][m])
                          for m in METRICS}

    verdicts: dict[str, dict] = {}
    for v in variants:
        if v == "CREF":
            continue
        mech = v.removeprefix("LOO-")
        # 真消费者线(预注册 §5):M2 主案/stuck 案 Δm2 ≥ +2(绝对阈值,跑后不改)
        earner_hits = [c for c in M2_EARNER_CASES
                       if c in table and v in table[c] and "P1-C" in table[c]
                       and (table[c][v]["m2"] - table[c]["P1-C"]["m2"]) >= M2_EARNER_THRESHOLD]
        # 拆台者线:流畅案 judge 回升 > 噪声带 且 state 无降级
        saboteur_hits = []
        positive_hits = []  # 反向信号:关闭后 judge 降幅超带(该机制有正贡献)
        for c in FLUENT_CASES + M2_EARNER_CASES:
            if not (c in table and v in table[c] and "P1-C" in table[c]):
                continue
            dj = table[c][v]["judge"] - table[c]["P1-C"]["judge"]
            band = (noise.get(c, {}).get("judge") or 0)
            degraded = (table[c][v]["state"] == "needs_review"
                        and table[c]["P1-C"]["state"] != "needs_review")
            if dj > band and not degraded:
                saboteur_hits.append(c)
            if dj < -band:
                positive_hits.append(c)
        neutral = not earner_hits and not saboteur_hits and not positive_hits
        verdicts[v] = {"mech": mech,
                       "earner_cases": earner_hits, "saboteur_cases": saboteur_hits,
                       "positive_cases": positive_hits,
                       "class": ("真消费者" if earner_hits and mech in EARNER_MECHS
                                 else "拆台者" if saboteur_hits and mech in SABOTEUR_MECHS
                                 else "正贡献确认" if positive_hits
                                 else "无感(带内)" if neutral and noise
                                 else "无感*" if neutral else "信号越类(呈 PM 裁)")}

    summary = {"by_case": table, "noise_band_CREF_vs_P1C": noise,
               "verdicts": verdicts,
               "lines": {"m2_earner_threshold": M2_EARNER_THRESHOLD,
                         "earner_mechs": sorted(EARNER_MECHS),
                         "saboteur_mechs": sorted(SABOTEUR_MECHS),
                         "noise_note": "带=|CREF−P1-C| 逐指标逐案(2026-09-19 phase2b 填实)"}}
    (OUT / "phase2-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("phase2-summary.json 落盘;变体数:", len(variants))
    for v, verdict in verdicts.items():
        print(v, "->", verdict["class"],
              "| earner:", verdict["earner_cases"],
              "| saboteur:", verdict["saboteur_cases"],
              "| positive:", verdict["positive_cases"])
    if noise:
        print("噪声带(judge):", {c: n.get("judge") for c, n in noise.items()})


if __name__ == "__main__":
    main()
