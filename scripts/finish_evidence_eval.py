#!/usr/bin/env python3
"""finish() 完成判定语义修订(2026-09-16 用户裁)的最小真实内核验收跑批器。

验收矩阵(answer_status=correct 四形态,同一题,各 2 重复):
  零发言 / 只报答案 / 两轮空泛回应 → 不得完成(final_state=needs_review);
  一轮完整解释 → 允许完成(ready_to_confirm 由修订后提示词驱动,零调用模板收束)。

被测 = KernelSubject(start→reply×N→finish)+ judge 六维单遍盲评。模型全本地:
tutor=qwen3_vl_8b@8303,judge=mlx_27b@8301。**零远程硬保证**:运行时从注册表
剥离 deepseek provider 并摘除引用它的 fallback(configs/models.yaml 不动,manifest
申明 sanitized);本地端点失败 = EnvironmentFailure 硬失败,不静默降级到远程。
跑后审计 facts.jsonl 的 gen_ai.provider.name / edu.fallback_to,出现非本地
provider 即非零退出。

用法(在被测工作树里):
    .venv/bin/python scripts/finish_evidence_eval.py --out <artifacts 目录>
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from edu_agent.evals import EvalRunner, KernelSubject, RunnerConfig, load_results
from edu_agent.evals.judge import judge_transcript
from edu_agent.gateway import Gateway, load_registry

REPEATS = 2
QUESTION = {"text": "把 12 个苹果平均分成 4 份,每份 3 个,取其中的 3 份,是多少个?",
            "answer": "9 个"}
FULL_EXPLANATION = "12 个平均分成 4 份,每份 3 个,取其中 3 份,所以是 9 个。"
BASE_CASES = [
    {"id": "finish_evidence_zero_utterance", "student_turns": [],
     "expect_final_state": "needs_review"},
    {"id": "finish_evidence_answer_only", "student_turns": ["9 个。"],
     "expect_final_state": "needs_review"},
    {"id": "finish_evidence_vague_two", "student_turns": ["好像还行吧。", "就那样算的呗。"],
     "expect_final_state": "needs_review"},
    {"id": "finish_evidence_full_explanation", "student_turns": [FULL_EXPLANATION],
     "expect_final_state": "completed"},
]


def build_cases() -> list[dict]:
    cases = []
    for base in BASE_CASES:
        for repeat in range(1, REPEATS + 1):
            item = {"question": QUESTION, "grade": "三年级", "answer_status": "correct"}
            item.update(base)
            item["id"] = f"{base['id']}__r{repeat}"
            cases.append(item)
    return cases


def sanitize_registry(registry):
    """零远程硬保证:剥离非本地 provider 及其模型,摘除引用已删模型的 fallback。

    全部 frozen dataclass → 以 dataclasses.replace 重建,原 registry 不动。"""
    removed = [name for name, p in registry.providers.items()
               if "127.0.0.1" not in p.base_url]
    providers = {n: p for n, p in registry.providers.items() if n not in removed}
    models = {n: m for n, m in registry.models.items() if m.provider in providers}
    roles = {}
    for name, role in registry.roles.items():
        if role.primary not in models:
            continue  # 角色整体引用已剥离模型(如 judge_independent)→ 移除
        if role.fallback and role.fallback not in models:
            role = dataclasses.replace(role, fallback=None)
        roles[name] = role
    return dataclasses.replace(registry, providers=providers, models=models, roles=roles), removed


def _judge_ok_rows(gateway: Gateway, rows: list[dict]) -> dict[str, dict]:
    """ok 行 → judge 单遍盲评(transcript turns 展开,summary 收尾;口径同 corpus_round)。"""
    scores: dict[str, dict] = {}
    for row in rows:
        if row["status"] != "ok":
            continue
        t = row["transcript"]
        messages = [{"role": "user", "content": turn["student"]}
                    for turn in t["turns"] if turn["student"]]
        messages += [{"role": "assistant", "content": turn["tutor"]}
                     for turn in t["turns"]]
        if t.get("summary"):
            messages.append({"role": "assistant", "content": t["summary"]})
        scores[row["case_id"]] = judge_transcript(gateway, {
            "id": row["case_id"], "question": QUESTION["text"], "grade": "三年级",
            "reference_answer": QUESTION["answer"], "messages": messages})
    return scores


def _audit_facts(facts_dir: Path, registry) -> tuple[dict, list[str], list[str]]:
    """facts.jsonl → (audit, providers_used, fallbacks);调用数按角色计数。"""
    facts = [json.loads(line) for f in sorted(facts_dir.glob("model_calls-*.jsonl"))
             for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
    providers_used = sorted({f.get("gen_ai.provider.name", "") for f in facts})
    fallbacks = sorted({f.get("edu.fallback_to") for f in facts
                        if f.get("edu.fallback_to")})
    calls_by_role: dict[str, int] = {}
    for f in facts:
        role = f.get("edu.role", "?")
        calls_by_role[role] = calls_by_role.get(role, 0) + 1
    audit = {"providers_used": providers_used, "fallback_to": fallbacks,
             "calls_by_role": calls_by_role}
    return audit, providers_used, fallbacks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, help="artifacts 输出目录")
    args = parser.parse_args()
    out = Path(args.out).resolve()
    (out / "collect").mkdir(parents=True, exist_ok=True)

    registry_before = load_registry(REPO / "configs" / "models.yaml")
    registry, removed = sanitize_registry(registry_before)
    removed_roles = sorted(set(registry_before.roles) - set(registry.roles))
    non_local = {name: p.base_url for name, p in registry.providers.items()
                 if "127.0.0.1" not in p.base_url}
    if non_local or removed == []:
        print(f"零远程前置失败:non_local={non_local} removed={removed}", file=sys.stderr)
        return 1

    cases = build_cases()
    cases_file = out / "cases.jsonl"
    cases_file.write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n", encoding="utf-8")

    facts_dir = out / "facts"
    gateway = Gateway(registry, facts_dir=facts_dir)
    manifest = {
        "purpose": "finish-evidence acceptance eval(2026-09-16 用户裁语义修订)",
        "git_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                                  capture_output=True, text=True).stdout.strip(),
        "prompts_sha256": hashlib.sha256(
            (REPO / "edu_agent" / "agents" / "small_lecturer" / "prompting.py")
            .read_bytes()).hexdigest(),
        "models_yaml_sha256": hashlib.sha256(
            (REPO / "configs" / "models.yaml").read_bytes()).hexdigest(),
        "registry_sanitized_removed_providers": removed,
        "registry_sanitized_removed_roles": removed_roles,
        "tutor": registry.roles["tutor"].primary,
        "judge": registry.roles["judge"].primary,
        "repeats": REPEATS,
        "expectations": {c["id"]: c["expect_final_state"] for c in cases},
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        EvalRunner(KernelSubject(gateway), RunnerConfig(concurrency=2),
                   out / "collect").run(cases_file, cases)
        rows = load_results(sorted((out / "collect").glob("*-*Z-*"))[-1])
        scores = _judge_ok_rows(gateway, rows)
    finally:
        gateway.close()
    (out / "judge-scores.json").write_text(
        json.dumps(scores, ensure_ascii=False, indent=1), encoding="utf-8")

    # 判定 + facts 审计(零远程:任何非本地 provider 或 fallback 记录 → 非零退出)
    audit, providers_used, fallbacks = _audit_facts(facts_dir, registry)
    bad_providers = [p for p in providers_used if p and "127.0.0.1" not in
                     registry.providers[p].base_url]
    (out / "remote-audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=1), encoding="utf-8")

    by_case: dict[str, list[dict]] = {}
    for row in rows:
        base_id = row["case_id"].rsplit("__", 1)[0]
        by_case.setdefault(base_id, []).append(row)
    all_pass = True
    lines = ["| 案例 | 期望 | 实测(final_state ×重复) | 判定 | judge 均分(/12) |",
             "|---|---|---|---|---:|"]
    for base in BASE_CASES:
        rows_ = by_case[base["id"]]
        states = [r["transcript"]["final_state"] if r["status"] == "ok" else f"ERR:{r['status']}"
                  for r in rows_]
        totals = [scores[r["case_id"]]["total"] for r in rows_
                  if r["case_id"] in scores and "total" in scores[r["case_id"]]]
        ok = all(s == base["expect_final_state"] for s in states)
        all_pass = all_pass and ok
        mean = f"{sum(totals) / len(totals):.1f}" if totals else "-"
        lines.append(f"| {base['id']} | {base['expect_final_state']} | "
                     f"{' / '.join(states)} | {'PASS' if ok else 'FAIL'} | {mean} |")
    lines += ["", f"providers_used={providers_used} fallback_to={fallbacks or '无'}",
              f"calls_by_role={audit['calls_by_role']}"]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    if bad_providers or fallbacks:
        print(f"零远程审计失败:bad_providers={bad_providers} fallbacks={fallbacks}",
              file=sys.stderr)
        return 1
    return 0 if all_pass else 2


if __name__ == "__main__":
    sys.exit(main())
