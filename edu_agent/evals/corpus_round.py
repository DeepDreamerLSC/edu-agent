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
    uv run python -m edu_agent.evals.corpus_round --config <run-spec.yaml> \
        [--plan] [--out <运行根目录>]           # #350 V0:声明式小试跑配方;--plan 零模型打印计划
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

import yaml  # 已有依赖(models.yaml 同源),#350 V0 不新增

from .judge import judge_transcript
from .kernel_subject import KernelSubject
from .runner import EvalRunner, ResumeMismatch, RunnerConfig
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
    """跑批身份(#238 件 A,GEPA 前置):git HEAD / prompt 组件 / models 配置
    + 脏工作树证据(#350 ⑧:git_dirty / git_diff_sha256——dirty 详情 patch 落 run 目录)。

    GEPA 优化对象是 prompting.py——每次迭代的可归因性从这三个哈希起步;
    机器可读进 manifest(此前只有 README 手写,不算溯源)。老轮次不回填。"""
    dirty = git_dirty_state()
    return {
        "git_sha": _git_sha(),
        "git_dirty": dirty["git_dirty"],
        "git_diff_sha256": dirty["git_diff_sha256"],
        "prompts_sha256": _file_sha256(
            REPO / "edu_agent" / "agents" / "small_lecturer" / "prompting.py"),
        "models_sha256": _file_sha256(REPO / "configs" / "models.yaml"),
    }


# === Run Spec V0(#350 用户裁定 2026-09-18:可复现的小试跑配方,不是可配置的产品) ===
# 只管怎么跑,不管产品怎么行为:状态机/prompt/泄露网/判据一概不可配(真实代码 diff 才是产品变更的证据)。
# 字段封闭集合五项 + version;优先级 CLI > run-spec > 代码默认;未知键/未知 case id fail closed。

RUN_SPEC_VERSION = 1
RUN_SPEC_KEYS = frozenset({"version", "name", "corpora", "cases", "judge", "concurrency"})


def load_run_spec(path: Path | str) -> dict:
    """读+校验 run spec(封闭键集;未知键/坏类型/坏值 fail closed,#350 ⑤)。

    spec 内相对路径按仓根解析(配方要可移植,不随 CWD 漂移);corpora 文件缺失即刻红。"""
    text = Path(path).read_text(encoding="utf-8")
    spec = yaml.safe_load(text)
    if not isinstance(spec, dict):
        raise ValueError(f"run spec 必须是映射,实际 {type(spec).__name__}")
    unknown = sorted(set(spec) - RUN_SPEC_KEYS)
    if unknown:
        raise ValueError(f"run spec 未知字段:{','.join(unknown)}"
                         f"(V0 封闭集合:{','.join(sorted(RUN_SPEC_KEYS))};"
                         "新字段先 #350 评论提案,等裁定再进代码)")
    if spec.get("version") != RUN_SPEC_VERSION:
        raise ValueError(f"version 必须为 {RUN_SPEC_VERSION}(实际 {spec.get('version')!r})")
    if not (isinstance(spec.get("name"), str) and spec["name"].strip()):
        raise ValueError("name 必须为非空字符串")
    corpora = spec.get("corpora")
    if not (isinstance(corpora, list) and corpora
            and all(isinstance(p, str) and p.strip() for p in corpora)):
        raise ValueError("corpora 必须为非空字符串路径列表")
    missing = [p for p in corpora if not _spec_repo_path(p).is_file()]
    if missing:
        raise ValueError(f"corpora 文件不存在:{','.join(missing)}(相对路径按仓根解析)")
    cases = spec.get("cases")
    if not (isinstance(cases, list) and cases
            and all(isinstance(c, str) and c.strip() for c in cases)):
        raise ValueError("cases 必须为非空字符串 id 列表(V0 只支持明确 case ID,无 query DSL)")
    if len(set(cases)) != len(cases):
        dupes = sorted({c for c in cases if cases.count(c) > 1})
        raise ValueError(f"cases 重复:{','.join(dupes)}")
    if not isinstance(spec.get("judge", True), bool):
        raise ValueError("judge 必须为布尔(缺省 true)")
    concurrency = spec.get("concurrency", 2)
    if isinstance(concurrency, bool) or not isinstance(concurrency, int) or concurrency < 1:
        raise ValueError("concurrency 必须为 ≥1 整数(缺省 2)")
    return spec


def _spec_repo_path(raw: str) -> Path:
    """spec 内相对路径按仓根解析;绝对路径原样。"""
    p = Path(raw)
    return p if p.is_absolute() else REPO / p


