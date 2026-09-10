#!/usr/bin/env python3
"""M2 调优循环一轮(00 §8.4 阶段 3):收集(内核)→ 评分(judge)→ 对照两轮基线。

用法:uv run python scripts/tuning_round.py --out var/tuning/round-N [--nightly]
11 场景 = 基线同款三数据集;judge 单遍 primary(调优轮口径;双评留正式轮);
对照值 = 基线报告 §3 R1×R2 两轮固定值(docs/evals/baseline-run1-run2.md,#58 落盘快照),
容差口径 = #34 2026-09-09 人批:场景两轮分差 ≤1 → 单值判(本轮 ≥ max(R1,R2) 才达标);
分差 ≥2 → 区间判([min,max] 落入即"不劣(噪声主导)",不判反超)。
数字全部落盘不手拼;判停/状态读 transcript 内部字段,不从学生文本反推。
--nightly(每晚 23:00,evals-nightly.yml):先预检(注册表全部 provider 端口可达,
不可达退出 1)并落溯源 manifest(git sha、models.yaml 哈希、launchctl 服务快照)
——劣化起始日的环境可解释性(1b 教训:蹭机服务几个月无人察觉)。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from scripts.json_first_pass import json_first_pass_report

from edu_agent.evals import EvalRunner, KernelSubject, RunnerConfig, judge_transcript, load_results
from edu_agent.gateway import Gateway, ModelRegistry, load_registry

REPO = Path(__file__).resolve().parents[1]
DATASETS = REPO / "edu_agent" / "evals" / "datasets"

# 两轮固定基线(基线报告 §3 R1/R2,#58 落盘快照;case_id → (R1, R2))
BASELINE = {
    "small_lecturer_dialogue_scenarios_equation_complete_reasoning": (8, 8),
    "small_lecturer_dialogue_stability_20_stability_chicken_rabbit": (6, 9),
    "small_lecturer_dialogue_stability_20_stability_equation_subtract": (7, 7),
    "small_lecturer_dialogue_stability_20_stability_fraction_addition": (3, 4),
    "small_lecturer_dialogue_stability_20_stability_triangle_area": (3, 3),
    "small_lecturer_dialogue_stability_20_stability_word_problem": (11, 5),
    "small_lecturer_teaching_context_shadow_pilot_20_stability_chicken_rabbit": (5, 5),
    "small_lecturer_teaching_context_shadow_pilot_20_stability_equation_subtract": (4, 4),
    "small_lecturer_teaching_context_shadow_pilot_20_stability_fraction_addition": (3, 4),
    "small_lecturer_teaching_context_shadow_pilot_20_stability_triangle_area": (2, 3),
    "small_lecturer_teaching_context_shadow_pilot_20_stability_word_problem": (11, 8),
}


def tolerance_verdict(got: int, r1: int, r2: int) -> str:
    """#34 2026-09-09 人批容差:两轮分差 ≤1 单值判(≥max 达标);≥2 区间判(≥min 不劣)。"""
    if abs(r1 - r2) <= 1:
        return "达标" if got >= max(r1, r2) else "低于基线"
    return "不劣(噪声主导)" if got >= min(r1, r2) else "低于基线"


def _probe(url: str, timeout: float = 2.0) -> str:
    """provider base_url 的 host:port TCP 可达性;返回 ok/失败原因。"""
    parsed = urlparse(url)
    host, port = parsed.hostname or "127.0.0.1", parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "ok"
    except OSError as exc:
        return f"不可达:{exc.__class__.__name__}"


