"""render 阶段(08 §3):PDF → pages/ PNG + pages.jsonl。纯函数,无全局状态。"""

from __future__ import annotations

import fitz
from pathlib import Path

from edu_agent.ingest.artifacts import validate_record, write_jsonl
from edu_agent.ingest.errors import IngestError


def render_pdf(
    pdf_path: Path,
    stage_dir: Path,
    *,
    dpi: int = 160,
    source_pdf: str | None = None,
) -> Path:
    """渲染 PDF 每页为 PNG 并写 stage_dir/pages.jsonl,返回 jsonl 路径。

    失败码:pdf_invalid(打不开/零页)、page_render_failed(渲染中断)。
    """
    if not pdf_path.is_file():
        raise IngestError("pdf_invalid", f"not a file: {pdf_path}")
    pages_dir = stage_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    try:
        document = fitz.open(pdf_path)
        with document:
            zoom = dpi / 72
            matrix = fitz.Matrix(zoom, zoom)
            for page_no, page in enumerate(document, start=1):
                image = f"pages/{page_no:04d}.png"
                try:
                    pixmap = page.get_pixmap(matrix=matrix)
                    pixmap.save(stage_dir / image)
                except (RuntimeError, ValueError) as exc:
                    raise IngestError("page_render_failed", f"page {page_no}: {exc}") from exc
                record = {
                    "version": "ingest_pages_v1",
                    "source_pdf": source_pdf or pdf_path.name,
                    "dpi": dpi,
                    "page_no": page_no,
                    "width_px": pixmap.width,
                    "height_px": pixmap.height,
                    "image": image,
                }
                validate_record(record)
                records.append(record)
    except IngestError:
        raise
    except (RuntimeError, ValueError) as exc:
        raise IngestError("pdf_invalid", str(exc)) from exc
    if not records:
        raise IngestError("pdf_invalid", f"zero pages: {pdf_path}")
    return write_jsonl(stage_dir / "pages.jsonl", records)