def resolve_spec_cases(spec_cases: list[str], scenarios: dict[str, dict]) -> list[str]:
    """spec.cases → 前缀化 case id 序列(#350 ①⑥):裸 id 单命中即解析,跨数据集
    歧义/零命中 fail fast(不静默少跑);已带前缀的 id 直接用。"""
    by_bare: dict[str, list[str]] = {}
    for prefixed, scenario in scenarios.items():
        by_bare.setdefault(scenario["id"], []).append(prefixed)
    resolved: list[str] = []
    for raw in spec_cases:
        if raw in scenarios:
            resolved.append(raw)
            continue
        matches = by_bare.get(raw, [])
        if len(matches) > 1:
            raise ValueError(f"case id 跨数据集歧义:{raw} 命中 {matches}(用前缀全名)")
        if not matches:
            raise ValueError(f"case id 不存在:{raw}(检索范围 = spec 声明的 corpora)")
        resolved.append(matches[0])
    return resolved


def merge_options(args, spec: dict | None) -> dict:
    """运行参数三级合并(#350 ④:CLI > run-spec > 代码默认)。

    corpora:CLI --corpus(可多传)> spec.corpora > DEFAULT_CORPUS;
    concurrency:--concurrency > spec > 2;judge:仅 spec 可关(缺省 true)。"""
    if args.corpus:
        corpora = list(args.corpus)
    elif spec is not None:
        corpora = [str(_spec_repo_path(p)) for p in spec["corpora"]]
    else:
        corpora = [DEFAULT_CORPUS]
    concurrency = args.concurrency
    if concurrency is None:
        concurrency = spec.get("concurrency", 2) if spec is not None else 2
    return {
        "name": spec["name"] if spec is not None else None,
        "corpora": corpora,
        "concurrency": concurrency,
        "judge": spec.get("judge", True) if spec is not None else True,
        "cases": list(spec["cases"]) if spec is not None else None,
    }


def git_dirty_state() -> dict:
    """脏工作树证据(#350 ⑧):dirty = status --porcelain 非空(含未跟踪);
    patch/diff_sha256 基于 `git diff HEAD`(已跟踪未提交改动;未跟踪文件不进
    patch,由 dirty 标记单独披露)。git 不可用时 dirty=None(不伪造)。"""
    status = _git_output("status", "--porcelain")
    if status is None:
        return {"git_dirty": None, "git_diff_sha256": None, "patch": ""}
    diff = _git_output("diff", "HEAD") or ""
    return {
        "git_dirty": bool(status.strip()),
        "git_diff_sha256": hashlib.sha256(diff.encode("utf-8")).hexdigest() if diff else None,
        "patch": diff,
    }


