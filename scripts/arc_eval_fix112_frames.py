#!/usr/bin/env python3
"""#112 before/after 帧:口径 F 重跑 + R 复讲扩展 + L 复读探针(产出 #148 数字的帧网格工具)。

用法(在**被测帧的工作树**里跑,import 的就是该帧的 kernel.py):

    .venv/bin/python scripts/arc_eval_fix112_frames.py --frame before --out edu_agent/evals/artifacts/teaching-arc-fix112

帧定义(#112 派发:修复分支 = main + 112 修复;before 帧 = 修复前同源内核):
  F = #143 冻结口径 F 原样重跑(10 incorrect + 1 correct 场景,剧本不动)——before/after 同剧本可比;
  R = 复讲扩展帧:F 的 10 条 incorrect 场景各追加 S5「学生从头复讲」一句(评测作者撰写的
      学生侧台词,含答案数字、用学生自己的话)——before 帧里 S4 后模型确认即判停、S5 发不出
      (复讲步不存在的对照);after 帧里 S4 触发确定性复讲引导、S5 即复讲内容(残留在留测量点);
  L = 复读探针帧:2 题各 8 轮重复同一句「非卡壳、非懂了、不含答案数字」的学生陈述——
      issue 实测 chicken_rabbit/triangle_area 9 轮不推进的复现探针;轮数对照证据来源;
  P = gate 口径现状 wiring(10 条 None + 2 条 correct)零回归对照(夜评 11 场景同源)。

臂标签恒 M(两帧 prompt 层均为主干版,内核为唯一变量);帧标签只用于输出目录根,不进模型。
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

# R 帧:S5 复讲台词(学生自己的话,从头讲;含答案数字——真实复讲必然复述结论)。
S5_RESTATEMENTS = {
    "chicken_rabbit": "我从头讲一遍:先假设8只全是鸡,只有16只脚;比实际少10只脚,"
                      "每把一只鸡换成兔多2只脚,所以要换5只,兔有5只,鸡有3只。",
    "equation_subtract": "我从头讲:先两边同时减去7,得到3x等于18;再两边同时除以3,"
                         "得到x等于6,代回原式检验相等。",
    "fraction_addition": "我从头讲:先通分,把四分之三化成八分之六;再和八分之一相加,"
                         "分子6加1等于7,结果是八分之七。",
    "triangle_area": "我从头讲:两个完全相同的三角形能拼成一个底10高6的平行四边形,"
                     "面积是10乘6等于60;三角形是它的一半,再除以2等于30平方厘米。",
    "word_problem": "我从头讲:图书馆原有120本,又买来45本,先算120加45等于165本;"
                    "再借出38本,算165减38等于127本,所以现在有127本。",
}

# L 帧:复读探针台词(8 轮逐字重复;不含卡壳/懂了信号词,不含答案数字集)。
LOOP_PROBES = [
    {"stem": "chicken_rabbit",
     "student_line": "我还是觉得鸡有4只,兔有4只。"},
    {"stem": "triangle_area",
     "student_line": "我还是觉得面积就是60平方厘米。"},
]
LOOP_TURNS = 8


def semantic_status(case_id: str) -> str:
    return "correct" if case_id.endswith("equation_complete_reasoning") else "incorrect"


def stem_of(case_id: str) -> str:
    return case_id.rsplit("stability_", 1)[-1]


def base_cases(caliber: str) -> list[dict]:
    """F:#143 口径 F 原样;R:incorrect 场景 + S5;L:2 题 × 8 轮重复探针句。"""
    cases = []
    if caliber == "L":
        by_stem = {stem_of(c["id"]): c for c in TR.CASES if stem_of(c["id"]) in
                   {p["stem"] for p in LOOP_PROBES}}
        for probe in LOOP_PROBES:
            row = dict(by_stem[probe["stem"]])
            row["student_turns"] = [probe["student_line"]] * LOOP_TURNS
            row["answer_status"] = "incorrect"
            cases.append(row)
    elif caliber == "P":
        # gate 口径现状 wiring(tuning_round.build_cases:10 条 None + word_problem correct):
        # 夜评 gate 帧零回归对照——#112 触发只认 incorrect,本口径无 incorrect 场景
        for case in TR.CASES:
            cases.append(dict(case))
    else:
        for case in TR.CASES:
            row = dict(case)
            if caliber == "F":
                row["answer_status"] = semantic_status(case["id"])
            else:  # R:incorrect 场景追加 S5 复讲台词(correct 场景无复讲步,不进 R)
                if semantic_status(case["id"]) != "incorrect":
                    continue
                row["answer_status"] = "incorrect"
                row["student_turns"] = [*row["student_turns"],
                                        S5_RESTATEMENTS[stem_of(case["id"])]]
            cases.append(row)
    out = []
    for case in cases:
        for repeat in range(1, REPEATS + 1):
            item = dict(case)
            item["id"] = f"{case['id']}__r{repeat}"
            item["base_id"] = case["id"]
            item["repeat"] = repeat
            out.append(item)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", required=True, choices=["before", "after", "after101", "before101"],
                        help="帧标签(只用于输出目录根;before=修复前内核,after=修复分支)")
    parser.add_argument("--out", required=True, help="共享 artifacts 根目录")
    parser.add_argument("--base-sha", default="origin/main",
                        help="清单里「与基线一致性」的比对基准(默认 origin/main;"
                             "pre-#101 帧用 6b69a4e,post-#101 帧用 origin/main)")
    parser.add_argument("--calibers", default="F,R,L",
                        help="逗号分隔,默认全跑(F/R/L)——公共纪律:单批 ≤30 分钟可分批")
    args = parser.parse_args()

    out = Path(args.out).resolve()
    registry = load_registry(REPO / "configs" / "models.yaml")
    gateway = Gateway(registry)
    kernel_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                                text=True, check=True).stdout.strip()
    kernel_diff = subprocess.run(
        ["git", "diff", args.base_sha, "HEAD", "--", "edu_agent/agents/small_lecturer/kernel.py"],
        cwd=REPO, capture_output=True, text=True, check=True).stdout
    # prompt 层必须与 main 一致(#112 只变内核;#101 的 prompt 改写不入帧)
    prompting_diff = subprocess.run(
        ["git", "diff", args.base_sha, "HEAD", "--", "edu_agent/agents/small_lecturer/prompting.py"],
        cwd=REPO, capture_output=True, text=True, check=True).stdout
    manifest = {
        "frame": args.frame,
        "worktree": str(REPO),
        "git_sha": kernel_sha,
        "kernel_diff_vs_main_6b69a4e_sha256": hashlib.sha256(
            kernel_diff.encode()).hexdigest()[:16],
        "kernel_diff_vs_base_empty": not bool(kernel_diff.strip()),
        "prompting_diff_vs_base_empty": not bool(prompting_diff.strip()),
        "models_yaml_sha256": hashlib.sha256(
            (REPO / "configs" / "models.yaml").read_bytes()).hexdigest(),
        "tutor": registry.roles["tutor"].primary,
        "judge": registry.roles["judge"].primary,
        "repeats": REPEATS,
        "calibers": args.calibers.split(","),
    }
    try:
        for caliber in args.calibers.split(","):
            cases = base_cases(caliber)
            cdir = out / args.frame / caliber / "M"
            cdir.mkdir(parents=True, exist_ok=True)
            cases_file = cdir / "cases.jsonl"
            cases_file.write_text(
                "\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n",
                encoding="utf-8")
            run_dir = cdir / "collect"
            EvalRunner(KernelSubject(gateway), RunnerConfig(concurrency=2), run_dir).run(
                cases_file, cases)
            target = sorted(run_dir.glob("*-*Z-*"))
            rows = load_results(target[-1] if target else run_dir)
            ok = sum(1 for r in rows if r["status"] == "ok")
            print(f"[frame {args.frame}] 口径 {caliber}: {ok}/{len(cases)} ok → {run_dir}")
    finally:
        gateway.close()

    mpath = out / f"manifest-{args.frame}.json"
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"manifest → {mpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
