"""#533 EvalLog Review Projection——五护栏逐条 + 附着往返的确定性测试。

被测件按文件路径加载(scripts/ 非公开入口,同 tests/evals/test_er_judge_v2.py 按路径
加载先例)。fixture 全合成(tmp_path 内自建 run 目录 + 最小 EvalLog),零网络零模型:
投影是纯离线件,测试面同样纯离线。护栏编号对应 #533 正文。
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from inspect_ai.log import (
    EvalConfig,
    EvalDataset,
    EvalLog,
    EvalPlan,
    EvalPlanStep,
    EvalSample,
    EvalSpec,
    read_eval_log,
    write_eval_log,
)

_TOOL = Path(__file__).resolve().parents[2] / "scripts" / "project_evallog_scores.py"
_spec = importlib.util.spec_from_file_location("project_evallog_scores", _TOOL)
projection = importlib.util.module_from_spec(_spec)
sys.modules["project_evallog_scores"] = projection  # dataclass 注解解析需要模块已注册
_spec.loader.exec_module(projection)

CASE_OK_RED = "case_ok_red"          # ok + 2 条 failures
CASE_OK_GREEN = "case_ok_green"      # ok + 无 failures
CASE_CONTENT = "case_content"        # 非 ok 行(declared=False/failures=None)
CASE_UNSCORED = "case_unscored"      # 只在 .eval 里,canonical 无行(子集语义)
JUDGE_MODEL = "/models/Qwen3.5-27B-4bit"
JUDGER_SHA = "f" * 64
SUBJECT_MODEL = "qwen3_vl_8b"
INPUT_EVAL_NAME = "2026-01-01T00-00-00_edu-x_TEST.eval"

CHECKS_ROWS = {
    CASE_OK_RED: {"status": "ok", "declared": True, "final_state": "needs_review",
                  "failures": [{"check": "finish_status", "detail": "期望 completed"}] * 2,
                  "advisories": []},
    CASE_OK_GREEN: {"status": "ok", "declared": True, "final_state": "completed",
                    "failures": [], "advisories": []},
    CASE_CONTENT: {"status": "content", "declared": False, "failures": None,
                   "final_state": None},
}
JUDGE_ROWS = {
    CASE_OK_RED: {"scores": {"first_question": 2}, "total": 6, "answer_leaked": False,
                  "math_integrity": 2, "evidence": {}, "verdict": "fail",
                  "judge_model": JUDGE_MODEL},
    CASE_OK_GREEN: {"scores": {"first_question": 2}, "total": 12, "answer_leaked": False,
                    "math_integrity": 2, "evidence": {}, "verdict": "pass",
                    "judge_model": JUDGE_MODEL},
}


def _write_run(run_dir: Path) -> Path:
    """合成 run 目录:canonical 工件 + 最小 .eval(无分数);返回输入 .eval 路径。"""
    (run_dir / "results").mkdir(parents=True)
    for case in (CASE_OK_RED, CASE_OK_GREEN, CASE_CONTENT):
        (run_dir / "results" / f"{case}.json").write_text(
            json.dumps({"case_id": case, "status": "ok" if case != CASE_CONTENT else "content",
                        "attempts": 1, "duration_ms": 1, "finished_at": "t",
                        "error": None, "transcript": {}}), encoding="utf-8")
    (run_dir / "checks.jsonl").write_text(
        "\n".join(json.dumps({"case_id": k, **v}) for k, v in CHECKS_ROWS.items()) + "\n",
        encoding="utf-8")
    (run_dir / "judge-scores.jsonl").write_text(
        "\n".join(json.dumps({"case_id": k, **v}) for k, v in JUDGE_ROWS.items()) + "\n",
        encoding="utf-8")
    (run_dir / "judger.sha256").write_text(JUDGER_SHA + "\n", encoding="utf-8")
    (run_dir / "manifest.json").write_text(json.dumps({"total_cases": 3}), encoding="utf-8")
    (run_dir / "facts.jsonl").write_text(json.dumps({
        "edu.role": "tutor", "gen_ai.request.model": SUBJECT_MODEL,
        "gen_ai.response.model": "Qwen3-VL-8B-GGUF"}) + "\n", encoding="utf-8")
    spec = EvalSpec(id="t", created=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    task="edu_x", task_version=0,
                    dataset=EvalDataset(name="cases", location="cases.jsonl"),
                    model="mockllm/model", config=EvalConfig())
    spec.metadata = {"execution_owner": "inspect", "inspect_role": "execution_owner"}
    samples = [EvalSample(id=case, epoch=1, input="{}", target="")
               for case in (CASE_OK_RED, CASE_OK_GREEN, CASE_CONTENT, CASE_UNSCORED)]
    log = EvalLog(eval=spec, plan=EvalPlan(steps=[EvalPlanStep(solver="bridge")]),
                  samples=samples, version=2, status="success")
    logs = run_dir / "inspect-logs"
    logs.mkdir()
    input_eval = logs / INPUT_EVAL_NAME
    write_eval_log(log, input_eval)
    return input_eval


def _project(run_dir: Path, extra: list[str] | None = None) -> Path:
    out = run_dir / "projected.eval"
    projection.main([str(run_dir), "--out", str(out), *(extra or [])])
    return out


def _scores(out_eval: Path) -> dict:
    return {str(s.id): dict(s.scores or {}) for s in read_eval_log(out_eval).samples}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------ 护栏 1 ----
def test_guardrail1_canonical_rows_projected_verbatim_no_scoring_code(tmp_path):
    """护栏 1:canonical 永远 truth——canonical 行原文逐字节进 score metadata;投影件
    零判分代码(AST import 面只含 stdlib + inspect_ai log/scorer API,判分/网关不可达)。"""
    run_dir = tmp_path / "run"
    _write_run(run_dir)
    scores = _scores(_project(run_dir))
    for case, row in CHECKS_ROWS.items():
        assert scores[case]["canonical_checks"].metadata["canonical_row"] == {
            "case_id": case, **row}
    for case, row in JUDGE_ROWS.items():
        assert scores[case]["canonical_judge"].metadata["canonical_row"] == {
            "case_id": case, **row}
    imported = set()
    for node in ast.walk(ast.parse(_TOOL.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert imported <= {"__future__", "argparse", "hashlib", "json", "sys", "dataclasses",
                        "pathlib", "typing", "inspect_ai.log", "inspect_ai.scorer"}
    assert not any(name.startswith("edu_agent") for name in imported)  # 亦即护栏 3 的结构钉


# ------------------------------------------------------------------ 护栏 2 ----
def test_guardrail2_every_score_carries_identity(tmp_path):
    """护栏 2:每个投影 score 带 projection_version / canonical_artifact(+sha)/
    scoring_identity(judger_sha256;judge 面另带 judge_model)。"""
    run_dir = tmp_path / "run"
    _write_run(run_dir)
    scores = _scores(_project(run_dir))
    scored = [score for face in scores.values() for score in face.values()]
    assert len(scored) == 5  # 3 checks + 2 judge
    for score in scored:
        block = score.metadata["projection"]
        assert block["projection_version"] == 1
        assert block["canonical_artifact_sha256"] == _sha(
            run_dir / block["canonical_artifact"])
        assert block["scoring_identity"]["judger_sha256"] == JUDGER_SHA
    judge_block = scores[CASE_OK_RED]["canonical_judge"].metadata["projection"]
    assert judge_block["scoring_identity"]["judge_model"] == JUDGE_MODEL


# ------------------------------------------------------------------ 护栏 3 ----
def test_guardrail3_zero_product_zero_judge_calls(tmp_path):
    """护栏 3:0 Product/0 Judge 调用——纯离线:输入 log 零分数,投影后样本集不变
    (id/epoch 一致),只有分数被附着(import 面结构钉见护栏 1 测试)。"""
    run_dir = tmp_path / "run"
    input_eval = _write_run(run_dir)
    out = _project(run_dir)
    before = read_eval_log(input_eval)
    after = read_eval_log(out)
    assert [s.id for s in after.samples] == [s.id for s in before.samples]
    assert [s.epoch for s in after.samples] == [s.epoch for s in before.samples]
    assert all(not (s.scores or {}) for s in before.samples)


# ------------------------------------------------------------------ 护栏 4 ----
def test_guardrail4_stale_projection_refused_after_canonical_change(tmp_path):
    """护栏 4:canonical 变更后旧投影身份失配——对已投影 log 再投影 → SystemExit 且
    明示;从原始 log 重新投影则采用新 sha(旧投影不冒充当前 score)。"""
    run_dir = tmp_path / "run"
    input_eval = _write_run(run_dir)
    out = _project(run_dir)
    lines = (run_dir / "judge-scores.jsonl").read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[0])
    row["verdict"] = "pass"  # canonical 变更
    lines[0] = json.dumps(row, ensure_ascii=False)
    (run_dir / "judge-scores.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:  # 在旧投影上叠加 → 拒绝
        projection.main([str(run_dir), "--eval", str(out), "--out",
                         str(run_dir / "again.eval")])
    assert "失配" in str(exc.value)
    assert not (run_dir / "again.eval").exists()
    fresh = run_dir / "fresh.eval"  # 原始 log 重新投影 → 新身份 + 新 verdict
    projection.main([str(run_dir), "--eval", str(input_eval), "--out", str(fresh)])
    fresh_block = _scores(fresh)[CASE_OK_RED]["canonical_judge"].metadata["projection"]
    assert fresh_block["canonical_artifact_sha256"] == _sha(run_dir / "judge-scores.jsonl")
    assert _scores(fresh)[CASE_OK_RED]["canonical_judge"].value == "pass"


# ------------------------------------------------------------------ 护栏 5 ----
def test_guardrail5_no_reverse_sync_canonical_bytes_untouched(tmp_path):
    """护栏 5:禁反向同步——投影后 run 目录全部 canonical 工件字节不变;
    --out 指向 canonical 工件直接拒绝。"""
    run_dir = tmp_path / "run"
    _write_run(run_dir)
    canonical = sorted(p for p in run_dir.rglob("*")
                       if p.is_file() and p.suffix != ".eval")
    before = {p: _sha(p) for p in canonical}
    _project(run_dir)
    assert {p: _sha(p) for p in canonical} == before
    with pytest.raises(SystemExit) as exc:
        projection.main([str(run_dir), "--out", str(run_dir / "judge-scores.jsonl")])
    assert "反向同步" in str(exc.value)


# ------------------------------------------------------------- 往返 + provenance ----
def test_roundtrip_scores_values_and_provenance_metadata(tmp_path):
    """附着往返:attach 后再读——checks 值=failures 条数(非 ok 行=状态字面量)、
    judge 值=verdict;canonical 无行的样本不冒充;model_provenance 四件核齐
    (subject 取 facts/grader 取 canonical judge_model/transport owner=Gateway/
    header model sentinel 保持);重复投影输出内容确定。"""
    run_dir = tmp_path / "run"
    _write_run(run_dir)
    out = _project(run_dir)
    scores = _scores(out)
    assert scores[CASE_OK_RED]["canonical_checks"].value == 2
    assert scores[CASE_OK_GREEN]["canonical_checks"].value == 0
    assert scores[CASE_CONTENT]["canonical_checks"].value == "content"
    assert scores[CASE_OK_RED]["canonical_judge"].value == "fail"
    assert scores[CASE_OK_GREEN]["canonical_judge"].value == "pass"
    assert scores[CASE_UNSCORED] == {}  # canonical 无行 → 不投影
    assert "sha=" in scores[CASE_OK_RED]["canonical_judge"].explanation
    metadata = read_eval_log(out).eval.metadata
    provenance = metadata["model_provenance"]
    assert provenance["transport_owner"] == "edu-agent Gateway"
    assert provenance["subject_model"]["request_models"] == {SUBJECT_MODEL: 1}
    assert provenance["models_by_role"]["tutor"]["response_models"] == {"Qwen3-VL-8B-GGUF": 1}
    assert provenance["grader_model"] == [JUDGE_MODEL]
    assert provenance["header_model"]["value"] == "mockllm/model"  # sentinel 不改真实名
    assert metadata["execution_owner"] == "inspect"  # 既有身份块保留
    projection.main([str(run_dir), "--out", str(run_dir / "projected2.eval")])
    first, second = _scores(out), _scores(run_dir / "projected2.eval")
    for case in first:
        for name in first[case]:
            a, b = first[case][name], second[case][name]
            assert (a.value, a.metadata, a.explanation) == (b.value, b.metadata, b.explanation)


def test_missing_canonical_artifacts_refused(tmp_path):
    """fail closed:无 canonical 评分工件 / 缺 judger.sha256 都不投影。"""
    empty = tmp_path / "empty"
    (empty / "inspect-logs").mkdir(parents=True)
    with pytest.raises(SystemExit):
        projection.main([str(empty)])
    run_dir = tmp_path / "run"
    _write_run(run_dir)
    (run_dir / "judger.sha256").unlink()
    with pytest.raises(SystemExit) as exc:
        projection.main([str(run_dir), "--out", str(run_dir / "x.eval")])
    assert "judger" in str(exc.value)
