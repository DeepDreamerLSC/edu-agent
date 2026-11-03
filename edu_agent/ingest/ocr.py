"""ocr 阶段(08 §3):pages.jsonl → elements.jsonl。逐页调引擎,逐条 schema 校验,同目录落 model_calls 事实。"""

from __future__ import annotations

import time
from typing import Any
from pathlib import Path

from edu_agent.ingest.artifacts import read_jsonl, validate_record, write_jsonl
from edu_agent.ingest.errors import IngestError
from edu_agent.ingest.engines import OcrEngine, get_engine


def run_ocr(
    pages_jsonl: Path,
    stage_dir: Path,
    engine: OcrEngine | str,
    *,
    run_id: str,
    page_limit: int | None = None,
) -> Path:
    """对 render 产物逐页执行 OCR;返回 stage_dir/elements.jsonl。

    页图取 pages_jsonl 同目录;单页失败即中断(引擎内部已带重试),失败码见 08 §3。
    """
    active = get_engine(engine) if isinstance(engine, str) else engine
    stage_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    for page in read_jsonl(pages_jsonl):
        if page_limit is not None and page["page_no"] > page_limit:
            break
        png_path = pages_jsonl.parent / str(page["image"])
        started = time.perf_counter()
        parsed = active.parse_page(png_path, int(page["width_px"]), int(page["height_px"]))
        record = {
            "version": "ingest_elements_v1",
            "run_id": run_id,
            "engine": active.name,
            "page_no": int(page["page_no"]),
            "lines": parsed["lines"],
            "visual_blocks": parsed["visual_blocks"],
        }
        validate_record(record)
        records.append(record)
        facts.append(
            {
                "engine": active.name,
                "page_no": int(page["page_no"]),
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "line_count": len(parsed["lines"]),
                "block_count": len(parsed["visual_blocks"]),
            }
        )
    if not records:
        raise IngestError("ocr_empty", f"no pages processed from {pages_jsonl}")  # 上游 render 已拦截零页,防御
    write_jsonl(stage_dir / "model_calls.jsonl", facts)
    return write_jsonl(stage_dir / "elements.jsonl", records)
