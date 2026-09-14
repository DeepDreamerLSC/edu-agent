#!/usr/bin/env python3
"""#254 件1 · #253 点火:offline rescore——存档轨迹 × 当前 judge → 新 Score,不重跑 tutor。

存档 collect run 的 results(transcript)+ 题面 cases.jsonl,按 corpus_round.judge_rows
同款取数(transcript_messages:turns[].student/tutor + summary → messages)重建 judge
输入;挑战案(C15/构造52 等 turns 为 [role,text] 对的 JSON)经 --extra-case 逐个喂,
judge 不被告知来源。单遍 primary(role=judge,mlx_27b),断点续跑复用 runner;
judger.sha256(#238 §5 判分器指纹)随产物落位。判分器本体(checks.py/judge.py)不在
本命令改动面,指纹与 main 一致。

用法:
  uv run python scripts/rescore_judge.py \
    --archive <collect run 目录> <题面 cases.jsonl> \
    [--extra-case <挑战案 JSON>]...        # C15/构造52 等,可多次
    [--only <case_id 清单文件,每行一个>] \
    [--old-scores <旧 judge-scores.jsonl,只做新旧对照>] \
    --out <产物目录> [--concurrency 2]

--archive 可多次(corpus-round-v2 / fix112 等存档源各一)。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from edu_agent.evals import (
    EvalRunner,
    JudgeSubject,
    RunnerConfig,
    judger_sha256,
    load_results,
    run_identity,
    transcript_messages,
)
from edu_agent.gateway import Gateway, load_registry


def _archive_cases(run_dir: Path, cases_file: Path, only: set[str] | None) -> list[dict]:
    """一个存档源 → judge 输入案(ok 行的 transcript × 题面;--only 过滤)。"""
    faces: dict[str, dict] = {}
    for line in cases_file.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            faces[row["id"]] = row
    cases: list[dict] = []
    for row in load_results(run_dir):
        if row["status"] != "ok" or (only is not None and row["case_id"] not in only):
            continue
        face = faces.get(row["case_id"])
        if face is None:
            raise SystemExit(f"题面缺 {row['case_id']}:{cases_file} 中无此 id")
        question = face.get("question")
        cases.append({
            "id": row["case_id"],
            "question": question["text"] if isinstance(question, dict) else question,
            "grade": row["transcript"].get("learner", {}).get("grade", "") or face.get("grade", ""),
            # corpus 题面答案在 question.answer;fix112 等存档在顶层 reference_answer
            "reference_answer": (question.get("answer", "") if isinstance(question, dict) else "")
                               or face.get("reference_answer", ""),
            "messages": transcript_messages(row["transcript"]),
        })
    return cases


def _extra_case(path: Path) -> dict:
    """挑战案 JSON(case_id/question/grade/reference_answer + turns=[[role,text],…])→ judge 输入。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "id": data.get("case_id") or data.get("id"),
        "question": data["question"],
        "grade": data.get("grade", ""),
        "reference_answer": data.get("reference_answer", ""),
        "messages": [{"role": role, "content": text} for role, text in data["turns"]],
    }


def _read_scores(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["case_id"]] = row
    return rows


def _resume_dir(root: Path) -> Path | None:
    """已有的 run 目录(续跑);无则 None 交 runner 自建。"""
    if not root.is_dir():
        return None
    existing = sorted(root.glob("cases-*"))
    return existing[-1] if existing else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", nargs=2, action="append", required=True,
                        metavar=("RUN_DIR", "CASES"),
                        help="存档源:<collect run 目录> <题面 cases.jsonl>,可多次")
    parser.add_argument("--extra-case", dest="extra_cases", action="append", default=[],
                        metavar="JSON", help="挑战案 JSON(turns=[[role,text],…]),可多次")
    parser.add_argument("--only", metavar="FILE",
                        help="case_id 清单文件(每行一个);给了则最终案集 = 清单,缺一报错")
    parser.add_argument("--old-scores", metavar="JSONL", help="旧 judge-scores.jsonl(只做新旧对照)")
    parser.add_argument("--out", required=True, help="产物目录")
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args()

    only = None
    if args.only:
        only = {line.strip() for line in Path(args.only).read_text(encoding="utf-8").splitlines()
                if line.strip()}

    cases: list[dict] = []
    for run_dir, cases_file in args.archive:
        cases += _archive_cases(Path(run_dir), Path(cases_file), only)
    cases += [_extra_case(Path(p)) for p in args.extra_cases]
    if only is not None:
        missing = only - {c["id"] for c in cases}
        if missing:
            print(f"清单案在存档/挑战案中未找全,缺 {len(missing)} 个:{sorted(missing)}",
                  file=sys.stderr)
            return 1
        cases = [c for c in cases if c["id"] in only]
    if not cases:
        print("没有可重判的案(存档全失败或清单为空?)", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cases_file = out / "judge-cases.jsonl"
    cases_file.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n",
                          encoding="utf-8")
    print(f"重判:{len(cases)} 案 → {out}(judge 单遍 primary;judge-cases.jsonl 已落,输入可复算)")

    gateway = Gateway(load_registry(Path("configs/models.yaml")))
    try:
        runner = EvalRunner(JudgeSubject(gateway, role="judge"),
                            RunnerConfig(concurrency=args.concurrency), out / "collect")
        run_dir = runner.run(cases_file, cases, run_dir=_resume_dir(out / "collect"),
                             identity=run_identity())
    finally:
        gateway.close()

    scores = {}
    for row in load_results(run_dir):
        if row["status"] == "ok":
            # runner 把 subject 返回值包在 transcript 键下;judge-scores 平铺 judge 产物本体
            scores[row["case_id"]] = row["transcript"]
    failed = [r["case_id"] for r in load_results(run_dir) if r["status"] != "ok"]

    def dump(path: Path, rows: dict[str, dict]) -> None:
        path.write_text("\n".join(json.dumps({"case_id": k, **{kk: vv for kk, vv in v.items()
                                                               if kk != "case_id"}},
                                             ensure_ascii=False)
                                  for k, v in sorted(rows.items())) + "\n", encoding="utf-8")

    dump(out / "judge-scores.jsonl", scores)
    (out / "judger.sha256").write_text(judger_sha256() + "\n", encoding="utf-8")

    if args.old_scores:
        old = _read_scores(Path(args.old_scores))
        comparison = {
            cid: {"old_verdict": old.get(cid, {}).get("verdict"),
                  "old_answer_leaked": old.get(cid, {}).get("answer_leaked"),
                  "old_total": old.get(cid, {}).get("total"),
                  "new_verdict": row.get("verdict"),
                  "new_answer_leaked": row.get("answer_leaked"),
                  "new_math_integrity": row.get("math_integrity"),
                  "new_total": row.get("total")}
            for cid, row in scores.items()}
        dump(out / "comparison.jsonl", comparison)

    print(f"judger_sha256:{judger_sha256()}")
    if failed:
        print(f"失败 {len(failed)} 案(台账见 collect 下 failures.jsonl,重跑同命令续跑):{failed}",
              file=sys.stderr)
        return 1
    print(f"完成:{len(scores)} 案评分落 {out / 'judge-scores.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
