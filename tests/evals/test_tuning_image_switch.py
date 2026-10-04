"""tuning_round + image_teaching_round Inspect consumer switch 合同(#521 I6-C C1-A G1):
同批一次验两面(处置矩阵 #3/#4)。零真模型——默认路径走真实 inspect_adapter
(execution-only 轮,scenarios=None,判分语义留两脚本),legacy 走显式 `--legacy-runner`。

覆盖清单(逐条):
- 默认 owner = Inspect:run_inspect_round 接线(scenarios=None/identity/task_name/
  concurrency)且 EvalRunner 零构造;identity 明示 execution_owner=inspect;
- End-to-end:假被测对象出 canned transcript → checkpoint Canonical 七字段 →
  to_judge_cases → 假 judge → comparison/report 全链不塌;manifest 带 harness 面,
  EvalLog 零 scorer 面(execution-only);
- 禁自动 fallback:Inspect 路径异常直接传播,不回落 EvalRunner;
- legacy 显式可用:manifest identity 明示 evalrunner_legacy,无 Inspect 工件;
- 身份面(每脚本抽 2 面:git/prompts):任一变化 → ResumeMismatch 且 0 调
  (机制共享已证,此处只验两脚本接线参与同一 strict preflight);
- 跨 owner:legacy-owned run 目录被脚本同形 Inspect 请求拒绝(禁双 owner 同 run)。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import scripts.image_teaching_round as image_round
import scripts.tuning_round as tuning_round
from edu_agent.evals import (
    InspectRoundRequest,
    ResumeMismatch,
    load_scenarios,
    run_identity,
    run_inspect_round,
    to_cases,
)

_REPO = Path(__file__).resolve().parents[2]
_DATASET = _REPO / "edu_agent" / "evals" / "datasets" / "small_lecturer_image_teaching_v1.json"


def _transcript(case: dict) -> dict:
    """canned ok transcript:1 首问 + 1 学生轮(报告层按 1/N 截断如实渲染)。"""
    return {
        "final_state": "completed",
        "turns": [
            {"student": "", "tutor": "首问:先想想已知条件。", "state": "first_question_ready"},
            {"student": (case.get("student_turns") or ["嗯。"])[0], "tutor": "很好,总结一下。",
             "state": "completed"},
        ],
        "summary": "总结:已收束。",
        "learner": {"grade": case.get("grade", "")},
        "guard_events": [],
    }


class FakeKernelSubject:
    """假内核被测对象(Subject 协议):canned transcript,计数 case 验 0 调/1 案 1 调。"""

    name = "fake-kernel"
    last: "FakeKernelSubject | None" = None

    def __init__(self, gateway):
        self.gateway = gateway
        self.calls: list[str] = []
        FakeKernelSubject.last = self

    def run_case(self, case: dict) -> dict:
        self.calls.append(case["id"])
        return _transcript(case)


class FakeGateway:
    """零真模型合同:收集/判分全假,gateway.invoke 被触达即红。"""

    last: "FakeGateway | None" = None

    def __init__(self, registry, facts_dir=None):
        FakeGateway.last = self
        self.invokes = 0

    def invoke(self, request):
        self.invokes += 1
        raise AssertionError("零真模型合同测试:gateway.invoke 不应被触达")

    def close(self):
        pass


class _ScriptJudge:
    """judge 单遍 primary 假实现:计数调用 + 六维满分(报告层全链可渲染)。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, gateway, case, role="judge", session_id=None):
        self.calls.append(case["id"])
        return {"scores": {dim: 2 for dim in tuning_round.DIMENSIONS}, "total": 12,
                "answer_leaked": False, "math_integrity": 2, "evidence": "canned",
                "verdict": "pass", "judge_model": "fake-judge"}


def _fake_judge() -> _ScriptJudge:
    return _ScriptJudge()


def _run_tuning(monkeypatch, tmp_path, legacy: bool = False):
    argv = ["tuning_round", "--out", str(tmp_path / "out")]
    if legacy:
        argv.append("--legacy-runner")
    return _run_main(monkeypatch, tmp_path, tuning_round, argv)


def _run_image(monkeypatch, tmp_path, legacy: bool = False):
    argv = ["image_teaching_round", "--dataset", str(_DATASET),
            "--out", str(tmp_path / "out")]
    if legacy:
        argv.append("--legacy-runner")
    return _run_main(monkeypatch, tmp_path, image_round, argv)


