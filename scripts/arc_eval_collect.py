#!/usr/bin/env python3
"""#101 双臂评测收集器:11 场景 × 2 重复,按口径 P/F 装配 answer_status。

用法(在**被测臂的工作树**里跑,这样 import 的就是该臂的 prompting.py):

    .venv/bin/python scripts/arc_eval_collect.py --arm M --out <共享 artifacts 目录>

口径定义见 docs/evals/teaching-arc-eval-v1.md(pre-registration,开跑前冻结):
  P = 现状 gate 口径(answer_status 照 tuning_round.build_cases 现状)
  F = 生产同构(剧本语义:equation_complete_reasoning→correct,其余 10 条 stability_*→incorrect)

臂标签只用于输出目录,**不进任何送给模型的 prompt**。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from edu_agent.evals import EvalRunner, KernelSubject, RunnerConfig, load_results  # noqa: E402
from edu_agent.gateway import Gateway, load_registry  # noqa: E402


def _load_tuning_round():
    spec = importlib.util.spec_from_file_location("tr", REPO / "scripts" / "tuning_round.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TR = _load_tuning_round()
REPEATS = 2


def semantic_status(case_id: str) -> str:
    """口径 F:剧本首轮语义 → answer_status(生产映射 service.py:160)。"""
    return "correct" if case_id.endswith("equation_complete_reasoning") else "incorrect"


def build_cases(caliber: str) -> list[dict]:
    """11 场景 × answer_status 装配;口径 P 沿用现状 wiring,口径 F 按语义复原。"""
    cases = []
    for case in TR.CASES:
        row = dict(case)
        if caliber == "F":
            row["answer_status"] = semantic_status(case["id"])
        for repeat in range(1, REPEATS + 1):
            item = dict(row)
            item["id"] = f"{case['id']}__r{repeat}"
            item["base_id"] = case["id"]
            item["repeat"] = repeat
            cases.append(item)
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", required=True, choices=["M", "A"], help="臂标签(只用于路径)")
    parser.add_argument("--out", required=True, help="共享 artifacts 根目录")
    args = parser.parse_args()

    out = Path(args.out).resolve()
    registry = load_registry(REPO / "configs" / "models.yaml")
    gateway = Gateway(registry)
    manifest = {
        "arm": args.arm,
        "worktree": str(REPO),
        "git_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                                  text=True, check=True).stdout.strip(),
        "models_yaml_sha256": hashlib.sha256(
            (REPO / "configs" / "models.yaml").read_bytes()).hexdigest(),
        "tutor": registry.roles["tutor"].primary,
        "repeats": REPEATS,
    }
    try:
        for caliber in ("P", "F"):
            cases = build_cases(caliber)
            cdir = out / caliber / args.arm
            cdir.mkdir(parents=True, exist_ok=True)
            cases_file = cdir / "cases.jsonl"
            cases_file.write_text(
                "\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n", encoding="utf-8")
            run_dir = cdir / "collect"
            EvalRunner(KernelSubject(gateway), RunnerConfig(concurrency=2), run_dir).run(
                cases_file, cases)
            target = sorted(run_dir.glob("*-*Z-*"))
            rows = load_results(target[-1] if target else run_dir)
            ok = sum(1 for r in rows if r["status"] == "ok")
            print(f"[arm {args.arm}] 口径 {caliber}: {ok}/{len(cases)} ok → {run_dir}")
    finally:
        gateway.close()

    mpath = out / f"manifest-{args.arm}.json"
    mpath.parent.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"manifest → {mpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
