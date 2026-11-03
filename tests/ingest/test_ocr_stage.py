"""ocr 阶段合同测试:假引擎驱动 artifacts 闭环与类型化失败(08 §3)。"""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from typing import Any

from edu_agent.ingest import IngestError, render_pdf, run_ocr, read_jsonl


class FakeEngine:
    name = "fake"

    def __init__(self, result: dict[str, Any] | None = None, code: str | None = None) -> None:
        self.result = result if result is not None else {
            "lines": [{"bbox": [1, 2, 30, 20], "text": "题干"}],
            "visual_blocks": [{"bbox": [0, 0, 50, 8], "kind": "header", "text": "栏目"}],
        }
        self.code = code

    def parse_page(self, png_path: Path, width_px: int, height_px: int) -> dict[str, Any]:
        if self.code:
            raise IngestError(self.code, "fake failure")
        return self.result


@pytest.fixture(name="render_dir")
def render_dir_fixture(tmp_path: Path) -> Path:
    import fitz

    document = fitz.open()
    document.new_page().insert_text((72, 72), "1+1=2")
    document.save(tmp_path / "mini.pdf")
    document.close()
    render_pdf(tmp_path / "mini.pdf", tmp_path / "render", dpi=72)
    return tmp_path / "render"


def test_run_ocr_writes_elements_and_facts(render_dir: Path, tmp_path: Path) -> None:
    stage = tmp_path / "ocr"
    out = run_ocr(render_dir / "pages.jsonl", stage, FakeEngine(), run_id="run_t")
    records = list(read_jsonl(out))
    assert len(records) == 1
    assert records[0]["engine"] == "fake"
    assert records[0]["lines"][0]["text"] == "题干"
    facts = [json.loads(line) for line in (stage / "model_calls.jsonl").read_text(encoding="utf-8").splitlines()]
    assert facts[0]["line_count"] == 1 and facts[0]["block_count"] == 1
    assert facts[0]["latency_ms"] >= 0


def test_run_ocr_page_limit_skips_all_raises_empty(render_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(IngestError) as info:
        run_ocr(render_dir / "pages.jsonl", tmp_path / "ocr", FakeEngine(), run_id="run_t", page_limit=0)
    assert info.value.code == "ocr_empty"


def test_run_ocr_propagates_typed_engine_error(render_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(IngestError) as info:
        run_ocr(render_dir / "pages.jsonl", tmp_path / "ocr", FakeEngine(code="ocr_timeout"), run_id="run_t")
    assert info.value.code == "ocr_timeout"


def test_run_ocr_rejects_unknown_engine_name(render_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(IngestError) as info:
        run_ocr(render_dir / "pages.jsonl", tmp_path / "ocr", "nope", run_id="run_t")
    assert info.value.code == "ocr_layout_invalid"

