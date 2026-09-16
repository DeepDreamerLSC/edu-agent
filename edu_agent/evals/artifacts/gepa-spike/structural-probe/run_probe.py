#!/usr/bin/env python3
"""
#256 结构性变体探针驱动脚本

用户批 A 方案:结构性变体 ×1,同批配对,~68 真 calls(硬顶 80)
无编辑器(变体手写);harness 复用 #303 修复版(pair evaluate + facts 记账)。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from edu_agent.evals.gepa import (
    _build_paired_cases,
    _compute_paired_verdict,
    evaluate_batch_paired,
)
from edu_agent.evals.image_teaching import load_scenarios
from edu_agent.gateway import Gateway, load_registry

# 模板定义(PM 起草,逐字使用,不自改)
PARENT_TEMPLATE = "我们从头把思路串一遍——先说说你第一步算了什么、为什么这样算。"
STRUCTURAL_VARIANT = (
    "这道题里有一个最关键的步骤——别的步骤错了都还能补救,就它错了整道题就歪了。"
    "你觉得是哪一步?为什么是它?如果这一步换一种做法,答案会怎么变?"
)

# 预算硬顶
HARD_CAP_CALLS = 80


def main() -> None:
    output_dir = Path(__file__).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    registry = load_registry(Path("configs/models.yaml"))
    gateway = Gateway(registry)

    scenarios_path = Path("edu_agent/evals/datasets/image_teaching_v1.json")
    cases = load_scenarios(scenarios_path)
    print(f"加载 {len(cases)} cases,准备跑 parent + variant 配对...")

    # parent
    print("跑 parent (original elicit)...")
    parent_scores, parent_fqs, parent_stats = evaluate_batch_paired(
        cases, PARENT_TEMPLATE, gateway)
    print(f"  parent stats: {parent_stats}")

    # variant
    print("跑 variant (structural variant)...")
    variant_scores, variant_fqs, variant_stats = evaluate_batch_paired(
        cases, STRUCTURAL_VARIANT, gateway)
    print(f"  variant stats: {variant_stats}")

    # 预算检查
    total_calls = parent_stats["calls"] + variant_stats["calls"]
    print(f"总调用: {total_calls} (硬顶 {HARD_CAP_CALLS})")
    if total_calls > HARD_CAP_CALLS:
        print(f"ERROR: 超预算 {total_calls} > {HARD_CAP_CALLS},停止")
        sys.exit(1)

    # 配对
    paired_cases = _build_paired_cases(
        parent_scores, variant_scores, parent_fqs, variant_fqs,
        PARENT_TEMPLATE, STRUCTURAL_VARIANT,
    )

    # 空转检查
    idle_count = sum(1 for c in paired_cases if c.get("idle"))
    if idle_count > 0:
        print(f"ERROR: 检测到 {idle_count} 案空转(变体首问 = parent 逐字),无效跑")
        sys.exit(1)

    # verdict
    deltas = [c["delta"] for c in paired_cases if "error" not in c]
    verdict = _compute_paired_verdict(deltas)
    print(f"Verdict: {verdict}")

    # round-00.json
    round_report = {
        "parent_template": PARENT_TEMPLATE,
        "variant_template": STRUCTURAL_VARIANT,
        "parent_stats": parent_stats,
        "variant_stats": variant_stats,
        "paired_cases": paired_cases,
    }
    with open(output_dir / "round-00.json", "w", encoding="utf-8") as f:
        json.dump(round_report, f, ensure_ascii=False, indent=2)

    # paired-report.json
    mean_delta = sum(deltas) / len(deltas) if deltas else 0.0
    paired_report = {
        "parent_template": PARENT_TEMPLATE,
        "variant_template": STRUCTURAL_VARIANT,
        "total_paired_cases": len(paired_cases),
        "deltas": deltas,
        "mean_delta": mean_delta,
        "verdict": verdict,
        "real_calls": total_calls,
        "tokens_in": parent_stats.get("tokens_in", 0) + variant_stats.get("tokens_in", 0),
        "tokens_out": parent_stats.get("tokens_out", 0) + variant_stats.get("tokens_out", 0),
        "over_budget": total_calls > HARD_CAP_CALLS,
    }
    with open(output_dir / "paired-report.json", "w", encoding="utf-8") as f:
        json.dump(paired_report, f, ensure_ascii=False, indent=2)

    print(f"工件写入: {output_dir}")
    print(f"  round-00.json")
    print(f"  paired-report.json")
    print(f"Verdict: {verdict}, Mean Δ: {mean_delta:.2f}, Calls: {total_calls}")


if __name__ == "__main__":
    main()
