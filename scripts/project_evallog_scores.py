#!/usr/bin/env python3
"""#533 EvalLog Review Projection——canonical 分数单向投影进 Inspect EvalLog。

迁移 COMPLETE 后的可观测性小件:读 run 目录的 canonical 评分工件(checks.jsonl /
judge-scores.jsonl / judger.sha256),用 Inspect 官方离线附着面(edit_score +
write_eval_log,即 `inspect score` 同一 API)把 precomputed scores 附到现有 .eval,
Inspect Viewer 即见分数列/筛选。**零 Product 调用 / 零 Judge 调用**:本工具不 import
任何 edu_agent 模块(判分代码不可达),只读文件 + 官方 log API。

五护栏(#533,逐条硬约束,tests/evals/test_project_evallog_scores.py 钉死):
  1. Canonical 永远 truth——投影只读 canonical 工件,canonical 行原文进 score
     metadata,不产生任何新判据;
  2. 每个投影 score 带 projection 块:projection_version / canonical_artifact(名字+
     sha256)/ scoring_identity(judger_sha256=判分器·rubric 指纹,judge 另带 judge_model);
  3. 0 Product / 0 Judge 调用(纯离线,结构性:无判分/网关代码路径);
  4. Canonical 变更后旧投影身份失配——输入 log 若已含投影 score 且其
     canonical_artifact_sha256 ≠ 当前 canonical 工件 sha,拒绝投影并明示;
  5. 禁反向同步——只写输出 .eval;写后复验 run 目录全部 canonical 工件字节不变。

用法:
  uv run python scripts/project_evallog_scores.py <run_dir> \
      [--eval <path.eval>] [--checks <checks.jsonl>] [--judge-scores <judge-scores.jsonl>] \
      [--judger-sha <judger.sha256>] [--facts <facts.jsonl>] [--out <out.eval>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from inspect_ai.log import edit_score, read_eval_log, write_eval_log
from inspect_ai.scorer import ScoreEdit

PROJECTION_VERSION = 1
CHECKS_SCORE = "canonical_checks"
JUDGE_SCORE = "canonical_judge"
# 护栏 5 的 canonical 工件面(字节级不变复验;results/ 单独枚举)
CANONICAL_FILES = ("checks.jsonl", "judge-scores.jsonl", "judger.sha256",
                   "manifest.json", "execution.json", "facts.jsonl")
STALE_EXIT = 2


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class _Face:
    """一个 canonical 评分面的附着参数束(PLR0913:一次收口)。"""

    name: str          # 投影 score 名(canonical_checks / canonical_judge)
    artifact: str      # canonical 工件文件名
    sha: str           # canonical 工件 sha256(护栏 2/4 的身份)
    judger_sha: str    # judger.sha256 判分器·rubric 指纹
    value_of: Callable[[dict], object]
    summary_of: Callable[[dict], str]


def read_rows(path: Path) -> dict[str, dict]:
    """canonical 评分工件 → {case_id: 行原文}(行必须有 case_id,fail closed)。"""
    rows: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if "case_id" not in row:
            raise SystemExit(f"{path}: 行缺 case_id(fail closed,不猜):{line[:120]}")
        rows[row["case_id"]] = row
    if not rows:
        raise SystemExit(f"{path}: 无有效行(fail closed)")
    return rows


def resolve_input_eval(run_dir: Path, explicit: str | None) -> Path:
    """定位输入 .eval:显式路径优先,缺省 run_dir/inspect-logs/ 下唯一 .eval。"""
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise SystemExit(f"--eval 不存在:{path}")
        return path
    logs = sorted((run_dir / "inspect-logs").glob("*.eval"))
    if not logs:
        raise SystemExit(f"{run_dir}/inspect-logs 下无 .eval(投影面向带 Inspect log 的 run)")
    if len(logs) > 1:
        raise SystemExit(f"多个 .eval 请用 --eval 指定:{[p.name for p in logs]}")
    return logs[0]


def _attach(log, sample, name: str, value, explanation: str, metadata: dict) -> None:
    """单样本单面附着:官方 edit_score 在位加 score(即 `inspect score` 同一 API)。
    recompute_metrics=False:不写 run 级派生指标——categorical verdict 被算成
    accuracy=0.0 是伪指标,与 #533 truthfulness 相悖;Viewer 分数列读 sample 级。"""
    edit_score(log, str(sample.id), name, ScoreEdit(value=value, explanation=explanation,
                                                    metadata=metadata),
               recompute_metrics=False, epoch=sample.epoch)


