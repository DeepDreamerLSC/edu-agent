"""题源适配器(00 §5.2 复用清单;M3 前置 PR1):question_id → 教学题目面。

双数据源(EDU_QUESTION_SOURCE 切换):
- "seed"(默认):seed bank JSON(edu_agent/evals/datasets,离线/CI);
- "snapshot":老库 published 题快照(edu_agent/contracts/db_snapshot.json,PM 数据翻转
  后的真实题面;快照口径=基线/评测题目集冻结,实时直读升级路径见 #34 工具冲突记录)。

resolve 返回字段:{text, answer, analysis, image, knowledge_points, grade, answer_status}。
answer_status 口径(#34 M3 前置):题源为 partner_question_bank → 有值;查无 → "unknown"。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_SEED_BANK = Path(__file__).resolve().parents[1] / "evals" / "datasets" / "release_acceptance_seed_question_bank.json"
_DB_SNAPSHOT = Path(__file__).resolve().parents[1] / "contracts" / "db_snapshot.json"
_ANSWER_STATUS_KNOWN = "partner_question_bank"
_ANSWER_STATUS_UNKNOWN = "unknown"


def question_source(source: str | None = None):
    """按 EDU_QUESTION_SOURCE 选择题源;显式传参优先(测试注入)。"""
    source = source or os.environ.get("EDU_QUESTION_SOURCE", "seed")
    if source == "seed":
        return SeedQuestionSource(_SEED_BANK)
    if source == "snapshot":
        return SnapshotQuestionSource(_DB_SNAPSHOT)
    raise ValueError(f"未知 EDU_QUESTION_SOURCE:{source}")


def normalize(payload: dict, question_id: str, answer_status: str) -> dict:
    """适配器统一输出面:内核与 api 层只认这七个键。"""
    image = payload.get("question_image")
    return {
        "text": str(payload.get("stem") or ""),
        "answer": str(payload.get("answer") or ""),
        "analysis": str(payload.get("original_analysis") or ""),
        "image": image if isinstance(image, dict) else None,
        "knowledge_points": list(payload.get("knowledge_points") or []),
        "grade": str(payload.get("grade") or ""),
        "answer_status": answer_status,
    }


class SeedQuestionSource:
    """本地 seed bank JSON(edu_agent/evals/datasets 同格式);离线与 CI 用。"""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or _SEED_BANK)
        self._records: dict[str, dict] | None = None

    def _records_by_id(self) -> dict[str, dict]:
        if self._records is None:
            records = json.loads(self.path.read_text(encoding="utf-8")).get("records", [])
            self._records = {r["question_id"]: r for r in records}
        return self._records

    def resolve(self, question_id: str) -> dict:
        record = self._records_by_id().get(question_id)
        if record is None:
            raise KeyError(f"题源(seed)不含 question_id:{question_id}")
        return normalize(record, question_id, _ANSWER_STATUS_KNOWN)


class SnapshotQuestionSource:
    """老库 published 题快照(contracts/db_snapshot.json,PM 数据翻转后的真实题面)。"""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or _DB_SNAPSHOT)
        self._records: dict[str, dict] | None = None

    def _records_by_id(self) -> dict[str, dict]:
        if self._records is None:
            records = json.loads(self.path.read_text(encoding="utf-8")).get("records", [])
            self._records = {r["question_id"]: r for r in records}
        return self._records

    def resolve(self, question_id: str) -> dict:
        record = self._records_by_id().get(question_id)
        if record is None:
            raise KeyError(f"题源(snapshot)不含 question_id:{question_id}")
        return normalize(record, question_id, _ANSWER_STATUS_KNOWN)
