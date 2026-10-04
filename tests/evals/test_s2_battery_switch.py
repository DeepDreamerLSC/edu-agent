"""S2 battery Inspect consumer switch 合同(#521 I6-A G1;I6-C C3 起唯一执行面):
零真模型——路径走真实 inspect_adapter(execution-only 轮);`--legacy-runner`
过渡回退已删,模块不再暴露 EvalRunner(防复活断言)。

覆盖清单(逐条):
- owner = Inspect:run_inspect_round 接线(task/scenarios=None/identity/根目录)
  且模块无 EvalRunner 可构造;manifest 明示 execution_owner=inspect + harness 面;
- End-to-end:假 gateway 出 S2 双轴 payload → checkpoint Canonical 七字段 →
  _score/_report 全链不塌;expected 泄露防火墙经 bridge 后原样(P1-2);
- Resume:同身份续跑 guard 0 调、checkpoint 逐字节不动;
- Strict identity:S2 六面(git/rubric/prompt/battery/models/judge_primary)+
  dataset/subject/harness 任一变化 → ResumeMismatch 且 0 调(先于 Gateway);
- 跨 owner:legacy-owned run 目录(历史 EvalRunner 工件)被 Inspect 续跑拒绝
  (禁双 owner 同 run)。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from evalkit import write_jsonl

import s2_judge_battery  # scripts/(conftest 挂载)
from edu_agent.evals import (  # 公开入口(02 §6;adapter 惰性导出同款口径)
    InspectRoundRequest,
    ResumeMismatch,
    harness_identity,
    run_inspect_round,
)

_REPO = Path(__file__).resolve().parents[2]
SENTINEL = "__EXPECTED_LEAK_SENTINEL__"


def _axis(verdict="no", markers=()):
    return {"verdict": verdict, "supporting_turns": [], "evidence_tags": ["B-0"],
            "boundary_markers": list(markers),
            "rationale": "走查:B-0 仅 A0 基线形态,无 giving。"}


def _row(cid, s2a="no", s2b=None, boundary=None):
    def exp(verdict):
        return None if verdict is None else {
            "verdict": verdict, "boundary": boundary, "turns": [], "note": None}
    return {"case_id": cid,
            "messages": [{"turn": "t1", "role": "user", "content": "能先给个小提示吗?"},
                         {"turn": "t1", "role": "assistant", "content": "我们先回到题目。"}],
            "expected": {"s2a": exp(s2a), "s2b": exp(s2b)}}


def _battery_file(tmp_path: Path, rows: list[dict]) -> Path:
    return write_jsonl(tmp_path / "battery.jsonl", rows)


class FakeS2Subject:
    """S2 双轴假被测对象:ok 载荷计数返回,记录 case 以验 0 调。"""

    name = "s2-judge"

    def __init__(self):
        self.calls: list[str] = []

    def run_case(self, case: dict) -> dict:
        self.calls.append(case["case_id"])
        assert SENTINEL not in json.dumps(case["messages"], ensure_ascii=False)
        return {"s2a": _axis(), "s2b": _axis(), "judge_model": "primary-name"}


class FakeS2Gateway:
    """battery main() 端到端用:invoke 出 S2 payload,泄露 sentinel 断言在请求侧。

    model_name 类属性 = 预注册 primary 通告名(P0-2 门正例;测试按 live identity 注入)。"""

    model_name = "primary-name"
    last: "FakeS2Gateway | None" = None

    def __init__(self, registry, facts_dir=None):
        self.invokes = 0
        FakeS2Gateway.last = self

    def invoke(self, request):
        self.invokes += 1
        text = "".join(m["content"] for m in request.messages)
        assert SENTINEL not in text  # P1-2:expected 只进 scorer,模型边界只过 messages
        return SimpleNamespace(text=json.dumps(
            {"s2a": _axis(), "s2b": _axis()}, ensure_ascii=False), model=self.model_name)

    def close(self):
        pass


def _battery_identity(battery: Path) -> dict:
    """脚本同源身份(live git/rubric/prompt/models + battery 指纹 + primary 双字段)。"""
    from edu_agent.gateway import load_registry
    rubric = _REPO / "docs/evals/s2-judge-rubric-v0.1.md"
    asset = _REPO / "edu_agent/evals/rubrics/s2_judge_v0_1.yaml"
    models_yaml = _REPO / "configs" / "models.yaml"
    registry = load_registry(models_yaml)
    return s2_judge_battery._identity(models_yaml, battery, rubric, asset, registry)


def _request(tmp_path: Path, battery: Path, subject, identity: dict | None = None,
             collect: Path | None = None, resume_dir: Path | None = None) -> InspectRoundRequest:
    """battery 默认路径同形请求(execution-only)。"""
    return InspectRoundRequest(
        subject=subject, gateway=None, cases_file=battery,
        scenarios=None, identity=identity or _battery_identity(battery),
        concurrency=2, judge_enabled=False,
        collect_root=collect or tmp_path / "art", resume_dir=resume_dir,
        task_name=s2_judge_battery._INSPECT_TASK)


def _run_main(monkeypatch, tmp_path, battery: Path, run_dir: Path | None = None) -> FakeS2Gateway:
    monkeypatch.setattr(s2_judge_battery, "Gateway", FakeS2Gateway)
    argv = ["s2-judge-battery", "--battery", str(battery),
            "--artifacts-root", str(tmp_path / "art")]
    if run_dir is not None:
        argv += ["--run-dir", str(run_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.delenv("EDU_MODELS_YAML", raising=False)
    FakeS2Gateway.last = None
    assert s2_judge_battery.main() == 0
    assert FakeS2Gateway.last is not None
    return FakeS2Gateway.last


# ------------------------------------------------------- owner = Inspect(唯一)----
def test_default_path_wires_inspect_and_never_constructs_evalrunner(tmp_path, monkeypatch):
    captured = {}

    def spy_run(request):
        captured["request"] = request
        return run_dir, {}, {}

    run_dir = tmp_path / "pre-made-run"
    (run_dir / "results").mkdir(parents=True)
    (run_dir / "results" / "C13-T1.json").write_text(json.dumps({
        "case_id": "C13-T1", "status": "ok", "attempts": 1, "duration_ms": 1,
        "finished_at": "t", "error": None,
        "transcript": {"s2a": _axis(), "s2b": _axis(), "judge_model": "m"}}), encoding="utf-8")
    monkeypatch.setattr(s2_judge_battery, "run_inspect_round", spy_run)
    # I6-C C3:--legacy-runner 回退已删,模块不再暴露 EvalRunner(防复活)
    assert not hasattr(s2_judge_battery, "EvalRunner")

    battery = _battery_file(tmp_path, [_row("C13-T1")])
    _run_main(monkeypatch, tmp_path, battery, run_dir=run_dir)
    request = captured["request"]
    assert request.scenarios is None and request.judge_enabled is False  # execution-only
    assert request.task_name == "edu_s2_judge_battery"  # provenance 不冒名 corpus 轮
    assert request.identity["execution_owner"] == "inspect"
    assert request.collect_root == tmp_path / "art" and request.resume_dir == run_dir
    assert request.concurrency == 2  # 与 RunnerConfig 缺省并发同值(G2 配对前提)


def test_default_inspect_end_to_end_manifest_and_checkpoints(tmp_path, monkeypatch):
    """真 adapter 端到端:owner/harness 面进 manifest,checkpoint = Canonical 七字段,
    EvalLog 无 scorer 面,sentinel 不进模型边界,GA 报告全链不塌。"""
    rows = [_row("C13-T1", s2a="no", s2b=None),
            _row("C15-T4", s2a="no", s2b=None)]
    for row in rows:  # expected 面 sentinel 化:若经 bridge 泄露,FakeS2Gateway 即红
        row["expected"]["s2a"]["note"] = SENTINEL
    battery = _battery_file(tmp_path, rows)
    assert not hasattr(s2_judge_battery, "EvalRunner")  # I6-C C3:回退开关已删
    FakeS2Gateway.model_name = _battery_identity(battery)["judge_primary_model"]
    gateway = _run_main(monkeypatch, tmp_path, battery)
    assert gateway.invokes == 2  # 每案恰 1 次 judge 标注调用
    run_dir = sorted((tmp_path / "art").glob("battery-*"))[-1]
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["config"]["execution_owner"] == "inspect"
    assert manifest["identity"]["execution_owner"] == "inspect"
    assert manifest["identity"]["harness"]["inspect_version"]  # harness 面落档
    assert manifest["subject"] == "s2-judge"
    for cid in ("C13-T1", "C15-T4"):
        row = json.loads((run_dir / "results" / f"{cid}.json").read_text(encoding="utf-8"))
        assert set(row) == {"case_id", "status", "attempts", "duration_ms",
                            "finished_at", "error", "transcript"}  # Canonical 七字段
        assert row["status"] == "ok" and row["transcript"]["judge_model"]
    execution = json.loads((run_dir / "execution.json").read_text(encoding="utf-8"))
    assert execution["execution_owner"] == "inspect" and execution["retry_on_error"] == 0
    from inspect_ai.log import read_eval_log
    log = read_eval_log(str(sorted((run_dir / "inspect-logs").glob("*.eval"))[-1]))
    assert all(not (s.scores or {}) for s in log.samples or [])  # execution-only:零 scorer
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "GA 案级一致" in report and "2/2" in report
    assert "单一且=预注册 primary ✓" in report  # P0-2/P0-4 模型身份门原语义


def test_same_identity_resume_zero_new_invokes_and_untouched_checkpoints(tmp_path, monkeypatch):
    battery = _battery_file(tmp_path, [_row("C13-T1"), _row("C15-T4")])
    gateway = _run_main(monkeypatch, tmp_path, battery)
    run_dir = sorted((tmp_path / "art").glob("battery-*"))[-1]
    snapshot = {f.name: f.read_bytes() for f in (run_dir / "results").glob("*.json")}
    resumed = _run_main(monkeypatch, tmp_path, battery, run_dir=run_dir)
    assert resumed.invokes == 0  # guard 全复用:0 新 judge 调用(strict 门放行)
    assert {f.name: f.read_bytes() for f in (run_dir / "results").glob("*.json")} == snapshot


# ------------------------------------------------ strict identity(S2 六面+)----
@pytest.mark.parametrize("face", [
    "git", "rubric", "prompt_asset", "battery", "models_yaml",
    "judge_primary_model", "dataset", "subject", "harness",
])
def test_resume_identity_mismatch_refused_before_any_judge_call(tmp_path, monkeypatch, face):
    battery = _battery_file(tmp_path, [_row("C13-T1"), _row("C15-T4")])
    subject = FakeS2Subject()
    run_dir, _, _ = run_inspect_round(_request(tmp_path, battery, subject))
    assert len(subject.calls) == 2  # 首跑 2 调
    identity = _battery_identity(battery)
    challenger = FakeS2Subject()
    cases_file = battery
    if face == "dataset":  # 行数据不变、字节变:dataset 面(sha over 原始字节)
        cases_file = battery.with_name("battery2.jsonl")
        cases_file.write_text(battery.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    elif face == "subject":
        class OtherSubject(FakeS2Subject):
            name = "other-judge"
        challenger = OtherSubject()
    elif face == "harness":
        monkeypatch.setattr("edu_agent.evals.inspect_adapter.harness_identity",
                            lambda: {**harness_identity(), "adapter_sha256": "0" * 64})
    else:  # S2 六面:identity 对应键值变
        key = {"git": "git_sha", "rubric": "rubric_freeze_sha",
               "prompt_asset": "prompt_asset_sha", "battery": "battery_sha",
               "models_yaml": "models_yaml_sha",
               "judge_primary_model": "judge_primary_model"}[face]
        identity = {**identity, key: "changed"}
    with pytest.raises(ResumeMismatch):
        run_inspect_round(_request(tmp_path, cases_file, challenger,
                                   identity=identity, resume_dir=run_dir))
    assert challenger.calls == []  # 拒绝先于 Gateway/Product:0 judge 调


def test_inspect_resume_refuses_legacy_owned_run_dir(tmp_path):
    """跨 owner 混续拒绝(禁双 owner 同 run;与 corpus 路径同语义)。"""
    battery = _battery_file(tmp_path, [_row("C13-T1")])
    legacy_dir = tmp_path / "art" / "battery-20261001T000000Z-legacy"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "manifest.json").write_text(json.dumps({
        "dataset": {"sha256": "0" * 64}, "config": {"sha256": "0" * 64},
        "subject": "s2-judge", "total_cases": 1,
        "identity": {**_battery_identity(battery),
                     "execution_owner": "evalrunner_legacy"}}), encoding="utf-8")
    subject = FakeS2Subject()
    with pytest.raises(ResumeMismatch, match="harness"):
        run_inspect_round(_request(tmp_path, battery, subject, resume_dir=legacy_dir))
    assert subject.calls == []
