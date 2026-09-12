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
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .judge import judge_transcript
from .kernel_subject import KernelSubject
from .runner import EvalRunner, RunnerConfig
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
    """场景 → runner cases;无剧本场景(模拟器消费面,#211 边界)显式跳过并返回名单。"""
    cases, skipped = [], []
    for case_id, scenario in scenarios.items():
        if not scenario.get("student_turns"):
            skipped.append(case_id)
            continue
        case = to_kernel_case(scenario)
        case["id"] = case_id
        cases.append(case)
    return cases, skipped


def judge_rows(gateway: Gateway, scenarios: dict[str, dict], results: list[dict]) -> dict[str, dict]:
    """ok 行 → judge 单遍 primary(评分失败记台账不炸整轮,口径同 tuning_round 单遍)。"""
    scores: dict[str, dict] = {}
    for row in results:
        if row["status"] != "ok":
            continue
        scenario = scenarios[row["case_id"]]
        question = scenario["question"]
        messages = []
        for turn in row["transcript"]["turns"]:
            if turn["student"]:
                messages.append({"role": "user", "content": turn["student"]})
            messages.append({"role": "assistant", "content": turn["tutor"]})
        if row["transcript"].get("summary"):
            messages.append({"role": "assistant", "content": row["transcript"]["summary"]})
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


def render_report(out_dir: Path, checks: dict[str, dict], scores: dict[str, dict],
                  diff: dict | None = None, skipped: list[str] | None = None) -> str:
    """报告即工件:逐场景 判定/终态/judge 一行;有基线时加跨轮列与新增红计数。

    跨轮对照收在一个 `diff` 上下文里:`{"from": 上轮 run 目录, "verdicts": {...},
    "prev_scores": {...}}`;有上轮 judge 分(按轮留存在上轮 run 目录)时 judge 列给
    「上轮→本轮」——轮间噪声对比由此可复算(审查 P3,2026-09-12)。
    """
    lines = [
        "# corpus checks × 真模型轮次报告(#216)",
        "",
        f"- 生成:{datetime.now(timezone.utc).isoformat()}",
        f"- 工件:{out_dir}",
    ]
    if skipped:
        lines.append(f"- 跳过无剧本场景:{len(skipped)} 条(模拟器消费面未接线,#211 边界)")
    if diff:
        new_red = sum(1 for v in diff["verdicts"].values() if v == "新增红")
        lines += [f"- 对照基线:{diff['from']}", f"- **新增红:{new_red}**(绿→红 = 回归信号)"]
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
        if "error" in score:
            judge_cell = f"评分失败:{score['error'][:40]}"
        else:
            prev_total = ((diff or {}).get("prev_scores") or {}).get(case_id, {}).get("total")
            prefix = f"{prev_total}→" if prev_total is not None else ""
            judge_cell = (f"total={prefix}{score.get('total')} {score.get('verdict')}"
                          f" 追问={score.get('scores', {}).get('socratic_followup')}")
        diff_cell = diff["verdicts"].get(case_id, "-") if diff else "-"
        lines.append(f"| {case_id} | ok | {row['final_state']} | {check_cell} | {diff_cell} | {judge_cell} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", action="append", default=[],
                        help="corpus 数据集 JSON(可多次;缺省 = teaching_context pilot 20)")
    parser.add_argument("--out", required=True, help="运行根目录(cases/collect/report 落这里)")
    parser.add_argument("--diff-from", dest="diff_from", default=None,
                        help="上轮 collect 下某 run 目录(跨轮对照)")
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args(argv)

    corpus_paths = [Path(p) for p in (args.corpus or DEFAULT_CORPUS)]
    registry = load_registry(REPO / "configs" / "models.yaml")
    probes = {name: _probe(provider.base_url) for name, provider in registry.providers.items()}
    bad = {k: v for k, v in probes.items() if v != "ok"}
    if bad:
        print(f"端点预检失败:{bad}", file=sys.stderr)
        return 1
    facts_dir = Path(tempfile.mkdtemp(prefix="corpus-round-facts-"))
    gateway = Gateway(registry, facts_dir=facts_dir)

    scenarios = real_model_scenarios(corpus_paths)
    cases, skipped = build_cases(scenarios)
    if skipped:
        print(f"跳过无剧本场景 {len(skipped)} 条(模拟器消费面未接线,#211 边界):{','.join(skipped)}")
    if not cases:
        print("没有可跑场景(全部无剧本?)", file=sys.stderr)
        return 1
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cases_file = out_dir / "cases.jsonl"
    cases_file.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n",
                          encoding="utf-8")
    collect_root = out_dir / "collect"
    print(f"批跑:{len(cases)} 场景(真模型口径;确定性口径不在本面)→ {collect_root}")
    EvalRunner(KernelSubject(gateway), RunnerConfig(concurrency=args.concurrency),
               collect_root).run(cases_file, cases)
    run_dir = sorted(collect_root.glob("*-*Z-*"))[-1]
    results = load_results(run_dir)

    checks = check_rows(scenarios, results)
    print(f"评分:{sum(1 for r in results if r['status'] == 'ok')} 行(judge 单遍 primary)")
    scores = judge_rows(gateway, scenarios, results)

    def dump(path: Path, rows: dict[str, dict]) -> None:
        path.write_text("\n".join(json.dumps({"case_id": k, **v}, ensure_ascii=False)
                                  for k, v in sorted(rows.items())) + "\n", encoding="utf-8")

    # 判定与 judge 分按轮留存在各自 run 目录(与 transcript 同处 = 该轮自足可复算);
    # out_dir 根下同名文件是最新一轮的便捷副本。—— 审查 P3(2026-09-12)
    dump(run_dir / "checks.jsonl", checks)
    dump(run_dir / "judge-scores.jsonl", scores)
    dump(out_dir / "checks.jsonl", checks)
    dump(out_dir / "judge-scores.jsonl", scores)

    diff_verdicts, prev_scores = None, None
    if args.diff_from:
        prev_dir = Path(args.diff_from)
        previous = check_rows(scenarios, load_results(prev_dir))
        diff_verdicts = diff_checks(checks, previous)
        prev_file = prev_dir / "judge-scores.jsonl"
        prev_scores = ({row["case_id"]: row for row in (json.loads(line) for line in
                       prev_file.read_text(encoding="utf-8").splitlines() if line.strip())}
                       if prev_file.is_file() else None)
    diff = ({"from": args.diff_from, "verdicts": diff_verdicts, "prev_scores": prev_scores}
            if args.diff_from else None)
    report = render_report(out_dir, checks, scores, diff, skipped)
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
