#!/usr/bin/env python3
"""#34 结构化输出合规率(json_schema 一次通过,01 §6)。

从 model_calls-*.jsonl 计算 M2 出口条件。口径(2026-09-10 评审修订,#34):
- 合规分母 = 产出了模型响应的行(outcome ∈ {ok, schema_violation, truncated, content_filtered});
  模型没产出响应的基础设施失败(timeout_*/rate_limited/upstream_*/connection)移出分母,
  单列 availability(那是 01 §6 "成功率/首次成功率"的职责,不混入合规率)。
- 分子 = outcome == "ok"(产出即合规);truncated/content_filtered/schema_violation 都算不合规。
- 角色分母:仅 schema 角色(tutor/judge,step p1 确认全部挂 response_schema)。

口径文档: docs/evals/json-first-pass-v1.md

用法:
  uv run python scripts/json_first_pass.py
  uv run python scripts/json_first_pass.py --dir /path/to/facts
  uv run python scripts/json_first_pass.py --since 2026-09-09
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_FACTS_DIR = Path(os.environ.get("EDU_FACTS_DIR") or REPO / "facts")

# schema 角色(全部挂 response_schema,step p1 确认)
SCHEMA_ROLES = frozenset({"tutor", "judge"})

# 产出模型响应的 outcome(在合规分母内)
RESPONDED_OUTCOMES = frozenset({"ok", "schema_violation", "truncated", "content_filtered"})
# 合规 = 一次产出即合规 JSON
COMPLIANT_OUTCOME = "ok"

M2_THRESHOLD = 0.98  # 98%


def _read_facts_dir(facts_dir: Path, since: str | None = None) -> list[dict]:
    """读取 facts 目录下所有 model_calls-*.jsonl,返回行列表。"""
    rows: list[dict] = []
    if not facts_dir.is_dir():
        return rows
    for path in sorted(facts_dir.glob("model_calls-*.jsonl")):
        if since is not None and path.stem.removeprefix("model_calls-") < since:
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[warn] 跳过 {path}: {exc}", file=sys.stderr)
    return rows


def _schema_rows(rows: list[dict]) -> list[dict]:
    """schema 角色 attempt==1 的行(每个调用恰好一行)。"""
    return [r for r in rows
            if r.get("edu.role") in SCHEMA_ROLES and r.get("edu.attempt") == 1]


def _outcome_counters(rows: list[dict]) -> tuple[dict[str, Counter], Counter]:
    """按 role 与 overall 统计 outcome 分布(schema 角色 attempt==1)。"""
    by_role: dict[str, Counter] = {}
    overall: Counter = Counter()
    for row in _schema_rows(rows):
        role = row["edu.role"]
        outcome = row.get("edu.outcome", "?")
        if role not in by_role:
            by_role[role] = Counter()
        by_role[role][outcome] += 1
        overall[outcome] += 1
    return by_role, overall


def _availability_note(overall: Counter) -> str:
    """基础设施失败(未产出响应)单列;那是 01 §6 成功率的职责。"""
    infra = {o: n for o, n in overall.items() if o not in RESPONDED_OUTCOMES}
    total = sum(overall.values())
    if not infra:
        return ""
    parts = ", ".join(f"{o}={n}" for o, n in sorted(infra.items()))
    return (f"\n> **availability**(01 §6 成功率职责,不计入合规分母): "
            f"基础设施失败 {sum(infra.values())}/{total} 行 —— {parts}")


def _model_decomposition(rows: list[dict]) -> str:
    """按模型分解:responded 与 ok 计数。"""
    model_stats: dict[str, Counter] = {}
    for row in _schema_rows(rows):
        model = row.get("gen_ai.request.model", "unknown")
        outcome = row.get("edu.outcome", "?")
        if model not in model_stats:
            model_stats[model] = Counter()
        model_stats[model][outcome] += 1

    if not model_stats:
        return ""
    lines = ["\n| model | responded | ok | rate |", "|---|---:|---:|---:|"]
    for model in sorted(model_stats):
        c = model_stats[model]
        responded = sum(n for o, n in c.items() if o in RESPONDED_OUTCOMES)
        ok = c.get(COMPLIANT_OUTCOME, 0)
        rate = 100.0 * ok / responded if responded else 0.0
        lines.append(f"| {model} | {responded} | {ok} | {rate:.1f}% |")
    return "\n".join(lines)


def json_first_pass_report(facts_dir: Path, since: str | None = None) -> str:
    """返回 Markdown 报告文本,供 tuning_round.py 挂载。"""
    rows = _read_facts_dir(facts_dir, since)
    by_role, overall = _outcome_counters(rows)
    responded_total = sum(n for o, n in overall.items() if o in RESPONDED_OUTCOMES)

    lines: list[str] = ["", "## json_first_pass(01 §6 结构化输出合规率)", ""]

    if responded_total == 0:
        lines.append("(无产出模型响应的 schema 调用行)")
        return "\n".join(lines)

    ok_total = overall.get(COMPLIANT_OUTCOME, 0)
    rate = 100.0 * ok_total / responded_total if responded_total else 0.0
    pass_icon = "✅" if rate / 100 >= M2_THRESHOLD else "❌"

    lines.append(f"M2 门 {M2_THRESHOLD*100:.0f}%: {pass_icon} 当前 **{rate:.1f}%** "
                 f"({ok_total}/{responded_total} 产出了结果)")

    # 按角色分解
    lines.append("\n| role | responded | ok | rate | breakdown |")
    lines.append("|---|---:|---:|---:|---|")
    for role in sorted(by_role):
        c = by_role[role]
        responded = sum(n for o, n in c.items() if o in RESPONDED_OUTCOMES)
        ok = c.get(COMPLIANT_OUTCOME, 0)
        role_rate = 100.0 * ok / responded if responded else 0.0
        breakdown_parts = [f"{o}={c[o]}" for o in sorted(c) if c[o] > 0]
        lines.append(f"| {role} | {responded} | {ok} | {role_rate:.1f}% "
                     f"| {', '.join(breakdown_parts)} |")
    lines.append(f"| **合计** | **{responded_total}** | **{ok_total}** | **{rate:.1f}%** | |")

    # 不合规明细(透明度):schema_violation/truncated/content_filtered
    non_compliant = [(r["edu.outcome"], r["edu.role"], r.get("edu.session_id", "?"))
                     for r in _schema_rows(rows)
                     if r.get("edu.outcome") in RESPONDED_OUTCOMES
                     and r.get("edu.outcome") != COMPLIANT_OUTCOME]
    if non_compliant:
        lines.append("\n> **不合规明细**(在合规分母内,计入未通过):")
        seen: set[str] = set()
        for outcome, role, sess in non_compliant:
            key = f"{outcome}:{sess}"
            if key not in seen:
                lines.append(f"> · {outcome} (role={role}, session={sess})")
                seen.add(key)

    avail_note = _availability_note(overall)
    if avail_note:
        lines.append(avail_note)

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
    args = parser.parse_args()

    rows = _read_facts_dir(args.dir, args.since)
    by_role, overall = _outcome_counters(rows)
    responded_total = sum(n for o, n in overall.items() if o in RESPONDED_OUTCOMES)

    if responded_total == 0:
        print("json_first_pass: 无产出模型响应的 schema 调用行")
        if rows:
            print(f"  (读取 {len(rows)} 行;schema 角色 attempt==1: "
                  f"{len(_schema_rows(rows))} 行,均无响应)")
        return 1

    ok_total = overall.get(COMPLIANT_OUTCOME, 0)
    rate = 100.0 * ok_total / responded_total
    flag = "达标" if rate / 100 >= M2_THRESHOLD else "未达标"
    print(f"json_first_pass: {ok_total}/{responded_total} = {rate:.1f}% "
          f"(合规分母=产出结果的行)[{flag}]")
    print(f"  M2 门 {M2_THRESHOLD*100:.0f}%: "
          f"{'✅' if rate/100 >= M2_THRESHOLD else '❌'}")
    for role in sorted(by_role):
        c = by_role[role]
        responded = sum(n for o, n in c.items() if o in RESPONDED_OUTCOMES)
        ok = c.get(COMPLIANT_OUTCOME, 0)
        rr = 100.0 * ok / responded if responded else 0.0
        print(f"  {role}: {ok}/{responded} = {rr:.1f}%")
        for o in sorted(c):
            if o in RESPONDED_OUTCOMES and o != COMPLIANT_OUTCOME and c[o] > 0:
                print(f"    不合规 {o}: {c[o]}")
    avail_note = _availability_note(overall)
    if avail_note:
        print(f"  {avail_note.replace(chr(10), ' ').strip()}")

    print("\n---\n")
    print(json_first_pass_report(args.dir, args.since))

    return 0


if __name__ == "__main__":
    sys.exit(main())