def _git_output(*cmd: str) -> str | None:
    """git 子命令输出(列表形参,无 shell);失败/不可用返回 None(不伪造)。"""
    try:
        out = subprocess.run(["git", *cmd], cwd=REPO, capture_output=True,
                             text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def build_plan(effective: dict, cases: list[dict]) -> dict:
    """--plan 的计划对象(#350 ②):与活跑同源解析(resolve_round),计划即事实。

    调用规模是估算口径:每案 tutor ≈ 首问 1 + 学生轮数(judge 关闭不计),
    不含修复重调/重试/降级——上界未封,数字仅供排队与夜间窗口规划。"""
    tutor_est = sum(1 + len(c.get("student_turns") or c.get("steps") or []) for c in cases)
    judge_est = len(cases) if effective["judge"] else 0
    dirty = git_dirty_state()
    return {
        "name": effective["name"],
        "corpora": effective["corpora"],
        "resolved_cases": [c["id"] for c in cases],
        "judge": effective["judge"],
        "concurrency": effective["concurrency"],
        "git_sha": _git_sha(),
        "git_dirty": dirty["git_dirty"],
        "git_diff_sha256": dirty["git_diff_sha256"],
        "call_scale": {"tutor_est": tutor_est, "judge_est": judge_est,
                       "total_est": tutor_est + judge_est,
                       "caliber": "估算:首问+每学生轮各 1 tutor;judge 每案 1;不含修复重调与重试"},
    }


def format_plan(plan: dict) -> str:
    """计划 → 人读文本(--plan 打印件;零模型调用)。"""
    scale = plan["call_scale"]
    lines = [
        f"name: {plan['name']}",
        f"corpora: {','.join(plan['corpora'])}",
        f"resolved_cases ({len(plan['resolved_cases'])}): {','.join(plan['resolved_cases'])}",
        f"judge: {'on' if plan['judge'] else 'off(0 judge calls)'}",
        f"concurrency: {plan['concurrency']}",
        f"git_sha: {plan['git_sha']}",
        f"git_dirty: {plan['git_dirty']}",
        f"git_diff_sha256: {plan['git_diff_sha256']}",
        f"call_scale: tutor≈{scale['tutor_est']} + judge≈{scale['judge_est']}"
        f" = ≈{scale['total_est']} calls({scale['caliber']})",
    ]
    return "\n".join(lines) + "\n"


def resolve_round(args, spec: dict | None) -> tuple[dict, dict[str, dict], list[dict], list[str]]:
    """corpora/cases/judge/concurrency 统一解析(#350 ①④⑥):--plan 与活跑同一条
    路径,计划打印的即活跑将执行的。"""
    effective = merge_options(args, spec)
    scenarios = real_model_scenarios([Path(p) for p in effective["corpora"]])
    if effective["cases"] is not None:
        wanted = resolve_spec_cases(effective["cases"], scenarios)
        scenarios = {case_id: scenarios[case_id] for case_id in wanted}
    cases, skipped = build_cases(scenarios)
    return effective, scenarios, cases, skipped


def judge_gate(gateway: Gateway, scenarios: dict[str, dict],
               results: list[dict], enabled: bool) -> dict[str, dict]:
    """judge 启停闸(#350 ③):关 = 硬零 judge calls(judge_rows 不进,网关零触达)。"""
    return judge_rows(gateway, scenarios, results) if enabled else {}


def dump_spec_artifacts(out_dir: Path, source_path: Path, resolved: dict) -> str:
    """run spec 双工件(#350 ⑦):source 原样拷贝 + resolved(含指纹)落运行根目录。

    指纹 = canonical JSON(resolved,排序键,去 resolved_sha256 自身)的 sha256;
    resume 身份校验(⑨)与 manifest identity 消费同一指纹。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, out_dir / "run-spec.source.yaml")
    payload = {k: v for k, v in resolved.items() if k != "resolved_sha256"}
    fingerprint = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    body = {**payload, "resolved_sha256": fingerprint}
    (out_dir / "run-spec.resolved.json").write_text(
        json.dumps(body, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return fingerprint


def resume_run_dir(collect_root: Path, cases_sha256: str, identity: dict) -> Path | None:
    """续跑闸(#350 ⑨):上轮 run 未完成 → 校验身份一致才返回该目录(续跑),
    不一致 ResumeMismatch(防拿另一份未提交代码/另一份 spec 续跑旧结果);
    上轮已完成 → None(照旧新开目录,不拦截改配方重跑)。

    身份面:git_sha / git_diff_sha256 / run_spec_sha256 / case 集哈希;
    配置与被测对象由 runner._verify_resume 在显式 run_dir 路径二次核对。"""
    runs = sorted(collect_root.glob("*-*Z-*"))
    if not runs:
        return None
    prior = runs[-1]
    manifest = json.loads((prior / "manifest.json").read_text(encoding="utf-8"))
    done = list((prior / "results").glob("*.json"))
    statuses = [json.loads(p.read_text(encoding="utf-8"))["status"] for p in done]
    incomplete = manifest["total_cases"] > len(done) or "environment" in statuses
    if not incomplete:
        return None
    prior_identity = manifest.get("identity") or {}
    mismatches = [key for key in ("git_sha", "git_diff_sha256", "run_spec_sha256")
                  if identity.get(key) != prior_identity.get(key)]
    if manifest["dataset"]["sha256"] != cases_sha256:
        mismatches.append("case 集(cases.jsonl)")
    if mismatches:
        raise ResumeMismatch(
            f"{prior} 未完成且身份不一致:{'/'.join(mismatches)}——续跑被拒,换新 --out 目录")
    return prior


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


def transcript_messages(transcript: dict) -> list[dict]:
    """存档 transcript(turns[].student/tutor + summary)→ judge messages。

    活跑(judge_rows)与 offline rescore(#254 件1)同源取数——两口径若各自维护
    会静默漂移,rescore 与活跑的 judge 输入必须逐字一致。"""
    messages: list[dict] = []
    for turn in transcript["turns"]:
        if turn["student"]:
            messages.append({"role": "user", "content": turn["student"]})
        messages.append({"role": "assistant", "content": turn["tutor"]})
    if transcript.get("summary"):
        messages.append({"role": "assistant", "content": transcript["summary"]})
    return messages


def judge_rows(gateway: Gateway, scenarios: dict[str, dict], results: list[dict]) -> dict[str, dict]:
    """ok 行 → judge 单遍 primary(评分失败记台账不炸整轮,口径同 tuning_round 单遍)。"""
    scores: dict[str, dict] = {}
    for row in results:
        if row["status"] != "ok":
            continue
        scenario = scenarios[row["case_id"]]
        question = scenario["question"]
        messages = transcript_messages(row["transcript"])
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


def judger_sha256() -> str:
    """判分器指纹:checks.py + judge.py + rubrics 资产 按文件名序拼接后 sha256(十六进制)。
    #238 §5:跨轮 diff 遇版本断点须标注;#254 P2 起含 rubrics 资产(后继纪元判据)。"""
    files = sorted((Path(__file__).parent / f)
                   for f in ("checks.py", "judge.py", "rubrics/small_lecturer_v3_2.yaml"))
    h = hashlib.sha256()
    for f in files:
        h.update(f.read_bytes())
    return h.hexdigest()


def _provenance_context(diff_from):
    """Compute current judger hash + read baseline hash (None = baseline has no provenance)."""
    judger_hash = judger_sha256()
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


def _judge_cell(score: dict, diff: dict | None, case_id: str) -> str:
    """报告 judge 列:评分失败 / judge 关闭(run-spec,#350 ③)/ 分数(带跨轮前缀)。"""
    if "error" in score:
        return f"评分失败:{score['error'][:40]}"
    if not score:
        return "judge 关闭(run-spec)"  # judge:off 的 ok 行;空分不冒充 0 分
    prev_total = ((diff or {}).get("prev_scores") or {}).get(case_id, {}).get("total")
    prefix = f"{prev_total}→" if prev_total is not None else ""
    return (f"total={prefix}{score.get('total')} {score.get('verdict')}"
            f" 追问={score.get('scores', {}).get('socratic_followup')}")


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
        judge_cell = _judge_cell(score, diff, case_id)
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


def _live_round(args, gateway: Gateway, facts_dir: Path,
                spec: dict | None = None, spec_source: Path | None = None) -> int:
    """活跑路径(#257 审 P3 后从 main 拆出:语句预算 PLR0915 + 平铺);facts
    tempdir 的清理在 main 的 finally(任何退出路径不留残骸)。
    #350:spec 在场时经 resolve_round 统一解析(CLI > spec > 默认;case 子集),
    spec 双工件与 dirty patch 落运行根目录,manifest identity 带 spec 指纹。"""
    effective, scenarios, cases, skipped = resolve_round(args, spec)
    if skipped:
        print(f"跳过无剧本场景 {len(skipped)} 条(模拟器消费面未接线,#211 边界):{','.join(skipped)}")
    if not cases:
        print("没有可跑场景(全部无剧本?)", file=sys.stderr)
        return 1
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    identity = run_identity()
    if spec is not None and spec_source is not None:
        resolved_payload = {**{k: v for k, v in effective.items() if k != "cases"},
                            "version": RUN_SPEC_VERSION,
                            "resolved_cases": [c["id"] for c in cases]}
        identity["run_spec_sha256"] = dump_spec_artifacts(out_dir, spec_source, resolved_payload)
    cases_file = out_dir / "cases.jsonl"
    cases_file.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n",
                          encoding="utf-8")
    collect_root = out_dir / "collect"
    resume_dir = resume_run_dir(collect_root, _file_sha256(cases_file), identity)
    if resume_dir is not None:
        print(f"续跑:{resume_dir}(上轮未完成,身份一致)")
    print(f"批跑:{len(cases)} 场景(真模型口径;确定性口径不在本面)→ {collect_root}")
    runner = EvalRunner(KernelSubject(gateway), RunnerConfig(concurrency=effective["concurrency"]),
                        collect_root)
    runner.run(cases_file, cases, run_dir=resume_dir, identity=identity)
    run_dir = resume_dir or sorted(collect_root.glob("*-*Z-*"))[-1]
    dirty = git_dirty_state()
    if identity.get("git_dirty") and dirty["patch"]:
        # ⑧:dirty 证据进 run 目录;仅未跟踪文件变脏时 patch 为空,由 git_diff_sha256=None 自述
        (run_dir / "worktree.patch").write_text(dirty["patch"], encoding="utf-8")
    results = load_results(run_dir)

    checks = check_rows(scenarios, results)
    if effective["judge"]:
        print(f"评分:{sum(1 for r in results if r['status'] == 'ok')} 行(judge 单遍 primary)")
        scores = judge_rows(gateway, scenarios, results)
    else:
        print("judge:off(run-spec)——本跑 0 judge calls")
        scores = {}

    def dump(path: Path, rows: dict[str, dict]) -> None:
        path.write_text("\n".join(json.dumps({"case_id": k, **v}, ensure_ascii=False)
                                  for k, v in sorted(rows.items())) + "\n", encoding="utf-8")

    # 判定与 judge 分按轮留存在各自 run 目录(与 transcript 同处 = 该轮自足可复算);
    # out_dir 根下同名文件是最新一轮的便捷副本。—— 审查 P3(2026-09-12)
    # judge:off 不落 judge-scores(空文件冒充评分面比缺文件更糟,#350 ③)
    dump(run_dir / "checks.jsonl", checks)
    dump(out_dir / "checks.jsonl", checks)
    if effective["judge"]:
        dump(run_dir / "judge-scores.jsonl", scores)
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


def _plan_mode(args, spec: dict | None) -> int:
    """--plan(#350 ②):零模型调用打印计划后退出;解析类失败干净退 2。"""
    try:
        effective, _scenarios, cases, skipped = resolve_round(args, spec)
    except ValueError as exc:
        print(f"计划解析失败:{exc}", file=sys.stderr)
        return 2
    if skipped:
        print(f"跳过无剧本场景 {len(skipped)} 条(#211 边界):{','.join(skipped)}")
    print(format_plan(build_plan(effective, cases)), end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", action="append", default=[],
                        help="corpus 数据集 JSON(可多次;缺省 = teaching_context pilot 20;"
                             "#350 ④:CLI 优先于 --config 的 corpora)")
    parser.add_argument("--out", help="运行根目录(cases/collect/report 落这里;跑批模式必填)")
    parser.add_argument("--diff-from", dest="diff_from", default=None,
                        help="上轮 collect 下某 run 目录(跨轮对照)")
    parser.add_argument("--render-from", dest="render_from_arg", metavar="OUT_DIR",
                        help="不跑批:从既有运行根目录(cases.jsonl/collect/…)零模型重渲染"
                             " report.md;可配 --diff-from(#257 审 P3-2,tuning_round 同款先例)")
    parser.add_argument("--config", type=Path, default=None,
                        help="run spec YAML(#350 V0:version/name/corpora/cases/judge/"
                             "concurrency 封闭五字段;只管怎么跑,不管产品行为)")
    parser.add_argument("--plan", action="store_true",
                        help="零模型调用:打印执行计划(resolved cases/judge 启停/并发/"
                             "git SHA/dirty/调用规模)后退出——在端点预检之前,不建网关")
    parser.add_argument("--concurrency", type=int, default=None,
                        help="并发(缺省 = run-spec 的 concurrency,再缺省 2;#350 ④ 三级优先)")
    args = parser.parse_args(argv)

    if args.render_from_arg:
        return render_from(Path(args.render_from_arg), args.diff_from)

    spec = None
    if args.config is not None:
        try:
            spec = load_run_spec(args.config)
        except ValueError as exc:
            print(f"run spec 校验失败:{exc}", file=sys.stderr)
            return 2
    if args.plan:
        return _plan_mode(args, spec)
    if not args.out:
        parser.error("跑批模式需要 --out;纯重渲染用 --render-from <运行根目录>;看计划用 --plan")

    registry = load_registry(REPO / "configs" / "models.yaml")
    probes = {name: _probe(provider.base_url) for name, provider in registry.providers.items()}
    bad = {k: v for k, v in probes.items() if v != "ok"}
    if bad:
        print(f"端点预检失败:{bad}", file=sys.stderr)
        return 1
    facts_dir = Path(tempfile.mkdtemp(prefix="corpus-round-facts-"))
    gateway = Gateway(registry, facts_dir=facts_dir)
    try:
        return _live_round(args, gateway, facts_dir, spec, args.config)
    except (ValueError, ResumeMismatch) as exc:
        # fail fast/fail closed 走干净退出码(2),不甩 traceback(夜间无人值守可读)
        print(f"运行失败:{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        # #257 审 P3-1:facts 已落 run 目录,tempdir 保留理由消失;任何退出路径不留残骸。
        shutil.rmtree(facts_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
