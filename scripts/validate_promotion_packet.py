#!/usr/bin/env python3
"""Promotion packet 确定性 validator(#537 M5-D;零模型调用)。

只验完备性与身份一致性,**不拥有 promotion authority**(Validator ≠ Approver,
#537 边界一):human_promotion.decision 非空即拒;全检查通过时唯一结论是
«structurally complete, awaiting human key»——本工具任何输出不含 approved 字样,
不存在可被机器填写的批准位。四问的机械化:

  ①哪些维有权变化  → change_scope.requested_dims ⊆ dimension-ownership registry
                     allowed(mutable)集;registry sha 与本仓重算比对(漂移=新 cycle);
  ②哪些维必须保持  → anchored_comparison 逐案逐字段 anchored == baseline 锁定值
                     (locked 集必须恰为 registry locked 集;不许丢案);
  ③如何证无 masking→ flags.jsonl 实际行集 == anchored-arm 检测器发散案集 ==
                     packet 申报 flag_cases(三方相等,零静默);检测器内部一致
                     (checks.baseline==baseline 锁定值,发散集可重算);old=fail 案
                     必须全部申报进 negative_protection_set 且与冻结 old 臂 verdict
                     三方一致(evidence 不改写);
  ④如何获得 promotion → 以上全过 + frozen evidence sha 链全对 + Scoring Identity/
                     Execution Identity 分离(product_rerun 恒 0)+ human key 在人手里。

fail-closed:任一检查不过即非零退出,逐条列 FAIL;缺 frozen evidence / identity /
negative protection / human 位任一项同为 FAIL(#537 Exit 2)。
历史重放验收(#537 Exit 5):tests/evals/fixtures/promotion-replay/ 四件——
M5-A/A'/B 三个 overreach 候选重构件全被拒,M5-B2 合规 packet 出结构完备结论。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import jsonschema

try:
    import anchored_calibration as ac  # scripts/(conftest 挂载或脚本直跑均可)
except ImportError:  # 以模块包路径执行时(scripts/ 不在 sys.path)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import anchored_calibration as ac

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = REPO / "docs" / "evals" / "promotion-packet.schema.json"
DEFAULT_REGISTRY = ac.REGISTRY_PATH
COMPLETE_PHRASE = "structurally complete, awaiting human key"


class PacketValidationError(RuntimeError):
    """fail-closed 闸:校验不过即抛,CLI 退出码 1(红灯如实,不静默)。"""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def resolve(packet_dir: Path, path: str) -> Path:
    """packet 内工件路径:相对 packet 文件所在目录解析(绝对路径亦可)。"""
    candidate = Path(path)
    return candidate if candidate.is_absolute() else packet_dir / candidate


def locked_value_of(row: dict, field: str):
    """anchored 行取锁定值:六维在 scores 内,硬门字段在行根(与 ac.locked_value 同口径)。"""
    return row["scores"][field] if field in row.get("scores", {}) else row[field]


# ---------- 四问①:ownership / change right ----------


def check_ownership(packet: dict, registry_path: Path) -> list[str]:
    """requested_dims 必须在 registry allowed 集内;locked 集必须恰为 registry locked;
    registry 文件 sha 必须与 packet 冻结值一致(漂移=meta-change=新 cycle,fail-closed)。"""
    failures = []
    try:
        ownership = ac.load_ownership(registry_path)
    except ac.CalibrationGateError as error:
        return [f"ownership: registry 不可装载——{error}"]
    if sha256_file(registry_path) != packet["change_scope"]["registry"]["sha256"]:
        failures.append("ownership: registry sha256 与 packet 冻结值不符——"
                        "registry change 是 meta-change,须新开 calibration cycle(#537 边界二)")
    requested = packet["change_scope"]["requested_dims"]
    undeclared = sorted(set(requested) - set(ownership["allowed_dims"]))
    if undeclared:
        failures.append(f"ownership: requested_dims 含无 change right 的维度 {undeclared}"
                        "(四问①:未声明/未授权维度不得变化)")
    if packet["anchored_comparison"]["locked_fields"] != ownership["locked_fields"]:
        failures.append("ownership: packet locked_fields != registry locked 集"
                        "(四问②:必须保持的面由 registry 决定,不得自定)")
    return failures


# ---------- 冻结 evidence 链 ----------


def check_evidence(packet: dict, packet_dir: Path, baseline: dict) -> list[str]:
    """packet 引用的每个工件 sha256 重算比对;judge-rows 与 baseline 溯源链闭合。"""
    failures = []
    declared = list(packet["frozen_evidence"]["files"])
    for key in ("baseline", "arm"):
        declared.append({**packet["anchored_comparison"][key], "role": key})
    declared.append({**packet["masking_proof"]["challenge_flags"], "role": "flags"})
    judge_rows = ""
    for entry in declared:
        path = resolve(packet_dir, entry["path"])
        if not path.is_file():
            failures.append(f"evidence: 工件缺失 {entry['path']}({entry['role']})")
            continue
        if sha256_file(path) != entry["sha256"]:
            failures.append(f"evidence: {entry['path']} sha256 不符——"
                            "evidence 不随尺改写,须回到冻结原件(#537 边界三)")
        if entry.get("role") == "judge-rows":
            judge_rows = sha256_file(path)
    if not judge_rows:
        # #539 独立验证员披露缺口收口:frozen_evidence.files 必须携带 judge-rows 角色
        # 条目——缺位即 fail-closed,不得静默跳过 judge-rows↔baseline 溯源链检查。
        failures.append("evidence: frozen_evidence.files 缺 judge-rows 角色条目"
                        "(四问④:溯源链检查不可跳过)")
    if judge_rows and baseline["provenance"].get("judge_rows_sha256") != judge_rows:
        failures.append("evidence: judge-rows 与 baseline.provenance.judge_rows_sha256 "
                        "链条不闭合(四问④:frozen evidence identity)")
    return failures


# ---------- 四问②:anchored comparison ----------


def check_anchored(baseline: dict, rows: list[dict], locked_fields: list[str],
                   summary: dict) -> list[str]:
    """逐案:案集全等(不许丢案)、old verdict 不改写、verdict delta 自洽、
    locked 逐字段 anchored == baseline(核心不变量,fail-closed)。"""
    failures = []
    base_cases = baseline["cases"]
    row_ids = [row.get("case_id") for row in rows]
    if sorted(row_ids) != sorted(base_cases):
        failures.append("anchored: arm 案集 != baseline 案集(丢案/加案都不可,"
                        f"arm {len(row_ids)} vs baseline {len(base_cases)})")
        return failures
    drift = []
    movements = []
    for row in rows:
        case_id = row["case_id"]
        entry = base_cases[case_id]
        ref, delta = row.get("old_arm_reference", {}), row.get("verdict_delta_vs_old_arm", {})
        if ref.get("verdict") != entry["old_arm_reference"]["verdict"]:
            failures.append(f"anchored: {case_id} old verdict 与冻结 old 臂不一致(evidence 改写)")
        if delta.get("old") != ref.get("verdict") or \
                delta.get("anchored") != row.get("anchored", {}).get("verdict"):
            failures.append(f"anchored: {case_id} verdict_delta_vs_old_arm 不自洽")
        if delta.get("old") != delta.get("anchored"):
            movements.append(f"{case_id}:{delta.get('old')}->{delta.get('anchored')}")
        for field in locked_fields:
            if locked_value_of(row["anchored"], field) != entry["locked"][field]:
                drift.append(f"{case_id}.{field}"
                             f"({entry['locked'][field]}→{locked_value_of(row['anchored'], field)})")
    if drift:
        failures.append("anchored: locked ≠ baseline,漂移 " + str(len(drift)) + " 处:"
                        + ";".join(drift[:12])
                        + ("…" if len(drift) > 12 else "")
                        + "(四问②:locked 面由 baseline 机械保证,漂移即拒)")
    summary["verdict_movements"] = movements
    return failures


# ---------- 四问③:masking / challenge flag 全覆盖 ----------


def check_flags(rows: list[dict], flags: list[dict], packet: dict,
                baseline: dict) -> list[str]:
    """flags.jsonl 行集 == 检测器发散案集 == packet 申报集(三方相等,零静默);
    检测器内部一致(checks.baseline==baseline 锁定值,发散集可重算)。"""
    failures = []
    detector_flags = {row["case_id"] for row in rows
                      if row.get("challenge_detector", {}).get("flag")}
    flag_ids = [row.get("case_id") for row in flags]
    if len(flag_ids) != len(set(flag_ids)):
        failures.append("masking: flags.jsonl 有重复案")
    if set(flag_ids) != detector_flags:
        silent = sorted(detector_flags - set(flag_ids))
        extra = sorted(set(flag_ids) - detector_flags)
        failures.append("masking: 检测器发散案集与 flags.jsonl 行集不等——"
                        f"未落 flag(静默吸收){silent};flag 无检测器支撑{extra}"
                        "(四问③:locked 张力只能路由新 cycle,不能被 candidate 值吸收)")
    if set(packet["masking_proof"]["challenge_flags"]["flag_cases"]) != detector_flags:
        failures.append("masking: packet 申报 flag_cases 与检测器发散案集不等(申报不实)")
    for flag in flags:
        if flag.get("flag") != ac.FLAG_TEXT:
            failures.append(f"masking: {flag.get('case_id')} flag 文本非标准通道文案")
        row = next((r for r in rows if r["case_id"] == flag.get("case_id")), None)
        det = (row or {}).get("challenge_detector", {})
        if det and flag.get("divergent_fields") != det.get("divergent_fields"):
            failures.append(f"masking: {flag['case_id']} flag 发散字段与检测器不一致")
    for row in rows:
        det = row.get("challenge_detector")
        if not det or row["case_id"] not in baseline["cases"]:
            continue  # 未跑探测的案(零额外调用纪律)不要求 detector;案集失配另有 FAIL
        checks = det.get("checks", {})
        if any(checks.get(f, {}).get("baseline") != baseline["cases"][row["case_id"]]["locked"][f]
               for f in baseline["ownership"]["locked_fields"]):
            failures.append(f"masking: {row['case_id']} 检测器 checks.baseline 与 baseline 锁定值不符")
        recomputed = sorted(f for f, v in checks.items() if v["baseline"] != v["probe"])
        if recomputed != det.get("divergent_fields"):
            failures.append(f"masking: {row['case_id']} 检测器发散集与 checks 重算结果不符")
        if det.get("flag") != bool(recomputed):
            failures.append(f"masking: {row['case_id']} 检测器 flag 位与发散集不一致(可重算)")
    return failures


def check_protection(rows: list[dict], packet: dict, baseline: dict) -> list[str]:
    """negative protection set:条目在案、old verdict 三方一致、old=fail 案全覆盖。"""
    failures = []
    by_id = {row["case_id"]: row for row in rows}
    protected = packet["masking_proof"]["negative_protection_set"]
    for entry in protected:
        row = by_id.get(entry["case_id"])
        if row is None:
            failures.append(f"protection: {entry['case_id']} 不在 anchored arm(申报不实)")
            continue
        frozen = baseline["cases"][entry["case_id"]]["old_arm_reference"]["verdict"]
        if entry["old_verdict"] != frozen or \
                row["old_arm_reference"]["verdict"] != frozen:
            failures.append(f"protection: {entry['case_id']} old_verdict 与冻结 old 臂不一致"
                            "(负保护集不得改写 evidence)")
    missing = sorted(case_id for case_id, row in by_id.items()
                     if row["old_arm_reference"]["verdict"] == "fail"
                     and case_id not in {e["case_id"] for e in protected})
    if missing:
        failures.append(f"protection: old=fail 案未全部申报进负保护集 {missing}"
                        "(四问③:不许为过门剔除保护案)")
    return failures


# ---------- 四问④:human key ----------


def check_human_key(packet: dict) -> list[str]:
    decision = packet.get("human_promotion", {}).get("decision")
    if decision is not None:
        return ["human-key: human_promotion.decision 非空——packet 在机器验证面自带人裁位,"
                "Validator ≠ Approver,拒绝退回(promotion key 只在人手里,#537 边界一)"]
    return []


# ---------- 主流程 ----------


def validate(packet_path: Path, registry_path: Path = DEFAULT_REGISTRY,
             schema_path: Path = DEFAULT_SCHEMA) -> dict:
    """全检查;返回 {failures, summary};failures 非空即 fail-closed。"""
    packet_path = Path(packet_path)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    failures = [f"schema: {error.json_path}: {error.message}"
                for error in jsonschema.Draft202012Validator(schema).iter_errors(packet)]
    failures += check_human_key(packet)
    summary: dict = {"packet": str(packet_path)}
    if failures:
        return {"failures": failures, "summary": summary}
    failures += check_ownership(packet, registry_path)
    packet_dir = packet_path.parent
    try:
        baseline = ac.load_baseline(resolve(packet_dir, packet["anchored_comparison"]["baseline"]["path"]),
                                    registry_path)
    except (ac.CalibrationGateError, OSError) as error:
        return {"failures": failures + [f"baseline: 装载失败——{error}"], "summary": summary}
    if packet["anchored_comparison"]["cases"] != len(baseline["cases"]):
        failures.append("anchored: packet cases 数与 baseline 案数不符")
    arm_path = resolve(packet_dir, packet["anchored_comparison"]["arm"]["path"])
    rows = read_jsonl(arm_path)
    flags = read_jsonl(resolve(packet_dir, packet["masking_proof"]["challenge_flags"]["path"]))
    failures += check_evidence(packet, packet_dir, baseline)
    failures += check_anchored(baseline, rows, baseline["ownership"]["locked_fields"], summary)
    failures += check_flags(rows, flags, packet, baseline)
    failures += check_protection(rows, packet, baseline)
    summary.update({"cases": len(rows), "flags": len(flags),
                    "locked_invariant": "PASS" if not any(
                        f.startswith("anchored:") for f in failures) else "FAIL"})
    return {"failures": failures, "summary": summary}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("packet", type=Path, help="promotion packet JSON 路径")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY,
                        help="dimension-ownership registry(默认仓库现值;漂移即拒)")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA,
                        help="packet schema(默认 docs/evals/promotion-packet.schema.json)")
    args = parser.parse_args(argv)
    try:
        result = validate(args.packet, args.registry, args.schema)
    except (json.JSONDecodeError, OSError) as error:
        print(f"FAIL-CLOSED: packet 不可读——{error}", file=sys.stderr)
        return 1
    for failure in result["failures"]:
        print(f"FAIL {failure}")
    if result["failures"]:
        print(f"FAIL-CLOSED: {len(result['failures'])} 项不过;缺 frozen evidence / identity / "
              "negative protection / human 位任一项即 fail-closed(#537 Exit 2)")
        return 1
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    print(COMPLETE_PHRASE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
