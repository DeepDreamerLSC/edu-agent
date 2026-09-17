#!/usr/bin/env python3
"""gateway 效率基准(01 §5):20 条固定回放 × {tutor stream(VL 8303), judge stream(MLX 8301)}。

口径照 01 §5:TTFT 仅 stream 有值;TTFT/端到端/生成速度全部来自 model_call 事实
记录(指标唯一来源),生成速度 = 输出 tokens / 生成秒数(总时长减 TTFT)。
回放是自造的延迟测量负载,不是 M1 评测数据集(教学指标归评测线,01 §8)。
对比 baselines/efficiency.json:门指标按角色定(见 GATED_CHECKS),p50 劣化 >10% 即
非零退出;tutor.ttft_p50 逐题双峰不设门(#142)——**保留在报告与基线里,只记不阻断**。
报告附 TTFT 前缀缓存分层诊断列(#338/#188:命中/未命中两列 n + TTFT 中位/p95,不设门,
数据源 = 事实记录既有 cache_read 字段,无新采集点)。
基线更新走 PR(--write-baseline 生成候选)。DEEPSEEK_API_KEY 走环境变量,
绝不进日志与报告。

批跑让路(#241 行1,设计稿 v2+v2.1):/tmp/edu-agent-batch/<name>.<pid> 有活标志 →
门中性 SKIPPED(::warning + 报告 + step summary 双留痕);**写基线分支(--write-baseline
或基线缺失自动重种)撞活标志一律拒**——被争用窗口污染的基线比门红更糟。
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
BATCH_DIR = Path("/tmp/edu-agent-batch")  # #241 行1:批跑申报标志(空 touch 文件 <name>.<pid>)
DEGRADE = 0.10  # 01 §5:p50 劣化阈值
# 门指标按角色定(#142 定案):tutor.ttft_p50_ms 逐题双峰(快簇 13-17ms = llama-server
# 前缀缓存命中 / 慢簇 54-126ms = 未命中,中位 ≈58ms,中间 20-50ms 空谷),p50 判的是
# "命中了几条样本"而不是性能;缓存态一变就整簇位移——2026-09-11 本机实跑逐题 59-165ms、
# p50 102(= 基线 43 的 +137%),而同一次 e2e 只 +7.7%、judge 正常,即纯 TTFT 面假红
# (该次连 fa80114 的 +100% 宽门 86 也会红)。故 tutor.ttft **不设门:保留在报告与基线
# 里,只记不阻断**(与 p95 同例)。
# 代价明写(别夸大兜底):TTFT 真回归不再有门拦——e2e_p50 只是**弱**兜底,TTFT p50 需涨到
# 约 +215%(≈135ms)才可能顶动 e2e 门线(#142 审查量化)。
# judge.ttft 单峰连续(p50 实测 348-644;负载相撞那次 815),门有效不陪绑。
GATED_CHECKS = {
    "tutor": (("e2e_p50_ms", +1), ("speed_p50", -1)),
    "judge": (("ttft_p50_ms", +1), ("e2e_p50_ms", +1), ("speed_p50", -1)),
}
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


def ttft_strata(ok: list[dict]) -> dict:
    """TTFT 前缀缓存分层(#338/#188,诊断列**不设门**)。分层口径照 #188 实测:
    未缓存输入 token = gen_ai.usage.input_tokens − gen_ai.usage.cache_read.input_tokens;
    ==1 → 命中层(前缀缓存整段命中),≥10 → 未命中层,2–9 为空谷(#188 本机实测
    0 条)不计入两列、计数入 mid_n。usage 字段缺失的行不可分层,不计入(总数仍见
    主表 n)。零判定逻辑:只产列,不进门(GATED_CHECKS 不含分层键)。"""
    hit: list = []
    miss: list = []
    mid_n = 0
    for p in ok:
        total = p.get("gen_ai.usage.input_tokens")
        cached = p.get("gen_ai.usage.cache_read.input_tokens")
        ttft = p.get("gen_ai.server.time_to_first_token")
        if total is None or cached is None or ttft is None:
            continue
        uncached = total - cached
        if uncached == 1:
            hit.append(ttft)
        elif uncached >= 10:
            miss.append(ttft)
        else:
            mid_n += 1

    def layer(values: list) -> dict:
        return {"n": len(values),
                "ttft_p50_ms": round(percentile(values, 0.5)) if values else None,
                "ttft_p95_ms": round(percentile(values, 0.95)) if values else None}

    return {"hit": layer(hit), "miss": layer(miss), "mid_n": mid_n}


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
        metrics[role]["ttft_strata"] = ttft_strata(ok)
    return metrics


def compare(current: dict, baseline: dict) -> list[str]:
    """门内 p50 越高越糟,speed_p50 越低越糟;劣化超 10% 即失败(01 §5,2026-09-07
    口径修订:门从 p95 改 p50——n=20 的 p95 尾部噪声天然超过 10%,六次实证见 #40;
    p95 保留在报告与基线中,仅记录不阻断)。门指标按角色定(GATED_CHECKS):
    tutor.ttft_p50 双峰空谷不设门(#142,只记不阻断,与 p95 同例);judge.ttft 单峰,门有效。"""
    failures = []
    for role, metrics in current.items():
        base = baseline.get("roles", {}).get(role, {})
        for name, direction in GATED_CHECKS.get(role, ()):
            now, old = metrics.get(name), base.get(name)
            if now is None or not old:
                continue
            if direction * (now - old) > DEGRADE * old:
                failures.append(f"{role}.{name}: {now} vs 基线 {old}(劣化 >{DEGRADE:.0%})")
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
    # TTFT 前缀缓存分层(#338/#188):诊断列,不设门——零判定逻辑,阈值不属本件
    lines += [
        "",
        "## TTFT 前缀缓存分层(#188 诊断列,不设门)",
        "",
        "未缓存输入 token = `usage.input_tokens` − `usage.cache_read.input_tokens`;"
        " ==1 → 命中,≥10 → 未命中,2–9 空谷不计入两列(仅注计数);usage 缺失的行不可分层,不计入(总数见主表 n)。",
        "",
        "| 角色 | 层 | n | TTFT p50 (ms) | TTFT p95 (ms) |",
        "|---|---|---|---|---|",
    ]
    for role in ROLES:
        st = metrics.get(role, {}).get("ttft_strata", {})
        for key, label in (("hit", "命中(未缓存==1)"), ("miss", "未命中(未缓存≥10)")):
            layer = st.get(key, {})
            lines.append(
                f"| {role} | {label} | {layer.get('n', 0)} "
                f"| {fmt(layer.get('ttft_p50_ms'))} | {fmt(layer.get('ttft_p95_ms'))} |"
            )
    mids = " / ".join(str(metrics.get(r, {}).get("ttft_strata", {}).get("mid_n", 0)) for r in ROLES)
    lines.append(f"- 空谷(2–9)计数(tutor / judge):{mids}")
    return "\n".join(lines) + "\n"


def git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def live() -> list[str]:
    """活批跑标志清单(#241 行1):<name>.<pid> 空文件,PID 查活不查名;死标志(崩溃
    遗留)顺手清。无续期无仲裁无进程管理(02 §5:一次性 kill(pid, 0) 纯查询,无
    spawn/supervise/reap;§5 出口本就指向 OS 设施)——批跑单向申报,门单方退避。"""
    if not BATCH_DIR.is_dir():
        return []
    alive: list[str] = []
    for flag in BATCH_DIR.iterdir():
        if not flag.is_file():
            continue  # 目录/非常规残留不碰(审查 P2-1:unlink 不吞目录,IsADirectoryError 会顶掉证据块)
        pid = flag.name.rpartition(".")[2]
        if not pid.isdigit() or int(pid) == 0:
            continue  # 非 <name>.<pid> 形态不碰
        try:
            os.kill(int(pid), 0)
        except ProcessLookupError:
            flag.unlink(missing_ok=True)  # 死标志顺手清
            continue
        except PermissionError:
            pass  # 别人的活进程:占机同样成立
        alive.append(flag.name)
    return alive


def contention_evidence() -> str:
    """门红时的争用证据块(#239 处置①「红先查并发源」的自动化):负载/模型服务
    CPU/批跑标志,分诊读块判回归——无申报 + 服务 CPU 低 → 按真回归走 30 分钟纪律。"""
    lines = [f"- load 1/5/15min: {' '.join(f'{v:.2f}' for v in os.getloadavg())}"]
    try:
        ps = subprocess.run(["ps", "-axo", "pid,pcpu,comm"], capture_output=True, text=True,
                            timeout=10).stdout.splitlines()
        lines += [f"- 模型服务:{ln.strip()}" for ln in ps
                  if ("mlx" in ln or "llama" in ln) and "grep" not in ln]
    except (OSError, subprocess.SubprocessError):
        lines.append("- 模型服务:ps 不可用")
    lines.append(f"- 批跑标志:{live() or '无(本窗口无申报——红大概率非争用)'}")
    return "\n## 争用证据块(#241 行1)\n" + "\n".join(lines) + "\n"


def gate_or_skip(args: argparse.Namespace) -> int | None:
    """#241 行1 批跑窗口让路:活标志非空 → 门中性 SKIPPED(exit 0);**写基线分支
    (--write-baseline 或基线缺失自动重种,P2-1)一律拒**——争用窗口重种的基线比门红更糟。
    无活标志返回 None,正常开跑。"""
    flags = live()
    if not flags:
        return None
    names = ", ".join(flags)
    if args.write_baseline or not BASELINE_PATH.exists():
        print(f"基线重种拒绝:批跑窗口活标志 {names};收工后重试(#241 行1)", file=sys.stderr)
        return 1
    print(f"::warning:: benchmark skipped: batch window({names});"
          "收工后 gh run rerun --job 补跑(#241 行1)", flush=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        "# gateway 效率基准报告(01 §5)\n\n"
        f"- 时间:{datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
        f"- **SKIPPED**:批跑窗口({names});收工后 `gh run rerun <run> --job <benchmark-job>` 补跑(#241 行1)\n",
        encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")  # 第二留痕(P3-3):run 页永久可查
    if summary:
        with Path(summary).open("a", encoding="utf-8") as fh:  # 显式关句柄(审查 P3)
            fh.write(f"- benchmark SKIPPED:批跑窗口({names})(#241 行1)\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-baseline", action="store_true", help="把本次结果写成新基线(走 PR 提交)")
    args = parser.parse_args()

    skipped = gate_or_skip(args)
    if skipped is not None:
        return skipped

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
        evidence = contention_evidence()
        REPORT_PATH.write_text(REPORT_PATH.read_text(encoding="utf-8") + evidence, encoding="utf-8")
        print(evidence)  # 同步进步骤日志 → main_red 报警 issue 直取证据
        return 1
    print("基准通过:相对基线无 >10% 劣化(01 §5)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
