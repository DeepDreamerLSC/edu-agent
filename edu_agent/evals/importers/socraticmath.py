"""SocraticMATH importer(#368 首 importer):冻结原件 → canonical v1,只到 normalized。

原结构(冻结原件逐条):{id, question, answer, license, version,
conversations:[{from, value}]} → reference_dialogue 的显式 role 映射表(未知
from 值 fail closed 列名报错,不自动猜测);license/version 逐条带进 source 块。

红线:不生成 student_turns、不编译可执行 case(slice 层人工挑选后另开任务);
answer 原样搬运(保真由 validator 以 expected_answer 锚核对)。

用法(仓根;原件目录 external/socraticmath/ 已 gitignore,license 核对人批后落):
  .venv/bin/python -m edu_agent.evals.importers.socraticmath \
    external/socraticmath edu_agent/evals/datasets/external_normalized/socraticmath.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ..external_scenario import (
    EXTERNAL_SCHEMA_VERSION,
    external_fingerprint,
    validate_external_scenario,
)

DATASET_NAME = "SocraticMATH"
# 显式映射表(章程反自动猜测):未知 from 值 fail closed。真原件落地时若 from 值
# 不同,改这一张表(数据驱动的一行修正),不加任何猜测逻辑。
FROM_ROLE_MAP = {"human": "student", "gpt": "tutor"}


def to_v1_record(raw: dict) -> dict:
    """单条上游记录 → v1 record(纯映射;不造数据,无据字段留 null/空)。"""
    turns = []
    for index, turn in enumerate(raw["conversations"]):
        role = FROM_ROLE_MAP.get(turn.get("from"))
        if role is None:
            raise ValueError(
                f"conversations[{index}].from={turn.get('from')!r} 不在映射表"
                f"{sorted(FROM_ROLE_MAP)}——扩充显式映射,不做自动猜测")
        turns.append({"role": role, "text": turn["value"]})
    record = {
        "schema_version": EXTERNAL_SCHEMA_VERSION,
        "id": f"{DATASET_NAME.lower()}_{raw['id']}",
        "source": {
            "dataset": DATASET_NAME,
            "upstream_id": str(raw["id"]),
            "license": raw["license"],
            "version": raw["version"],
            "modified": False,
        },
        "problem": {
            "text": raw["question"],
            "answer": raw["answer"],
            "analysis": None,
            "image": None,
            "grade": None,
            "knowledge_tags": [],
        },
        "reference_dialogue": turns,
        "annotations": {"difficulty": None, "teacher_moves": [], "outcome": None},
    }
    record["fingerprint"] = external_fingerprint(record)
    return record


def import_socraticmath(input_dir: Path | str, output_path: Path | str) -> dict:
    """冻结原件目录(*.jsonl)→ normalized jsonl;逐条过闸(带原答保真锚)。

    首参是**目录**(装 *.jsonl 原件的冻结目录),不是单个文件——传文件路径
    会被明确指路(#369 审 P3-1,审查者亲踩)。
    任一条不过闸即中止不落盘(证据层宁缺毋滥);返回统计 {records, skipped_files}。
    """
    input_path = Path(input_dir)
    if input_path.is_file():
        raise ValueError(f"首参是冻结原件**目录**,不是文件:{input_path}"
                         "(传包含 *.jsonl 的目录,如 external/socraticmath)")
    sources = sorted(input_path.glob("*.jsonl"))
    if not sources:
        raise ValueError(f"{input_dir} 下没有 *.jsonl 原件(冻结原件目录待 license 人批后落)")
    records = []
    for source in sources:
        for line_no, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            raw = json.loads(line)
            record = to_v1_record(raw)
            errors = validate_external_scenario(
                record, base_dir=Path(input_dir), expected_answer=raw["answer"])
            if errors:
                raise ValueError(f"{source.name}:{line_no} 未过闸:{';'.join(errors[:3])}")
            records.append(record)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    return {"records": len(records), "skipped_files": 0}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print("用法:python -m edu_agent.evals.importers.socraticmath <原件目录> <输出.jsonl>\n"
              "示例:python -m edu_agent.evals.importers.socraticmath external/socraticmath "
              "edu_agent/evals/datasets/external_normalized/socraticmath.jsonl"
              "  # 首参=目录(含 *.jsonl),非单个文件",
              file=sys.stderr)
        return 2
    try:
        stats = import_socraticmath(argv[0], argv[1])
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"import 失败:{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"import-ok {argv[1]} records={stats['records']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
