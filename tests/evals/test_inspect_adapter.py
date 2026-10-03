"""Inspect adapter 合同测试(#521 I5 G1):零真模型——Fake Subject + 真实 inspect-ai
runtime(mockllm 占位从不调用,solver 不走 Inspect 模型通道)。

覆盖清单(G1 逐条):
- Canonical:ok/environment/content 通过 / 未知状态、ok 无 transcript、失败行无 error
  全部 fail closed;
- Idempotency:终态 checkpoint → Subject 0 调;env 缺终态 → 补跑;guard 只看本 case
  (不扫其它 sample、不决定 pending);
- Retry:content 不进 Inspect error channel(sample success)/ EnvironmentFailure 才进
  (sample error)/ retry_on_error=0 下无外层循环(env 恰 1 次执行);
- Identity:六面(git/prompt/models/dataset/subject/harness)任一变化 → ResumeMismatch
  且 Subject 0 调(拒绝先于 Gateway/Product);
- Concurrency:to_thread 后 ≥2 个阻塞 Subject 可重叠;
- Grader:scorer 异常 → unscored/grader_failed + 降级行,checkpoint 逐字节不动。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from evalkit import write_jsonl

from edu_agent.evals import DET_SCORER_NAME as DET_NAME
from edu_agent.evals import EnvironmentFailure, ResumeMismatch, harness_identity
from edu_agent.evals import InspectRoundRequest as _Request
from edu_agent.evals import run_inspect_round, validate_canonical

OK_TRANSCRIPT = {"final_state": "completed", "turns": [], "guard_events": []}
IDENTITY = {"git_sha": "abc", "git_dirty": False, "git_diff_sha256": None,
            "prompts_sha256": "p" * 64, "models_sha256": "m" * 64}


class FakeSubject:
    """可编程假被测对象(同 test_runner 口径):按 case id 剧本出牌,记录执行区间。"""

    name = "fake-subject"

    def __init__(self, script: dict | None = None, delay_s: float = 0.0):
        self.script = script or {}
        self.delay_s = delay_s
        self.calls: list[str] = []
        self.intervals: list[tuple[float, float]] = []

    def run_case(self, case: dict) -> dict:
        self.calls.append(case["id"])
        started = time.monotonic()
        try:
            time.sleep(self.delay_s)
            outcome = self.script.get(case["id"], "ok")
            if outcome == "env":
                raise EnvironmentFailure("服务暂不可用")
            if isinstance(outcome, BaseException):
                raise outcome
            return dict(OK_TRANSCRIPT)
        finally:
            self.intervals.append((started, time.monotonic()))


class Round:
    """一轮的最小脚手架:cases.jsonl + scenarios + InspectRoundRequest 构造。"""

    def __init__(self, root: Path, case_ids: list[str], scenarios: dict | None = None):
        self.root = root
        (root / "collect").mkdir(parents=True, exist_ok=True)
        self.cases_file = write_jsonl(root / "cases.jsonl",
                                      [{"id": cid, "question": "3+4=?"} for cid in case_ids])
        self.scenarios = scenarios or {
            cid: {"id": cid, "question": "3+4=?", "student_turns": ["6"]}
            for cid in case_ids}

    def request(self, subject, identity: dict | None = None, resume_dir: Path | None = None,
                concurrency: int = 2) -> _Request:
        return _Request(
            subject=subject, gateway=None, cases_file=self.cases_file,
            scenarios=self.scenarios, identity=identity or dict(IDENTITY),
            concurrency=concurrency, judge_enabled=False,
            collect_root=self.root / "collect", resume_dir=resume_dir)


def _status_of(run_dir: Path, case_id: str) -> str:
    return json.loads((run_dir / "results" / f"{case_id}.json").read_text(encoding="utf-8"))["status"]


def _latest_log(run_dir: Path):
    from inspect_ai.log import read_eval_log
    return read_eval_log(str(sorted((run_dir / "inspect-logs").glob("*.eval"))[-1]))


def _sample_errors(run_dir: Path) -> dict[str, bool]:
    """log 面:sample 是否 error(唯一允许进入 error channel 的分类 = environment)。"""
    return {str(s.id): bool(s.error) for s in _latest_log(run_dir).samples or []}


# ---------------------------------------------------------------- Canonical ----
def test_canonical_ok_environment_content_pass_validation():
    base = {"case_id": "c1", "attempts": 1, "duration_ms": 5, "finished_at": "t"}
    assert validate_canonical({**base, "status": "ok", "error": None,
                               "transcript": OK_TRANSCRIPT})["status"] == "ok"
    for status in ("environment", "content"):
        row = validate_canonical({**base, "status": status, "error": "x",
                                  "transcript": None})
        assert row["status"] == status


@pytest.mark.parametrize("row,why", [
    ({"case_id": "c", "status": "weird", "attempts": 1, "duration_ms": 1,
      "finished_at": "t", "error": "x", "transcript": None}, "未知状态 fail closed"),
    ({"case_id": "c", "status": "ok", "attempts": 1, "duration_ms": 1,
      "finished_at": "t", "error": None, "transcript": None}, "ok 无 transcript fail closed"),
    ({"case_id": "c", "status": "environment", "attempts": 1, "duration_ms": 1,
      "finished_at": "t", "error": None, "transcript": None}, "失败行无 error fail closed"),
    ({"case_id": "c", "status": "ok", "duration_ms": 1, "finished_at": "t",
      "error": None, "transcript": OK_TRANSCRIPT}, "缺 attempts fail closed"),
])
def test_canonical_malformed_rows_fail_closed(row, why):
    with pytest.raises(ValueError, match="fail closed"):
        validate_canonical(row)


def test_canonical_case_id_must_match_sample():
    row = {"case_id": "a", "status": "ok", "attempts": 1, "duration_ms": 1,
           "finished_at": "t", "error": None, "transcript": OK_TRANSCRIPT}
    with pytest.raises(ValueError, match="case_id"):
        validate_canonical(row, sample_id="b")


def test_harness_identity_pins_inspect_version_and_lock_closure():
    import importlib.metadata
    import re as re_mod
    identity = harness_identity()
    assert identity["inspect_version"] == importlib.metadata.version("inspect-ai")
    assert re_mod.fullmatch(r"[0-9a-f]{64}", identity["adapter_sha256"])
    assert identity["task_sha256"] == identity["adapter_sha256"]  # 单文件承载,分体后分记
    assert identity["dependency_identity"].startswith("uv-lock-inspect-closure:")
    assert harness_identity() == identity  # 同 lock 同文件 → 稳定


# --------------------------------------------- Idempotency / guard(职责④)----
def test_guard_reuses_terminal_checkpoints_zero_subject_calls(tmp_path):
    rnd = Round(tmp_path, ["a", "b"])
    first = FakeSubject(script={"a": "env"})
    run_dir, _, _ = run_inspect_round(rnd.request(first))
    assert first.calls and _status_of(run_dir, "a") == "environment"
    snapshot = {f.name: f.read_bytes() for f in (run_dir / "results").glob("*.json")}
    second = FakeSubject()
    run_dir2, _, _ = run_inspect_round(rnd.request(second, resume_dir=run_dir))
    assert second.calls == ["a"]  # env 是唯一非终态:真补跑;ok 案 guard 0 调
    assert run_dir2 == run_dir
    assert (run_dir / "results" / "b.json").read_bytes() == snapshot["b.json"]  # 逐字节不动
    assert _status_of(run_dir, "a") == "ok"  # 补跑后终态;guard 不扫其它 sample


def test_guard_reuses_content_checkpoints_content_is_terminal(tmp_path):
    rnd = Round(tmp_path, ["c"])
    first = FakeSubject(script={"c": ValueError("坏题面")})
    run_dir, _, _ = run_inspect_round(rnd.request(first))
    assert _status_of(run_dir, "c") == "content"
    second = FakeSubject()
    run_inspect_round(rnd.request(second, resume_dir=run_dir))
    assert second.calls == []  # content 也是终态:0 调(合同 §6,content 不重跑)


# ------------------------------------------------- Retry / failure mapping ----
def test_content_failure_stays_sample_success_env_enters_error_channel(tmp_path):
    rnd = Round(tmp_path, ["ok1", "content1", "env1"])
    subject = FakeSubject(script={"content1": ValueError("schema violation"),
                                  "env1": "env"})
    run_dir, checks, _ = run_inspect_round(rnd.request(subject))
    errors = _sample_errors(run_dir)
    assert errors == {"ok1": False, "content1": False, "env1": True}  # 只有 env 进 error
    assert subject.calls.count("env1") == 1  # retry_on_error=0:无外层循环,恰 1 次执行
    assert _status_of(run_dir, "env1") == "environment"
    assert _status_of(run_dir, "content1") == "content"
    assert checks["content1"] == {"status": "content", "declared": False,
                                  "failures": None, "final_state": None}


def test_failure_ledger_written_in_legacy_shape(tmp_path):
    rnd = Round(tmp_path, ["env1", "content1"])
    subject = FakeSubject(script={"env1": "env", "content1": TypeError("boom")})
    run_dir, _, _ = run_inspect_round(rnd.request(subject))
    ledger = [json.loads(line) for line
              in (run_dir / "failures.jsonl").read_text(encoding="utf-8").splitlines()]
    kinds = {row["kind"] for row in ledger}
    assert kinds == {"environment", "content"}  # 与 EvalRunner._ledger 同两类同键集
    assert all(set(row) == {"ts", "case_id", "kind", "attempt", "detail"} for row in ledger)


# ------------------------------------------------------- Identity preflight ----
def test_resume_same_identity_passes_and_manifest_pins_harness(tmp_path):
    rnd = Round(tmp_path, ["x"])
    run_dir, _, _ = run_inspect_round(rnd.request(FakeSubject()))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["config"]["execution_owner"] == "inspect"
    assert manifest["identity"]["execution_owner"] == "inspect"
    assert manifest["identity"]["harness"]["inspect_version"]  # 六面之 harness 落 manifest
    again = FakeSubject()
    run_inspect_round(rnd.request(again, resume_dir=run_dir))
    assert again.calls == []  # 全终态:guard 全复用,同身份放行


@pytest.mark.parametrize("face", ["git", "prompt", "models", "dataset", "subject", "harness"])
def test_resume_six_face_mismatch_refused_before_product_calls(tmp_path, face, monkeypatch):
    rnd = Round(tmp_path, ["x"])
    run_dir, _, _ = run_inspect_round(rnd.request(FakeSubject()))
    challenger = FakeSubject()
    if face == "dataset":  # dataset 面:换 cases 文件(sha 变),被测对象不变
        rnd.cases_file = write_jsonl(tmp_path / "cases2.jsonl",
                                     [{"id": "x", "question": "5+5=?"}])
        identity = dict(IDENTITY)
    elif face == "subject":

        class OtherSubject(FakeSubject):
            name = "other-subject"  # subject 面只变 name
        challenger, identity = OtherSubject(), dict(IDENTITY)
    elif face == "harness":  # harness 面:adapter sha 漂移(经真实装配路径注入)
        identity = dict(IDENTITY)
        monkeypatch.setattr("edu_agent.evals.inspect_adapter.harness_identity",
                            lambda: {**harness_identity(), "adapter_sha256": "0" * 64})
    else:  # git / prompt / models:identity 对应键值变
        key = {"git": "git_sha", "prompt": "prompts_sha256", "models": "models_sha256"}[face]
        identity = {**IDENTITY, key: "changed"}
    with pytest.raises(ResumeMismatch):
        run_inspect_round(rnd.request(challenger, identity=identity, resume_dir=run_dir))
    assert challenger.calls == []  # 拒绝先于 Gateway/Product:0 调


def test_resume_refuses_legacy_owned_run_dir_no_silent_dual_owner(tmp_path):
    rnd = Round(tmp_path, ["x"])
    legacy_dir = rnd.root / "collect" / "cases-20261001T000000Z-legacy"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "manifest.json").write_text(json.dumps({
        "dataset": {"sha256": "0" * 64}, "config": {"sha256": "0" * 64},
        "subject": "fake-subject", "total_cases": 1,
        "identity": {**IDENTITY, "execution_owner": "evalrunner_legacy"}}), encoding="utf-8")
    subject = FakeSubject()
    with pytest.raises(ResumeMismatch, match="harness"):
        run_inspect_round(rnd.request(subject, resume_dir=legacy_dir))
    assert subject.calls == []


# ---------------------------------------------------------- Concurrency(⑩)----
def test_to_thread_restores_sample_concurrency(tmp_path):
    rnd = Round(tmp_path, ["s1", "s2", "s3"])
    subject = FakeSubject(delay_s=0.4)
    started = time.monotonic()
    run_inspect_round(rnd.request(subject, concurrency=3))
    elapsed = time.monotonic() - started
    assert len(subject.calls) == 3
    assert elapsed < 1.0  # 串行 ≥1.2s;to_thread 重叠执行 < 1.0s(I4 P6b 口径)
    events = sorted([(s, 1) for s, _ in subject.intervals]
                    + [(e, -1) for _, e in subject.intervals])
    current = peak = 0
    for _, delta in events:
        current += delta
        peak = max(peak, current)
    assert peak >= 2  # ≥2 个阻塞 Subject 真重叠


# ------------------------------------------------------- Grader isolation ----
def test_scorer_exception_isolated_unscored_and_checkpoint_untouched(tmp_path):
    # 声明了未注册 check → 真实 grader 失败路径(run_check 抛 UnknownCheck)
    broken = {"id": "g1", "question": "3+4=?", "student_turns": ["6"],
              "expect": {"checks": [{"name": "totally_unknown_check_xyz"}]}}
    rnd = Round(tmp_path, ["g1"], scenarios={"g1": broken})
    subject = FakeSubject()
    run_dir, checks, _ = run_inspect_round(rnd.request(subject))
    checkpoint_before = (run_dir / "results" / "g1.json").read_bytes()
    det = (_latest_log(run_dir).samples or [])[0].scores[DET_NAME]
    assert det.value == "unscored" and det.reason == "grader_failed"
    assert det.metadata["grader_failed"] is True
    # 隔离义务:Product evidence 不动;extraction 降级行不冒充全绿、不炸整轮
    assert (run_dir / "results" / "g1.json").read_bytes() == checkpoint_before
    assert _status_of(run_dir, "g1") == "ok"
    assert checks["g1"]["status"] == "ok" and checks["g1"]["declared"] is False
    assert "grader_failed" in checks["g1"]
