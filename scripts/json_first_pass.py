#!/usr/bin/env python3
"""#34 结构化输出合规率(json_schema 一次通过,01 §6)。

从 model_calls-*.jsonl 计算 M2 出口条件:
- 分母: metadata 型调用(role in {tutor, judge}, edu.attempt==1)
- 分子: 分母中 edu.outcome != "schema_violation"
- 输出: 整体率 + 按角色/模型/provider 分解

口径文档: docs/evals/json-first-pass-v1.md

用法:
  uv run python scripts/json_first_pass.py
  uv run python scripts/json_first_pass.py --dir /path/to/facts
  uv run python scripts/json_first_pass.py --since 2026-09-09
  uv run python scripts/json_first_pass.py --strict  # 辅助:仅 outcome=="ok"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_FACTS_DIR = Path(os.environ.get("EDU_FACTS_DIR") or REPO / "facts")

# metadata 角色(全部挂 response_schema,step p1 确认)
SCHEMA_ROLES = frozenset({"tutor", "judge"})

M2_THRESHOLD = 0.98  # 98%


def _read_facts_dir(facts_dir: Path, since: str | None = None) -> list[dict]:
    """读取 facts 目录下所有 model_calls-*.jsonl,返回行列表。"""
    rows: list[dict] = []
    if not facts_dir.is_dir():
        return rows
    for path in sorted(facts_dir.glob("model_calls-*.jsonl")):
        if since is not None:
            # 文件名 model_calls-YYYY-MM-DD.jsonl
            day_str = path.stem.removeprefix("model_calls-")
            try:
                if day_str < since:
                    continue
            except ValueError:
                pass
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[warn] 跳过 {path}: {exc}", file=sys.stderr)
    return rows


def _role_outcome_tables(rows: list[dict]) -> tuple[dict[str, Counter], Counter]:
    """按 role 和 overall 统计 attempt==1 的 outcome 分布。"""
    by_role: dict[str, Counter] = {}
    overall: Counter = Counter()
    for row in rows:
        if row.get("edu.role") not in SCHEMA_ROLES:
            continue
        if row.get("edu.attempt") != 1:
            continue
        role = row["edu.role"]
        outcome = row.get("edu.outcome", "?")
        if role not in by_role:
            by_role[role] = Counter()
        by_role[role][outcome] += 1
        overall[outcome] += 1
    return by_role, overall


def _model_decomposition(rows: list[dict]) -> str:
    """按模型分解:caller 看到的 request.model 维度。"""
    model_stats: dict[str, Counter] = {}
    for row in rows:
        if row.get("edu.role") not in SCHEMA_ROLES:
            continue
        if row.get("edu.attempt") != 1:
            continue
        model = row.get("gen_ai.request.model", "unknown")
        outcome = row.get("edu.outcome", "?")
        if model not in model_stats:
            model_stats[model] = Counter()
        model_stats[model][outcome] += 1

    if not model_stats:
        return ""
    lines = ["\n| model | calls | first_pass | rate |", "|---|---:|---:|---:|"]
    for model in sorted(model_stats):
        c = model_stats[model]
        calls = sum(c.values())
        first_pass = calls - c.get("schema_violation", 0)
        rate = 100.0 * first_pass / calls if calls else 0.0
        lines.append(f"| {model} | {calls} | {first_pass} | {rate:.1f}% |")
    return "\n".join(lines)


def json_first_pass_report(facts_dir: Path, since: str | None = None) -> str:
    """返回 Markdown 报告文本,供 tuning_round.py 挂载。"""
    rows = _read_facts_dir(facts_dir, since)
    by_role, overall = _role_outcome_tables(rows)
    total_calls = sum(overall.values())

    lines: list[str] = ["", "## json_first_pass(01 §6 结构化输出合规率)", ""]

    if not total_calls:
        lines.append("(无 schema 角色 attempt==1 的事实行)")
        return "\n".join(lines)

    # 主定义:未发生 schema_violation
    schema_fails = overall.get("schema_violation", 0)
    first_pass = total_calls - schema_fails
    rate = 100.0 * first_pass / total_calls if total_calls else 0.0
    pass_icon = "✅" if rate / 100 >= M2_THRESHOLD else "❌"

    lines.append(f"M2 门 {M2_THRESHOLD*100:.0f}%: {pass_icon} 当前 **{rate:.1f}%** "
                 f"({first_pass}/{total_calls})")

    # 按角色分解
    lines.append("\n| role | calls | first_pass | rate | breakdown |")
    lines.append("|---|---:|---:|---:|---|")
    sorted_roles = sorted(by_role)
    for role in sorted_roles:
        c = by_role[role]
        calls = sum(c.values())
        role_first_pass = calls - c.get("schema_violation", 0)
        role_rate = 100.0 * role_first_pass / calls if calls else 0.0
        breakdown_parts = []
        for outcome in sorted(c):
            if c[outcome] > 0:
                breakdown_parts.append(f"{outcome}={c[outcome]}")
        lines.append(f"| {role} | {calls} | {role_first_pass} | {role_rate:.1f}% "
                     f"| {', '.join(breakdown_parts)} |")
    lines.append(f"| **合计** | **{total_calls}** | **{first_pass}** | **{rate:.1f}%** |"
                 f" |")

    # 非 schema 首次失败明细(透明度)
    non_schema_fails = [(r["edu.outcome"], r["edu.role"], r.get("edu.session_id", "?"))
                        for r in rows
                        if r.get("edu.role") in SCHEMA_ROLES
                        and r.get("edu.attempt") == 1
                        and r.get("edu.outcome") not in ("ok", "schema_violation")]
    if non_schema_fails:
        lines.append("\n> **注意**:按定义计入通过(未发生 schema_violation 事件)的首次失败:")
        seen: set[str] = set()
        for outcome, role, sess in non_schema_fails:
            key = f"{outcome}:{sess}"
            if key not in seen:
                lines.append(f"> · {outcome} (role={role}, session={sess})")
                seen.add(key)

    # 按模型分解
    model_section = _model_decomposition(rows)
    if model_section:
        lines.append(model_section)

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=DEFAULT_FACTS_DIR,
                        help="facts 目录(默认 facts/)")
    parser.add_argument("--since", type=str, default=None,
                        help="起始日期 YYYY-MM-DD(可选,按文件名过滤)")
    parser.add_argument("--strict", action="store_true",
                        help="辅助:严格一次通过(仅 outcome==ok,含非 schema 失败)")
    args = parser.parse_args()

    rows = _read_facts_dir(args.dir, args.since)
    by_role, overall = _role_outcome_tables(rows)
    total_calls = sum(overall.values())

    if total_calls == 0:
        print("json_first_pass: 无 schema 角色 attempt==1 的事实行")
        if rows:
            print(f"  (读取 {len(rows)} 行但未匹配 role in {SCHEMA_ROLES}, attempt==1)")
        return 1

    # 主口径
    schema_fails = overall.get("schema_violation", 0)
    first_pass = total_calls - schema_fails
    rate = 100.0 * first_pass / total_calls
    flag = "达标" if rate / 100 >= M2_THRESHOLD else "未达标"
    print(f"json_first_pass: {first_pass}/{total_calls} = {rate:.1f}% [{flag}]")
    print(f"  M2 门 {M2_THRESHOLD*100:.0f}%: "
          f"{'✅' if rate/100 >= M2_THRESHOLD else '❌'}")
    for role in sorted(by_role):
        c = by_role[role]
        rc = sum(c.values())
        rp = rc - c.get("schema_violation", 0)
        rr = 100.0 * rp / rc if rc else 0.0
        print(f"  {role}: {rp}/{rc} = {rr:.1f}%")
        if c.get("schema_violation", 0) > 0:
            print(f"    schema_violation: {c['schema_violation']}")

    # 严格口径(辅助)
    if args.strict:
        strict_pass = overall.get("ok", 0)
        strict_rate = 100.0 * strict_pass / total_calls
        print(f"\n  --strict: {strict_pass}/{total_calls} = {strict_rate:.1f}% "
              f"(仅 outcome==ok)")

    # 打印 Markdown 报告
    print("\n---\n")
    print(json_first_pass_report(args.dir, args.since))

    return 0


if __name__ == "__main__":
    sys.exit(main())