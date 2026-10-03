"""晨间摘要(00 §8.2 过夜安全第 6 项):纯读 run 目录,生成完成度/时长/失败按类计数/建议动作。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path


def _percentile(sorted_values: list[int], ratio: float) -> int:
    if not sorted_values:
        return 0
    index = min(int(len(sorted_values) * ratio), len(sorted_values) - 1)
    return sorted_values[index]


def _fmt_seconds(ms: int) -> str:
    return f"{ms / 1000:.1f}s"


def load_results(run_dir: Path) -> list[dict]:
    results_dir = run_dir / "results"
    if not results_dir.is_dir():
        return []
    payloads = [json.loads(path.read_text(encoding="utf-8"))
                for path in sorted(results_dir.glob("*.json"))]
    return sorted(payloads, key=lambda item: item["case_id"])


def morning_summary(run_dir: Path | str) -> str:
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    results = load_results(run_dir)
    total = manifest["total_cases"]
    if total == 0:
        return f"# 评测晨间摘要 — {run_dir.name}\n空批,无结果。"
    ok = [r for r in results if r["status"] == "ok"]
    env = [r for r in results if r["status"] == "environment"]
    content = [r for r in results if r["status"] == "content"]
    unfinished = total - len(results)
    durations = sorted(r["duration_ms"] for r in results)
    started = datetime.fromisoformat(manifest["started_at"])
    ended = max((datetime.fromisoformat(r["finished_at"]) for r in results), default=started)
    lines = [
        f"# 评测晨间摘要 — {run_dir.name}",
        f"- 被测对象: {manifest['subject']} · 数据集: {manifest['dataset']['name']}"
        f"(sha256 {manifest['dataset']['sha256'][:8]})",
        f"- 完成度: ok {len(ok)}/{total}({len(ok) * 100 // total}%)"
        f" · 未跑 {unfinished} · 环境失败 {len(env)} · 内容失败 {len(content)}",
        f"- 时长: 总 {_fmt_seconds(int((ended - started).total_seconds() * 1000))}"
        f" · 单条 p50 {_fmt_seconds(_percentile(durations, 0.5))}"
        f" / p95 {_fmt_seconds(_percentile(durations, 0.95))}",
        f"- 失败按类: environment {len(env)} · content {len(content)}",
    ]
    for result in env[:5]:
        first_line = (result["error"] or "").splitlines()
        lines.append(f"  - environment {result['case_id']}(尝试 {result['attempts']} 次:"
                     f"{first_line[0] if first_line else ''})")
    for result in content[:5]:
        first_line = (result["error"] or "").splitlines()
        lines.append(f"  - content {result['case_id']}({first_line[0] if first_line else ''})")
    lines.append("- 建议动作:")
    lines.extend(f"  - {action}" for action in _actions(unfinished, env, content, total))
    return "\n".join(lines) + "\n"


def _actions(unfinished: int, env: list[dict], content: list[dict], total: int) -> list[str]:
    actions = []
    if unfinished > 0:
        actions.append(f"续跑:还有 {unfinished} 条未执行,以同一 run 目录重入 runner")
    if env:
        actions.append(f"补跑环境失败 {len(env)} 条(重试安全,同目录重入即自动补)")
    if content:
        actions.append(f"内容失败 {len(content)} 条转 judge 评分与人工定位,不重跑")
    if not actions:
        actions.append(f"全部 {total} 条完成:进入 judge 评分与报告(00 §8.2)")
    return actions


def write_summary(run_dir: Path | str) -> Path:
    run_dir = Path(run_dir)
    target = run_dir / "summary.md"
    target.write_text(morning_summary(run_dir), encoding="utf-8")
    return target

# ---- 三口径×四指标与软化报告段(#521 I5 自 corpus_round 移驻:纯报告 helper,零行为变化)----
def soften_counts(results: list[dict]) -> dict[str, int]:
    """软化两造计数(#241 行 4「掩码成功 vs 整步弃用」):transcript.guard_events 的 reveal 轮——
    cut = 同分句边界收回;mask = 兜底改写「几」;dropped = 整步弃用(轮级 dropped=True,
    此前全仓只写不读)。无 tag 且未弃用(无泄漏保留原文/未走揭示)不计。"""
    counts = {"cut": 0, "mask": 0, "dropped": 0}
    for row in results:
        for event in (row.get("transcript") or {}).get("guard_events") or []:
            if event.get("soften") in ("cut", "mask"):
                counts[event["soften"]] += 1
            elif event.get("dropped"):
                counts["dropped"] += 1
    return counts


def soften_line(counts: dict[str, int]) -> str:
    """软化计数 → 报告脚注行(拼在 render_report 产物之后,#244 审 P1:不加参防
    与 #242 provenance 撞 PLR0913 max-args=6);三值全零 → 空串(不占行)。"""
    if not any(counts.get(k) for k in ("cut", "mask", "dropped")):
        return ""
    return (f"\n- 软化路径命中(#241 行 4):cut={counts.get('cut', 0)}(同分句边界收回) / "
            f"mask={counts.get('mask', 0)}(兜底改写「几」) / "
            f"dropped={counts.get('dropped', 0)}(整步弃用)")

def facts_calibers(facts_rows: list[dict]) -> dict:
    """三口径数据底座(#238 件 B):调用级按 role 计数 + 会话级 fallback 标记。

    - roles:role → {calls, fallbacks(edu.fallback_to 非 None), rate};
    - sessions:session_id → 该会话是否走过 fallback(任一调用 fallback 即 True)
      ——case 级口径由调用方查表:tutor 会话 = transcript.session_id,
      judge 会话 = "judge-{case_id}"(judge.py 的 session 命名)。"""
    roles: dict[str, dict] = {}
    sessions: dict[str, bool] = {}
    for row in facts_rows:
        stats = roles.setdefault(row.get("edu.role") or "?", {"calls": 0, "fallbacks": 0})
        stats["calls"] += 1
        fell = row.get("edu.fallback_to") is not None
        if fell:
            stats["fallbacks"] += 1
        sid = row.get("edu.session_id") or ""
        if sid:
            sessions[sid] = sessions.get(sid, False) or fell
    for stats in roles.values():
        stats["rate"] = stats["fallbacks"] / stats["calls"] if stats["calls"] else 0.0
    return {"roles": roles, "sessions": sessions}


def _ascii_numbers(text: str) -> set[float]:
    """false-confirm 代理的数字提取(件 B 口径注记的一部分):ASCII 数字集合。

    仅报告层代理判据,非内核护栏判据(kernel 侧 _answer_focus_numbers 的允许集
    口径与用途都不同;报告只描述不拦截,#184 的「第二套判据」禁令不适用)。"""
    return {float(m) for m in re.findall(r"\d+(?:\.\d+)?", text or "")}


def _case_fell_back(row: dict, sessions: dict[str, bool]) -> bool:
    transcript = row.get("transcript") or {}
    return bool(sessions.get(transcript.get("session_id") or "")
                or sessions.get(f"judge-{row['case_id']}"))


def _pct(x: float | None) -> str:
    return f"{x:.1%}" if x is not None else "-"


def _four_metrics(subset: list[dict], checks: dict[str, dict], scores: dict[str, dict],
                  scenarios: dict[str, dict]) -> dict:
    """四指标(评审 P1-7)在给定 case 子集上算;口径注记见 caliber_section。"""
    completed = [r for r in subset
                 if (checks.get(r["case_id"]) or {}).get("final_state") == "completed"]
    student_turn_counts = [sum(1 for t in r["transcript"].get("turns") or [] if t.get("student"))
                           for r in completed]
    false_n = denom = 0
    for row in completed:
        question = scenarios[row["case_id"]]["question"]
        expected = _ascii_numbers(question.get("answer", "") if isinstance(question, dict) else "")
        if not expected:
            continue  # 定性/无数字答案:不进 false-confirm 分母(口径注记)
        denom += 1
        said: set[float] = set()
        for turn in row["transcript"].get("turns") or []:
            said |= _ascii_numbers(turn.get("student") or "")
        if not expected <= said:
            false_n += 1
    stuck = sum(1 for r in subset
                if any(e.get("branch") == "reveal"
                       for e in (r["transcript"].get("guard_events") or [])))
    needs_review = sum(1 for r in subset
                       if (checks.get(r["case_id"]) or {}).get("final_state") == "needs_review")
    totals = [scores[r["case_id"]]["total"] for r in subset
              if r["case_id"] in scores and "total" in scores[r["case_id"]]]
    return {
        "n": len(subset),
        "completed": len(completed),
        "turns_to_confirm": (round(sum(student_turn_counts) / len(student_turn_counts), 1)
                             if student_turn_counts else None),
        "false_confirm_n": false_n,
        "false_confirm_denom": denom,
        "false_confirm_rate": round(false_n / denom, 3) if denom else None,
        "stuck_rate": round(stuck / len(subset), 3) if subset else None,
        "needs_review_rate": round(needs_review / len(subset), 3) if subset else None,
        "judge_mean": round(sum(totals) / len(totals), 1) if totals else None,
    }


def caliber_section(calibers: dict, results: list[dict], checks: dict[str, dict],
                    scores: dict[str, dict], scenarios: dict[str, dict]) -> str:
    """三口径 × 四指标报告段(#238 件 B,GEPA 前置):calibers = facts_calibers(facts 行)。

    口径钉死在段内(报告不说清就没法判「优化对象是 system score 还是
    primary-only」):primary-only = ok case 中 tutor/judge 会话全无 fallback 的
    干净集;with-fallback = 全部 ok case(system 实产);fallback-rate 按调用级
    分 role 列。四指标 = mean turns-to-confirm / false-confirm(代理)/ stuck /
    needs-review,口径见注记。"""
    sessions = calibers["sessions"]
    ok = [r for r in results if r["status"] == "ok"]
    rows = [("primary-only", [r for r in ok if not _case_fell_back(r, sessions)]),
            ("with-fallback", ok)]
    lines = [
        "",
        "## 三口径 × 四指标(#238 件 B,GEPA 前置)",
        "",
        "口径注记:",
        "- primary-only = ok case 中 tutor 会话与 judge 会话均未走 fallback 的子集",
        "  (tutor 备选 mlx_27b / judge 备选 deepseek;case 级 = 任一调用 fallback 即出局,",
        "  GEPA 归因要的干净集——优化对象是 system score 还是 primary-only 由此可判)",
        "- with-fallback = 全部 ok case(system 实产口径);fallback-rate = 调用级按 role 分列",
        "- turns-to-confirm = completed 帧学生轮数均值(一轮 = 一学生消息 + 一导师回应,首问不计)",
        "- false-confirm(代理)= completed ∧ 期望答案含 ASCII 数字 ∧ 期望数字集未全现于",
        "  学生消息;定性答案不进分母,中文数字不在判据内(已知盲区)",
        "- stuck = guard_events 出现 reveal 分支(窄词表「不会」族)占比;",
        "  needs-review = final_state=needs_review 占比;judge 均值 = total/12 口径内均值",
        "",
        "| 口径 | n | completed | turns-to-confirm | false-confirm | stuck | needs-review | judge 均值 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, subset in rows:
        m = _four_metrics(subset, checks, scores, scenarios)
        lines.append(
            f"| {name} | {m['n']} | {m['completed']} "
            f"| {m['turns_to_confirm'] if m['turns_to_confirm'] is not None else '-'} "
            f"| {m['false_confirm_n']}/{m['false_confirm_denom']} ({_pct(m['false_confirm_rate'])}) "
            f"| {_pct(m['stuck_rate'])} | {_pct(m['needs_review_rate'])} "
            f"| {m['judge_mean'] if m['judge_mean'] is not None else '-'} |")
    lines += ["", "调用级 fallback:", "", "| role | calls | fallbacks | rate |", "|---|---|---|---|"]
    for role, stats in sorted(calibers["roles"].items()):
        lines.append(f"| {role} | {stats['calls']} | {stats['fallbacks']} | {stats['rate']:.1%} |")
    return "\n".join(lines) + "\n"
