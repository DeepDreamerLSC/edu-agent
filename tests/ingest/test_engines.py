"""引擎归一化层测试:OXR 真实响应夹具 + 老网关通用合同(08 §4)。"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from edu_agent.ingest import IngestError, get_engine

FIXTURES = Path(__file__).parent / "fixtures"


def _oxr_response(payload: dict) -> object:
    import httpx

    return httpx.Response(200, json=payload)


def test_oxr_normalize_maps_real_shape() -> None:
    payload = json.loads((FIXTURES / "oxr_p4_response.json").read_text(encoding="utf-8"))
    parsed = get_engine("oxr").normalize(_oxr_response(payload))
    texts = [line["text"] for line in parsed["lines"]]
    assert any("选择题每小题3分" in text for text in texts)
    # 真实行为:栏目/页眉文字被 OXR 判为 Title(→line,由 segment 按位置排除);视觉块=图
    kinds = {block["kind"] for block in parsed["visual_blocks"]}
    assert "figure" in kinds
    assert all(len(line["bbox"]) == 4 and line["bbox"][2] > line["bbox"][0] for line in parsed["lines"])


def test_oxr_normalize_rejects_error_code() -> None:
    with pytest.raises(IngestError) as info:
        get_engine("oxr").normalize(_oxr_response({"code": "500", "message": "boom"}))
    assert info.value.code == "ocr_layout_invalid"


def test_oxr_normalize_empty_blocks_raises() -> None:
    ok = {"code": "0", "data": {"result": {"outputs": {"json": {"pages": [{"blocks": []}]}}}}}
    with pytest.raises(IngestError) as info:
        get_engine("oxr").normalize(_oxr_response(ok))
    assert info.value.code == "ocr_empty"


def test_legacy_requires_configured_url() -> None:
    with pytest.raises(IngestError) as info:
        get_engine("legacy_gateway").parse_page(Path("x.png"), 10, 10)
    assert info.value.code == "ocr_layout_invalid"


def test_legacy_normalizes_nested_content_contract() -> None:
    payload = json.loads((FIXTURES / "legacy_elements.json").read_text(encoding="utf-8"))
    parsed = get_engine("legacy_gateway").normalize_elements(payload)
    assert parsed["lines"][0]["text"].startswith("1.计算")
    assert parsed["visual_blocks"][0]["kind"] == "figure"
    assert len(parsed["lines"]) == 1


def test_get_engine_registry() -> None:
    assert get_engine("oxr").name == "oxr"
    assert get_engine("legacy_gateway").name == "legacy_gateway"
    with pytest.raises(IngestError):
        get_engine("unknown_engine")