def _checks_value(row: dict):
    """checks score 值:ok 行 = failures 条数(0=无红),非 ok 行 = 状态字面量;
    两者都是 canonical 行的直接呈现,零新判据。"""
    if row.get("status") != "ok":
        return row.get("status", "?")
    return len(row.get("failures") or [])


def _judge_value(payload: dict):
    return payload.get("verdict") or "judge-error"


def _projection_block(artifact_name: str, artifact_sha: str, judger_sha: str,
                      judge_model: str | None) -> dict:
    """护栏 2 的身份块(每个投影 score 一份,内容确定性:无时间戳)。"""
    identity = {"judger_sha256": judger_sha}  # 判分器·rubric 指纹(run 的 judger.sha256 边车)
    if judge_model:
        identity["judge_model"] = judge_model
    return {"projection_version": PROJECTION_VERSION,
            "canonical_artifact": artifact_name,
            "canonical_artifact_sha256": artifact_sha,
            "scoring_identity": identity}


def _attach_face(log, rows: dict[str, dict], face: "_Face") -> int:
    """一个 canonical 面的附着循环:sample id 命中 canonical 行才投影(不缺行冒充)。"""
    attached = 0
    for sample in log.samples or []:
        row = rows.get(str(sample.id))
        if row is None:
            continue
        block = _projection_block(face.artifact, face.sha, face.judger_sha,
                                  row.get("judge_model"))
        explanation = (f"{face.summary_of(row)} | canonical projection "
                       f"v{PROJECTION_VERSION} sha={face.sha[:12]} judger={face.judger_sha[:12]}")
        _attach(log, sample, face.name, face.value_of(row),
                explanation, {"projection": block, "canonical_row": row})
        attached += 1
    if not attached:
        raise SystemExit(f"{face.artifact} 与 .eval 样本 id 零交集(fail closed)")
    return attached


def _checks_summary(row: dict) -> str:
    return (f"status={row.get('status')} declared={row.get('declared')} "
            f"final_state={row.get('final_state')} failures={len(row.get('failures') or [])}")


def _judge_summary(payload: dict) -> str:
    if "verdict" not in payload:
        return f"judge-error:{str(payload.get('error'))[:80]}"
    return (f"verdict={payload['verdict']} total={payload.get('total')} "
            f"answer_leaked={payload.get('answer_leaked')} "
            f"math_integrity={payload.get('math_integrity')}")


def _existing_projection_shas(log) -> dict[str, str]:
    """输入 log 里已存在的投影面:{score 名: 记录的 canonical_artifact_sha256}。"""
    found: dict[str, str] = {}
    for sample in log.samples or []:
        for name, score in (sample.scores or {}).items():
            if name not in (CHECKS_SCORE, JUDGE_SCORE):
                continue
            block = ((score.metadata or {}) if score else {}).get("projection")
            if not isinstance(block, dict):
                raise SystemExit(f"score 名 {name} 已被非投影面占用,拒绝改写(fail closed)")
            found[name] = str(block.get("canonical_artifact_sha256"))
    return found


