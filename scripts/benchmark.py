#!/usr/bin/env python3
"""gateway 效率基准(01 §5):20 条固定回放 × {tutor stream(VL 8303), judge stream(MLX 8301)}。

口径照 01 §5:TTFT 仅 stream 有值;TTFT/端到端/生成速度全部来自 model_call 事实
记录(指标唯一来源),生成速度 = 输出 tokens / 生成秒数(总时长减 TTFT)。
回放是自造的延迟测量负载,不是 M1 评测数据集(教学指标归评测线,01 §8)。
对比 baselines/efficiency.json:ttft/e2e/生成速度的 p50 劣化 >10% 即非零
退出;基线更新走 PR(--write-baseline 生成候选)。DEEPSEEK_API_KEY 走环境变量,
绝不进日志与报告。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from edu_agent.gateway import GatewayError, ModelRequest, RegistryError, stream

REPO = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO / "baselines" / "efficiency.json"
REPORT_PATH = REPO / "var" / "benchmark-report.md"
FACTS_DIR = Path(os.environ.get("EDU_FACTS_DIR") or REPO / "facts")
DEGRADE = 0.10  # 01 §5:p50 劣化阈值
# 逐指标劣化系数(#142 取证):tutor.ttft_p50_ms 在"双峰空谷"上不可复现——逐题确定性双峰
# (快簇 13-17ms / 慢簇 54-126ms,中间 20-50ms 为空谷),n=20 时中位数在谷上空跳,实测噪声带
# +14~37%。故单列 +100%(门槛 86ms)留足余量,只拦真回归;judge.ttft 单峰(334-612)门有效,不陪绑。
COEFFICIENTS = {("tutor", "ttft_p50_ms"): 1.00}
ROLES = ("tutor", "judge")  # 主选:tutor=VL 8303,judge=MLX 8301(备选 DeepSeek)

# 自造延迟负载:固定 20 条单轮提问,长度与题型错开;不是评测数据集,不做教学断言。
REPLAYS = (
    "3+4 等于几?",
    "用一句话解释什么是光合作用。",
    "小明有 12 个苹果,分给 4 个朋友,每人几个?",
    "「举头望明月」的下一句是什么?",
    "水在标准大气压下多少度沸腾?",
    "把「我明天要去学校」翻译成英语。",
    "一小时有多少秒?",
    "三角形内角和是多少度?",
    "中国的首都是哪里?",
    "5 乘以 8 再减去 10 等于多少?",
    "用一句话说明为什么天空是蓝色的。",
    "「守株待兔」讲了一个什么道理?",
    "一个长方形长 6 宽 4,面积是多少?",
    "地球绕太阳一圈要多久?",
    "用一句话定义「分数」。",
    "1 到 10 的质数有哪些?",
    "鲸鱼是鱼类吗?为什么?",
    "把 3/4 化成小数。",
    "一年有几个月,一个月最多有多少天?",
    "用一句话鼓励一位考试失利的同学。",
)


def percentile(values: list, q: float):
    """线性插值分位数(标准口径);空表返回 None。小样本下比 nearest-rank 稳。"""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * q
    low, high = math.floor(rank), math.ceil(rank)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def run_role(role: str, run_id: str) -> None:
    """单次调用失败(截断/超时等)不计入样本:延迟测量只收 ok 记录,n 在报告可见。"""
    for i, prompt in enumerate(REPLAYS, 1):
        request = ModelRequest(
            role=role,
            messages=[{"role": "user", "content": prompt}],
            session_id=f"{run_id}-{role}",
            max_tokens=512,
            temperature=0,
        )
        start = time.monotonic()
        try:
            for _ in stream(request):
                pass
        except GatewayError as error:
            print(f"  {role} #{i:02d} 失败({error.failure.value}),不计入样本", flush=True)
            continue
        print(f"  {role} #{i:02d} {time.monotonic() - start:.1f}s", flush=True)


def collect(run_id: str) -> dict:
    """从本次 run 的事实记录汇总指标(01 §5:事实记录是唯一来源)。"""
    rows: dict[str, list] = defaultdict(list)
    for file in sorted(FACTS_DIR.glob("model_calls-*.jsonl")):
        for line in file.read_text(encoding="utf-8").splitlines():
            payload = json.loads(line)
            for role in ROLES:
                if payload.get("edu.session_id") == f"{run_id}-{role}":
                    rows[role].append(payload)
    metrics = {}
    for role in ROLES:
        ok = [p for p in rows[role] if p["edu.outcome"] == "ok"]
        ttft = [p["gen_ai.server.time_to_first_token"] for p in ok
                if p["gen_ai.server.time_to_first_token"] is not None]
        e2e = [p["edu.total_ms"] for p in ok if p["edu.total_ms"] is not None]
        speed = [
            p["gen_ai.usage.output_tokens"] / ((p["edu.total_ms"] - p["gen_ai.server.time_to_first_token"]) / 1000)
            for p in ok
            if p["gen_ai.server.time_to_first_token"] is not None and p["gen_ai.usage.output_tokens"]
            and p["edu.total_ms"] and p["edu.total_ms"] > p["gen_ai.server.time_to_first_token"]
        ]
        metrics[role] = {
            "n": len(ok),
            "ttft_p50_ms": percentile(ttft, 0.5),
            "ttft_p95_ms": percentile(ttft, 0.95),
            "e2e_p50_ms": percentile(e2e, 0.5),
            "e2e_p95_ms": percentile(e2e, 0.95),
            "speed_p50": round(percentile(speed, 0.5), 1) if speed else None,
        }
        for key in ("ttft_p50_ms", "ttft_p95_ms", "e2e_p50_ms", "e2e_p95_ms"):
            if metrics[role][key] is not None:
                metrics[role][key] = round(metrics[role][key])
    return metrics


def compare(current: dict, baseline: dict) -> list[str]:
    """ttft/e2e 的 p50 越高越糟,speed_p50 越低越糟;劣化超阈值即失败(01 §5,2026-09-07
    口径修订:门从 p95 改 p50——n=20 的 p95 尾部噪声天然超过 10%,六次实证见 #40;
    p95 保留在报告与基线中,仅记录不阻断)。逐指标阈值见 COEFFICIENTS,未列出的用 DEGRADE。"""
    failures = []
    for role, metrics in current.items():
        base = baseline.get("roles", {}).get(role, {})
        checks = [("ttft_p50_ms", +1), ("e2e_p50_ms", +1), ("speed_p50", -1)]
        for name, direction in checks:
            now, old = metrics.get(name), base.get(name)
            if now is None or not old:
                continue
            coeff = COEFFICIENTS.get((role, name), DEGRADE)
            if direction * (now - old) > coeff * old:
                failures.append(f"{role}.{name}: {now} vs 基线 {old}(劣化 >{coeff:.0%})")
    return failures


def render(metrics: dict) -> str:
    lines = [
        "# gateway 效率基准报告(01 §5)",
        "",
        f"- 时间:{datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "- 口径:TTFT 仅 stream;生成速度 = 输出 tokens / 生成秒数;来源=model_call 事实记录",
        "",
        "| 角色 | n | TTFT p50/p95 (ms) | 端到端 p50/p95 (ms) | 生成速度 p50 (tok/s) |",
        "|---|---|---|---|---|",
    ]
    for role in ROLES:
        m = metrics.get(role, {})
        fmt = lambda v: "-" if v is None else v
        lines.append(
            f"| {role} | {m.get('n', 0)} | {fmt(m.get('ttft_p50_ms'))} / {fmt(m.get('ttft_p95_ms'))} "
            f"| {fmt(m.get('e2e_p50_ms'))} / {fmt(m.get('e2e_p95_ms'))} | {fmt(m.get('speed_p50'))} |"
        )
    return "\n".join(lines) + "\n"


def git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-baseline", action="store_true", help="把本次结果写成新基线(走 PR 提交)")
    args = parser.parse_args()

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print(f"效率基准 {run_id}:20 条固定回放 × {ROLES}(01 §5;不是评测数据集)")
    try:
        for role in ROLES:
            run_role(role, run_id)
    except (GatewayError, RegistryError) as error:
        print(f"基准失败:{error}", file=sys.stderr)
        return 1

    metrics = collect(run_id)
    for role in ROLES:
        if metrics.get(role, {}).get("n", 0) < len(REPLAYS) // 2:
            print(f"基准失败:{role} 有效样本不足一半({metrics.get(role, {}).get('n', 0)}/{len(REPLAYS)})", file=sys.stderr)
            return 1
    report = render(metrics)
    print(report)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")

    if args.write_baseline or not BASELINE_PATH.exists():
        baseline = {
            "note": "01 §5 效率基线;更新走 PR(结构路径);ttft/e2e 单位 ms,speed 单位 tok/s",
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "main_sha": git_sha(),
            "roles": metrics,
        }
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"基线已写入 {BASELINE_PATH}(更新走 PR)")
        return 0

    failures = compare(metrics, json.loads(BASELINE_PATH.read_text(encoding="utf-8")))
    if failures:
        for failure in failures:
            print(f"基准劣化:{failure}", file=sys.stderr)
        return 1
    print("基准通过:相对基线无 >10% 劣化(01 §5)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
