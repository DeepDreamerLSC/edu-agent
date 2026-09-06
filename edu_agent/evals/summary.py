"""晨间摘要(00 §8.2 过夜安全第 6 项):纯读 run 目录,生成完成度/时长/失败按类计数/建议动作。"""

from __future__ import annotations

import json
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
