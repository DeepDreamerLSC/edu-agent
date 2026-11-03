"""OXR 引擎(SoMark OXR-1.0,08 §4):/v1/parse/sync,JSON blocks → lines+visual_blocks。"""

from __future__ import annotations

import os
import time
from typing import Any
from pathlib import Path

import httpx

from edu_agent.ingest.errors import IngestError

_DEFAULT_BASE = "https://free-oxr.somark.cn/api/v1"
_LINE_TYPES = frozenset({"Title", "Text", "Caption", "Footnote", "Code", "Code Block"})
_KIND_MAP = {
    "Picture": "figure", "Figure": "figure", "Table": "table", "Formula": "formula",
    "Stamp": "stamp", "Chemical Equation": "other", "Chemical Structure": "other",
    "Header": "header", "Footer": "footer", "Page-header": "header", "Page-footer": "footer",
}


def _int_bbox(bbox: list[float]) -> list[int] | None:
    try:
        x1, y1, x2, y2 = (int(round(float(v))) for v in bbox[:4])
    except (TypeError, ValueError):
        return None
    if x2 <= x1 or y2 <= y1 or min(x1, y1) < 0:
        return None
    return [x1, y1, x2, y2]


def _multipart(png: bytes, name: str, api_key: str) -> tuple[bytes, str]:
    """手工构造 multipart(经代理时 httpx 自带编码器有 h11 兼容问题,故自建)。"""
    boundary = "----eduagentingest7f3a1c"
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"api_key\"\r\n\r\n{api_key}\r\n",
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"output_formats\"\r\n\r\njson\r\n",
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"output_formats\"\r\n\r\nmarkdown\r\n",
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
        f"Content-Type: image/png\r\n\r\n",
    ]
    body = "".join(parts).encode("utf-8") + png + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return body, f"multipart/form-data; boundary={boundary}"


class OxrEngine:
    """免费/自部署 OXR 服务的同步解析客户端;环境变量覆盖 base/key/超时。"""

    name = "oxr"

    def __init__(self) -> None:
        self.base_url = os.environ.get("OXR_BASE_URL", _DEFAULT_BASE).rstrip("/")
        self.api_key = os.environ.get("OXR_API_KEY", "dummy")
        self.timeout = float(os.environ.get("OXR_TIMEOUT_S", "240"))
        self.retries = int(os.environ.get("OXR_RETRIES", "2"))

    def parse_page(self, png_path: Path, width_px: int, height_px: int) -> dict[str, Any]:
        content, content_type = _multipart(png_path.read_bytes(), png_path.name, self.api_key)
        headers = {"Content-Type": content_type}
        last_error = "unattempted"
        for attempt in range(self.retries + 1):
            try:
                response = httpx.post(
                    f"{self.base_url}/parse/sync",
                    content=content,
                    headers=headers,
                    timeout=self.timeout,
                )
                if response.status_code >= 500:
                    last_error = f"http {response.status_code}"
                else:
                    return self.normalize(response)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            if attempt < self.retries:
                time.sleep(2.0)
        raise IngestError("ocr_timeout", f"oxr parse failed after {self.retries + 1} tries: {last_error}")

    def normalize(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code != 200:
            raise IngestError("ocr_layout_invalid", f"oxr http {response.status_code}: {response.text[:200]}")
        payload = response.json()
        if str(payload.get("code")) != "0":
            raise IngestError("ocr_layout_invalid", f"oxr code={payload.get('code')} msg={payload.get('message')}")
        outputs = payload.get("data", {}).get("result", {}).get("outputs", {})
        pages = (outputs.get("json") or {}).get("pages") or []
        blocks = pages[0].get("blocks", []) if pages else []
        lines: list[dict[str, Any]] = []
        visual: list[dict[str, Any]] = []
        for block in blocks:
            bbox = _int_bbox(block.get("bbox") or [])
            if bbox is None or not isinstance(block, dict):
                continue
            text = str(block.get("content") or "").strip()
            block_type = str(block.get("type") or "")
            if block_type in _LINE_TYPES:
                lines.append({"bbox": bbox, "text": text})
            else:
                visual.append({"bbox": bbox, "kind": _KIND_MAP.get(block_type, "other"), "text": text or None})
        if not lines and not visual:
            raise IngestError("ocr_empty", "oxr returned no blocks")
        return {"lines": lines, "visual_blocks": visual}
