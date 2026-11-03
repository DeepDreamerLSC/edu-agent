"""artifact 读写与四份合同 schema 的样本闭环(08 §3)。"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from edu_agent.ingest import IngestError, read_jsonl, validate_record, write_jsonl

SAMPLES = {
    "ingest_pages_v1": {
        "version": "ingest_pages_v1",
        "source_pdf": "8math_a.pdf",
        "dpi": 160,
        "page_no": 1,
        "width_px": 1322,
        "height_px": 1871,
        "image": "pages/0001.png",
    },
    "ingest_elements_v1": {
        "version": "ingest_elements_v1",
        "run_id": "run_x",
        "engine": "pp-ocrv6-medium-ocr-layout-v1",
        "page_no": 1,
        "lines": [{"bbox": [10, 20, 300, 44], "text": "选择题每小题3分", "confidence": 0.98}],
        "visual_blocks": [{"bbox": [0, 0, 1322, 60], "kind": "header", "text": "基础对点练"}],
    },
    "ingest_questions_v1": {
        "version": "ingest_questions_v1",
        "run_id": "run_x",
        "page_no": 4,
        "question_no": 1,
        "target_block_ids": [3, 4],
        "question_bbox": [80, 120, 640, 400],
        "excluded_block_ids": [0],
        "status": "needs_review",
    },
    "ingest_crop_v1": {
        "version": "ingest_crop_v1",
        "run_id": "run_x",
        "page_no": 4,
        "question_no": 1,
        "crop_image": "crops/p4q1.png",
        "markdown": "计算 $1+1=$ ______。",
        "latex_fragments": ["1+1="],
        "figures": [],
    },
}


@pytest.mark.parametrize("version", sorted(SAMPLES))
def test_sample_records_pass_schema(version: str) -> None:
    validate_record(SAMPLES[version])


def test_bad_bbox_fails_schema() -> None:
    record = dict(SAMPLES["ingest_questions_v1"])
    record["question_bbox"] = [1, 2, 3]
    with pytest.raises(IngestError) as info:
        validate_record(record)
    assert info.value.code == "artifact_schema_invalid"


def test_unknown_version_fails_schema() -> None:
    with pytest.raises(IngestError) as info:
        validate_record({"version": "ingest_nonexistent_v9"})
    assert info.value.code == "artifact_schema_invalid"


def test_jsonl_roundtrip(tmp_path: Path) -> None:
    second = dict(SAMPLES["ingest_pages_v1"], page_no=2, image="pages/0002.png")
    out = write_jsonl(tmp_path / "pages.jsonl", [SAMPLES["ingest_pages_v1"], second])
    assert [r["page_no"] for r in read_jsonl(out)] == [1, 2]


def test_read_missing_jsonl_fails(tmp_path: Path) -> None:
    with pytest.raises(IngestError) as info:
        list(read_jsonl(tmp_path / "nothing.jsonl"))
    assert info.value.code == "artifact_read_failed"


def test_read_malformed_line_fails(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps(SAMPLES["ingest_pages_v1"]) + "\n{broken\n", encoding="utf-8")
    with pytest.raises(IngestError) as info:
        list(read_jsonl(path))
    assert info.value.code == "artifact_read_failed"
