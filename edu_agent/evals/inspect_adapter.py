"""Inspect 执行 adapter(#521 I5):corpus_round 默认 execution owner 切到 inspect-ai
之后的 edu-agent 侧窄模块。spike(/tmp/i2 i3 i4)只抽生产必需件,不整包搬。
#521 I6-A 窄扩展:InspectRoundRequest.scenarios=None 表达 execution-only 轮
(S2 判卷电池形态——判分是 run 级确定性计算,由消费面自 checkpoint 复算,不经
Inspect scorer),task_name 可指定(Task 元数据即 provenance,不冒名 corpus 轮)。

十职责(全部单内,零调度):
  ① Subject→Inspect solver bridge ② Canonical 翻译(fail closed,合同 §4)
  ③ durable checkpoint 写(results/<case>.json,与 EvalRunner 同形——report/render/
  rescore 消费面零感知) ④ passive idempotency guard(仅 if/else:checkpoint 终态即
  复用,不判 pending/不选下一案/不排队) ⑤ strict identity preflight(六面 fail
  closed,先于 Gateway/Product) ⑥ deterministic scorer wrapper(复用 check_rows,
  语义零复制) ⑦ judge scorer wrapper(复用 judge_rows/Gateway/SCHEMA/verdict)
  ⑧ grader 异常隔离(unscored/grader_failed,经 runner.isolated_call 全仓单点)
  ⑨ Harness provenance(合同 §5-C) ⑩ asyncio.to_thread Subject 执行(同步直放会使
  Inspect max_samples 名存实亡,I4 P6/P6b 实证)。

六禁:corpus 晋升政策 / Gold / release verdict / 业务调度 / 第二 retry scheduler /
外层 retry loop。sample 调度·并发·sample 级 retry 唯一归 Inspect(本模块以
retry_on_error=0 运行,env 恢复由显式 resume 承担)+ Gateway(单次调用 retry/fallback);
checkpoint 是 Canonical durable evidence + 被动幂等守卫,不是 scheduler(I4 裁定:
主从关系 = checkpoint 目录为主、EvalLog 为视图)。

失败映射(冻结,合同 §6;I4 四行实证):
  ok→sample success→Canonical ok;content→sample success→content 不进 retry
  (content 不得抛 Inspect error,否则 retry_on_error 会错重跑);
  EnvironmentFailure→checkpoint 落档后 raise→Inspect error→environment 可 retry;
  grader→unscored/grader_failed 永不重跑 Product。EvalLog.status 仅表示 log
  artifact 状态,不覆盖 Canonical status(F1);epoch=1(F2)。
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import re
import threading
import tomllib
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from inspect_ai import Task
from inspect_ai import eval as inspect_eval
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import Score, Scorer, Target, scorer
from inspect_ai.solver import Generate, TaskState, solver

from .corpus_round import check_rows, judge_rows
from .runner import (
    EnvironmentFailure,
    ResumeMismatch,
    Subject,
    _identity_resume_diffs,
    atomic_write_json,
    execute_subject_case,
    isolated_call,
    now_iso,
    safe_case_id,
    sha256_bytes,
)
from .summary import load_results

EXECUTION_OWNER = "inspect"
REPO = Path(__file__).resolve().parents[2]
CANONICAL_FIELDS = ("case_id", "status", "attempts", "duration_ms", "finished_at",
                    "error", "transcript")
STATUS_CLOSED_SET = frozenset({"ok", "environment", "content"})
GUARD_REUSE_STATUSES = frozenset({"ok", "content"})  # env 不是终态,由 Inspect 真补跑
DET_SCORER_NAME = "edu_deterministic_checks"
JUDGE_SCORER_NAME = "edu_judge_v33"
TASK_NAME = "edu_corpus_round"
STATUS_NOTE = ("EvalLog.status 仅表示 log artifact 状态;Canonical status 以 "
               "results/*.json checkpoint / sample.metadata.edu_agent_canonical 为准(F1)")


# ------------------------------------------------------------------ Canonical ----
def validate_canonical(row: dict, sample_id: str | None = None) -> dict:
    """Canonical 七字段 fail-closed 校验(合同 §4 缺失处置):字段全集 / 状态闭集 /
    ok 行必须有 transcript / 失败行必须有 error / case_id 与 sample 对齐。"""
    missing = [field for field in CANONICAL_FIELDS if field not in row]
    if missing:
        raise ValueError(f"{row.get('case_id', '?')}: Canonical 缺字段 {missing}(fail closed)")
    if row["status"] not in STATUS_CLOSED_SET:
        raise ValueError(f"{row['case_id']}: 未知 status {row['status']!r}(fail closed,不猜)")
    if row["status"] == "ok" and row["transcript"] is None:
        raise ValueError(f"{row['case_id']}: ok 行 transcript 缺失(fail closed)")
    if row["status"] != "ok" and row["error"] is None:
        raise ValueError(f"{row['case_id']}: 失败行 error 缺失(fail closed)")
    if sample_id is not None and row["case_id"] != sample_id:
        raise ValueError(f"sample id {sample_id!r} != case_id(fail closed)")
    return {field: row[field] for field in CANONICAL_FIELDS}


def canonical_from_metadata(metadata: dict | None, sample_id: str) -> dict:
    """scorer 侧唯一取数口:sample.metadata.edu_agent_canonical → 校验后的 Canonical。"""
    canonical = (metadata or {}).get("edu_agent_canonical")
    if not isinstance(canonical, dict):
        raise ValueError(f"sample {sample_id!r} 无 edu_agent_canonical(fail closed)")
    return validate_canonical(canonical, sample_id)


# ------------------------------------------------------------- Harness identity ----
def inspect_closure_sha256(repo_root: Path = REPO) -> str:
    """uv.lock 内 inspect-ai 依赖闭包指纹(合同 §5-C 进仓后正式口径,替代 spike 的
    丢弃式 venv pip-freeze):闭包内 name==version 行排序后整体 sha256。"""
    lock = tomllib.loads((repo_root / "uv.lock").read_text(encoding="utf-8"))
    packages = {p["name"]: p for p in lock.get("package", [])}

    def dep_name(dep) -> str:
        if isinstance(dep, str):
            return re.split(r"[<>=!~;\[]", dep)[0].strip()
        return dep.get("name", "")

    seen: set[str] = set()
    queue = ["inspect-ai"]
    while queue:
        name = queue.pop()
        if name in seen or name not in packages:
            continue
        seen.add(name)
        queue.extend(dep_name(dep) for dep in packages[name].get("dependencies", []) or [])
    lines = sorted(f"{name}=={packages[name]['version']}" for name in seen)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def harness_identity(repo_root: Path = REPO) -> dict:
    """Harness Identity(合同 §5-C):Inspect 版本变更 = Harness change,不是透明升级。"""
    adapter_sha = sha256_bytes(Path(__file__).read_bytes())
    return {
        "execution_owner": EXECUTION_OWNER,
        "inspect_version": importlib.metadata.version("inspect-ai"),
        "adapter_sha256": adapter_sha,
        "task_sha256": adapter_sha,  # solver bridge 与 adapter 同文件;分体实现后分记
        "dependency_identity": f"uv-lock-inspect-closure:{inspect_closure_sha256(repo_root)}",
    }


# ------------------------------------------------------- solver bridge(职责①③④⑩)----
def _make_ledger(run_dir: Path, lock: threading.Lock) -> Callable[[str, str, str], None]:
    """failures.jsonl writer(与 EvalRunner._ledger 同行形状——晨间摘要消费面零感知)。"""
    def write(case_id: str, kind: str, detail: str) -> None:
        line = json.dumps({"ts": now_iso(), "case_id": case_id, "kind": kind,
                           "attempt": 1, "detail": detail[:500]}, ensure_ascii=False)
        with lock:
            with (run_dir / "failures.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    return write


def _execute_and_checkpoint(subject: Subject, case: dict, case_id: str, ledger,
                            checkpoint: Path) -> tuple[dict, bool]:
    """线程体内执行 Subject 并即刻落 checkpoint:durable evidence 的写出不受事件循环
    取消影响(I4 P4:SIGINT 落在 in-flight 案时,线程照常完成并落档,该案成为
    「checkpoint 在、log 缺」的 gap 态,由 guard 在 resume 时 0 调复用)。"""
    result, retryable = execute_subject_case(subject, case, case_id, ledger)
    atomic_write_json(checkpoint, result)
    return result, retryable


def make_bridge_solver(subject: Subject, run_dir: Path):
    """Subject bridge solver:guard(if/else)→ to_thread 执行+落档 → 映射。"""
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    ledger = _make_ledger(run_dir, threading.Lock())

    @solver(name="edu_subject_bridge")
    def _factory():
        async def solve(state: TaskState, generate: Generate) -> TaskState:
            case_id = str(state.sample_id)
            checkpoint = results_dir / f"{case_id}.json"
            if checkpoint.is_file():  # 被动幂等守卫:只看本 case 的终态 checkpoint
                prior = validate_canonical(
                    json.loads(checkpoint.read_text(encoding="utf-8")), case_id)
                if prior["status"] in GUARD_REUSE_STATUSES:
                    state.metadata["edu_agent_canonical"] = prior
                    state.metadata["execution_provenance"] = {
                        "execution_owner": EXECUTION_OWNER,
                        "evidence_origin": "checkpoint_guard_reuse",
                        "inspect_role": "execution_owner", "guard_reuse": True}
                    return state
            case = json.loads(state.input)
            result, retryable = await asyncio.to_thread(
                _execute_and_checkpoint, subject, case, case_id, ledger, checkpoint)
            state.metadata["edu_agent_canonical"] = result
            state.metadata["execution_provenance"] = {
                "execution_owner": EXECUTION_OWNER,
                "evidence_origin": "inspect_execution",
                "inspect_role": "execution_owner", "guard_reuse": False}
            if retryable:  # environment:唯一进入 Inspect error channel 的分类
                raise EnvironmentFailure(result["error"] or "environment failure")
            return state  # ok/content:sample 执行成功,content 不进 retry_on_error
        return solve
    return _factory()


# ---------------------------------------------------- scorer wrappers(职责⑥⑦⑧)----
def _grader_isolated(action: Callable[[], Score]) -> Score:
    """grader 异常隔离(职责⑧):裸异常→unscored/grader_failed,不炸 Product
    evidence、不触发任何 Product 重跑;捕获经 runner.isolated_call 全仓单点。"""
    def on_error(exc: BaseException) -> Score:
        return Score(value="unscored", reason="grader_failed",
                     metadata={"scoring_status": "unscored", "grader_failed": True,
                               "error": f"{type(exc).__name__}: {exc}"[:200]})
    return isolated_call(action, on_error)


def _check_one(state: TaskState, scenarios: dict[str, dict]) -> Score:
    canonical = canonical_from_metadata(state.metadata, str(state.sample_id))
    case_id = canonical["case_id"]
    # check_rows 自带非 ok 行形态(status/declared=False/failures=None),零复制
    row = check_rows({case_id: scenarios[case_id]}, [canonical])[case_id]
    return Score(value="scored", metadata={"scoring_status": "scored", "check_row": row})


def make_deterministic_scorer(scenarios: dict[str, dict]) -> Scorer:
    """deterministic checks wrapper:check_rows 原函数单案调用,语义零复制、零模型调用。"""
    @scorer(name=DET_SCORER_NAME, metrics=[])
    def _factory() -> Scorer:
        async def score(state: TaskState, target: Target) -> Score:
            return _grader_isolated(lambda: _check_one(state, scenarios))
        return score
    return _factory()


def _judge_one(state: TaskState, gateway, scenarios: dict[str, dict]) -> Score:
    canonical = canonical_from_metadata(state.metadata, str(state.sample_id))
    if canonical["status"] != "ok":
        return Score(value="not-scored",
                     metadata={"scoring_status": "not-scored",
                               "note": "非 ok 行不评(legacy judge_rows 同口径)"})
    payload = judge_rows(gateway, scenarios, [canonical])[canonical["case_id"]]
    return Score(value=payload.get("verdict", "judge-error"),
                 metadata={"scoring_status": "scored", "judge_payload": payload})


def make_judge_scorer(gateway, scenarios: dict[str, dict]) -> Scorer:
    """v3.3 Judge wrapper:judge_rows 原路径(Gateway/SCHEMA/verdict)单案调用;
    非 ok 行不评(legacy judge_rows 同口径);HTTP 阻塞段 to_thread 不卡并发。"""
    @scorer(name=JUDGE_SCORER_NAME, metrics=[])
    def _factory() -> Scorer:
        async def score(state: TaskState, target: Target) -> Score:
            action = lambda: _judge_one(state, gateway, scenarios)  # to_thread 零参回调
            return await asyncio.to_thread(_grader_isolated, action)
        return score
    return _factory()


# ----------------------------------------------------- identity preflight(职责⑤)----
@dataclass(frozen=True)
class InspectRoundRequest:
    """run_inspect_round 入参束(PLR0913:路径/身份/配置/场景一次收口)。

    scenarios=None = execution-only(#521 I6-A,S2 判卷电池):不装配 corpus scorer,
    返回 (run_dir, {}, {})——GA/GB/VOID 等 run 级判分由消费面自 results/*.json
    checkpoint 复算,判分语义不复制进 adapter。task_name 随消费面命名(provenance
    不冒名 corpus 轮;缺省 = corpus 轮名)。"""

    subject: Subject
    gateway: object
    cases_file: Path
    scenarios: dict | None
    identity: dict
    concurrency: int
    judge_enabled: bool
    collect_root: Path
    resume_dir: Path | None
    task_name: str = TASK_NAME


def _verify_resume_identity(run_dir: Path, request: InspectRoundRequest,
                            dataset_sha: str, config_sha: str) -> None:
    """strict 六面续跑门(先于 Gateway invoke/Product 调用):stored/current 两边必须
    存在且全等(#490 口径);dataset/subject/config 与 identity 六面合成同一比较视图,
    跨 owner(harness 面缺或多)同样 fail closed——不允许 legacy/Inspect 混续同一 run。"""
    try:
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ResumeMismatch(f"{run_dir} 不是可续跑的 run 目录(无 manifest)") from exc
    stored = {**(manifest.get("identity") or {}),
              "dataset_sha256": manifest["dataset"]["sha256"],
              "subject": manifest["subject"], "config_sha256": manifest["config"]["sha256"]}
    current = {**request.identity, "dataset_sha256": dataset_sha,
               "subject": request.subject.name, "config_sha256": config_sha}
    problems = _identity_resume_diffs(stored, current)
    if problems:
        raise ResumeMismatch(
            f"{run_dir} 的运行身份不满足 strict 续跑条件({'; '.join(problems)}),请新开 run 目录")


def _prepare_run_dir(request: InspectRoundRequest, dataset_sha: str,
                     config_sha: str, total_cases: int) -> Path:
    """run 目录与 manifest(同 EvalRunner 形状 + execution_owner/harness 面);resume
    先过六面门,后建/复用目录。"""
    if request.resume_dir is not None:
        _verify_resume_identity(Path(request.resume_dir), request, dataset_sha, config_sha)
        return Path(request.resume_dir)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = request.collect_root / f"{request.cases_file.stem}-{stamp}-{uuid.uuid4().hex[:4]}"
    target.mkdir(parents=True)
    atomic_write_json(target / "manifest.json", {
        "started_at": now_iso(),
        "dataset": {"name": request.cases_file.name, "sha256": dataset_sha},
        "config": {"execution_owner": EXECUTION_OWNER,
                   "concurrency": request.concurrency, "retry_on_error": 0,
                   "sha256": config_sha},
        "subject": request.subject.name,
        "total_cases": total_cases,
        "identity": request.identity,
    })
    return target


# ------------------------------------------------------------- round execution ----
def _read_case_lines(request: InspectRoundRequest) -> list[str]:
    text = request.cases_file.read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line.strip()]


def _case_samples(lines: list[str]) -> list[Sample]:
    """cases.jsonl 行 → Inspect samples:id 用 safe_case_id(legacy checkpoint 同口径),
    input 为原行文本(Subject 输入与 legacy 逐字同源),target 恒空(Gold 不迁入)。"""
    samples = []
    for index, line in enumerate(lines):
        case = json.loads(line)
        samples.append(Sample(id=safe_case_id(case.get("id", case.get("case_id")), index),
                              input=line, target=""))
    return samples


def _build_task(request: InspectRoundRequest, run_dir: Path) -> Task:
    """Inspect Task 装配:scorer 语义全在 edu-agent 侧 wrapper(职责⑥⑦),样本集与
    Subject 输入同 legacy 一条 cases.jsonl,不建第二套 dataset truth。scenarios=None
    (execution-only)不装 scorer——该形态的判分是 run 级计算,归消费面。"""
    samples = MemoryDataset(samples=_case_samples(_read_case_lines(request)),
                            name=request.cases_file.stem)
    scorers: list[Scorer] = []
    if request.scenarios is not None:
        scorers.append(make_deterministic_scorer(request.scenarios))
        if request.judge_enabled:
            scorers.append(make_judge_scorer(request.gateway, request.scenarios))
    return Task(name=request.task_name, dataset=samples,
                solver=make_bridge_solver(request.subject, run_dir),
                scorer=scorers or None, metadata={
                    "execution_owner": EXECUTION_OWNER,
                    "evidence_origin": "inspect_execution",
                    "inspect_role": "execution_owner",
                    "harness": harness_identity(),
                    "status_note": STATUS_NOTE, "epochs": 1})


def _write_execution_provenance(run_dir: Path, log, request: InspectRoundRequest) -> None:
    """execution.json:Harness/execution 面 run 后落档(EvalLog version、log 状态、
    checkpoint-主/EvalLog-视图主从披露)。"""
    atomic_write_json(run_dir / "execution.json", {
        "execution_owner": EXECUTION_OWNER,
        "harness": harness_identity(),
        "inspect_version": importlib.metadata.version("inspect-ai"),
        "evallog_version": getattr(log, "version", None),
        "evallog_status": getattr(log, "status", None),
        "evallog_location": getattr(log, "location", None),
        "checkpoint_vs_evallog": "checkpoint 目录为主(Canonical),EvalLog 为视图(I4)",
        "max_samples": request.concurrency, "retry_on_error": 0, "epochs": 1,
        "finished_at": now_iso(),
    })


def _degraded_check_row(row: dict, exc: BaseException) -> dict:
    """grader 失败行的降级形态(职责⑧ 的 extraction 面):不冒充全绿(declared=False
    + grader_failed 披露)、不炸整轮;Product evidence(checkpoint)不受影响。"""
    ok = row["status"] == "ok"
    return {"status": row["status"], "declared": False, "failures": None,
            "final_state": (row.get("transcript") or {}).get("final_state") if ok else None,
            "grader_failed": f"{type(exc).__name__}: {exc}"[:200]}


def _fallback_check_row(row: dict, case_id: str, scenarios: dict) -> dict:
    """兜底 check 行(同隔离内):checkpoint 行 + 场景走 check_rows 原函数。"""
    return isolated_call(
        lambda: check_rows({case_id: scenarios[case_id]}, [row])[case_id],
        lambda exc: _degraded_check_row(row, exc))


def extract_scoring(log, run_dir: Path, scenarios: dict, judge_enabled: bool) -> tuple[dict, dict]:
    """EvalLog → (checks 行, judge payloads):report/render/diff 消费面拿到的仍是
    legacy 形状,无须知道 Inspect 私有结构。checkpoint 为 master:未进 log/未评分的
    行(env error、cancelled、grader 失败)由 check_rows 对 checkpoint 行兜底(隔离
    内),不静默缺行。"""
    sample_scores = {str(s.id): (s.scores or {}) for s in (log.samples or [])}
    rows = load_results(run_dir)
    checks: dict[str, dict] = {}
    scores: dict[str, dict] = {}
    for row in rows:
        case_id = row["case_id"]
        scores_of = sample_scores.get(case_id, {})
        det = scores_of.get(DET_SCORER_NAME)
        check_row = ((det.metadata or {}) if det else {}).get("check_row")
        checks[case_id] = check_row if check_row else _fallback_check_row(row, case_id, scenarios)
        judge = scores_of.get(JUDGE_SCORER_NAME)
        payload = ((judge.metadata or {}) if judge else {}).get("judge_payload")
        if judge_enabled and payload is not None:
            scores[case_id] = payload
    return checks, scores


def run_inspect_round(request: InspectRoundRequest) -> tuple[Path, dict, dict]:
    """Inspect execution owner 主入口:preflight → task 装配 → eval(调度/并发/retry
    归 Inspect)→ extraction。SIGINT/cancel → KeyboardInterrupt(与 legacy Ctrl-C
    同出口,corpus_round finally 的 facts 保全照常生效)。"""
    request = replace(request, identity={**request.identity,
                                         "execution_owner": EXECUTION_OWNER,
                                         "harness": harness_identity()})
    dataset_sha = sha256_bytes(request.cases_file.read_bytes())
    config = {"execution_owner": EXECUTION_OWNER, "concurrency": request.concurrency,
              "retry_on_error": 0}
    config_sha = sha256_bytes(json.dumps(config, sort_keys=True).encode())
    run_dir = _prepare_run_dir(request, dataset_sha, config_sha, len(_read_case_lines(request)))
    task = _build_task(request, run_dir)
    logs = inspect_eval(
        task, model="mockllm/model",  # 占位:bridge 不经 Inspect 模型通道,零调用
        max_samples=request.concurrency, retry_on_error=0, fail_on_error=False,
        log_dir=str(run_dir / "inspect-logs"), display="plain", log_level="error")
    if not logs or logs[0].status == "cancelled":
        raise KeyboardInterrupt  # SIGINT:checkpoint 已原子落档,续跑由 guard 复用
    log = logs[0]
    _write_execution_provenance(run_dir, log, request)
    if request.scenarios is None:  # execution-only:无 scorer 面,消费面自 checkpoint 取数
        return run_dir, {}, {}
    if request.judge_enabled:
        print(f"评分:{sum(1 for r in load_results(run_dir) if r['status'] == 'ok')} 行(judge 单遍 primary)")
    else:
        print("judge:off(run-spec)——本跑 0 judge calls")
    return run_dir, *extract_scoring(log, run_dir, request.scenarios, request.judge_enabled)
