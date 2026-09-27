#!/usr/bin/env python3
"""S2 battery 运行脚本(#459 件二):24 案 → S2JudgeSubject → runner 断点续跑通道。

运行纪律(方案 v0.1.1,点火令钉死):
- P0-6 resume 同一性门:进 resume 前 manifest.identity 须与当前实现身份完全相等,
  不等即拒绝(引擎/Schema/转换器/prompt 资产/battery 数据/模型配置任一变化,
  原结果即失效,须新开 run);
- P0-2/P0-4 模型身份门:24 案 judge_model 同值 ∧ == judge_primary_model
  (服务通告名,不是 registry 内部 ID);任一不满足 → 整轮作废,不计算 GA/GB;
- 核实重跑 = 新开 run(resume 只补环境失败案,不得当第二次评分);
- 批声明旗标先行(/tmp/edu-agent-batch/,端口竞争教训);
- 期望值泄露防火墙:expected 只进 scorer,模型边界只过 messages(引擎侧钉死,
  sentinel 测试守护)。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from edu_agent.evals import EvalRunner, RunnerConfig, S2JudgeSubject
from edu_agent.gateway import Gateway, load_registry

_REPO = Path(__file__).resolve().parents[1]
_ROLE = "judge"
_AXES = ("s2a", "s2b")
# 口径注记(已呈裁,GA 案级分母 24 与 GB 四案不受影响)
_DENOMINATOR_NOTE = (
    "件一 §4 表头声明 37 显式轴期望(24 S2a+13 S2b);本报告按机械实数计"
    "(当前 36=23+13:C15-T4 的 S2a 未单列,三面件一表/CASES.md/battery 一致)——"
    "轴级分母口径待裁;GA 案级 ≥20/24 与 GB 四案不受影响。"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rubric_freeze_sha(rubric: Path) -> str:
    """冻结件 head -n -1 口径 sha:应恒等于 e381c331…;rubric 被改即变值,
    旧 run 随之拒绝续跑(identity 纪律的机械落点,不做字符串断言)。"""
    head = "".join(rubric.read_text(encoding="utf-8").splitlines(keepends=True)[:-1])
    return hashlib.sha256(head.encode()).hexdigest()


def _identity(models_yaml: Path, battery: Path, rubric: Path,
              prompt_asset: Path, registry) -> dict:
    role = registry.role(_ROLE)
    return {
        "git_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=_REPO, capture_output=True,
            text=True, check=True,
        ).stdout.strip(),
        "rubric_freeze_sha": _rubric_freeze_sha(rubric),
        "prompt_asset_sha": _sha(prompt_asset),
        "battery_sha": _sha(battery),
        "models_yaml_sha": _sha(models_yaml),
        # P0-4 双字段:id 仅追溯,不与 response.model 比;model 才是比较基准
        "judge_primary_id": role.primary,
        "judge_primary_model": registry.model(role.primary).name,
    }


def _resume_gate(run_dir: Path, identity: dict) -> None:
    """P0-6:runner 的 _verify_resume 只比 dataset/config/subject 三面,不比
    identity——本脚本在进入 resume 前补齐该恢复语义(消费现成 manifest 字段)。"""
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        return  # 新目录,由 runner 首建
    stored = json.loads(manifest_path.read_text(encoding="utf-8")).get("identity")
    if stored != identity:
        diff = [k for k in sorted(set(stored or {}) | set(identity))
                if (stored or {}).get(k) != identity.get(k)]
        sys.exit(
            f"resume 拒绝(P0-6):manifest.identity 与当前实现身份不一致"
            f"({', '.join(diff)})——引擎/Schema/转换器/prompt 资产/battery 数据/"
            f"模型配置有变,原结果已失效,请新开 run 目录。"
        )


def _boundary_evidence(expected: dict, actual: dict) -> bool:
    """GB 边界证据:①/④/② marker 词级;U-0 按 marker 或 rationale 二选一(P0-5)。"""
    boundary = expected["boundary"]
    if boundary in actual["boundary_markers"]:
        return True
    return boundary == "U-0" and "U-0" in actual["rationale"]


def _score(rows: list[dict], results: dict[str, dict], identity: dict) -> dict:
    ok_rows = {r["case_id"]: r for r in rows
               if results.get(r["case_id"], {}).get("status") == "ok"}
    models = {results[c]["transcript"]["judge_model"] for c in ok_rows}
    valid_model = (len(models) == 1
                   and bool(ok_rows)
                   and next(iter(models)) == identity["judge_primary_model"])
    case_hits, misses, gb_cases = [], [], []
    for row in rows:
        cid = row["case_id"]
        result = results.get(cid, {})
        if result.get("status") != "ok":
            case_hits.append((cid, False))
            continue
        transcript = result["transcript"]
        hit = True
        for axis in _AXES:
            expected = row["expected"][axis]
            if expected is None:
                continue  # 未单列轴不记分不推断
            actual = transcript[axis]
            if expected["verdict"] != actual["verdict"]:
                hit = False
                misses.append({
                    "case": cid, "axis": axis,
                    "expected": expected["verdict"],
                    "actual": actual["verdict"],
                    "rationale": actual["rationale"][:160],
                })
            if expected["verdict"] == "unsure":
                gb_cases.append((cid, axis, expected,
                                 _boundary_evidence(expected, actual)))
        case_hits.append((cid, hit))
    ga = sum(1 for _, hit in case_hits if hit)
    gb_pass = bool(gb_cases) and all(ok for *_, ok in gb_cases)
    return {
        "total": len(rows),
        "ok": len(ok_rows),
        "model_valid": valid_model,
        "models": sorted(models),
        "ga": ga,
        "gb_cases": gb_cases,
        "gb_pass": gb_pass,
        "misses": misses,
        "case_hits": case_hits,
    }


def _report(run_dir: Path, scored: dict, identity: dict) -> Path:
    lines = [
        "# S2 battery 报告(#459 件二,annotation-only)",
        "",
        f"- run 目录:`{run_dir}`",
        f"- 实现身份:git `{identity['git_sha'][:7]}` / rubric 冻结 `{identity['rubric_freeze_sha'][:12]}…`"
        f" / prompt 资产 `{identity['prompt_asset_sha'][:12]}…` / battery `{identity['battery_sha'][:12]}…`"
        f" / models `{identity['models_yaml_sha'][:12]}…`",
        f"- judge_primary:id `{identity['judge_primary_id']}`(仅追溯)"
        f" / model `{identity['judge_primary_model']}`(比较基准)",
        "",
        "## 运行有效性(P0-2/P0-4)",
        f"- judge_model 集合:{json.dumps(scored['models'], ensure_ascii=False)}",
        f"- 判定:{'单一且=预注册 primary ✓' if scored['model_valid'] else '**作废(VOID)**——任一 fallback/异值即整轮作废,不计算 GA/GB,新开 run'}",
        "",
        "## G0 运行完整性",
        f"- ok {scored['ok']}/{scored['total']}"
        + ("" if scored["ok"] == scored["total"] else "(不完整:environment 可续跑;content 不补跑,呈 ①A/③ 归因)"),
        "",
        "## GA 案级一致(门 ≥20/24;verdict 词级,supporting_turns 仅诊断)",
        f"- {scored['ga']}/{scored['total']}",
        "",
        "## GB unsure 纪律(①/④/② marker 词级;U-0 marker 或 rationale 二选一)",
    ]
    for cid, axis, expected, ok in scored["gb_cases"]:
        lines.append(f"- {cid} {axis}:期望边界 {expected['boundary']}"
                     f" → {'✓' if ok else '✗ 未命中(错误规则猜出的 unsure 不算可靠执行)'}")
    lines += [
        f"- 判定:{'4/4 ✓' if scored['gb_pass'] else '✗(私闭合/边界未命中单列零容忍)'}",
        "",
        f"## miss 清单(GC 归因用:①A 实现失真/①B 翻译失真/② 判据—终验张力/③ 模型执行噪声)",
    ]
    if scored["misses"]:
        for miss in scored["misses"]:
            lines.append(f"- {miss['case']} {miss['axis']}:期望 {miss['expected']}"
                         f" / 实得 {miss['actual']}|rationale:{miss['rationale']}")
    else:
        lines.append("- 无")
    lines += [
        "",
        f"## 口径注记",
        f"- {_DENOMINATOR_NOTE}",
        "- 核实重跑 = 新开 run(resume 只补环境失败案)。",
        "",
    ]
    path = run_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--battery", type=Path,
                        default=_REPO / "docs/evals/s2-judge-battery-v0.1.jsonl")
    parser.add_argument("--artifacts-root", type=Path,
                        default=_REPO / "edu_agent/evals/artifacts/s2-judge-battery-v0.1")
    parser.add_argument("--run-dir", type=Path, default=None,
                        help="续跑既有 run 目录(先过 P0-6 identity 全等门)")
    args = parser.parse_args()

    rubric = _REPO / "docs/evals/s2-judge-rubric-v0.1.md"
    prompt_asset = _REPO / "edu_agent/evals/rubrics/s2_judge_v0_1.yaml"
    models_yaml = Path(os.environ.get("EDU_MODELS_YAML")
                        or _REPO / "configs" / "models.yaml")
    registry = load_registry(models_yaml)
    identity = _identity(models_yaml, args.battery, rubric, prompt_asset, registry)

    if args.run_dir is not None:
        _resume_gate(args.run_dir, identity)  # P0-6:先于 runner 的一切续跑检查

    rows = [json.loads(line) for line in
            args.battery.read_text(encoding="utf-8").strip().splitlines()]
    args.artifacts_root.mkdir(parents=True, exist_ok=True)

    flag = Path(f"/tmp/edu-agent-batch/s2-judge-battery.{os.getpid()}")
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text(f"s2-judge-battery pid={os.getpid()}\n", encoding="utf-8")
    try:
        gateway = Gateway(registry, facts_dir=os.environ.get("EDU_FACTS_DIR") or "facts")
        try:
            runner = EvalRunner(S2JudgeSubject(gateway), RunnerConfig(),
                                runs_root=args.artifacts_root)
            run_dir = runner.run(args.battery, rows,
                                 run_dir=args.run_dir, identity=identity)
        finally:
            gateway.close()
    finally:
        flag.unlink(missing_ok=True)

    results = {
        json.loads(path.read_text(encoding="utf-8"))["case_id"]:
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((run_dir / "results").glob("*.json"))
    }
    scored = _score(rows, results, identity)
    report = _report(run_dir, scored, identity)
    print(f"run 目录:{run_dir}")
    print(f"模型身份:{'单一 ✓' if scored['model_valid'] else 'VOID(作废)'}"
          f"(judge_model={scored['models']},primary={identity['judge_primary_model']})")
    print(f"G0 ok {scored['ok']}/{scored['total']};GA {scored['ga']}/{scored['total']}"
          f"(门 ≥20);GB {'✓' if scored['gb_pass'] else '✗'};"
          f"miss {len(scored['misses'])}")
    print(f"报告:{report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
