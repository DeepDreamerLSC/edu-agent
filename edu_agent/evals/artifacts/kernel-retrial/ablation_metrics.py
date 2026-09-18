#!/usr/bin/env python3
"""M1-M6 量化+三臂对照+真差异对清单(#333 kernel-ablation;协议 §3 操作化)。

零模型 calls:读 out/ablation/{A,B,C}/<case>.json 计算,落 ablation-summary.json
+M7 材料(真差异对:A vs C 逐轮文本不等的案)。
判读=人(协议 §5 四情况);本脚本只出数,不下结论。
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "ablation"
ARMS = ["A", "B", "C"]

_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def _tutor_turns(transcript: dict) -> list[str]:
    return [str(t.get("tutor") or "").strip() for t in transcript.get("turns") or []
            if str(t.get("tutor") or "").strip()]


def _student_turns(transcript: dict) -> list[str]:
    return [str(t.get("student") or "").strip() for t in transcript.get("turns") or []
            if str(t.get("student") or "").strip()]


def m1_grounding(transcript: dict) -> float | None:
    """M1 turn grounding:每 tutor 轮(非首问)与前一学生轮的 SequenceMatcher ratio 均值。"""
    pairs = []
    prev_student = None
    for t in transcript.get("turns") or []:
        s, u = str(t.get("student") or "").strip(), str(t.get("tutor") or "").strip()
        if s:
            prev_student = s
        if u and prev_student is not None:
            pairs.append(difflib.SequenceMatcher(None, prev_student, u).ratio())
    return round(sum(pairs) / len(pairs), 3) if pairs else None


def m2_requestion(transcript: dict) -> int:
    """M2 已答重问:同问点复读对数(相邻两 tutor 轮 ratio>0.6——possible_no_progress_cycle
    同口径窗口 3 简化为相邻对,M6 判读面读 events 原文)。"""
    ts = _tutor_turns(transcript)
    n = 0
    for i in range(1, len(ts)):
        if difflib.SequenceMatcher(None, ts[i - 1], ts[i]).ratio() > 0.6:
            n += 1
    return n


_CLOSURE_PREFIXES = ("你已经说到了", "我们从头把思路", "这一题(")


def m3_overcollect(transcript: dict) -> int:
    """M3 证据过采集:ready_to_confirm 首现后的非收束/总结轮数。"""
    turns = transcript.get("turns") or []
    first_ready = next((i for i, t in enumerate(turns)
                        if str(t.get("state") or "") == "ready_to_confirm"), None)
    if first_ready is None:
        return 0
    return sum(1 for t in turns[first_ready:]
               if str(t.get("tutor") or "").strip()
               and not str(t.get("tutor") or "").startswith(_CLOSURE_PREFIXES))


def m4_answer_in_question(transcript: dict, answer: str) -> int:
    """M4 answer-in-question:answer 数值出现在 tutor 轮的轮数(教学证据污染;
    排除 bottom-out 明示前缀「这一步我们直接看结果」与 L468 收束句)。"""
    nums = {n.replace(",", "") for n in _NUM.findall(str(answer or ""))} - {""}
    if not nums:
        return 0
    n = 0
    for u in _tutor_turns(transcript):
        if u.startswith(("这一步我们直接看结果", "你已经说到了自己的结论")):
            continue
        in_round = {x.replace(",", "") for x in _NUM.findall(u)}
        if in_round & nums:
            n += 1
    return n


def m5_turns_to_closure(transcript: dict) -> int | None:
    """M5 充分证据到收束轮数:首个含步骤+结论信号的学生轮 → final 轮的距离
    (确定性代理:学生轮含数字或「等于/所以/是」判据词)。"""
    turns = transcript.get("turns") or []
    students = [(i, str(t.get("student") or "").strip()) for i, t in enumerate(turns)]
    students = [(i, s) for i, s in students if s]
    if not students:
        return None
    def _sufficient(s: str) -> bool:
        has_num = bool(_NUM.search(s))
        has_conn = any(w in s for w in ("所以", "等于", "得到", "就是"))
        return has_num and has_conn
    first = next((i for i, s in students if _sufficient(s)), None)
    if first is None:
        return None
    return len(turns) - 1 - first


def m6_interventions(guard_events: list[dict], transcript: dict) -> dict:
    """M6 kernel 介入密度:既有量化器口径(reveal/regen/leak/soften/pc)+
    A 臂 would_* shadow 同口径;轮比=事件数/tutor 轮数。"""
    ts = _tutor_turns(transcript)
    n_turns = len(ts) or 1
    counts = {
        "reveal": sum(1 for e in guard_events if e.get("branch") == "reveal"),
        "regen": sum(1 for e in guard_events if e.get("regenerated")),
        "leak_block": sum(1 for e in guard_events if e.get("guard") == "answer_leak"),
        "soften": sum(1 for e in guard_events if e.get("soften")),
        "pc": sum(1 for e in guard_events if e.get("guard") == "premature_confirm"),
        "arm_b_safety": sum(1 for e in guard_events
                            if e.get("arm_b") == "safety_regen" and e.get("round") == 1),
        "would_block": sum(1 for e in guard_events if e.get("shadow") == "would_block"),
        "would_rewrite": sum(1 for e in guard_events if e.get("shadow") == "would_rewrite"),
        "would_reveal": sum(1 for e in guard_events if e.get("shadow") == "would_reveal"),
    }
    counts["rate"] = round(
        (counts["reveal"] + counts["regen"] + counts["leak_block"] + counts["pc"]
         + counts["arm_b_safety"]
         + counts["would_block"] + counts["would_rewrite"] + counts["would_reveal"]) / n_turns, 3)
    return counts


def real_diff_pairs(case_id: str, a: dict, c: dict) -> dict:
    """M7 材料:真差异对——A vs C 逐轮 tutor 文本不等即差异;输出轮号+双方文本。"""
    at = _tutor_turns(a["transcript"])
    ct = _tutor_turns(c["transcript"])
    diffs = []
    for i in range(max(len(at), len(ct))):
        x = at[i] if i < len(at) else "<无>"
        y = ct[i] if i < len(ct) else "<无>"
        if x != y:
            diffs.append({"round": i, "A": x[:80], "C": y[:80]})
    return {"case_id": case_id, "rounds_differ": len(diffs), "diffs": diffs,
            "pairs_for_review": bool(diffs)}


def main() -> None:
    cases = {}
    for arm in ARMS:
        for f in sorted((OUT / arm).glob("*.json")):
            cases.setdefault(f.stem, {})[arm] = json.loads(f.read_text(encoding="utf-8"))
    # 案面(M4 的 answer 数值)从 fixture 读——与 runner 同源
    import importlib.util
    spec = importlib.util.spec_from_file_location("ablation_run", HERE / "ablation_run.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    fixtures = runner.load_cases()

    summary = {"by_case": {}, "by_arm": {}, "m7_real_diff": []}
    for cid, arms in sorted(cases.items()):
        row = {}
        answer = str((fixtures.get(cid, {}).get("question") or {}).get("answer") or "")
        for arm, rec in arms.items():
            tr, ge = rec["transcript"], rec["guard_events"]
            row[arm] = {
                "m1_grounding": m1_grounding(tr),
                "m2_requestion": m2_requestion(tr),
                "m3_overcollect": m3_overcollect(tr),
                "m4_answer_in_question": m4_answer_in_question(tr, answer),
                "m5_turns_to_closure": m5_turns_to_closure(tr),
                "m6_interventions": m6_interventions(ge, tr),
                "final_state": tr.get("final_state"),
                "judge_total": (rec.get("judge") or {}).get("total"),
                "tutor_turns": len(_tutor_turns(tr)),
            }
        summary["by_case"][cid] = row
        if "A" in arms and "C" in arms:
            summary["m7_real_diff"].append(real_diff_pairs(cid, arms["A"], arms["C"]))
    # 臂级汇总(均值)
    for arm in ARMS:
        rows = [r[arm] for r in summary["by_case"].values() if arm in r]

        def _avg(k, rows=rows):  # B023:默认参绑定当前臂
            vals = [r[k] for r in rows if isinstance(r.get(k), (int, float))]
            return round(sum(vals) / len(vals), 3) if vals else None
        summary["by_arm"][arm] = {
            "m1_grounding": _avg("m1_grounding"),
            "m2_requestion": _avg("m2_requestion"),
            "m3_overcollect": _avg("m3_overcollect"),
            "m4_answer_in_question": _avg("m4_answer_in_question"),
            "m5_turns_to_closure": _avg("m5_turns_to_closure"),
            "intervention_rate_avg": round(
                sum(r["m6_interventions"]["rate"] for r in rows) / len(rows), 3) if rows else None,
            "judge_total": _avg("judge_total"),
            "cases": len(rows),
        }
    (OUT / "ablation-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("ablation-summary.json 落盘;案数:", len(summary["by_case"]))
    for arm in ARMS:
        print(arm, json.dumps(summary["by_arm"][arm], ensure_ascii=False))
    diff_cases = [d["case_id"] for d in summary["m7_real_diff"] if d["pairs_for_review"]]
    print("M7 真差异对案数:", len(diff_cases), diff_cases)


if __name__ == "__main__":
    main()