def _run_main(monkeypatch, tmp_path, module, argv: list[str]):
    monkeypatch.setattr(module, "Gateway", FakeGateway)
    monkeypatch.setattr(module, "KernelSubject", FakeKernelSubject)
    judge = _fake_judge()
    monkeypatch.setattr(module, "judge_transcript", judge)
    (tmp_path / "facts").mkdir(exist_ok=True)
    monkeypatch.setenv("EDU_FACTS_DIR", str(tmp_path / "facts"))
    monkeypatch.setattr(sys, "argv", argv)
    FakeGateway.last = None
    FakeKernelSubject.last = None
    module.main()
    assert FakeGateway.last is not None and FakeGateway.last.invokes == 0  # 零真模型
    return judge


def _write_checkpoints(run_dir: Path, cases: list[dict]) -> None:
    (run_dir / "results").mkdir(parents=True, exist_ok=True)
    for case in cases:
        (run_dir / "results" / f"{case['id']}.json").write_text(json.dumps({
            "case_id": case["id"], "status": "ok", "attempts": 1, "duration_ms": 1,
            "finished_at": "t", "error": None, "transcript": _transcript(case)},
            ensure_ascii=False), encoding="utf-8")


def _latest_collect(tmp_path: Path) -> Path:
    return sorted((tmp_path / "out" / "collect").glob("cases-*"))[-1]


def _image_cases() -> list[dict]:
    return to_cases(load_scenarios(_DATASET))


# ------------------------------------------------------- 默认 owner = Inspect ----
def test_tuning_default_wires_inspect_and_never_constructs_evalrunner(tmp_path, monkeypatch):
    captured = {}
    run_dir = tmp_path / "out" / "collect" / "pre-made"
    _write_checkpoints(run_dir, tuning_round.CASES)

    def spy_run(request):
        captured["request"] = request
        return run_dir, {}, {}

    monkeypatch.setattr(tuning_round, "run_inspect_round", spy_run)
    monkeypatch.setattr(tuning_round, "EvalRunner",
                        lambda *a, **k: pytest.fail("默认路径禁触 EvalRunner(legacy 需显式 --legacy-runner)"))
    judge = _run_tuning(monkeypatch, tmp_path)
    request = captured["request"]
    assert request.scenarios is None and request.judge_enabled is False  # execution-only
    assert request.task_name == "edu_tuning_round"  # provenance 不冒名 corpus 轮
    assert request.identity["execution_owner"] == "inspect"  # owner 明示
    assert request.concurrency == 2  # 与 legacy RunnerConfig 同并发(G2 配对前提)
    assert request.resume_dir is None and request.collect_root == tmp_path / "out" / "collect"
    assert request.cases_file == tmp_path / "out" / "cases.jsonl"
    assert request.subject is FakeKernelSubject.last
    assert sorted(judge.calls) == sorted(c["id"] for c in tuning_round.CASES)  # 判分仍走脚本


def test_image_default_wires_inspect_and_never_constructs_evalrunner(tmp_path, monkeypatch):
    captured = {}
    run_dir = tmp_path / "out" / "collect" / "pre-made"
    _write_checkpoints(run_dir, _image_cases())

    def spy_run(request):
        captured["request"] = request
        return run_dir, {}, {}

    monkeypatch.setattr(image_round, "run_inspect_round", spy_run)
    monkeypatch.setattr(image_round, "EvalRunner",
                        lambda *a, **k: pytest.fail("默认路径禁触 EvalRunner(legacy 需显式 --legacy-runner)"))
    judge = _run_image(monkeypatch, tmp_path)
    request = captured["request"]
    assert request.scenarios is None and request.judge_enabled is False  # execution-only
    assert request.task_name == "edu_image_teaching_round"
    assert request.identity["execution_owner"] == "inspect"
    assert request.concurrency == 2 and request.resume_dir is None
    assert sorted(judge.calls) == sorted(c["id"] for c in _image_cases())  # 判分仍走脚本


