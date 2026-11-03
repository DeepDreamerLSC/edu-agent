"""render 阶段合同测试:生成 PDF → 渲染 → artifact 回读校验闭环(08 §3)。"""

from __future__ import annotations

import fitz
import pytest
from pathlib import Path

from edu_agent.ingest import IngestError, read_jsonl, render_pdf


def _make_pdf(path: Path, pages: int = 2) -> Path:
    document = fitz.open()
    for _ in range(pages):
        document.new_page().insert_text((72, 72), "1+1=2")
    document.save(path)
    document.close()
    return path


def test_render_writes_pages_jsonl_and_pngs(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "mini.pdf")
    stage = tmp_path / "render"
    out = render_pdf(pdf, stage, dpi=160)
    assert out == stage / "pages.jsonl"
    records = list(read_jsonl(out))
    assert len(records) == 2
    assert (stage / "pages/0001.png").is_file()
    assert (stage / "pages/0002.png").is_file()
    first = records[0]
    assert first["source_pdf"] == "mini.pdf"
    assert first["dpi"] == 160
    assert first["page_no"] == 1
    assert first["width_px"] > 0 and first["height_px"] > 0


def test_render_dpi_doubles_pixel_size(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "mini.pdf", pages=1)
    low = list(read_jsonl(render_pdf(pdf, tmp_path / "low", dpi=72)))
    high = list(read_jsonl(render_pdf(pdf, tmp_path / "high", dpi=144)))
    assert high[0]["width_px"] == low[0]["width_px"] * 2
    assert high[0]["height_px"] == low[0]["height_px"] * 2


def test_render_rejects_missing_pdf(tmp_path: Path) -> None:
    with pytest.raises(IngestError) as info:
        render_pdf(tmp_path / "nope.pdf", tmp_path / "stage")
    assert info.value.code == "pdf_invalid"


def test_render_rejects_non_pdf(tmp_path: Path) -> None:
    fake = tmp_path / "fake.pdf"
    fake.write_text("not a pdf", encoding="utf-8")
    with pytest.raises(IngestError) as info:
        render_pdf(fake, tmp_path / "stage")
    assert info.value.code == "pdf_invalid"
