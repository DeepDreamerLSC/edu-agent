"""segment 阶段合同测试:题号锚定、顶部排除、无锚点降级(08 §3)。"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from edu_agent.ingest import IngestError, run_segment, segment_page


def _elements(tmp_path: Path, lines: list[tuple[int, int, int, int, str]], blocks: list[dict] | None = None) -> Path:
    record = {
        "version": "ingest_elements_v1",
        "run_id": "run_t",
        "engine": "fake",
        "page_no": 1,
        "lines": [{"bbox": list(box), "text": text} for box, text in lines],
        "visual_blocks": blocks or [],
    }
    path = tmp_path / "elements.jsonl"
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def test_segment_anchors_and_top_strip_exclusion(tmp_path: Path) -> None:
    path = _elements(tmp_path, [
        ((10, 20, 300, 40), "基础对点练 选择题每小题3分"),   # 顶部栏目 → excluded
        ((10, 100, 300, 120), "1.计算下列各题"),
        ((10, 130, 300, 150), "由题意得 x=3"),
        ((10, 200, 300, 220), "2.如图,钝角三角形的个数"),
        ((10, 230, 300, 250), "答:5 个"),
    ])
    questions = segment_page({"run_id": "run_t", "page_no": 1, "lines": [
        {"bbox": [10, 20, 300, 40], "text": "基础对点练 选择题每小题3分"},
        {"bbox": [10, 100, 300, 120], "text": "1.计算下列各题"},
        {"bbox": [10, 130, 300, 150], "text": "由题意得 x=3"},
        {"bbox": [10, 200, 300, 220], "text": "2.如图,钝角三角形的个数"},
        {"bbox": [10, 230, 300, 250], "text": "答:5 个"},
    ], "visual_blocks": []})
    assert [q["question_no"] for q in questions] == [1, 2]
    assert questions[0]["status"] == "accepted"
    assert 0 in questions[0]["excluded_block_ids"]
    assert questions[1]["target_block_ids"] == [3, 4]
    records = [json.loads(line) for line in Path(run_segment(path, tmp_path / "segment")).read_text(encoding="utf-8").splitlines()]
    assert len(records) == 2


def test_section_number_is_not_anchor() -> None:
    questions = segment_page({"run_id": "r", "page_no": 9, "lines": [
        {"bbox": [10, 90, 300, 110], "text": "1.1 认识三角形"},
        {"bbox": [10, 130, 300, 150], "text": "2.如图"},
    ], "visual_blocks": []})
    assert [q["question_no"] for q in questions] == [2]
    assert questions[0]["excluded_block_ids"] == [0]


def test_segment_no_anchor_single_review(tmp_path: Path) -> None:
    questions = segment_page({"run_id": "r", "page_no": 2, "lines": [
        {"bbox": [10, 100, 300, 120], "text": "阅读短文"},
    ], "visual_blocks": []})
    assert len(questions) == 1
    assert questions[0]["status"] == "needs_review"
    assert questions[0]["question_no"] == 0


def test_segment_empty_page_returns_empty() -> None:
    assert segment_page({"run_id": "r", "page_no": 3, "lines": [], "visual_blocks": []}) == []


def test_run_segment_empty_raises(tmp_path: Path) -> None:
    import json as _json

    record = {"version": "ingest_elements_v1", "run_id": "r", "engine": "e", "page_no": 1, "lines": [], "visual_blocks": []}
    path = tmp_path / "e.jsonl"
    path.write_text(_json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(IngestError) as info:
        run_segment(path, tmp_path / "s")
    assert info.value.code == "segment_empty"
