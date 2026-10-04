#!/usr/bin/env python3
"""题图教学评测集 v1(#130 WP5)一轮:收集(KernelSubject 透图)→ judge → 报告。

默认 execution owner = Inspect(#521 I6-C C1-A):收集相 case 级调度/并发/sample
retry 归 inspect-ai(execution-only 轮,复用 I5 inspect_adapter);judge 单遍
primary 与报告语义留本脚本(判分语义不迁);checkpoint 仍是 Canonical durable
evidence + 被动幂等守卫,collect 工件面与旧执行同形。过渡期显式 `--legacy-runner`
走 EvalRunner 旧执行面(禁自动 fallback,manifest 明示 execution_owner)。

用法:
  uv run python scripts/image_teaching_round.py \
      --dataset edu_agent/evals/datasets/small_lecturer_image_teaching_v1.json \
      --out var/image-teaching/baseline-v1 [--legacy-runner]

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
    InspectRoundRequest,
    KernelSubject,
    RunnerConfig,
    judge_transcript,
    load_results,
    load_scenarios,
    run_identity,
    run_inspect_round,
    to_cases,
)
from edu_agent.gateway import Gateway, load_registry

REPO = Path(__file__).resolve().parents[1]
_INSPECT_TASK = "edu_image_teaching_round"  # Inspect Task 名即 provenance,不冒名 corpus 轮


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
    parser.add_argument("--legacy-runner", dest="legacy_runner", action="store_true",
                        help="#521 I6-C 过渡回退:显式用 EvalRunner 旧执行面(默认 = Inspect;"
                             "禁自动 fallback/禁双 owner 同 run,manifest 明示 execution_owner)")
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
        collect_root = out / "collect"
        # 跑批身份(corpus_round.run_identity 同源:git/dirty/diff/prompts/models)+
        # owner 明示(manifest 落档;跨 owner 混续同一 run 在 adapter preflight 被拒)
        identity = {**run_identity(),
                    "execution_owner": "evalrunner_legacy" if args.legacy_runner else "inspect"}
        subject = KernelSubject(gateway)
        if args.legacy_runner:
            # 过渡回退(#521 I6-C C1-A G6):显式 --legacy-runner 才走 EvalRunner 旧执行面
            run_dir = EvalRunner(subject, RunnerConfig(concurrency=2), collect_root).run(
                cases_file, cases, identity=identity)
        else:
            # 默认 execution owner = Inspect(#521 I6-C C1-A):调度/并发/sample retry 归
            # inspect-ai(execution-only 轮,scenarios=None);判分语义留本脚本
            # (to_judge_cases → judge_transcript 单遍 primary 原路径不动);checkpoint =
            # Canonical durable evidence + 被动幂等守卫,collect 工件面与 legacy 同形。
            run_dir, _checks, _scores = run_inspect_round(InspectRoundRequest(
                subject=subject, gateway=gateway, cases_file=cases_file, scenarios=None,
                identity=identity, concurrency=2, judge_enabled=False,
                collect_root=collect_root, resume_dir=None, task_name=_INSPECT_TASK))
        rows = load_results(run_dir)
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
