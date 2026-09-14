"""corpus checks × 真模型运行面(#216):corpus 真模型口径场景批跑 → checks 判定 →
judge 评分 → run 工件落盘 → 跨轮对照报告。口径对齐 scripts/tuning_round.py(#211 先例):
KernelSubject + EvalRunner(case 级 checkpoint/续跑/失败台账)+ judge 单遍 primary。

边界(#216,不扩界):
- 确定性口径(fake_model 罐头)**不在此跑**——它们在 pytest 参数化里永久回放,重复接线零增益;
- 真模型场景**不进 CI 回归**(无罐头,pytest 零真模型)——本面只产 run 工件与报告,人工/夜评触发;
- 工件入库按仓库惯例落在 edu_agent/evals/artifacts/(评审 840 即此形态):判定表与 judge
  分**按轮**落在各自 collect run 目录(与 transcript 同处,该轮自足可复算),根下同名文件
  为最新一轮便捷副本。

入口(模块入口,不动 scripts/ 结构路径):
    uv run python -m edu_agent.evals.corpus_round --out <运行根目录> \
        [--corpus <数据集 JSON>]... [--diff-from <上轮 collect run 目录>]
    uv run python -m edu_agent.evals.corpus_round --render-from <运行根目录> \
        [--diff-from <上轮 collect run 目录>]   # 不跑批,零模型重渲染 report(#257 审 P3-2)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .judge import judge_transcript
from .kernel_subject import KernelSubject
from .runner import EvalRunner, RunnerConfig
from .scenario_corpus import load_shortboard_corpus, run_scenario_checks, to_kernel_case
from .summary import load_results
from edu_agent.gateway import Gateway, GatewayError, load_registry

REPO = Path(__file__).resolve().parents[2]
# 默认 corpus = teaching_context pilot(20,有学生剧本)。
# adaptive pilot 无剧本(模拟器消费面,#211 明确「另行接入」)——kernel 批跑面跑不了,
# 传 --corpus 进来也会被 build_cases 显式跳过并计数,不静默。
DEFAULT_CORPUS = (
    "edu_agent/evals/datasets/small_lecturer_teaching_context_shadow_pilot_20.json",
)


def _probe(url: str, timeout: float = 2.0) -> str:
    parsed = urlparse(url)
    host, port = parsed.hostname or "127.0.0.1", parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "ok"
    except OSError as exc:
        return f"不可达:{exc.__class__.__name__}"


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_sha() -> str | None:
    """跑批 commit(#238 件 A):git 不可用/非仓库时 None(不伪造,README 手写不算溯源)。"""
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                             text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def run_identity() -> dict:
    """跑批身份三件套(#238 件 A,GEPA 前置):git HEAD / prompt 组件 / models 配置。

    GEPA 优化对象是 prompting.py——每次迭代的可归因性从这三个哈希起步;
    机器可读进 manifest(此前只有 README 手写,不算溯源)。老轮次不回填。"""
    return {
        "git_sha": _git_sha(),
        "prompts_sha256": _file_sha256(
            REPO / "edu_agent" / "agents" / "small_lecturer" / "prompting.py"),
        "models_sha256": _file_sha256(REPO / "configs" / "models.yaml"),
    }


def real_model_scenarios(corpus_paths: list[Path]) -> dict[str, dict]:
    """读 corpus 文件,取真模型口径子集(无 fake_model);case id 加数据集前缀防跨文件撞名。

    loader(load_shortboard_corpus)已做形状/答案可提取校验——写错在这里红,不静默跳过。
    """
    scenarios: dict[str, dict] = {}
    for path in corpus_paths:
        stem = Path(path).stem
        for scenario in load_shortboard_corpus(path):
            if scenario.get("fake_model"):
                continue  # 确定性口径:pytest 已永久回放(#216 边界)
            case_id = f"{stem}_{scenario['id']}"
            if case_id in scenarios:
                raise ValueError(f"case_id 撞名:{case_id}(数据集前缀后仍重复,改 id)")
            scenarios[case_id] = scenario
    if not scenarios:
        raise ValueError("corpus 里没有真模型口径场景(全部带 fake_model?)")
    return scenarios


def build_cases(scenarios: dict[str, dict]) -> tuple[list[dict], list[str]]:
    """场景 → runner cases;无剧本场景(模拟器消费面,#211 边界)显式跳过并返回名单。

    v2 分支剧本(steps)不算「无剧本」——学生消息由跟随器逐轮选(#178 方案 A)。"""
    cases, skipped = [], []
    for case_id, scenario in scenarios.items():
        if not scenario.get("student_turns") and not scenario.get("steps"):
            skipped.append(case_id)
            continue
        case = to_kernel_case(scenario)
        case["id"] = case_id
        cases.append(case)
    return cases, skipped


def judge_rows(gateway: Gateway, scenarios: dict[str, dict], results: list[dict]) -> dict[str, dict]:
    """ok 行 → judge 单遍 primary(评分失败记台账不炸整轮,口径同 tuning_round 单遍)。"""
    scores: dict[str, dict] = {}
    for row in results:
        if row["status"] != "ok":
            continue
        scenario = scenarios[row["case_id"]]
        question = scenario["question"]
        messages = []
        for turn in row["transcript"]["turns"]:
            if turn["student"]:
                messages.append({"role": "user", "content": turn["student"]})
            messages.append({"role": "assistant", "content": turn["tutor"]})
        if row["transcript"].get("summary"):
            messages.append({"role": "assistant", "content": row["transcript"]["summary"]})
        try:
            scores[row["case_id"]] = judge_transcript(gateway, {
                "id": row["case_id"],
                "question": question["text"] if isinstance(question, dict) else question,
                "grade": row["transcript"].get("learner", {}).get("grade", ""),
                "reference_answer": question.get("answer", "") if isinstance(question, dict) else "",
                "messages": messages,
            })
        except (GatewayError, json.JSONDecodeError, KeyError) as exc:
            # 评分失败记台账不炸整轮(judge 路径可抛的全集:网关/剥壳解析/缺键);
            # 其余异常照常炸出(评分器自身的 bug 不许被台账吞掉)
            scores[row["case_id"]] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    return scores


def check_rows(scenarios: dict[str, dict], results: list[dict]) -> dict[str, dict]:
    """每场景的 checks 判定行:声明了 expect.checks 才跑;未声明记 declared=False(不冒充全绿)。"""
    rows: dict[str, dict] = {}
    for row in results:
        scenario = scenarios[row["case_id"]]
        if row["status"] != "ok":
            rows[row["case_id"]] = {"status": row["status"], "declared": False,
                                    "failures": None, "final_state": None}
            continue
        declared = bool((scenario.get("expect") or {}).get("checks"))
        rows[row["case_id"]] = {
            "status": "ok",
            "declared": declared,
            "final_state": row["transcript"].get("final_state", ""),
            "failures": run_scenario_checks(scenario, row["transcript"]) if declared else None,
        }
    return rows


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


def dump_facts(facts_dir: Path | str, run_dir: Path | str) -> list[dict]:
    """model_call facts 落 run 目录(#238 件 B):FactWriter 按 UTC 天切文件、且原
    tempdir 随进程丢——本函数把整轮(tutor + judge)合并成 run_dir/facts.jsonl,
    该轮自足可复算(offline rescore 的地基)。返回行列表供报告层直接消费。"""
    rows: list[dict] = []
    for path in sorted(Path(facts_dir).glob("model_calls-*.jsonl")):
        rows += [json.loads(line) for line in
                 path.read_text(encoding="utf-8").splitlines() if line.strip()]
    (Path(run_dir) / "facts.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return rows


def load_facts(run_dir: Path | str) -> list[dict]:
    """dump_facts 的对偶:读 run 目录 facts.jsonl(offline rescore / 报告复算消费)。"""
    path = Path(run_dir) / "facts.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


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


def diff_checks(current: dict[str, dict], previous: dict[str, dict]) -> dict[str, str]:
    """跨轮 check 对照:绿→红 = 新增红(回归信号),红→绿 = 翻绿(修复或噪声,看 judge)。"""
    verdicts: dict[str, str] = {}
    for case_id, row in current.items():
        prev = previous.get(case_id)
        was_red = bool(prev and prev.get("failures"))
        now_red = bool(row.get("failures"))
        if now_red and not was_red:
            verdicts[case_id] = "新增红"
        elif was_red and not now_red:
            verdicts[case_id] = "翻绿"
        elif now_red and was_red:
            verdicts[case_id] = "持续红"
        else:
            verdicts[case_id] = "绿"
    return verdicts


def _judger_sha256() -> str:
    """判分器指纹:checks.py + judge.py 按文件名序拼接后 sha256(十六进制)。
    #238 §5:跨轮 diff 遇版本断点须标注,此函数提供可比对的哈希。"""
    files = sorted((Path(__file__).parent / f) for f in ("checks.py", "judge.py"))
    h = hashlib.sha256()
    for f in files:
        h.update(f.read_bytes())
    return h.hexdigest()


def _provenance_context(diff_from):
    """Compute current judger hash + read baseline hash (None = baseline has no provenance)."""
    judger_hash = _judger_sha256()
    prev_hash = None
    if diff_from:
        prev_file = Path(diff_from) / "judger.sha256"
        if prev_file.is_file():
            prev_hash = prev_file.read_text(encoding="utf-8").strip()
    return judger_hash, prev_hash


def _compute_diff(diff_from: str | None, scenarios: dict, checks: dict):
    """Compute cross-round diff context (verdicts + prev scores) if diff_from given."""
    if not diff_from:
        return None, None
    prev_dir = Path(diff_from)
    previous = check_rows(scenarios, load_results(prev_dir))
    verdicts = diff_checks(checks, previous)
    prev_file = prev_dir / "judge-scores.jsonl"
    scores = ({row["case_id"]: row for row in (json.loads(line) for line in
              prev_file.read_text(encoding="utf-8").splitlines() if line.strip())}
              if prev_file.is_file() else None)
    return verdicts, scores


def render_report(out_dir: Path, checks: dict[str, dict], scores: dict[str, dict],
                  diff: dict | None = None, skipped: list[str] | None = None,
                  provenance: dict | None = None) -> str:
    """报告即工件:逐场景 判定/终态/judge 一行;有基线时加跨轮列与新增红计数。

    跨轮对照收在一个 `diff` 上下文里:`{"from": 上轮 run 目录, "verdicts": {...},
    "prev_scores": {...}}`;有上轮 judge 分(按轮留存在上轮 run 目录)时 judge 列给
    「上轮→本轮」——轮间噪声对比由此可复算(审查 P3,2026-09-12)。
    软化命中行由调用方以 `+ soften_line(soften_counts(results))` 追加(#241 行 4)。

    `provenance`:判分器指纹上下文(#238 §5),键 `current`(本轮)/`prev`(基线);
    基线无溯源时 `prev` 为 None(首轮基线 math-gold-v1 即此形态,#238 §5 记欠账)。
    """
    lines = [
        "# corpus checks × 真模型轮次报告(#216)",
        "",
        f"- 生成:{datetime.now(timezone.utc).isoformat()}",
        f"- 工件:{out_dir}",
        f"- judger_sha256:{(provenance or {}).get('current', '')}",
    ]
    if skipped:
        lines.append(f"- 跳过无剧本场景:{len(skipped)} 条(模拟器消费面未接线,#211 边界)")
    if diff:
        new_red = sum(1 for v in diff["verdicts"].values() if v == "新增红")
        lines += [f"- 对照基线:{diff['from']}", f"- **新增红:{new_red}**(绿→红 = 回归信号)"]
        prev_hash = (provenance or {}).get("prev")
        curr_hash = (provenance or {}).get("current", "")
        if prev_hash is None:
            lines.append("- 基线无溯源(判分器指纹自本轮起,#238 §5 首轮基线欠账)")
        elif prev_hash != curr_hash:
            lines.append(f"- 判分器已变更(基线 {prev_hash[:12]}→{curr_hash[:12]},#238 §5 跨轮版本断点)")
    else:
        lines += ["- 对照基线:无(首轮即基线;下轮用 --diff-from 指向本轮 collect 下最新 run 目录)"]
    lines += ["", "| case_id | status | final_state | checks | 判定(跨轮) | judge |", "|---|---|---|---|---|---|"]
    for case_id in sorted(checks):
        row = checks[case_id]
        if row["status"] != "ok":
            lines.append(f"| {case_id} | {row['status']} | - | - | - | - |")
            continue
        if not row["declared"]:
            check_cell = "无声明"
        elif row["failures"]:
            check_cell = ";".join(f"{f['check']}:{f['detail'][:60]}" for f in row["failures"])
        else:
            check_cell = "全绿"
        score = scores.get(case_id, {})
        if "error" in score:
            judge_cell = f"评分失败:{score['error'][:40]}"
        else:
            prev_total = ((diff or {}).get("prev_scores") or {}).get(case_id, {}).get("total")
            prefix = f"{prev_total}→" if prev_total is not None else ""
            judge_cell = (f"total={prefix}{score.get('total')} {score.get('verdict')}"
                          f" 追问={score.get('scores', {}).get('socratic_followup')}")
        diff_cell = diff["verdicts"].get(case_id, "-") if diff else "-"
        lines.append(f"| {case_id} | ok | {row['final_state']} | {check_cell} | {diff_cell} | {judge_cell} |")
    return "\n".join(lines) + "\n"


def _read_rows(path: Path) -> dict[str, dict]:
    """读 checks/judge-scores 类 {case_id: 行} JSONL(离线重渲染/跨轮对照消费)。"""
    if not path.is_file():
        return {}
    rows: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["case_id"]] = row
    return rows


def render_from(out_dir: Path, diff_from: str | None = None) -> int:
    """--render-from(#257 审 P3-2):不跑批、零模型调用,从既有运行根目录重渲染 report.md。

    读 out_dir 根 cases.jsonl(期望答案面)+ 最新 collect run 的落盘件(results /
    checks / judge-scores / facts / judger.sha256)。跨轮对照用 --diff-from 指向上轮
    collect run 目录,其判定/judge 行**直接读落盘、不重算**(「该轮自足」原则,
    与活跑的 _compute_diff 重算路径不同源但同义)。跳过计数是语料装载面信息、
    不落 run 目录,重渲染报告里该行缺席(仅活跑有)。"""
    run_dir = sorted((out_dir / "collect").glob("*-*Z-*"))[-1]
    results = load_results(run_dir)
    checks = _read_rows(run_dir / "checks.jsonl")
    scores = _read_rows(run_dir / "judge-scores.jsonl")
    cases = [json.loads(line) for line
             in (out_dir / "cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    scenarios = {c["id"]: c for c in cases}
    diff = None
    if diff_from:
        prev_dir = Path(diff_from)
        diff = {"from": diff_from, "verdicts": diff_checks(checks, _read_rows(prev_dir / "checks.jsonl")),
                "prev_scores": _read_rows(prev_dir / "judge-scores.jsonl") or None}
    judger_file = run_dir / "judger.sha256"
    prev_hash = None
    if diff_from and (Path(diff_from) / "judger.sha256").is_file():
        prev_hash = (Path(diff_from) / "judger.sha256").read_text(encoding="utf-8").strip()
    provenance = {"current": judger_file.read_text(encoding="utf-8").strip()
                  if judger_file.is_file() else "", "prev": prev_hash}
    report = render_report(out_dir, checks, scores, diff, provenance=provenance) + soften_line(
        soften_counts(results)) + caliber_section(
        facts_calibers(load_facts(run_dir)), results, checks, scores, scenarios)
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


def _live_round(args, gateway: Gateway, facts_dir: Path) -> int:
    """活跑路径(#257 审 P3 后从 main 拆出:语句预算 PLR0915 + 平铺);facts
    tempdir 的清理在 main 的 finally(任何退出路径不留残骸)。"""
    scenarios = real_model_scenarios([Path(p) for p in (args.corpus or DEFAULT_CORPUS)])
    cases, skipped = build_cases(scenarios)
    if skipped:
        print(f"跳过无剧本场景 {len(skipped)} 条(模拟器消费面未接线,#211 边界):{','.join(skipped)}")
    if not cases:
        print("没有可跑场景(全部无剧本?)", file=sys.stderr)
        return 1
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cases_file = out_dir / "cases.jsonl"
    cases_file.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n",
                          encoding="utf-8")
    collect_root = out_dir / "collect"
    print(f"批跑:{len(cases)} 场景(真模型口径;确定性口径不在本面)→ {collect_root}")
    EvalRunner(KernelSubject(gateway), RunnerConfig(concurrency=args.concurrency),
               collect_root).run(cases_file, cases, identity=run_identity())
    run_dir = sorted(collect_root.glob("*-*Z-*"))[-1]
    results = load_results(run_dir)

    checks = check_rows(scenarios, results)
    print(f"评分:{sum(1 for r in results if r['status'] == 'ok')} 行(judge 单遍 primary)")
    scores = judge_rows(gateway, scenarios, results)

    def dump(path: Path, rows: dict[str, dict]) -> None:
        path.write_text("\n".join(json.dumps({"case_id": k, **v}, ensure_ascii=False)
                                  for k, v in sorted(rows.items())) + "\n", encoding="utf-8")

    # 判定与 judge 分按轮留存在各自 run 目录(与 transcript 同处 = 该轮自足可复算);
    # out_dir 根下同名文件是最新一轮的便捷副本。—— 审查 P3(2026-09-12)
    dump(run_dir / "checks.jsonl", checks)
    dump(run_dir / "judge-scores.jsonl", scores)
    dump(out_dir / "checks.jsonl", checks)
    dump(out_dir / "judge-scores.jsonl", scores)

    # #238 件 B:model_call facts(tutor + judge 全轮)落 run 目录——原 tempdir 随进程丢,
    # 落盘后该轮自足(offline rescore 的地基),报告层据此拆三口径。
    facts_rows = dump_facts(facts_dir, run_dir)
    print(f"facts:{len(facts_rows)} 行 model_call 落 {run_dir / 'facts.jsonl'}")

    diff_verdicts, prev_scores = _compute_diff(args.diff_from, scenarios, checks)
    diff = ({"from": args.diff_from, "verdicts": diff_verdicts, "prev_scores": prev_scores}
            if args.diff_from else None)

    # #238 §5 判分器溯源:每轮 run 目录落指纹,report 头带行;跨轮先比哈希
    judger_hash, prev_hash = _provenance_context(args.diff_from)
    (run_dir / "judger.sha256").write_text(judger_hash + "\n", encoding="utf-8")
    provenance = {"current": judger_hash, "prev": prev_hash}
    report = render_report(out_dir, checks, scores, diff, skipped, provenance=provenance) + soften_line(
        soften_counts(results)) + caliber_section(
        facts_calibers(facts_rows), results, checks, scores, scenarios)
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", action="append", default=[],
                        help="corpus 数据集 JSON(可多次;缺省 = teaching_context pilot 20)")
    parser.add_argument("--out", help="运行根目录(cases/collect/report 落这里;跑批模式必填)")
    parser.add_argument("--diff-from", dest="diff_from", default=None,
                        help="上轮 collect 下某 run 目录(跨轮对照)")
    parser.add_argument("--render-from", dest="render_from_arg", metavar="OUT_DIR",
                        help="不跑批:从既有运行根目录(cases.jsonl/collect/…)零模型重渲染"
                             " report.md;可配 --diff-from(#257 审 P3-2,tuning_round 同款先例)")
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args(argv)

    if args.render_from_arg:
        return render_from(Path(args.render_from_arg), args.diff_from)
    if not args.out:
        parser.error("跑批模式需要 --out;纯重渲染用 --render-from <运行根目录>")

    registry = load_registry(REPO / "configs" / "models.yaml")
    probes = {name: _probe(provider.base_url) for name, provider in registry.providers.items()}
    bad = {k: v for k, v in probes.items() if v != "ok"}
    if bad:
        print(f"端点预检失败:{bad}", file=sys.stderr)
        return 1
    facts_dir = Path(tempfile.mkdtemp(prefix="corpus-round-facts-"))
    gateway = Gateway(registry, facts_dir=facts_dir)
    try:
        return _live_round(args, gateway, facts_dir)
    finally:
        # #257 审 P3-1:facts 已落 run 目录,tempdir 保留理由消失;任何退出路径不留残骸。
        shutil.rmtree(facts_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
