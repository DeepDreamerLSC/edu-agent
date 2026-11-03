"""老仓库公网 OCR 网关 adapter(08 §4):invoke 合同移植 + 通用元素归一化。

环境变量:INGEST_LEGACY_GATEWAY_URL / _API_KEY / _MODEL_ID / _TIMEOUT_S。
未配置 URL 即抛 ocr_layout_invalid(配置错误,不是引擎故障)。
默认模型 pp-ocrv6-medium-ocr-layout-v1(行级 JSON 合同);generic 模型返回
elements/blocks/layout/lines 任一形态均可归一化。
"""

from __future__ import annotations

import json
import os
from typing import Any
from pathlib import Path

import httpx

from edu_agent.ingest.errors import IngestError

_DEFAULT_MODEL = "pp-ocrv6-medium-ocr-layout-v1"
_FIGURE_KINDS = frozenset({"image", "figure", "diagram", "chart", "picture"})


class LegacyGatewayEngine:
    """老 edu_agent 模型网关的 vision_layout invoke 客户端(实验合同移植,未经线上验证)。"""

    name = "legacy_gateway"

    def __init__(self) -> None:
        self.url = os.environ.get("INGEST_LEGACY_GATEWAY_URL", "").strip()
        self.api_key = os.environ.get("INGEST_LEGACY_GATEWAY_API_KEY", "").strip()
        self.model_id = os.environ.get("INGEST_LEGACY_GATEWAY_MODEL_ID", _DEFAULT_MODEL)
        self.timeout = float(os.environ.get("INGEST_LEGACY_GATEWAY_TIMEOUT_S", "180"))

    def parse_page(self, png_path: Path, width_px: int, height_px: int) -> dict[str, Any]:
        if not self.url:
            raise IngestError("ocr_layout_invalid", "INGEST_LEGACY_GATEWAY_URL not configured")
        payload = {
            "request_id": f"ingest-ocr-layout-{png_path.stem}",
            "model_policy": "vision_doc_default",
            "required_capability": "vision_layout",
            "invoke_type": "vision_layout",
            "timeout_ms": int(self.timeout * 1000),
            "messages": [{"role": "user", "content": "ocr layout"}],
            "inputs": [{"type": "image_file", "path": str(png_path)}],
            "generation": {"max_tokens": 4096, "temperature": 0.0, "stream": False},
            "response_format": {"type": "json_object"},
            "metadata": {"preferred_model_id": self.model_id, "require_preferred_model_id": True, "stage": "ocr_layout"},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            response = httpx.post(self.url, json=payload, headers=headers, timeout=self.timeout)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise IngestError("ocr_timeout", f"legacy gateway: {type(exc).__name__}: {exc}") from exc
        if response.status_code != 200:
            raise IngestError("ocr_layout_invalid", f"legacy gateway http {response.status_code}: {response.text[:200]}")
        return self.normalize_elements(response.json())

    def __repr__(self) -> str:  # pragma: no cover - 调试便利
        return f"LegacyGatewayEngine(model_id={self.model_id!r}, configured={bool(self.url)})"

    @staticmethod
    def normalize_elements(payload: dict[str, Any]) -> dict[str, Any]:
        """归一化网关响应为 lines+visual_blocks(公开:测试与 1c 门禁回放复用)。"""
        lines: list[dict[str, Any]] = []
        visual: list[dict[str, Any]] = []
        for raw in _raw_elements(payload):
            if not isinstance(raw, dict):
                continue
            bbox = raw.get("bbox") or raw.get("box")
            if not isinstance(bbox, list) or len(bbox) < 4:
                continue
            try:
                x1, y1, x2, y2 = (int(round(float(v))) for v in bbox[:4])
            except (TypeError, ValueError):
                continue
            if x2 <= x1 or y2 <= y1:
                continue
            text = str(raw.get("text") or raw.get("content") or "").strip()
            kind = str(raw.get("kind") or raw.get("type") or "").lower()
            box = [max(0, x1), max(0, y1), x2, y2]
            if kind in _FIGURE_KINDS:
                visual.append({"bbox": box, "kind": "figure", "text": text[:80] or None})
            else:
                lines.append({"bbox": box, "text": text})
        if not lines and not visual:
            raise IngestError("ocr_empty", "legacy gateway returned no usable elements")
        return {"lines": lines, "visual_blocks": visual}


def _raw_elements(payload: Any) -> list[Any]:
    """从网关响应里提取元素列表:兼容 output/elements/blocks/layout/lines 与 content JSON 字符串。"""
    for _ in range(4):
        if isinstance(payload, list):
            return payload
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return []
        elif isinstance(payload, dict):
            content = payload.get("content") or payload.get("output") or payload.get("result")
            if isinstance(content, (str, dict)) and not any(k in payload for k in ("elements", "blocks", "lines", "layout")):
                payload = content
                continue
            for key in ("elements", "blocks", "lines", "layout"):
                if isinstance(payload.get(key), list):
                    return payload[key]
            return []
        else:
            return []
    return []
