#!/usr/bin/env python3
"""题图教学评测集 v1(#130 WP5)一轮:收集(KernelSubject 透图)→ judge → 报告。

用法:
  uv run python scripts/image_teaching_round.py \
      --dataset edu_agent/evals/datasets/small_lecturer_image_teaching_v1.json \
      --out var/image-teaching/baseline-v1

数据集先过 schema 门(必填/枚举/sha256 与图字节对账/图路径存在),任一错误即退出 1
——不让坏数据进模型层变噪声。收集走 KernelSubject(question 传 v1 dict,内核透图),
judge 用 gateway 的 judge 角色(mlx 27B,单遍 primary,同 11 场景口径)。

效率指标不在本脚本采(隧道只许冒烟;官方效率数字只在 Mac 本地/runner 路径采)。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from edu_agent.evals import (
    DIMENSIONS,
    EvalRunner,
    KernelSubject,
    RunnerConfig,
    judge_transcript,
    load_results,
    load_scenarios,
    to_cases,
)
from edu_agent.gateway import Gateway, load_registry

REPO = Path(__file__).resolve().parents[1]


def _latest_run(root: Path) -> Path:
    existing = sorted(root.glob("*-*Z-*"))
    return existing[-1] if existing else root


def to_judge_cases(rows: list[dict], cases: list[dict]) -> list[dict]:
    """run 结果 → judge 输入:题目传转录文本(judge 是纯文本 27B,不看图)。"""
    by_id = {case["id"]: case for case in cases}
    judge_cases = []
    for row in rows:
        if row["status"] != "ok":
            continue
        transcript = row["transcript"]
        messages = []
        for turn in transcript["turns"]:
            if turn["student"]:
                messages.append({"role": "user", "content": turn["student"]})
            messages.append({"role": "assistant", "content": turn["tutor"]})
        if transcript.get("summary"):
            messages.append({"role": "assistant", "content": transcript["summary"]})
        case = by_id[row["case_id"]]
        judge_cases.append({
            "id": row["case_id"],
            "question": case["question"]["text"],
            "grade": case["grade"],
            "reference_answer": case["reference_answer"],
            "messages": messages,
        })
    return judge_cases


def render_report(cases: list[dict], scores: dict) -> str:
    header = "| 题 | " + " | ".join(DIMENSIONS) + " | 总分 | 判定 |"
    divider = "|---|" + "---:|" * (len(DIMENSIONS) + 2)
    lines = ["# 题图教学评测集 v1 跑批(#130)", "", header, divider]
    for case in cases:
        verdict = scores.get(case["id"])
        if verdict is None:
            lines.append(f"| {case['id']} | " + " | ".join(["失败"] * len(DIMENSIONS))
                         + " | FAIL | FAIL |")
            continue
        dims = " | ".join(str(verdict["scores"][dim]) for dim in DIMENSIONS)
        lines.append(f"| {case['id']} | {dims} | {verdict['total']} | {verdict['verdict']} |")
    passed = sum(1 for case in cases if scores.get(case["id"], {}).get("verdict") == "pass")
    lines += ["", f"pass {passed}/{len(cases)};逐维依据见 judge-scores.json(含 judge 模型披露)。"]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, help="v1 数据集 JSON 路径")
    parser.add_argument("--out", required=True, help="输出目录,如 var/image-teaching/baseline-v1")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    scenarios = load_scenarios(args.dataset)  # schema 门:不过即抛,退出 1
    cases = to_cases(scenarios)
    cases_file = out / "cases.jsonl"
    cases_file.write_text(
        "\n".join(json.dumps(case, ensure_ascii=False) for case in cases) + "\n", encoding="utf-8")
    print(f"数据集:{len(cases)} 题(schema 门全过)")

    registry = load_registry(REPO / "configs" / "models.yaml")
    gateway = Gateway(registry)
    scores: dict = {}
    try:
        run_dir = out / "collect"
        EvalRunner(KernelSubject(gateway), RunnerConfig(concurrency=2), run_dir).run(
            cases_file, cases)
        rows = load_results(_latest_run(run_dir))
        judge_input = to_judge_cases(rows, cases)
        (out / "judge-cases.jsonl").write_text(
            "\n".join(json.dumps(case, ensure_ascii=False) for case in judge_input) + "\n",
            encoding="utf-8")
        print(f"评分:{len(judge_input)} case(judge {registry.roles['judge'].primary},单遍 primary)")
        for case in judge_input:
            verdict = judge_transcript(gateway, case)
            scores[case["id"]] = verdict
            print(f"  {case['id'][:58]:60s} total={verdict['total']:2d} {verdict['verdict']}")
    finally:
        gateway.close()

    (out / "judge-scores.json").write_text(
        json.dumps(scores, ensure_ascii=False, indent=1), encoding="utf-8")
    report = render_report(cases, scores)
    (out / "comparison.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
