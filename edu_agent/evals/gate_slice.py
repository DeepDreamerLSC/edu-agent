"""⑦门候选切片跑批器(#256 阶段 3):candidate (elicit, support) × 11 案 × 2 跑。

候选双旋钮经 ElicitSubject seam 注入(seam 机制与 GEPA 长跑同一件,非新缝合),
11 案切片(teacher-gate-slice,输入逐字冻结)重放出新转录,判卷走冻结指纹口径
(judge_transcript,role=judge),产出 lane_m 输入({case_id: judge payload} ×2)。

案源三路(可运行形态,不动冻结件):
- corpus-round-v2 池内的 9 案:直接用池 case(steps 分支剧本);
- 池外 2 案(shadow pilot __r1 重跑槽位案、challenge 构造案):从 slice-cases
  冻结 messages 抽学生侧 → 线性 student_turns 剧本(__rN = 独立重跑槽位,
  finish_evidence_eval.py 先例;候选重跑的学生剧本 = 基线转录的学生侧)。
judge 输入 = slice-cases 冻结行,仅 messages 换成候选新转录——题面/参考答案/
判据逐字不动。
"""

from __future__ import annotations

import json
from pathlib import Path

from edu_agent.gateway import Gateway

from .corpus_round import transcript_messages
from .gepa import DEFAULT_SUPPORT_HINT, ElicitSubject
from .judge import judge_transcript
from .lane_m import compare_lane_m

SLICE_DIR = Path(__file__).parent / "artifacts" / "teacher-gate-slice"
POOL_PATH = Path(__file__).parent / "artifacts" / "corpus-round-v2" / "cases.jsonl"


def load_slice_rows() -> dict[str, dict]:
    """slice-cases.jsonl 冻结判卷行,按 case_id 索引。"""
    rows = [json.loads(line) for line in
            (SLICE_DIR / "slice-cases.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    return {row["id"]: row for row in rows}


def load_runnable_cases() -> list[dict]:
    """11 案可运行形态:池内用 steps 剧本,池外抽学生侧线性剧本。"""
    slice_rows = load_slice_rows()
    pool = {json.loads(line)["id"]: json.loads(line) for line in
            POOL_PATH.read_text(encoding="utf-8").splitlines() if line.strip()}
    cases = []
    for case_id, row in slice_rows.items():
        if case_id in pool:
            cases.append(pool[case_id])
        else:
            cases.append({
                "id": case_id,
                "question": row["question"],
                "grade": row.get("grade", ""),
                "student_turns": [m["content"] for m in row["messages"]
                                  if m.get("role") == "user"],
            })
    return cases


def run_candidate_slice(elicit: str, support: str, gateway: Gateway,
                        judge_role: str = "judge") -> tuple[dict, dict]:
    """候选双旋钮 × 11 案 × 2 独立跑 → (run1, run2) 判分行({case_id: payload})。"""
    cases = load_runnable_cases()
    slice_rows = load_slice_rows()
    runs: list[dict] = []
    for _ in range(2):
        run = {}
        for case in cases:
            subject = ElicitSubject(elicit, gateway, support_hint=support)
            result = subject.run_case(case)
            judge_case = dict(slice_rows[case["id"]])
            judge_case["messages"] = transcript_messages(result)
            run[case["id"]] = judge_transcript(gateway, judge_case, role=judge_role)
        runs.append(run)
    return runs[0], runs[1]


def gate_from_runs(baseline_rows: list[dict], run1: dict, run2: dict):
    """跑批直比(lane_m 判定照协议原文)。"""
    return compare_lane_m(baseline_rows, run1, run2)


def main() -> None:
    """CLI:checkpoint(best 候选)→ 11 案 ×2 → lane-m-result。

    用法:PYTHONPATH=. python -m edu_agent.evals.gate_slice <out_dir> --checkpoint <gepa checkpoint.json>
    """
    import argparse

    from edu_agent.gateway import Gateway, load_registry

    parser = argparse.ArgumentParser(description="⑦门候选切片跑批")
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--checkpoint", type=Path, required=True,
                        help="GEPA checkpoint(best.template + best.support_hint)")
    parser.add_argument("--judge-role", default="judge", choices=["judge", "judge_independent"])
    args = parser.parse_args()

    saved = json.loads(args.checkpoint.read_text(encoding="utf-8"))
    elicit = saved["best"]["template"]
    support = saved["best"].get("support_hint") or DEFAULT_SUPPORT_HINT

    gateway = Gateway(load_registry(Path("configs/models.yaml")))
    try:
        run1, run2 = run_candidate_slice(elicit, support, gateway, args.judge_role)
    finally:
        gateway.close()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "run1.json").write_text(json.dumps(run1, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    (args.out_dir / "run2.json").write_text(json.dumps(run2, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    baseline_rows = [json.loads(line) for line in
                     (SLICE_DIR / "slice-baseline.jsonl").read_text(encoding="utf-8").splitlines()
                     if line.strip()]
    result = gate_from_runs(baseline_rows, run1, run2)
    (args.out_dir / "lane-m-result.json").write_text(
        json.dumps({"gate": result.gate, "rows": result.rows}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"Lane M gate: {result.gate}")