def _refuse_stale(found: dict[str, str], current: dict[str, str]) -> None:
    """护栏 4:旧投影记录的 canonical sha ≠ 当前工件 sha ⇒ 身份失配,拒绝并明示。"""
    problems = []
    for name, recorded in found.items():
        live = current.get(name, "")
        if recorded != live:
            problems.append(f"{name}: 投影记录 {recorded[:12]}… ≠ 当前 {live[:12]}…")
    if problems:
        raise SystemExit(
            f"拒绝投影:{'; '.join(problems)}。canonical 已变更,旧投影身份失配(#533 护栏 4);"
            "请以原始(未投影).eval 重新投影,勿在旧投影上叠加。")


def _model_census(facts_path: Path) -> dict | None:
    """facts.jsonl → {role: {request/response model 计数}}( truthful 取自 run 工件)。"""
    if not facts_path.is_file():
        return None
    census: dict[str, dict] = {}
    for line in facts_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        fact = json.loads(line)
        role = fact.get("edu.role")
        if role is None:
            continue
        slot = census.setdefault(role, {"request_models": {}, "response_models": {}})
        for key, bucket in (("gen_ai.request.model", "request_models"),
                            ("gen_ai.response.model", "response_models")):
            model = fact.get(key)
            if model:
                slot[bucket][model] = slot[bucket].get(model, 0) + 1
    return census or None


def _attach_provenance_metadata(log, census: dict | None, judge_rows: dict[str, dict],
                                artifacts: dict[str, str]) -> None:
    """truthful model provenance 核齐(#533):真实身份由 eval.metadata 承载并进 Viewer;
    header model 保持 sentinel,不改成真实模型名(另一种失真,#533 裁定)。"""
    metadata = dict(log.eval.metadata or {})
    metadata["model_provenance"] = {
        "transport_owner": "edu-agent Gateway",
        "subject_model": (census or {}).get("tutor") or {
            "note": "run 目录无 facts.jsonl——主体模型名未在工件内记录,不代填"},
        "models_by_role": census or {
            "note": "run 目录无 facts.jsonl——各角色模型调用未在工件内记录"},
        "grader_model": sorted({row["judge_model"] for row in judge_rows.values()
                                if row.get("judge_model")}) or None,
        "header_model": {"value": log.eval.model,
                         "note": "sentinel 占位:模型调用不经 Inspect 模型通道,"
                                 "由 edu-agent Gateway 承载;不改成真实名(#533 裁定)"},
    }
    metadata["score_projection"] = {
        "projection_version": PROJECTION_VERSION,
        "canonical_artifacts": artifacts,
        "direction": "canonical → EvalLog 单向投影;EvalLog 分数是可删可重建的视图",
    }
    log.eval.metadata = metadata


def _canonical_snapshot(run_dir: Path, explicit: dict[str, Path | None]) -> dict[Path, str]:
    """护栏 5 基线:canonical 面候选 = run 目录固定名 + results/** + 显式工件路径,
    存在即入快照(用户把某面指到 run 外时不漏拍 run 内同名工件)。"""
    candidates = [run_dir / name for name in CANONICAL_FILES]
    candidates += [p for p in explicit.values() if p is not None]
    candidates += [p for p in (run_dir / "results").rglob("*") if p.is_file()]
    return {p: sha256_file(p) for p in candidates if p.is_file()}


def _verify_unchanged(before: dict[Path, str]) -> None:
    for path, sha in before.items():
        if not path.is_file() or sha256_file(path) != sha:
            raise SystemExit(f"护栏 5 违例:canonical 工件被改动 {path}(本工具只读 canonical)")


