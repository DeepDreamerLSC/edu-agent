#!/usr/bin/env python3
"""S2 battery 运行脚本(#459 件二):24 案 → S2JudgeSubject → 断点续跑通道。

默认 execution owner = Inspect(#521 I6-A):case 级调度/并发/sample retry 归
inspect-ai(execution-only 轮,无 scorer 面),checkpoint 仍是 Canonical durable
evidence + 被动幂等守卫;GA/GB/VOID 判分与模型身份门是 run 级确定性计算,仍由
本脚本自 results/*.json checkpoint 复算——report 语义与 expected 泄露防火墙零变化。
`--legacy-runner` 过渡回退已删(#521 I6-C C3):Inspect 是唯一执行面。

运行纪律(方案 v0.1.1,点火令钉死):
- P0-6 resume 同一性门(#490 M3 起由公共层承载):strict 门在 inspect_adapter
  preflight(同一 _identity_resume_diffs 全等比较,另加 owner/harness 面,跨 owner
  混续拒绝)——manifest.identity 须与当前实现身份完全相等,不等即拒(引擎/Schema/
  转换器/prompt 资产/battery 数据/模型配置任一变化,原结果即失效,须新开 run);
  identity 指纹构造走公共 helper(#490 M0 表第③项);
- P0-2/P0-4 模型身份门:24 案 judge_model 同值 ∧ == judge_primary_model
  (服务通告名,不是 registry 内部 ID);身份比较走公共 compare_models(#490 M2),
  任一不满足 → 整轮作废,不计算 GA/GB(VOID 处置留本脚本);
- 核实重跑 = 新开 run(resume 只补环境失败案,不得当第二次评分);
- 批声明旗标先行(/tmp/edu-agent-batch/,端口竞争教训);
- 期望值泄露防火墙:expected 只进 scorer,模型边界只过 messages(引擎侧钉死,
  sentinel 测试守护)。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from edu_agent.evals import (
    InspectRoundRequest,
    ResumeMismatch,
    RunnerConfig,
    S2JudgeSubject,
    compare_models,
    file_sha256,
    git_head_sha,
    head_sha256,
    run_inspect_round,
)
from edu_agent.gateway import Gateway, load_registry

_REPO = Path(__file__).resolve().parents[1]
_ROLE = "judge"
_AXES = ("s2a", "s2b")
_INSPECT_TASK = "edu_s2_judge_battery"  # Task 名即 provenance,不冒名 corpus 轮
# 口径注记(已呈裁,GA 案级分母 24 与 GB 四案不受影响)
_DENOMINATOR_NOTE = (
    "轴级分母 = 36 显式轴期望(23 S2a+13 S2b):终裁机械真值——C15-T4 的 S2a 未单列,"
    "未单列轴不记分不推断(不为凑 37 补裁)。件一 v0.1 表头的 37 声明系算术口径偏差,"
    "已由 rubric v0.2 改字(PR #463);GA 案级 ≥20/24 分母不受影响(GB 案数随期望动态,v0.3 起 = 3)。"
)


def _identity(models_yaml: Path, battery: Path, rubric: Path,
              prompt_asset: Path, registry) -> dict:
    role = registry.role(_ROLE)
    return {
        # 指纹构造走公共 helper(#490 M0 表第③项):文件字节/rubric 冻结
        # (head -n -1)/git HEAD 三面;字段集与键名仍由本专项声明
        "git_sha": git_head_sha(_REPO),
        "rubric_freeze_sha": head_sha256(rubric),
        "prompt_asset_sha": file_sha256(prompt_asset),
        "battery_sha": file_sha256(battery),
        "models_yaml_sha": file_sha256(models_yaml),
        # P0-4 双字段:id 仅追溯,不与 response.model 比;model 才是比较基准
        "judge_primary_id": role.primary,
        "judge_primary_model": registry.model(role.primary).name,
    }


def _boundary_evidence(expected: dict, actual: dict) -> bool:
    """GB 边界证据:①/④/② marker 词级;U-0 按 marker 或 rationale 二选一(P0-5)。"""
    boundary = expected["boundary"]
    if boundary in actual["boundary_markers"]:
        return True
    return boundary == "U-0" and "U-0" in actual["rationale"]


def _score(rows: list[dict], results: dict[str, dict], identity: dict) -> dict:
    ok_rows = {r["case_id"]: r for r in rows
               if results.get(r["case_id"], {}).get("status") == "ok"}
    # P0-2/P0-4 模型身份比较(#490 M2 公共 helper):observed 提取(仅 ok 行的
    # transcript.judge_model)与 VOID 处置留本脚本
    comparison = compare_models(
        (results[c]["transcript"]["judge_model"] for c in ok_rows),
        identity["judge_primary_model"])
    valid_model = comparison.matched
    case_hits, misses, gb_cases, turns_diag = [], [], [], []
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
            # D2:supporting_turns 仅诊断——精确匹配计数(列表相等,序敏感;
            # [t2,t3] vs [t3,t2] 不算精确),不入 GA
            turns_match = actual["supporting_turns"] == expected["turns"]
            turns_diag.append({"case": cid, "axis": axis,
                               "expected": expected["turns"],
                               "actual": actual["supporting_turns"],
                               "match": turns_match})
            if expected["verdict"] != actual["verdict"]:
                hit = False
                misses.append({
                    "kind": "verdict", "case": cid, "axis": axis,
                    "expected": expected["verdict"],
                    "actual": actual["verdict"],
                    "rationale": actual["rationale"][:160],
                })
            if expected["verdict"] == "unsure":
                # GB 钉死定义:输出 unsure ∧ 命中预期边界证据,两条件同时满足
                # (P0 修复:此前只看证据——verdict=yes 带正确 marker 也会过门)
                evidence_ok = _boundary_evidence(expected, actual)
                gb_cases.append((cid, axis, expected,
                                 actual["verdict"] == "unsure" and evidence_ok))
                # GB-only miss 也必须进归因输入(GC:全部 miss 必须归因)——
                # verdict 命中但边界证据未命中 = 边界 miss,单列 kind
                if evidence_ok is False and expected["verdict"] == actual["verdict"]:
                    misses.append({
                        "kind": "boundary", "case": cid, "axis": axis,
                        "expected": f"unsure+{expected['boundary']}(边界证据)",
                        "actual": f"unsure,markers={actual['boundary_markers']}",
                        "rationale": actual["rationale"][:160],
                    })
        case_hits.append((cid, hit))
    ga = sum(1 for _, hit in case_hits if hit)
    gb_pass = bool(gb_cases) and all(ok for *_, ok in gb_cases)
    return {
        "total": len(rows),
        "ok": len(ok_rows),
        "model_valid": valid_model,
        "models": comparison.observed_models,
        "ga": ga,
        "gb_cases": gb_cases,
        "gb_pass": gb_pass,
        "misses": misses,
        "case_hits": case_hits,
        "turns_diag": turns_diag,
        "turns_match": sum(1 for d in turns_diag if d["match"]),
        "turns_total": len(turns_diag),
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
        "## GB unsure 纪律(判定 = verdict=unsure ∧ 边界证据命中;①/④/② marker 词级;U-0 marker 或 rationale 二选一)",
    ]
    gb_hits = sum(1 for *_, ok in scored["gb_cases"] if ok)
    for cid, axis, expected, ok in scored["gb_cases"]:
        lines.append(f"- {cid} {axis}:期望边界 {expected['boundary']}"
                     f" → {'✓' if ok else '✗ 未命中(错误规则猜出的 unsure 不算可靠执行)'}")
    lines += [
        f"- 判定:{gb_hits}/{len(scored['gb_cases'])}"
        f"{' ✓' if scored['gb_pass'] else ' ✗(私闭合/边界未命中单列零容忍)'}"
        f"(unsure 期望案数随 battery 期望动态,v0.3 起 = 3)",
        "",
        f"## supporting_turns 诊断(D2:不入 GA,精确匹配计数)",
        f"- {scored['turns_match']}/{scored['turns_total']}",
    ]
    for d in scored["turns_diag"]:
        if not d["match"]:
            lines.append(f"- ✗ {d['case']} {d['axis']}:期望 {d['expected']} / 实得 {d['actual']}")
    lines += [
        "",
        f"## 轴级 miss 清单({len(scored['misses'])} 个轴级 miss,"
        f"涉及 {len({m['case'] for m in scored['misses']})} 个失败 case;"
        "GC 归因用:①A 实现失真/①B 翻译失真/② 判据—终验张力/③ 模型执行噪声)",
    ]
    if scored["misses"]:
        for miss in scored["misses"]:
            lines.append(f"- [{miss['kind']}] {miss['case']} {miss['axis']}:"
                         f"期望 {miss['expected']} / 实得 {miss['actual']}"
                         f"|rationale:{miss['rationale']}")
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
                        help="续跑既有 run 目录(#490 M3:公共层 strict identity 全等门)")
    args = parser.parse_args()

    rubric = _REPO / "docs/evals/s2-judge-rubric-v0.1.md"
    prompt_asset = _REPO / "edu_agent/evals/rubrics/s2_judge_v0_1.yaml"
    models_yaml = Path(os.environ.get("EDU_MODELS_YAML")
                        or _REPO / "configs" / "models.yaml")
    registry = load_registry(models_yaml)
    identity = _identity(models_yaml, args.battery, rubric, prompt_asset, registry)

    rows = [json.loads(line) for line in
            args.battery.read_text(encoding="utf-8").strip().splitlines()]
    args.artifacts_root.mkdir(parents=True, exist_ok=True)

    flag = Path(f"/tmp/edu-agent-batch/s2-judge-battery.{os.getpid()}")
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text(f"s2-judge-battery pid={os.getpid()}\n", encoding="utf-8")
    try:
        gateway = Gateway(registry, facts_dir=os.environ.get("EDU_FACTS_DIR") or "facts")
        try:
            subject = S2JudgeSubject(gateway)
            # owner 明示进 identity(manifest 落档;跨 owner 混续同一 run 被拒)
            identity["execution_owner"] = "inspect"
            # execution owner = Inspect(#521 I6-A;I6-C C3 删 --legacy-runner 回退后
            # 唯一执行面):调度/并发/sample retry 归 inspect-ai,checkpoint 为
            # Canonical durable evidence + 被动幂等守卫;strict 门(六面 + owner/
            # harness)在 adapter preflight,先于 Gateway。execution-only(scenarios=
            # None):GA/GB/VOID 判分仍由本脚本自 checkpoint 复算,expected 不进模型
            # 边界(P1-2 防火墙原样)。
            run_dir, _checks, _scores = run_inspect_round(InspectRoundRequest(
                subject=subject, gateway=gateway, cases_file=args.battery,
                scenarios=None, identity=identity,
                concurrency=RunnerConfig().concurrency, judge_enabled=False,
                collect_root=args.artifacts_root, resume_dir=args.run_dir,
                task_name=_INSPECT_TASK))
        finally:
            gateway.close()
    except ResumeMismatch as exc:
        sys.exit(f"resume 拒绝(P0-6):{exc}")
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
