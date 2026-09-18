#!/usr/bin/env python3
"""泄露网 V1 viability 4 案重放跑器(#333 裁定执行序 5 首验;PM 49255c5dba108a0b)。

复用 teacher-delta-review 设施模式(KernelSubject 自然剧本驱动 + 真实本地 gateway
+ calls 硬顶 + 工件落盘);**本地模型执行由 PM 路由**——本跑器备好即交,无本地栈
不跑(零远程零 API)。判读口径跑前冻结,跑后不改(预注册纪律,同 run_pairs)。

预期输出预声明(派单原文):
- image_v2_stuck_02:锚过(re-stuck 轮 anchor_numbers 非空,且不含终答数字)
- image_v2_answerhit_01:仍拦(全程无 anchor_numbers;单步 value=终答天然 fail-closed)
- image_v2_stuck_01 / image_v2_understanding_04:无锚(纯文字答案 / 多部件全保护)
- 硬判据(独立于锚预期,92/93 泄漏=0 硬门的单案形态):reveal/bottom-out 后 tutor
  文本不出现终答数字——bottom-out(「这一步我们直接看结果:」前缀)与 finish 两条
  设计内披露点除外。

注意:剧本若未产生 re-stuck 轮,锚预期记 diverge(如实记录,那就是读数)——
不构造对话、不重跑换读数;diverge 清单交 PM 裁定是否补剧本。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DATASET = ROOT / "edu_agent/evals/datasets/small_lecturer_image_teaching_v2_enriched12.json"
OUT = Path(__file__).resolve().parent / "out" / "replay-v1"
MAX_CALLS = 60  # 4 案硬顶(tutor ~3/轮 × ~4 轮 + 裕量;超顶停跑报 PM)

CASE_IDS = ("image_v2_stuck_02", "image_v2_answerhit_01",
            "image_v2_stuck_01", "image_v2_understanding_04")
# 预声明锚预期(见模块 docstring;None=无锚预期)
ANCHOR_EXPECTED = {"image_v2_stuck_02": True, "image_v2_answerhit_01": False,
                   "image_v2_stuck_01": False, "image_v2_understanding_04": False}
_ASCII_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_BOTTOMOUT_PREFIX = "这一步我们直接看结果:"


def _answer_numbers(case: dict) -> set[float]:
    """终答数字池(canonical:reference_answer.value;多部件全保护)。"""
    raw = str((case.get("reference_answer") or {}).get("value") or "")
    return {float(m) for m in _ASCII_NUMBER.findall(raw)}


def _leak_scan(case: dict, transcript: dict) -> list[int]:
    """终答数字泄露扫描:非 bottom-out 的 tutor 轮出现终答数字 → 轮号清单。"""
    pool = _answer_numbers(case)
    hits = []
    for i, turn in enumerate(transcript.get("turns") or []):
        text = str(turn.get("tutor") or "")
        if text.startswith(_BOTTOMOUT_PREFIX) or turn.get("state") == "completed":
            continue  # 设计内披露点(bottom-out / finish)
        if pool & {float(m) for m in _ASCII_NUMBER.findall(text)}:
            hits.append(i)
    return hits


def main() -> int:
    from edu_agent.evals.kernel_subject import KernelSubject
    from edu_agent.gateway import Gateway
    from edu_agent.gateway.registry import load_registry

    OUT.mkdir(parents=True, exist_ok=True)
    payload = json.loads(DATASET.read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in payload["scenarios"]}
    gateway = Gateway(load_registry(ROOT / "configs/models.yaml"), facts_dir=str(OUT / "facts"))
    w0 = gateway.writer.count
    summary = []
    for cid in CASE_IDS:
        if gateway.writer.count - w0 + 8 > MAX_CALLS:
            print(f"[ABORT] 预算将越顶(已用 {gateway.writer.count - w0}),按硬顶停跑报 PM")
            sys.exit(2)
        case = cases[cid]
        transcript = KernelSubject(gateway).run_case(case)
        guard_events = transcript.get("guard_events") or []
        anchor_events = [e for e in guard_events if e.get("anchor_numbers")]
        leaks = _leak_scan(case, transcript)
        expected = ANCHOR_EXPECTED[cid]
        fired = bool(anchor_events)
        verdict = "pass" if leaks == [] and fired == expected else (
            "leak" if leaks else "diverge")
        rec = {"case_id": cid, "anchor_expected": expected, "anchor_fired": fired,
               "anchor_events": anchor_events, "leak_turns": leaks, "verdict": verdict,
               "transcript": transcript, "calls_used": gateway.writer.count - w0}
        (OUT / f"{cid}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{cid}] 锚预期={expected} 实触发={fired} 泄漏轮={leaks} → {verdict}")
        summary.append({k: rec[k] for k in ("case_id", "anchor_expected", "anchor_fired",
                                            "leak_turns", "verdict")})
    (OUT / "run-summary.json").write_text(
        json.dumps({"note": "判读口径跑前冻结(模块 docstring);diverge=如实记录待 PM 裁定",
                    "cases": summary}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
