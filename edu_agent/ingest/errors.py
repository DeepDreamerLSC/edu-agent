"""ingest 类型化失败(08 §3:失败归入固定枚举,不允许裸 Exception 冒出阶段边界)。"""

from __future__ import annotations

RENDER_CODES = frozenset({"pdf_invalid", "page_render_failed"})
OCR_CODES = frozenset({"ocr_timeout", "ocr_empty", "ocr_layout_invalid"})
SEGMENT_CODES = frozenset({"segment_empty", "segment_boundary_invalid"})
COMPOSE_CODES = frozenset({"crop_out_of_page", "formula_missing"})
ARTIFACT_CODES = frozenset({"artifact_read_failed", "artifact_schema_invalid"})


class IngestError(Exception):
    """携带固定失败码与明细的 ingest 错误;code 必须属于某阶段枚举。"""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