def _resolve_judger(explicit: Path | None, judge_path: Path, run_dir: Path) -> Path:
    """judger.sha256 定位:显式(必须在场)> judge-scores 同目录(rescore 形态)> run 根。"""
    if explicit is not None:
        if not explicit.is_file():
            raise SystemExit(f"--judger-sha 不存在:{explicit}")
        return explicit
    for candidate in (judge_path.parent / "judger.sha256", run_dir / "judger.sha256"):
        if candidate.is_file():
            return candidate
    raise SystemExit("缺 judger.sha256(判分器指纹,护栏 2 的 scoring_identity,不投影)")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path, help="run 目录(含 .eval 与 canonical 工件)")
    parser.add_argument("--eval", help="输入 .eval(缺省 run_dir/inspect-logs/ 唯一 .eval)")
    parser.add_argument("--checks", type=Path, help="canonical checks.jsonl(缺省 run_dir 下)")
    parser.add_argument("--judge-scores", type=Path,
                        help="canonical judge-scores.jsonl(缺省 run_dir 下)")
    parser.add_argument("--judger-sha", type=Path,
                        help="judger.sha256(缺省 judge-scores 同目录,再缺省 run 根)")
    parser.add_argument("--facts", type=Path, help="facts.jsonl(缺省 run_dir 下,可缺)")
    parser.add_argument("--out", type=Path, help="输出 .eval(缺省输入旁 *.projected.eval)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    run_dir = args.run_dir.resolve()
    checks_path = args.checks or run_dir / "checks.jsonl"
    judge_path = args.judge_scores or run_dir / "judge-scores.jsonl"
    if not checks_path.is_file() and not judge_path.is_file():
        raise SystemExit(f"{run_dir} 无 canonical 评分工件(checks/judge-scores 至少一件)")
    judger_path = _resolve_judger(args.judger_sha, judge_path, run_dir)
    judger_sha = judger_path.read_text(encoding="utf-8").strip()
    input_eval = resolve_input_eval(run_dir, args.eval)
    out_path = args.out or input_eval.with_name(input_eval.stem + ".projected.eval")
    if out_path.resolve() == input_eval.resolve():
        raise SystemExit("--out 不得等于输入 .eval(原始 EvalLog 不改写,投影只出旁路 .projected.eval)")
    if out_path.resolve() in {p.resolve() for p in (checks_path, judge_path, judger_path)}:
        raise SystemExit("--out 不得指向 canonical 工件(护栏 5:禁反向同步)")
    snapshot = _canonical_snapshot(run_dir, {"checks.jsonl": checks_path,
                                             "judge-scores.jsonl": judge_path,
                                             "judger.sha256": judger_path,
                                             "manifest.json": None, "execution.json": None,
                                             "facts.jsonl": args.facts})
    log = read_eval_log(input_eval)
    current: dict[str, str] = {}
    attached: dict[str, int] = {}
    artifacts: dict[str, str] = {}
    faces: list[_Face] = []
    for path, name, value_of, summary_of in (
            (checks_path, CHECKS_SCORE, _checks_value, _checks_summary),
            (judge_path, JUDGE_SCORE, _judge_value, _judge_summary)):
        if path.is_file():
            current[name] = sha256_file(path)
            artifacts[path.name] = current[name]
            faces.append(_Face(name, path.name, current[name], judger_sha,
                               value_of, summary_of))
    _refuse_stale(_existing_projection_shas(log), current)  # 护栏 4
    judge_rows = read_rows(judge_path) if judge_path.is_file() else {}
    for face in faces:
        rows = judge_rows if face.name == JUDGE_SCORE else read_rows(checks_path)
        attached[face.name] = _attach_face(log, rows, face)
    _attach_provenance_metadata(
        log, _model_census(args.facts or run_dir / "facts.jsonl"), judge_rows, artifacts)
    write_eval_log(log, out_path)
    _verify_unchanged(snapshot)  # 护栏 5 写后复验
    _refuse_stale(_existing_projection_shas(read_eval_log(out_path)), current)  # 写后自检
    print(f"投影完成:{out_path}")
    for name, count in attached.items():
        print(f"  {name}: {count} scores(0 模型调用,#533 护栏 3)")
    print(f"  provenance:model_provenance/score_projection 已入 eval.metadata"
          f"(header model={log.eval.model!r} sentinel 保持)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