def nightly_preflight(registry: ModelRegistry, out: Path) -> None:
    """预检 + 溯源 manifest(--nightly):端口不可达直接退出 1(流水线红灯)。"""
    probes = {name: _probe(p.base_url) for name, p in registry.providers.items()}
    unreachable = {k: v for k, v in probes.items() if v != "ok"}
    sha = os.environ.get("GITHUB_SHA", "").strip() or subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
        cwd=REPO).stdout.strip()
    models_sha = hashlib.sha256((REPO / "configs" / "models.yaml").read_bytes()).hexdigest()[:16]
    try:
        services = subprocess.run(["launchctl", "list"], capture_output=True,
                                  text=True, check=True).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        services = []  # 非 macOS 环境只留空快照
    (out / "manifest.json").write_text(json.dumps({
        "git_sha": sha, "models_yaml_sha256": models_sha,
        "provider_probes": probes, "launchctl_services": services,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    if unreachable:
        for name, why in unreachable.items():
            print(f"nightly 预检失败:provider {name} {why}", file=sys.stderr)
        sys.exit(1)


def build_cases() -> list[dict]:
    """11 场景:dialogue_scenarios 1 + stability_20 5 + teaching_context 5(基线同款)。"""
    bank = {r["question_id"]: r for r in json.loads(
        (REPO / "edu_agent" / "contracts" / "release_acceptance_seed_question_bank.json").read_text(encoding="utf-8"))["records"]}
    stability_ids = ["chicken_rabbit", "equation_subtract", "fraction_addition",
                     "triangle_area", "word_problem"]
    cases = []

    def scenario_row(dataset_name: str, wanted_id: str) -> dict:
        rows = json.loads((DATASETS / f"{dataset_name}.json").read_text(encoding="utf-8"))["scenarios"]
        return next(r for r in rows if r["id"] == wanted_id)

    by_stem = {r["stem"]: r for r in bank.values()}

    def bank_record(key: str, question: str) -> dict:
        return bank.get(key) or by_stem.get(question) or {}  # id 优先,题干文本兜底(同题不同 id)

    for dataset, sid in [("small_lecturer_dialogue_scenarios", "equation_complete_reasoning")] + \
                        [("small_lecturer_dialogue_stability_20", f"stability_{s}") for s in stability_ids] + \
                        [("small_lecturer_teaching_context_shadow_pilot_20", f"stability_{s}") for s in stability_ids]:
        row = scenario_row(dataset, sid)
        bank_key = sid.removeprefix("stability_") if sid.startswith("stability_") else sid
        record = bank_record(bank_key, row["question"])
        # R6 评测数据侧(任务书第 3 条):word_problem 补传 answer_status 验证策略分派
        # 与结构化 summary 通路;其余场景不带(unknown → 首问无提示、finish 走原路径)。
        answer_status = "correct" if bank_key == "word_problem" else None
        cases.append({
            "id": f"{dataset}_{sid}",
            "question": row["question"],
            "student_turns": row["student_turns"],
            "grade": record.get("grade", ""),
            "reference_answer": record.get("answer", ""),
            **({"answer_status": answer_status} if answer_status else {}),
        })
    return cases


def to_judge_cases(rows: list[dict]) -> list[dict]:
    """run 结果 → judge 输入(judge_score.py 同款形态;transcript 的 turns 展开)。"""
    judge_cases = []
    for row in rows:
        if row["status"] != "ok":
            continue
        t = row["transcript"]
        messages = []
        for turn in t["turns"]:
            if turn["student"]:
                messages.append({"role": "user", "content": turn["student"]})
            messages.append({"role": "assistant", "content": turn["tutor"]})
        if t.get("summary"):
            messages.append({"role": "assistant", "content": t["summary"]})
        judge_cases.append({
            "id": row["case_id"],
            "question": next(c["question"] for c in CASES if c["id"] == row["case_id"]),
            "grade": t.get("learner", {}).get("grade", ""),
            "reference_answer": next(c["reference_answer"] for c in CASES if c["id"] == row["case_id"]),
            "messages": messages,
        })
    return judge_cases


CASES = build_cases()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="输出目录,如 var/tuning/round-1")
    parser.add_argument("--nightly", action="store_true",
                        help="夜评模式:预检 provider 可达性 + 落溯源 manifest(evals-nightly.yml)")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    registry = load_registry(REPO / "configs" / "models.yaml")
    if args.nightly:
        nightly_preflight(registry, out)
    facts_dir = Path(os.environ.get("EDU_FACTS_DIR") or REPO / "facts")
    gateway = Gateway(registry, facts_dir=facts_dir)
    try:
        print(f"收集:11 场景,KernelSubject(tutor 主选 {registry.roles['tutor'].primary})")
        run_dir = out / "collect"
        cases_file = out / "cases.jsonl"
        cases_file.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in CASES) + "\n",
                              encoding="utf-8")
        EvalRunner(KernelSubject(gateway), RunnerConfig(concurrency=2), run_dir).run(
            cases_file, CASES)
        rows = load_results(_latest_run(run_dir))
        judge_input = to_judge_cases(rows)
        (out / "judge-cases.jsonl").write_text(
            "\n".join(json.dumps(c, ensure_ascii=False) for c in judge_input) + "\n", encoding="utf-8")
        print(f"评分:{len(judge_input)} case(judge 27B,单遍 primary)")
        scores = {}
        for case in judge_input:
            verdict = judge_transcript(gateway, case)
            scores[case["id"]] = verdict
            print(f"  {case['id'][:58]:60s} total={verdict['total']:2d} {verdict['verdict']}")
    finally:
        gateway.close()

    (out / "judge-scores.json").write_text(json.dumps(scores, ensure_ascii=False, indent=1), encoding="utf-8")
    report = ["# 调优轮对照(vs 基线 R1×R2,#34 容差口径:分差≤1 单值判/≥2 区间判)", "",
              "| 场景 | R1 | R2 | 本轮 | 判定 |", "|---|---:|---:|---:|---|"]
    deltas = []
    for case_id, (r1, r2) in BASELINE.items():
        got = scores.get(case_id, {}).get("total")
        if got is None:
            report.append(f"| {case_id} | {r1} | {r2} | 失败 | FAIL |")
            continue
        deltas.append(got - (r1 + r2) / 2)
        report.append(f"| {case_id} | {r1} | {r2} | {got} | {tolerance_verdict(got, r1, r2)} |")
    report += ["", f"逐维均分:见 judge-scores.json;对两轮均值差:{sum(deltas) / len(deltas):+.2f}"]
    # #34 M2 出口条件:json 一次通过率(结构化输出合规率,01 §6)
    jfp_text = json_first_pass_report(facts_dir)
    report += jfp_text.splitlines() + [""]
    text = "\n".join(report) + "\n"
    (out / "comparison.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


def _latest_run(root: Path) -> Path:
    return sorted(root.glob("*-*Z-*"))[-1] if sorted(root.glob("*-*Z-*")) else root


if __name__ == "__main__":
    sys.exit(main())
