"""Run Spec V0(#350 用户裁定)九条完成线逐条钉死:零模型调用。

V0 = 可复现的小试跑配方,不是可配置的产品:封闭五字段、CLI > spec > 默认、
未知键/未知 case id fail closed/fail fast、judge:false 硬零 judge calls、
spec 双工件+指纹、dirty 证据、resume 身份闸。任何「想再加的字段」先去
#350 评论提案,不进代码——本文件同时钉住「没有第六个字段」这件事。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys

from argparse import Namespace
from pathlib import Path

import pytest

from edu_agent.evals import (
    DEFAULT_CORPUS,
    ResumeMismatch,
    build_plan,
    dump_spec_artifacts,
    format_plan,
    git_dirty_state,
    judge_gate,
    load_run_spec,
    merge_options,
    real_model_scenarios,
    render_report,
    resolve_round,
    resolve_spec_cases,
    resume_run_dir,
)

REPO = Path(__file__).resolve().parents[2]


def _scenario(sid: str) -> dict:
    return {
        "id": sid,
        "status": "guarded",
        "question": {"text": "长方形长8厘米宽5厘米,周长多少?", "answer": "26厘米"},
        "student_turns": ["(8+5)×2 算出来是 26。", "我算完了。"],
        "grade": "三年级",
        "source": {"issue": 350},
    }


def _write_corpus(tmp_path: Path, name: str, ids: list[str]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(
        {"schema_version": "small_lecturer_shadow_pilot_corpus/v1",
         "scenarios": [_scenario(i) for i in ids]}, ensure_ascii=False), encoding="utf-8")
    return path


def _write_spec(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "spec.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _spec_yaml(corpus_rel: str, cases: str, extra: str = "") -> str:
    return (f"version: 1\nname: t\ncorpora:\n  - {corpus_rel}\n"
            f"cases:{cases}\n{extra}")


def _args(**kw):
    return Namespace(corpus=kw.get("corpus", []), concurrency=kw.get("concurrency"))


# ① spec 选案:裸 id 解析为前缀 id,顺序保持 spec 序
def test_spec_selects_cases_in_order(tmp_path):
    corpus = _write_corpus(tmp_path, "alpha.json", ["s1", "s2", "s3"])
    spec = load_run_spec(_write_spec(
        tmp_path, _spec_yaml(str(corpus), "\n  - s2\n  - s1")))
    scenarios = real_model_scenarios([corpus])
    resolved = resolve_spec_cases(spec["cases"], scenarios)
    assert resolved == ["alpha_s2", "alpha_s1"]  # 顺序 = spec 序,非字典序
    effective, scenarios2, cases, _ = resolve_round(_args(), spec)
    assert [c["id"] for c in cases] == resolved  # 活跑/计划同源解析


# ② --plan:零模型调用打印 resolved/judge/并发/git/规模(真实 CLI 子进程)
def test_plan_mode_zero_calls_and_complete(tmp_path):
    corpus = _write_corpus(tmp_path, "alpha.json", ["s1", "s2"])
    spec_path = _write_spec(tmp_path, _spec_yaml(
        str(corpus), "\n  - s1\n  - s2", extra="judge: false\nconcurrency: 1\n"))
    out = subprocess.run(
        [sys.executable, "-m", "edu_agent.evals.corpus_round",
         "--config", str(spec_path), "--plan"],
        cwd=REPO, capture_output=True, text=True, timeout=60, check=False)
    assert out.returncode == 0, out.stderr
    assert "resolved_cases (2): alpha_s1,alpha_s2" in out.stdout
    assert "judge: off(0 judge calls)" in out.stdout
    assert "concurrency: 1" in out.stdout
    assert "git_sha: " in out.stdout and "git_dirty: " in out.stdout
    assert "call_scale: tutor≈" in out.stdout  # 规模估算在场


def test_build_plan_carries_git_and_scale(tmp_path):
    corpus = _write_corpus(tmp_path, "alpha.json", ["s1"])
    spec = load_run_spec(_write_spec(tmp_path, _spec_yaml(str(corpus), "\n  - s1")))
    effective, _sc, cases, _ = resolve_round(_args(), spec)
    plan = build_plan(effective, cases)
    assert plan["resolved_cases"] == ["alpha_s1"]
    assert plan["call_scale"]["total_est"] == plan["call_scale"]["tutor_est"] + 1  # judge on
    assert plan["git_sha"]  # 真仓内必有
    text = format_plan(plan)
    assert "judge: on" in text and "git_diff_sha256" in text


# ③ judge:false 硬零 judge calls:绊网网关(off 臂零触达;on 臂对照必触达)
def test_judge_gate_off_is_hard_zero():
    class Tripwire:
        def invoke(self, request):
            raise AssertionError("judge:off 不得触达网关")

    results = [{"case_id": "x", "status": "ok", "transcript": {"turns": [], "final_state": ""}}]
    scenarios = {"x": {"question": {"text": "q"}}}
    assert judge_gate(Tripwire(), scenarios, results, enabled=False) == {}  # 零调用铁证:绊网未响
    with pytest.raises(AssertionError):
        judge_gate(Tripwire(), scenarios, results, enabled=True)  # 对照臂:开=真会调


def test_render_report_marks_judge_off_rows():
    checks = {"x_s1": {"status": "ok", "declared": False,
                       "final_state": "completed", "failures": None}}
    report = render_report(Path("/tmp/x"), checks, scores={})
    assert "judge 关闭(run-spec)" in report


# ④ 优先级 CLI > run-spec > 默认
def test_priority_cli_over_spec_over_default(tmp_path):
    corpus = _write_corpus(tmp_path, "alpha.json", ["s1"])
    spec = load_run_spec(_write_spec(
        tmp_path, _spec_yaml(str(corpus), "\n  - s1", extra="concurrency: 3\n")))
    assert merge_options(_args(concurrency=5), spec)["concurrency"] == 5  # CLI 赢
    assert merge_options(_args(), spec)["concurrency"] == 3               # spec 赢
    assert merge_options(_args(), spec)["corpora"] == [str(corpus)]       # spec corpora
    cli_wins = merge_options(_args(corpus=["/other.json"]), spec)
    assert cli_wins["corpora"] == ["/other.json"]                          # CLI --corpus 赢
    assert merge_options(_args(), None)["concurrency"] == 2                # 默认
    assert merge_options(_args(), None)["corpora"] == [DEFAULT_CORPUS]
    assert merge_options(_args(), None)["judge"] is True                   # judge 缺省开


# ⑤ 未知 key fail closed
def test_unknown_key_fails_closed(tmp_path):
    corpus = _write_corpus(tmp_path, "alpha.json", ["s1"])
    path = _write_spec(tmp_path, _spec_yaml(
        str(corpus), "\n  - s1", extra="overrides:\n  prompt: hacked\n"))
    with pytest.raises(ValueError, match="未知字段:overrides"):
        load_run_spec(path)


@pytest.mark.parametrize("bad,needle", [
    ("version: 2\n", "version"),
    ("judge: 'no'\n", "judge"),
    ("concurrency: 0\n", "concurrency"),
    ("cases:\n  - s1\n  - s1\n", "重复"),
])
def test_bad_values_fail_closed(tmp_path, bad, needle):
    corpus = _write_corpus(tmp_path, "alpha.json", ["s1"])
    body = _spec_yaml(str(corpus), "\n  - s1") + bad
    with pytest.raises(ValueError, match=needle):
        load_run_spec(_write_spec(tmp_path, body))


def test_missing_corpus_file_fails_fast(tmp_path):
    with pytest.raises(ValueError, match="不存在"):
        load_run_spec(_write_spec(tmp_path, _spec_yaml("/no/such.json", "\n  - s1")))


# ⑥ 不存在 case id fail fast(干净退出码,真实 CLI)
def test_unknown_case_id_fails_fast(tmp_path):
    corpus = _write_corpus(tmp_path, "alpha.json", ["s1"])
    path = _write_spec(tmp_path, _spec_yaml(str(corpus), "\n  - ghost"))
    out = subprocess.run(
        [sys.executable, "-m", "edu_agent.evals.corpus_round",
         "--config", str(path), "--plan"],
        cwd=REPO, capture_output=True, text=True, timeout=60, check=False)
    assert out.returncode == 2
    assert "case id 不存在:ghost" in out.stderr
    assert "Traceback" not in out.stderr  # fail fast 且体面


def test_ambiguous_bare_id_fails_fast(tmp_path):
    a = _write_corpus(tmp_path, "alpha.json", ["s1"])
    b = _write_corpus(tmp_path, "beta.json", ["s1"])
    scenarios = real_model_scenarios([a, b])
    with pytest.raises(ValueError, match="歧义"):
        resolve_spec_cases(["s1"], scenarios)


def test_jsonl_as_corpus_gets_actionable_error(tmp_path):
    """JSONL 冒充 corpus(#351 审 P3-1 审查者亲踩):裸 Extra data → 可行动提示。"""
    jsonl = tmp_path / "cases.jsonl"
    jsonl.write_text('{"id": "s1"}\n{"id": "s2"}\n', encoding="utf-8")
    spec_path = _write_spec(tmp_path, _spec_yaml(str(jsonl), "\n  - s1"))
    spec = load_run_spec(spec_path)  # 存在性检查过(是文件)
    with pytest.raises(ValueError, match="envelope JSON.*疑似 JSONL"):
        resolve_round(_args(), spec)  # 裸错在装载面转可行动提示


# ⑦ source+resolved 落工件且指纹可复算
def test_spec_artifacts_and_fingerprint(tmp_path):
    src = _write_spec(tmp_path, "version: 1\nname: t\ncorpora: [x]\ncases: [a]\n")
    resolved = {"name": "t", "corpora": ["x"], "cases": ["a"], "judge": True}
    fp = dump_spec_artifacts(tmp_path, src, resolved)
    body = json.loads((tmp_path / "run-spec.resolved.json").read_text(encoding="utf-8"))
    assert body["resolved_sha256"] == fp
    assert (tmp_path / "run-spec.source.yaml").read_text(encoding="utf-8") == src.read_text(encoding="utf-8")
    payload = {k: v for k, v in body.items() if k != "resolved_sha256"}
    recomputed = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    assert recomputed == fp  # 第三方可复算


# ⑧ dirty worktree:dirty 标记与 patch 一致于 git 一手事实
def test_git_dirty_state_matches_git():
    state = git_dirty_state()
    status = subprocess.run(["git", "status", "--porcelain"], cwd=REPO,
                            capture_output=True, text=True, timeout=10)
    assert state["git_dirty"] == bool(status.stdout.strip())
    diff = subprocess.run(["git", "diff", "HEAD"], cwd=REPO,
                          capture_output=True, text=True, timeout=10)
    expected = hashlib.sha256(diff.stdout.encode("utf-8")).hexdigest() if diff.stdout else None
    assert state["git_diff_sha256"] == expected
    if state["git_dirty"] and diff.stdout:
        assert state["patch"] == diff.stdout  # patch 进 artifact 的内容即 git 一手 diff


# ⑨ resume 身份闸:未完成+身份不一致拒;一致续;完成不拦
def _prior_run(collect: Path, identity: dict, dataset_sha: str, statuses: list[str],
               total: int | None = None) -> Path:
    run_dir = collect / "cases-20260918T000000Z-abcd"
    (run_dir / "results").mkdir(parents=True)
    (run_dir / "manifest.json").write_text(json.dumps({
        "dataset": {"sha256": dataset_sha}, "config": {"sha256": "x"},
        "total_cases": total if total is not None else len(statuses)} | {"identity": identity}), encoding="utf-8")
    for i, status in enumerate(statuses):
        (run_dir / "results" / f"c{i}.json").write_text(
            json.dumps({"status": status}), encoding="utf-8")
    return run_dir


def test_resume_identity_gate(tmp_path):
    collect = tmp_path / "collect"
    ident = {"git_sha": "a", "git_diff_sha256": None, "run_spec_sha256": "f"}
    prior = _prior_run(collect, ident, "sha", statuses=["ok"], total=2)  # 未完成(2>1)
    assert resume_run_dir(collect, "sha", ident) == prior        # 身份一致 → 续跑
    with pytest.raises(ResumeMismatch, match="git_sha"):          # 换代码 → 拒
        resume_run_dir(collect, "sha", {**ident, "git_sha": "b"})
    with pytest.raises(ResumeMismatch, match="case 集"):          # 换 case 集 → 拒
        resume_run_dir(collect, "sha2", ident)
    complete = tmp_path / "collect2"
    _prior_run(complete, ident, "sha", statuses=["ok", "ok"])  # total=2 全终态
    assert resume_run_dir(complete, "sha", {"git_sha": "zzz"}) is None  # 已完成不拦改配方重跑
    assert resume_run_dir(tmp_path / "empty", "sha", ident) is None     # 无历史 → 新开
