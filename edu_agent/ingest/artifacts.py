"""阶段 artifact 读写:JSONL + contracts schema 校验(08 §3)。

version 字段即合同名,同时是 contracts/ 下 schema 文件名 stem;
不兼容变更=新版本号,旧版本只读兼容一个里程碑(08 §3)。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from functools import lru_cache
from importlib import resources
from jsonschema import Draft202012Validator
from pathlib import Path
from typing import Any

from edu_agent.ingest.errors import IngestError

_MAX_SCHEMA_ERRORS = 3


@lru_cache(maxsize=None)
def _validator(version: str) -> Draft202012Validator:
    schema_file = resources.files("edu_agent.contracts") / f"{version}.json"
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_record(record: dict[str, Any]) -> None:
    """校验单条 artifact 记录;不合规抛 artifact_schema_invalid。"""
    version = record.get("version")
    if not isinstance(version, str) or not version:
        raise IngestError("artifact_schema_invalid", "record missing 'version'")
    try:
        validator = _validator(version)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise IngestError("artifact_schema_invalid", f"unknown version {version}: {exc}") from exc
    errors = sorted(validator.iter_errors(record), key=lambda e: e.json_path)
    if errors:
        detail = "; ".join(f"{e.json_path} {e.message}" for e in errors[:_MAX_SCHEMA_ERRORS])
        raise IngestError("artifact_schema_invalid", f"{version}: {detail}")


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> Path:
    """原子写 JSONL:先写临时文件再替换,产物要么完整要么不存在。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    temp.replace(path)
    return path


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """逐行读 JSONL 并逐条校验 schema;坏行抛 artifact_read_failed/artifact_schema_invalid。"""
    if not path.is_file():
        raise IngestError("artifact_read_failed", f"missing artifact: {path}")
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise IngestError("artifact_read_failed", f"{path}:{line_no} {exc}") from exc
            if not isinstance(record, dict):
                raise IngestError("artifact_read_failed", f"{path}:{line_no} non-object record")
            validate_record(record)
            yield record
