#!/usr/bin/env python3
"""
#256 结构性变体探针驱动脚本(重跑信封:硬顶 104;首跑 97 calls 超顶 80 已按停)

结构性变体 ×1,同批配对,一轮,无编辑器(变体手写);harness 复用 #303 修复版
(pair evaluate + facts 记账 + 全转录空转扫描)。

判读(冻结,review-303-rerun P1-1 修正):空转 = 无效跑(judge 敏感度不可测),
非红灯;Δ≈0 才是红灯;稳定非零 → GO。
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

# 预算硬顶(用户批重跑信封,2026-09-16;review-303-rerun P1-2 入库)
HARD_CAP_CALLS = 104


def _artifact_path(name: str) -> Path:
    """Mimosa 安全约束:工件路径规范化并收容在探针目录内,禁止穿越。"""
    root = Path(__file__).resolve().parent
    target = (root / name).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"工件路径越界:{target}")
    return target


def main() -> None:
    output_dir = Path(__file__).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    registry = load_registry(Path("configs/models.yaml"))
    gateway = Gateway(registry)

    scenarios_path = Path("edu_agent/evals/datasets/small_lecturer_image_teaching_v1.json")
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

    # 配对
    paired_cases = _build_paired_cases(
        parent_scores, variant_scores, parent_fqs, variant_fqs,
        PARENT_TEMPLATE, STRUCTURAL_VARIANT,
    )

    # 空转检查(全转录口径:_build_paired_cases 内逐案扫描,模板未注入任意 tutor 轮 = 空转)
    idle_count = sum(1 for c in paired_cases if c.get("idle"))
    idle_detected = idle_count > 0

    # verdict(冻结协议):空转 → 无效跑(override,先于 Δ 分支;
    # 转录全同 + judge temp=0 确定性 → Δ=0 对 judge 敏感度零信息量)
    deltas = [c["delta"] for c in paired_cases if "error" not in c]
    verdict = _compute_paired_verdict(deltas, idle_detected=idle_detected)
    print(f"Verdict: {verdict}")

    # 预算统计
    total_calls = parent_stats["calls"] + variant_stats["calls"]
    over_budget = total_calls > HARD_CAP_CALLS

    # round-00.json (先落工件,再检查预算)
    round_report = {
        "parent_template": PARENT_TEMPLATE,
        "variant_template": STRUCTURAL_VARIANT,
        "parent_stats": parent_stats,
        "variant_stats": variant_stats,
        "paired_cases": paired_cases,
    }
    with _artifact_path("round-00.json").open("w", encoding="utf-8") as f:
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
        "over_budget": over_budget,
        "idle_detected": idle_detected,
    }
    with _artifact_path("paired-report.json").open("w", encoding="utf-8") as f:
        json.dump(paired_report, f, ensure_ascii=False, indent=2)

    print(f"工件写入: {output_dir}")
    print(f"  round-00.json")
    print(f"  paired-report.json")
    print(f"Verdict: {verdict}, Mean Δ: {mean_delta:.2f}, Calls: {total_calls}")

    # 预算检查 (工件已落,再退出)
    print(f"总调用: {total_calls} (硬顶 {HARD_CAP_CALLS})")
    if over_budget:
        print(f"ERROR: 超预算 {total_calls} > {HARD_CAP_CALLS},停止")
        sys.exit(1)

    if idle_detected:
        print(f"ERROR: 检测到 {idle_count} 案空转(变体模板未注入全转录)→ 无效跑,"
              f"judge 敏感度不可测,停,报 PM")
        sys.exit(1)


if __name__ == "__main__":
    main()
