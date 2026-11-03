"""OCR 引擎层(08 §4):每引擎一个薄 adapter(硬上限 150 行),统一输出 lines+visual_blocks。

v1 引擎登记:oxr、legacy_gateway(上限 2,08 §7;第三个必须先删一个)。
"""

from __future__ import annotations

from typing import Any, Protocol
from pathlib import Path

from edu_agent.ingest.errors import IngestError

ENGINES = ("oxr", "legacy_gateway")


class OcrEngine(Protocol):
    """引擎协议:输入页图,输出归一化元素;失败抛 IngestError(ocr_* 失败码)。"""

    name: str

    def parse_page(self, png_path: Path, width_px: int, height_px: int) -> dict[str, Any]:
        """返回 {"lines": [...], "visual_blocks": [...]},坐标为输入图像素整型 bbox。"""
        ...


def get_engine(name: str) -> OcrEngine:
    """按登记名取引擎;未知名即配置错误(ocr_layout_invalid)。"""
    if name == "oxr":
        from edu_agent.ingest.engines.oxr import OxrEngine

        return OxrEngine()
    if name == "legacy_gateway":
        from edu_agent.ingest.engines.legacy_gateway import LegacyGatewayEngine

        return LegacyGatewayEngine()
    raise IngestError("ocr_layout_invalid", f"unknown engine '{name}', registered: {ENGINES}")