def test_tuning_default_inspect_end_to_end_manifest_and_checkpoints(tmp_path, monkeypatch):
    """真 adapter 端到端:owner/harness 面进 manifest,checkpoint = Canonical 七字段,
    EvalLog 零 scorer 面,comparison.md 全链不塌(11 场景全量)。"""
    monkeypatch.setattr(tuning_round, "EvalRunner",
                        lambda *a, **k: pytest.fail("默认路径禁触 EvalRunner"))
    judge = _run_tuning(monkeypatch, tmp_path)
    assert sorted(FakeKernelSubject.last.calls) == sorted(c["id"] for c in tuning_round.CASES)
    assert len(judge.calls) == 11
    run_dir = _latest_collect(tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["config"]["execution_owner"] == "inspect"
    assert manifest["identity"]["execution_owner"] == "inspect"
    assert manifest["identity"]["harness"]["inspect_version"]  # harness 面落档
    assert manifest["subject"] == "fake-kernel"
    for case in tuning_round.CASES:
        row = json.loads((run_dir / "results" / f"{case['id']}.json").read_text(encoding="utf-8"))
        assert set(row) == {"case_id", "status", "attempts", "duration_ms",
                            "finished_at", "error", "transcript"}  # Canonical 七字段
        assert row["status"] == "ok"
    execution = json.loads((run_dir / "execution.json").read_text(encoding="utf-8"))
    assert execution["execution_owner"] == "inspect" and execution["retry_on_error"] == 0
    from inspect_ai.log import read_eval_log
    log = read_eval_log(str(sorted((run_dir / "inspect-logs").glob("*.eval"))[-1]))
    assert all(not (s.scores or {}) for s in log.samples or [])  # execution-only:零 scorer
    report = (tmp_path / "out" / "comparison.md").read_text(encoding="utf-8")
    assert "| 场景 | R1 | R2 | 本轮 | 判定 |" in report and "达标" in report  # 主表全链不塌


def test_image_default_inspect_end_to_end_manifest_and_checkpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(image_round, "EvalRunner",
                        lambda *a, **k: pytest.fail("默认路径禁触 EvalRunner"))
    judge = _run_image(monkeypatch, tmp_path)
    cases = _image_cases()
    assert sorted(FakeKernelSubject.last.calls) == sorted(c["id"] for c in cases)
    assert len(judge.calls) == len(cases)
    run_dir = _latest_collect(tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["config"]["execution_owner"] == "inspect"
    assert manifest["identity"]["execution_owner"] == "inspect"
    assert manifest["identity"]["harness"]["inspect_version"]
    execution = json.loads((run_dir / "execution.json").read_text(encoding="utf-8"))
    assert execution["execution_owner"] == "inspect" and execution["retry_on_error"] == 0
    from inspect_ai.log import read_eval_log
    log = read_eval_log(str(sorted((run_dir / "inspect-logs").glob("*.eval"))[-1]))
    assert all(not (s.scores or {}) for s in log.samples or [])  # execution-only:零 scorer
    report = (tmp_path / "out" / "comparison.md").read_text(encoding="utf-8")
    assert f"pass {len(cases)}/{len(cases)}" in report


# ------------------------------------------------- 禁自动 fallback / legacy 显式 ----
def test_tuning_inspect_failure_propagates_no_silent_fallback(tmp_path, monkeypatch):
    def boom(request):
        raise RuntimeError("inspect down")

    monkeypatch.setattr(tuning_round, "run_inspect_round", boom)
    monkeypatch.setattr(tuning_round, "EvalRunner",
                        lambda *a, **k: pytest.fail("禁自动 fallback:Inspect 失败不得回落 EvalRunner"))
    with pytest.raises(RuntimeError, match="inspect down"):
        _run_tuning(monkeypatch, tmp_path)


def test_image_inspect_failure_propagates_no_silent_fallback(tmp_path, monkeypatch):
    def boom(request):
        raise RuntimeError("inspect down")

    monkeypatch.setattr(image_round, "run_inspect_round", boom)
    monkeypatch.setattr(image_round, "EvalRunner",
                        lambda *a, **k: pytest.fail("禁自动 fallback:Inspect 失败不得回落 EvalRunner"))
    with pytest.raises(RuntimeError, match="inspect down"):
        _run_image(monkeypatch, tmp_path)


def test_tuning_legacy_runner_explicit(tmp_path, monkeypatch):
    """"--legacy-runner:EvalRunner 旧执行面 + manifest identity 明示 evalrunner_legacy,
    无 Inspect 工件(一次 execution 只有一个 owner)。"""
    monkeypatch.setattr(tuning_round, "run_inspect_round",
                        lambda *a, **k: pytest.fail("legacy 显式路径禁触 Inspect(禁双 owner)"))
    judge = _run_tuning(monkeypatch, tmp_path, legacy=True)
    run_dir = _latest_collect(tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["identity"]["execution_owner"] == "evalrunner_legacy"  # owner 明示
    assert not (run_dir / "execution.json").exists()  # 无 Inspect 工件
    assert not (run_dir / "inspect-logs").exists()
    assert len(list((run_dir / "results").glob("*.json"))) == len(tuning_round.CASES)
    assert len(judge.calls) == 11
    assert (tmp_path / "out" / "comparison.md").is_file()


def test_image_legacy_runner_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(image_round, "run_inspect_round",
                        lambda *a, **k: pytest.fail("legacy 显式路径禁触 Inspect(禁双 owner)"))
    judge = _run_image(monkeypatch, tmp_path, legacy=True)
    run_dir = _latest_collect(tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["identity"]["execution_owner"] == "evalrunner_legacy"
    assert not (run_dir / "execution.json").exists()
    assert not (run_dir / "inspect-logs").exists()
    assert len(list((run_dir / "results").glob("*.json"))) == len(_image_cases())
    assert len(judge.calls) == len(_image_cases())
    assert (tmp_path / "out" / "comparison.md").is_file()


# ------------------------------------------- 身份面(G4/G5:接线参与共享 preflight)----
_CASES_ROWS = [{"id": "switch_face_case_1", "question": "解方程 x+2=5。", "grade": "五年级",
                "reference_answer": "x=3", "student_turns": ["x=3。"]}]


def _cases_file(tmp_path: Path) -> Path:
    path = tmp_path / "cases.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in _CASES_ROWS) + "\n",
                    encoding="utf-8")
    return path


def _script_request(cases_file: Path, subject, identity: dict, collect: Path,
                    resume_dir: Path | None, task_name: str) -> InspectRoundRequest:
    """脚本默认路径同形请求(execution-only;identity = run_identity + owner)。"""
    return InspectRoundRequest(
        subject=subject, gateway=None, cases_file=cases_file, scenarios=None,
        identity=identity, concurrency=2, judge_enabled=False,
        collect_root=collect, resume_dir=resume_dir, task_name=task_name)


_CONSUMERS = [pytest.param(tuning_round, "edu_tuning_round", id="tuning"),
              pytest.param(image_round, "edu_image_teaching_round", id="image")]


@pytest.mark.parametrize("module,task", _CONSUMERS)
@pytest.mark.parametrize("face", ["git_sha", "prompts_sha256"])
def test_resume_identity_face_mismatch_refused_before_any_call(tmp_path, module, task, face):
    """两脚本同款身份(run_identity + owner)任一面变化 → ResumeMismatch 且 0 调
    (strict preflight 先于 Gateway/Product;机制共享已证,此处验接线)。"""
    cases_file = _cases_file(tmp_path)
    identity = {**run_identity(), "execution_owner": "inspect"}
    first = FakeKernelSubject(None)
    run_dir, _, _ = run_inspect_round(
        _script_request(cases_file, first, identity, tmp_path / "collect", None, task))
    assert len(first.calls) == 1  # 首跑 1 调
    challenger = FakeKernelSubject(None)
    with pytest.raises(ResumeMismatch):
        run_inspect_round(_script_request(
            cases_file, challenger, {**identity, face: "changed"},
            tmp_path / "collect", run_dir, task))
    assert challenger.calls == []  # 拒绝先于 Gateway/Product:0 调


@pytest.mark.parametrize("module,task", _CONSUMERS)
def test_inspect_resume_refuses_legacy_owned_run_dir(tmp_path, module, task):
    """跨 owner 混续拒绝(禁双 owner 同 run;与 corpus/S2 路径同语义)。"""
    cases_file = _cases_file(tmp_path)
    legacy_dir = tmp_path / "collect" / "cases-20261004T000000Z-legacy"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "manifest.json").write_text(json.dumps({
        "dataset": {"sha256": "0" * 64}, "config": {"sha256": "0" * 64},
        "subject": "fake-kernel", "total_cases": 1,
        "identity": {**run_identity(), "execution_owner": "evalrunner_legacy"},
    }), encoding="utf-8")
    subject = FakeKernelSubject(None)
    with pytest.raises(ResumeMismatch, match="harness"):
        run_inspect_round(_script_request(
            cases_file, subject, {**run_identity(), "execution_owner": "inspect"},
            tmp_path / "collect", legacy_dir, task))
    assert subject.calls == []
