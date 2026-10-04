"""rescore_judge Inspect offline re-score switch 合同(#521 I6-C C1-B G1;
I6-C C4 删 EvalRunner 后 Inspect 为唯一执行面,防复活断言持有)。

零真模型——路径走真实 inspect_adapter(execution-only 轮,scenarios=None,
评分语义与平铺留脚本)。覆盖清单(逐条):
- owner = Inspect:run_inspect_round 接线(scenarios=None/identity/task_name/
  concurrency/resume_dir)且模块无 EvalRunner 可构造;identity 明示
  execution_owner=inspect;
- End-to-end:假存档(历史 EvalRunner 工件形)→ _archive_cases 读者面 → 假 judge →
  checkpoint Canonical 七字段 → judge-scores.jsonl 平铺;judger.sha256 资产指纹不变;
  manifest 带 harness 面,EvalLog 零 scorer 面(execution-only);
- 历史 artifact 只读:存档 run 目录文件字节零改写、零新增;
- 禁自动 fallback:Inspect 路径异常直接传播(无第二执行面可回落);
- resume 自动探测:out/collect 下已有 judge-cases-* run 目录 → 作 resume_dir 传 adapter;
- 身份面(抽 2 面:git/prompts):任一变化 → ResumeMismatch 且 0 调(strict
  preflight 先于 Gateway/judge);
- 跨 owner:legacy-owned run 目录被同形 Inspect 请求拒绝(禁双 owner 同 run)。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import scripts.rescore_judge as rescore
from edu_agent.evals import (
    InspectRoundRequest,
    ResumeMismatch,
    judger_sha256,
    run_identity,
    run_inspect_round,
)

_REPO = Path(__file__).resolve().parents[2]

# 假存档题面 + 假 transcript(历史 EvalRunner 工件形:results/<case_id>.json 七字段)
_FACES = [
    {"id": "rescore_case_alpha", "question": {"text": "解方程 x+2=5。", "answer": "x=3"},
     "grade": "五年级"},
    {"id": "rescore_case_beta", "question": "鸡兔同笼,共 5 头 14 脚,几只兔?",
     "reference_answer": "兔 2 只"},
]


def _archive_transcript(face: dict) -> dict:
    return {
        "question_id": face["id"], "final_state": "completed",
        "turns": [
            {"student": "", "tutor": "先想想已知条件。", "state": "first_question_ready"},
            {"student": "x=3。", "tutor": "很好,总结一下。", "state": "completed"},
        ],
        "summary": "总结:已收束。", "learner": {"grade": face.get("grade", "")},
    }


def _fake_archive(root: Path) -> tuple[Path, Path]:
    """历史 collect run(run_dir/results/*.json)+ 题面 cases.jsonl → (run_dir, cases)。"""
    run_dir = root / "archive-run" / "cases-20260101T000000Z-old1"
    (run_dir / "results").mkdir(parents=True, exist_ok=True)
    for face in _FACES:
        (run_dir / "results" / f"{face['id']}.json").write_text(json.dumps({
            "case_id": face["id"], "status": "ok", "attempts": 1, "duration_ms": 1,
            "finished_at": "t", "error": None,
            "transcript": _archive_transcript(face)}, ensure_ascii=False), encoding="utf-8")
    faces = root / "archive-run" / "cases.jsonl"
    faces.write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in _FACES) + "\n",
                     encoding="utf-8")
    return run_dir, faces


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


class FakeJudgeSubject:
    """假判分被测对象(Subject 协议):canned judge 载荷,计数 case 验 0 调/1 案 1 调。"""

    name = "fake-judge-subject"
    last: "FakeJudgeSubject | None" = None

    def __init__(self, gateway, role="judge"):
        self.gateway = gateway
        self.role = role
        self.calls: list[str] = []
        FakeJudgeSubject.last = self

    def run_case(self, case: dict) -> dict:
        self.calls.append(case["id"])
        return {"scores": {"accuracy": 2, "reasoning": 2}, "total": 12,
                "answer_leaked": False, "math_integrity": 2, "evidence": "canned",
                "verdict": "pass", "judge_model": "fake-judge"}


class FakeGateway:
    """零真模型合同:重判全假,gateway.invoke 被触达即红。"""

    last: "FakeGateway | None" = None

    def __init__(self, registry, facts_dir="facts"):
        FakeGateway.last = self
        self.invokes = 0

    def invoke(self, request):
        self.invokes += 1
        raise AssertionError("零真模型合同测试:gateway.invoke 不应被触达")

    def close(self):
        pass


def _run_main(monkeypatch, tmp_path, argv: list[str]) -> None:
    monkeypatch.setattr(rescore, "Gateway", FakeGateway)
    monkeypatch.setattr(rescore, "JudgeSubject", FakeJudgeSubject)
    monkeypatch.setattr(sys, "argv", ["rescore_judge", *argv])
    FakeGateway.last = None
    FakeJudgeSubject.last = None
    rescore.main()
    assert FakeGateway.last is not None and FakeGateway.last.invokes == 0  # 零真模型


def _argv(tmp_path: Path, out_name: str, extra: list[str] | None = None) -> tuple[list[str], Path, Path]:
    run_dir, faces = _fake_archive(tmp_path)
    out = tmp_path / out_name
    return ["--archive", str(run_dir), str(faces), "--out", str(out), *(extra or [])], run_dir, out


def _latest_collect(out: Path) -> Path:
    return sorted((out / "collect").glob("judge-cases-*"))[-1]


def _scores(out: Path) -> dict[str, dict]:
    rows = {}
    for line in (out / "judge-scores.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["case_id"]] = row
    return rows


# ------------------------------------------------------- owner = Inspect(唯一)----
def test_default_wires_inspect_and_never_constructs_evalrunner(tmp_path, monkeypatch):
    captured = {}
    run_dir = tmp_path / "out" / "collect" / "pre-made"
    (run_dir / "results").mkdir(parents=True)
    for face in _FACES:
        (run_dir / "results" / f"{face['id']}.json").write_text(json.dumps({
            "case_id": face["id"], "status": "ok", "attempts": 1, "duration_ms": 1,
            "finished_at": "t", "error": None,
            "transcript": FakeJudgeSubject(None).run_case(face)}, ensure_ascii=False),
            encoding="utf-8")

    def spy_run(request):
        captured["request"] = request
        return run_dir, {}, {}

    monkeypatch.setattr(rescore, "run_inspect_round", spy_run)
    assert not hasattr(rescore, "EvalRunner")  # I6-C C4:第二执行面已删,不复活
    argv, _, out = _argv(tmp_path, "out")
    _run_main(monkeypatch, tmp_path, argv)
    request = captured["request"]
    assert isinstance(request, InspectRoundRequest)
    assert request.scenarios is None and request.judge_enabled is False  # execution-only
    assert request.task_name == "edu_rescore_judge"  # provenance 不冒名 corpus 轮
    assert request.identity["execution_owner"] == "inspect"  # owner 明示
    assert "git_sha" in request.identity and "prompts_sha256" in request.identity  # run_identity 同源
    assert request.concurrency == 2  # 与原 legacy 通道同并发(paired 前提)
    assert request.resume_dir is None and request.collect_root == out / "collect"
    assert request.cases_file == out / "judge-cases.jsonl"
    assert request.subject is FakeJudgeSubject.last
    assert FakeJudgeSubject.last.calls == []  # 评分载荷来自 spy 返回的 checkpoint,不再跑
    rows = _scores(out)
    assert set(rows) == {f["id"] for f in _FACES}  # 平铺:transcript → judge-scores.jsonl
    assert rows[_FACES[0]["id"]]["total"] == 12 and rows[_FACES[0]["id"]]["verdict"] == "pass"


def test_default_inspect_end_to_end_reader_compat_and_flattening(tmp_path, monkeypatch):
    """真 adapter 端到端:历史工件读者面只读、judge-cases 输入同 corpus 口径、owner/harness
    面进 manifest,checkpoint = Canonical 七字段,EvalLog 零 scorer,judger 指纹不变。"""
    assert not hasattr(rescore, "EvalRunner")  # I6-C C4:第二执行面已删,不复活
    extra = tmp_path / "extra.json"
    extra.write_text(json.dumps({
        "case_id": "rescore_case_c15", "question": "构造挑战案", "grade": "六年级",
        "reference_answer": "见判据", "turns": [["user", "我的答案是 9。"],
                                               ["assistant", "再验证一下。"]]},
        ensure_ascii=False), encoding="utf-8")
    argv, run_dir, out = _argv(tmp_path, "out", ["--extra-case", str(extra)])
    before = _snapshot(run_dir.parent)  # 历史 artifact 只读:字节快照
    _run_main(monkeypatch, tmp_path, argv)
    assert _snapshot(run_dir.parent) == before  # 存档 run 目录零改写、零新增
    assert sorted(FakeJudgeSubject.last.calls) == ["rescore_case_alpha", "rescore_case_beta",
                                                   "rescore_case_c15"]  # 1 案 1 调
    cases = [json.loads(line) for line
             in (out / "judge-cases.jsonl").read_text(encoding="utf-8").splitlines() if line]
    by_id = {c["id"]: c for c in cases}
    assert by_id["rescore_case_alpha"]["question"] == "解方程 x+2=5。"  # question dict → text
    assert by_id["rescore_case_alpha"]["reference_answer"] == "x=3"  # question.answer 优先
    assert by_id["rescore_case_beta"]["reference_answer"] == "兔 2 只"  # 裸题面顶层兜底
    assert by_id["rescore_case_c15"]["messages"] == [  # 挑战案 turns=[[role,text]…]
        {"role": "user", "content": "我的答案是 9。"},
        {"role": "assistant", "content": "再验证一下。"}]
    assert by_id["rescore_case_alpha"]["messages"][0] == {  # transcript_messages 同款取数
        "role": "assistant", "content": "先想想已知条件。"}
    collect = _latest_collect(out)
    manifest = json.loads((collect / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["config"]["execution_owner"] == "inspect"
    assert manifest["identity"]["execution_owner"] == "inspect"
    assert manifest["identity"]["harness"]["inspect_version"]  # harness 面落档
    assert manifest["subject"] == "fake-judge-subject"
    for cid in ["rescore_case_alpha", "rescore_case_beta", "rescore_case_c15"]:
        row = json.loads((collect / "results" / f"{cid}.json").read_text(encoding="utf-8"))
        assert set(row) == {"case_id", "status", "attempts", "duration_ms",
                            "finished_at", "error", "transcript"}  # Canonical 七字段
        assert row["status"] == "ok"
    execution = json.loads((collect / "execution.json").read_text(encoding="utf-8"))
    assert execution["execution_owner"] == "inspect" and execution["retry_on_error"] == 0
    from inspect_ai.log import read_eval_log
    log = read_eval_log(str(sorted((collect / "inspect-logs").glob("*.eval"))[-1]))
    assert all(not (s.scores or {}) for s in log.samples or [])  # execution-only:零 scorer
    rows = _scores(out)
    assert rows["rescore_case_alpha"]["judge_model"] == "fake-judge"  # 平铺保 judge 载荷本体
    assert (out / "judger.sha256").read_text(encoding="utf-8").strip() == judger_sha256()


# --------------------------------------------------------- 禁自动 fallback ----
def test_inspect_failure_propagates_no_silent_fallback(tmp_path, monkeypatch):
    def boom(request):
        raise RuntimeError("inspect down")

    monkeypatch.setattr(rescore, "run_inspect_round", boom)
    assert not hasattr(rescore, "EvalRunner")  # I6-C C4:第二执行面已删,无回落地
    argv, _, _ = _argv(tmp_path, "out")
    with pytest.raises(RuntimeError, match="inspect down"):
        _run_main(monkeypatch, tmp_path, argv)


# ------------------------------------------------------- resume 自动探测 ----
def test_resume_autodetects_latest_judge_cases_run(tmp_path, monkeypatch):
    """out/collect 已有 judge-cases-* run 目录 → 作 resume_dir 传 adapter
    (glob 修正后真实生效;I6-C C4 起 owner 只剩 Inspect 一面)。"""
    existing = tmp_path / "out" / "collect" / "judge-cases-20260101T000000Z-old1"
    existing.mkdir(parents=True)
    captured = {}

    def spy_run(request):
        captured["resume"] = request.resume_dir
        return existing, {}, {}

    monkeypatch.setattr(rescore, "run_inspect_round", spy_run)
    argv, _, _ = _argv(tmp_path, "out")
    _run_main(monkeypatch, tmp_path, argv)
    assert captured["resume"] == existing


# ------------------------------------------- 身份面(抽 2 面:接线参与共享 preflight)----
def _script_request(cases_file: Path, subject, identity: dict, collect: Path,
                    resume_dir: Path | None) -> InspectRoundRequest:
    """脚本默认路径同形请求(execution-only;identity = run_identity + owner)。"""
    return InspectRoundRequest(
        subject=subject, gateway=None, cases_file=cases_file, scenarios=None,
        identity=identity, concurrency=2, judge_enabled=False,
        collect_root=collect, resume_dir=resume_dir, task_name="edu_rescore_judge")


@pytest.mark.parametrize("face", ["git_sha", "prompts_sha256"])
def test_resume_identity_face_mismatch_refused_before_any_call(tmp_path, face):
    """脚本同款身份(run_identity + owner)任一面变化 → ResumeMismatch 且 0 调
    (strict preflight 先于 Gateway/judge;机制共享已证,此处验接线)。"""
    cases_file = tmp_path / "judge-cases.jsonl"
    cases_file.write_text(json.dumps({"id": "rescore_face_case", "question": "q",
                                      "grade": "", "reference_answer": "",
                                      "messages": []}, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    identity = {**run_identity(), "execution_owner": "inspect"}
    first = FakeJudgeSubject(None)
    run_dir, _, _ = run_inspect_round(
        _script_request(cases_file, first, identity, tmp_path / "collect", None))
    assert first.calls == ["rescore_face_case"]  # 首跑 1 调
    challenger = FakeJudgeSubject(None)
    with pytest.raises(ResumeMismatch):
        run_inspect_round(_script_request(
            cases_file, challenger, {**identity, face: "changed"},
            tmp_path / "collect", run_dir))
    assert challenger.calls == []  # 拒绝先于 Gateway/judge:0 调


def test_inspect_resume_refuses_legacy_owned_run_dir(tmp_path):
    """跨 owner 混续拒绝(禁双 owner 同 run;与 corpus/S2/tuning 路径同语义)。"""
    cases_file = tmp_path / "judge-cases.jsonl"
    cases_file.write_text(json.dumps({"id": "rescore_owner_case", "question": "q",
                                      "grade": "", "reference_answer": "",
                                      "messages": []}, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    legacy_dir = tmp_path / "collect" / "judge-cases-20260101T000000Z-legacy"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "manifest.json").write_text(json.dumps({
        "dataset": {"sha256": "0" * 64}, "config": {"sha256": "0" * 64},
        "subject": "fake-judge-subject", "total_cases": 1,
        "identity": {**run_identity(), "execution_owner": "evalrunner_legacy"},
    }), encoding="utf-8")
    subject = FakeJudgeSubject(None)
    with pytest.raises(ResumeMismatch, match="harness"):
        run_inspect_round(_script_request(
            cases_file, subject, {**run_identity(), "execution_owner": "inspect"},
            tmp_path / "collect", legacy_dir))
    assert subject.calls == []
