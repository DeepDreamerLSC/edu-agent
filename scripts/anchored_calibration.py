#!/usr/bin/env python3
"""Baseline Anchored Dimension Isolation v0.1——生产 calibration primitive(#535)。

授权:#535 comment 5981592681(Architect 2026-10-04)——「primitive 接入生产
calibration 流程」,三治理约束生效;**不批** anchored 替换生产默认 ruler。
生产化自 M5-B2 实验资产(/tmp/m5b2,只读参考):冻结/组装/flag 通道语义复刻,
输入面改为通用 JSONL,judge 活评复用生产 judge_transcript(温度/Schema/rubric
全部产线默认,本工具不碰判分语义)。

anchored 合同:
  final = {locked 五维 = baseline 机械取值(baseline.json,本 cycle immutable,零重判)}
        ∪ {allowed 三维 = candidate 活评(生产 judge 面)}
  → 生产 verdict_from_scores 重算(阈值不动)。
锁定集/活评集由 Dimension Ownership Registry 驱动
(edu_agent/evals/rubrics/dimension-ownership.yaml),本脚本不硬编码维度归属。

flag 通道(零静默):活评 judge 输出对 locked 字段的取值(隔离 locked-view)与
baseline 锁定值有张力 → flag=「locked 张力→路由新 calibration cycle」,逐字段记录
baseline/probe 值,写 flags.jsonl 工件;组装仍按合同用 baseline 值,张力如实披露。

fail-closed:预算闸(--budget,默认 32)、baseline schema/immutable 标记、
sidecar sha(篡改即非零退出)、registry sha 链(改 locked 维没另开 cycle 即拒)、
组装不变量(anchored locked == baseline,逐案校验)。

红线:anchored 非生产默认路径——本工具只能显式 --cycle-id 运行,无任何调用方;
不改现行 judge/rubrics 生产语义;冻结面零模型调用。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import yaml

from edu_agent.evals import DIMENSIONS, judge_transcript, verdict_from_scores
from edu_agent.gateway import Gateway, load_registry

REPO = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO / "edu_agent" / "evals" / "rubrics" / "dimension-ownership.yaml"
BASELINE_SCHEMA = "anchored-baseline/1"
FLAG_TEXT = "locked 张力→路由新 calibration cycle"
DEFAULT_BUDGET = 32
# 独立硬门字段(不计六维总分):verdict_from_scores 的直接输入,锚定组装合同
# 要求其归 baseline 所有——改归属 = 改 locked 维,须另开 calibration cycle。
HARD_FIELDS = ("answer_leaked", "math_integrity")
PRODUCTION_FACE = DIMENSIONS + HARD_FIELDS


class CalibrationGateError(RuntimeError):
    """fail-closed 闸:校验不过即抛,CLI 退出码 1(红灯如实,不静默)。"""


def fail_closed(condition: bool, message: str) -> None:
    if not condition:
        raise CalibrationGateError(message)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    Path(path).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8")


def load_ownership(registry_path: Path = REGISTRY_PATH) -> dict:
    """读 Dimension Ownership Registry → {locked_fields, allowed_dims}(登记序)。

    registry 驱动锁定集(不硬编码):owner=baseline 且 mutable=false → locked;
    owner=calibration_candidate 且 mutable=true → allowed。覆盖集必须恰为生产
    判分面(六维 + 两个独立硬门字段);硬门字段必须锁定(锚定组装合同)。"""
    data = yaml.safe_load(Path(registry_path).read_text(encoding="utf-8"))
    fail_closed(str(data.get("version", "")).startswith("dimension_ownership"),
                f"{registry_path} 非 dimension-ownership registry(fail-closed)")
    ownership = data.get("ownership")
    fail_closed(isinstance(ownership, dict) and bool(ownership),
                f"{registry_path} 无 ownership 登记(fail-closed)")
    locked: list[str] = []
    allowed: list[str] = []
    for field, spec in ownership.items():
        owner = spec.get("owner")
        fail_closed(owner in ("baseline", "calibration_candidate"),
                    f"{field}: 未知 owner={owner}(fail-closed)")
        fail_closed(spec.get("mutable") is (owner == "calibration_candidate"),
                    f"{field}: owner={owner} 与 mutable={spec.get('mutable')} 不一致(fail-closed)")
        (allowed if owner == "calibration_candidate" else locked).append(field)
    fail_closed(sorted(ownership) == sorted(PRODUCTION_FACE),
                f"registry 覆盖集 != 生产判分面 {sorted(PRODUCTION_FACE)}(fail-closed)")
    fail_closed(all(f in locked for f in HARD_FIELDS),
                f"锚定组装合同要求硬门字段 {HARD_FIELDS} 为 baseline 所有(fail-closed)")
    return {"locked_fields": locked, "allowed_dims": allowed}


def _require(row: dict, key: str):
    fail_closed(key in row, f"{row.get('case_id', '?')} 冻结 judge 行缺 {key}(fail-closed)")
    return row[key]


def locked_value(row: dict, field: str):
    """从冻结 judge 行取锁定值:六维在 scores 内,硬门字段在行根(fail-closed)。"""
    if field in row.get("scores", {}):
        return int(row["scores"][field])
    fail_closed(field in row,
                f"{row.get('case_id', '?')}.{field} 冻结 judge 行缺失(fail-closed)")
    return bool(row[field]) if field == "answer_leaked" else int(row[field])


def freeze_baseline(cycle_id: str, rows_path: Path, out_dir: Path,
                    registry_path: Path = REGISTRY_PATH) -> dict:
    """冻结 baseline.json:逐案 locked 五值 + 来源 sha 链 + immutable_this_cycle
    + sidecar sha256。零模型调用(值取自冻结 judge 行,机械读出)。"""
    ownership = load_ownership(registry_path)
    locked_fields = ownership["locked_fields"]
    cases: dict[str, dict] = {}
    for row in read_jsonl(rows_path):
        case_id = _require(row, "case_id")
        fail_closed(case_id not in cases, f"{case_id} 冻结行重复(fail-closed)")
        reference = {"total": int(_require(row, "total")),
                     "verdict": _require(row, "verdict"),
                     "judge_model": _require(row, "judge_model")}  # #32 披露义务
        if "judge_input_sha256" in row:
            reference["judge_input_sha256"] = row["judge_input_sha256"]
        cases[case_id] = {"locked": {f: locked_value(row, f) for f in locked_fields},
                          "old_arm_reference": reference}
    fail_closed(bool(cases), "冻结 judge 行为空(fail-closed)")
    baseline = {
        "schema": BASELINE_SCHEMA,
        "primitive": "baseline-anchored-dimension-isolation",
        "version": "v0.1",
        "cycle_id": cycle_id,
        "cycle": "#535 Baseline Anchored Dimension Isolation v0.1",
        "created": date.today().isoformat(),
        "immutable_this_cycle": True,
        "ownership": {"registry": str(registry_path),
                      "registry_sha256": sha256_file(registry_path),
                      "locked_fields": locked_fields,
                      "allowed_dims": ownership["allowed_dims"]},
        "provenance": {
            "judge_rows_file": str(rows_path),
            "judge_rows_sha256": sha256_file(rows_path),
            "locked_values_source": "冻结 judge 行(零模型调用,机械取值)",
            "sha_chain": "baseline.json ← sidecar baseline.json.sha256;"
                         "baseline ← judge_rows_sha256;逐案 ← judge_input_sha256(行内携带时)"},
        "cases": cases,
        "counts": {"cases": len(cases)},
    }
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / "baseline.json"
    target.write_text(json.dumps(baseline, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "baseline.json.sha256").write_text(
        f"{sha256_file(target)}  baseline.json\n", encoding="utf-8")
    return baseline


def load_baseline(baseline_path: Path, registry_path: Path = REGISTRY_PATH) -> dict:
    """fail-closed 装载:schema、immutable 标记、sidecar sha、registry sha 链。

    baseline 被篡改(内容与 sidecar 不符/缺 sidecar)、或 dimension ownership
    registry 已漂移(改 locked 维没另开 cycle)→ CalibrationGateError,退出码非零。"""
    path = Path(baseline_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    fail_closed(data.get("schema") == BASELINE_SCHEMA,
                f"{path} schema != {BASELINE_SCHEMA}(fail-closed)")
    fail_closed(data.get("immutable_this_cycle") is True,
                f"{path} 非 immutable_this_cycle(fail-closed)")
    sidecar = path.parent / (path.name + ".sha256")
    expect = sidecar.read_text(encoding="utf-8").split()[0] if sidecar.is_file() else ""
    fail_closed(expect == sha256_file(path),
                f"{path} sha 与 sidecar 不符(篡改或漂移,fail-closed)")
    ownership = data.get("ownership", {})
    fail_closed(ownership.get("registry_sha256") == sha256_file(registry_path),
                "dimension-ownership registry 与 baseline 冻结时不一致——"
                "改 locked 维须另开 calibration cycle(fail-closed)")
    fail_closed(ownership.get("locked_fields") == load_ownership(registry_path)["locked_fields"],
                "baseline 锁定集与 registry 现值不一致(fail-closed)")
    return data


def assemble(locked: dict, allowed_scores: dict) -> dict:
    """机械组装:locked 维取 baseline,allowed 维取活评;生产 verdict 重算(阈值不动)。"""
    scores = {**{d: locked[d] for d in locked if d in DIMENSIONS}, **allowed_scores}
    return {"scores": scores, "total": sum(scores.values()),
            "answer_leaked": locked["answer_leaked"],
            "math_integrity": locked["math_integrity"],
            "verdict": verdict_from_scores(scores, locked["answer_leaked"],
                                           locked["math_integrity"])}


def detect_tension(baseline_locked: dict, live: dict, locked_fields) -> dict:
    """检测器:活评 judge 输出(隔离 locked-view)与 baseline 锁定值逐字段比对。"""
    checks = {field: {"baseline": baseline_locked[field],
                      "probe": live["scores"][field] if field in DIMENSIONS else live[field]}
              for field in locked_fields}
    diverged = {f: v for f, v in checks.items() if v["baseline"] != v["probe"]}
    return {"checks": checks, "divergent_fields": sorted(diverged),
            "divergence": diverged, "flag": bool(diverged)}


def make_flag(case_id: str, detection: dict) -> dict:
    """flag 工件行:张力如实披露,路由新 calibration cycle,不静默。"""
    return {"case_id": case_id, "flag": FLAG_TEXT,
            "divergent_fields": detection["divergent_fields"],
            "divergence": detection["divergence"],
            "probe_source": "活评 judge 输出 locked-view(生产 judge_transcript 面,零额外调用)",
            "action": "路由新 calibration cycle(本 cycle anchored 输出不改用 probe 值;张力如实披露)"}


def check_invariant(case_id: str, assembled: dict, locked: dict, locked_fields) -> None:
    """anchored 合同不变量:locked 五字段逐案全等于 baseline(fail-closed)。"""
    for field in locked_fields:
        actual = assembled["scores"].get(field, assembled.get(field))
        fail_closed(actual == locked[field],
                    f"{case_id}.{field} anchored ≠ baseline(组装不变量 fail-closed)")


def _anchored_row(case_id: str, entry: dict, live: dict, detection: dict,
                  assembled: dict, allowed_dims) -> dict:
    old = entry["old_arm_reference"]
    return {"case_id": case_id,
            "locked_source": "baseline.json(immutable,机械取值,零重判)",
            "allowed_source": "live judge 活评(生产 judge_transcript 面,allowed 三维)",
            "locked": entry["locked"],
            "allowed": {d: live["scores"][d] for d in allowed_dims},
            "anchored": assembled,
            "judge_model": live["judge_model"],
            "old_arm_reference": old,
            "verdict_delta_vs_old_arm": {"old": old["verdict"],
                                         "anchored": assembled["verdict"]},
            "challenge_detector": detection}


def _write_artifacts(out_dir: Path, baseline: dict, results: list[dict],
                     flags: list[dict], calls: int, budget: int) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "anchored-arm.jsonl", results)
    write_jsonl(out / "flags.jsonl", flags)  # flag 通道工件(空也落盘,零静默)
    summary = {"cycle_id": baseline["cycle_id"], "cases": len(results),
               "judge_score_calls": calls, "budget": budget,
               "flags": len(flags), "flag_cases": [f["case_id"] for f in flags],
               "flag_meaning": FLAG_TEXT,
               "locked_invariant": "PASS(anchored locked == baseline,逐案 fail-closed 校验)"}
    (out / "anchored-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


def run_anchored(gateway: Gateway, baseline: dict, cases: list[dict], out_dir: Path,
                 budget: int = DEFAULT_BUDGET) -> dict:
    """活评 allowed 三维 → 机械组装 → flag 通道;预算闸与不变量 fail-closed。

    活评复用生产 judge_transcript(全案六维一次评出,allowed 三维取用,locked
    五维仅作张力探测比对,不进组装);#464 同案同 session 口径。"""
    locked_fields = baseline["ownership"]["locked_fields"]
    allowed_dims = baseline["ownership"]["allowed_dims"]
    calls, results, flags = 0, [], []
    for case in cases:
        case_id = _require(case, "case_id")
        entry = baseline["cases"].get(case_id)
        fail_closed(entry is not None,
                    f"{case_id} 活评案不在 baseline——先 --freeze-baseline(fail-closed)")
        fail_closed(calls < budget, f"judge 调用预算 {budget} 用尽(fail-closed)")
        live = judge_transcript(gateway, {**case, "id": case_id},
                                session_id=f"judge-{case_id}")
        calls += 1
        detection = detect_tension(entry["locked"], live, locked_fields)
        if detection["flag"]:
            flags.append(make_flag(case_id, detection))
        assembled = assemble(entry["locked"],
                             {d: live["scores"][d] for d in allowed_dims})
        check_invariant(case_id, assembled, entry["locked"], locked_fields)
        results.append(_anchored_row(case_id, entry, live, detection, assembled, allowed_dims))
        flag_note = (f"YES {detection['divergent_fields']}" if detection["flag"] else "no")
        print(f"{case_id}: anchored={assembled['total']}/{assembled['verdict']} "
              f"old={entry['old_arm_reference']['verdict']} flag={flag_note}", flush=True)
    return _write_artifacts(out_dir, baseline, results, flags, calls, budget)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cycle-id", required=True,
                        help="calibration cycle 标识;显式指定才运行——anchored 无默认路径(#535 约束一)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze-baseline", action="store_true",
                      help="冻结 baseline.json(逐案 locked 五值+sha 链+sidecar;零模型调用)")
    mode.add_argument("--run-anchored", action="store_true",
                      help="活评 allowed 三维(生产 judge 面)→组装→flag 通道")
    parser.add_argument("--judge-rows", type=Path,
                        help="冻结 judge 行 JSONL(--freeze-baseline 输入)")
    parser.add_argument("--cases", type=Path,
                        help="活评案 JSONL(--run-anchored 输入:"
                             "{case_id,question,grade,reference_answer,messages})")
    parser.add_argument("--baseline", type=Path,
                        help="baseline.json 路径(默认 <out-dir>/baseline.json)")
    parser.add_argument("--out-dir", type=Path,
                        help="工件目录(默认 var/anchored/<cycle-id>)")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET,
                        help=f"judge 调用预算,fail-closed(默认 {DEFAULT_BUDGET})")
    parser.add_argument("--models-config", type=Path, default=REPO / "configs" / "models.yaml",
                        help="judge 角色 models.yaml(--run-anchored 用)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = args.out_dir or (REPO / "var" / "anchored" / args.cycle_id)
    try:
        if args.freeze_baseline:
            fail_closed(args.judge_rows is not None,
                        "--freeze-baseline 需要 --judge-rows(fail-closed)")
            baseline = freeze_baseline(args.cycle_id, args.judge_rows, out_dir)
            print(json.dumps({"cycle_id": args.cycle_id,
                              "baseline": str(out_dir / "baseline.json"),
                              "cases": baseline["counts"]["cases"]},
                             ensure_ascii=False, indent=1))
            return 0
        fail_closed(args.cases is not None, "--run-anchored 需要 --cases(fail-closed)")
        baseline = load_baseline(args.baseline or (out_dir / "baseline.json"))
        gateway = Gateway(load_registry(args.models_config), facts_dir=out_dir / "facts")
        try:
            summary = run_anchored(gateway, baseline, read_jsonl(args.cases),
                                   out_dir, args.budget)
        finally:
            gateway.close()
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        return 0
    except CalibrationGateError as error:
        print(f"FAIL-CLOSED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
