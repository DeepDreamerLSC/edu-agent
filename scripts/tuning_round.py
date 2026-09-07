#!/usr/bin/env python3
"""M2 调优循环一轮(00 §8.4 阶段 3):收集(内核)→ 评分(judge)→ 对照 Run1 基线。

用法:uv run python scripts/tuning_round.py [--out var/tuning/round-N]
11 场景 = 基线同款三数据集;judge 单遍 primary(调优轮口径;双评留正式轮);
对照值 = 基线报告 §3 Run1 固定值(docs/evals/baseline-run1-run2.md,#58 落盘快照),
容差 12 分制 1 分,分差 ≤1 标记 borderline(下轮复跑取均值)。数字全部落盘
不手拼;判停/状态读 transcript 内部字段,不从学生文本反推。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from edu_agent.evals import EvalRunner, KernelSubject, RunnerConfig, judge_transcript, load_results
from edu_agent.gateway import Gateway, load_registry

REPO = Path(__file__).resolve().parents[1]
DATASETS = REPO / "edu_agent" / "evals" / "datasets"

# Run1 固定基线(基线报告 §3,#58;case_id → 总分)
RUN1_BASELINE = {
    "small_lecturer_dialogue_scenarios_equation_complete_reasoning": 8,
    "small_lecturer_dialogue_stability_20_stability_chicken_rabbit": 6,
    "small_lecturer_dialogue_stability_20_stability_equation_subtract": 7,
    "small_lecturer_dialogue_stability_20_stability_fraction_addition": 3,
    "small_lecturer_dialogue_stability_20_stability_triangle_area": 3,
    "small_lecturer_dialogue_stability_20_stability_word_problem": 11,
    "small_lecturer_teaching_context_shadow_pilot_20_stability_chicken_rabbit": 5,
    "small_lecturer_teaching_context_shadow_pilot_20_stability_equation_subtract": 4,
    "small_lecturer_teaching_context_shadow_pilot_20_stability_fraction_addition": 3,
    "small_lecturer_teaching_context_shadow_pilot_20_stability_triangle_area": 2,
    "small_lecturer_teaching_context_shadow_pilot_20_stability_word_problem": 11,
}
TOLERANCE = 1  # 看板 #34 已批口径:12 分制 1 分


def build_cases() -> list[dict]:
    """11 场景:dialogue_scenarios 1 + stability_20 5 + teaching_context 5(基线同款)。"""
    bank = {r["question_id"]: r for r in json.loads(
        (DATASETS / "release_acceptance_seed_question_bank.json").read_text(encoding="utf-8"))["records"]}
    stability_ids = ["chicken_rabbit", "equation_subtract", "fraction_addition",
                     "triangle_area", "word_problem"]
    cases = []

    def scenario_row(dataset_name: str, wanted_id: str) -> dict:
        rows = json.loads((DATASETS / f"{dataset_name}.json").read_text(encoding="utf-8"))["scenarios"]
        return next(r for r in rows if r["id"] == wanted_id)

    by_stem = {r["stem"]: r for r in bank.values()}

    def bank_record(key: str, question: str) -> dict:
        return bank.get(key) or by_stem.get(question) or {}  # id 优先,题干文本兜底(同题不同 id)

    for dataset, sid in [("small_lecturer_dialogue_scenarios", "equation_complete_reasoning")] + \
                        [("small_lecturer_dialogue_stability_20", f"stability_{s}") for s in stability_ids] + \
                        [("small_lecturer_teaching_context_shadow_pilot_20", f"stability_{s}") for s in stability_ids]:
        row = scenario_row(dataset, sid)
        bank_key = sid.removeprefix("stability_") if sid.startswith("stability_") else sid
        record = bank_record(bank_key, row["question"])
        cases.append({
            "id": f"{dataset}_{sid}",
            "question": row["question"],
            "student_turns": row["student_turns"],
            "grade": record.get("grade", ""),
            "reference_answer": record.get("answer", ""),
        })
    return cases


def to_judge_cases(rows: list[dict]) -> list[dict]:
    """run 结果 → judge 输入(judge_score.py 同款形态;transcript 的 turns 展开)。"""
    judge_cases = []
    for row in rows:
        if row["status"] != "ok":
            continue
        t = row["transcript"]
        messages = []
        for turn in t["turns"]:
            if turn["student"]:
                messages.append({"role": "user", "content": turn["student"]})
            messages.append({"role": "assistant", "content": turn["tutor"]})
        if t.get("summary"):
            messages.append({"role": "assistant", "content": t["summary"]})
        judge_cases.append({
            "id": row["case_id"],
            "question": next(c["question"] for c in CASES if c["id"] == row["case_id"]),
            "grade": t.get("learner", {}).get("grade", ""),
            "reference_answer": next(c["reference_answer"] for c in CASES if c["id"] == row["case_id"]),
            "messages": messages,
        })
    return judge_cases


CASES = build_cases()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="输出目录,如 var/tuning/round-1")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    gateway = Gateway(load_registry(REPO / "configs" / "models.yaml"))
    try:
        print(f"收集:11 场景,KernelSubject(9B tutor)")
        run_dir = out / "collect"
        cases_file = out / "cases.jsonl"
        cases_file.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in CASES) + "\n",
                              encoding="utf-8")
        EvalRunner(KernelSubject(gateway), RunnerConfig(concurrency=2), run_dir).run(
            cases_file, CASES)
        rows = load_results(_latest_run(run_dir))
        judge_input = to_judge_cases(rows)
        (out / "judge-cases.jsonl").write_text(
            "\n".join(json.dumps(c, ensure_ascii=False) for c in judge_input) + "\n", encoding="utf-8")
        print(f"评分:{len(judge_input)} case(judge 27B,单遍 primary)")
        scores = {}
        for case in judge_input:
            verdict = judge_transcript(gateway, case)
            scores[case["id"]] = verdict
            print(f"  {case['id'][:58]:60s} total={verdict['total']:2d} {verdict['verdict']}")
    finally:
        gateway.close()

    (out / "judge-scores.json").write_text(json.dumps(scores, ensure_ascii=False, indent=1), encoding="utf-8")
    report = ["# 调优轮对照(vs Run1 固定基线,容差 1 分)", "",
              "| 场景 | Run1 | 本轮 | 差 | 判定 |", "|---|---:|---:|---:|---|"]
    deltas = []
    for case_id, base in RUN1_BASELINE.items():
        got = scores.get(case_id, {}).get("total")
        if got is None:
            report.append(f"| {case_id} | {base} | 失败 | - | FAIL |")
            continue
        delta = got - base
        deltas.append(delta)
        verdict = "达标" if delta >= 0 else ("borderline(复跑)" if delta >= -TOLERANCE else "低于基线")
        report.append(f"| {case_id} | {base} | {got} | {delta:+d} | {verdict} |")
    report += ["", f"逐维均分:见 judge-scores.json;均值差:{sum(deltas) / len(deltas):+.2f}"]
    text = "\n".join(report) + "\n"
    (out / "comparison.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


def _latest_run(root: Path) -> Path:
    return sorted(root.glob("*-*Z-*"))[-1] if sorted(root.glob("*-*Z-*")) else root


if __name__ == "__main__":
    sys.exit(main())
