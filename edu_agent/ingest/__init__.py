"""题目入库线(08 §3):阶段=纯函数+不可变 artifact,阶段间只经 contracts schema 衔接。

公开面:render_pdf 阶段入口、artifact 读写与校验、IngestError。
子模块(render/artifacts/errors)对测试不可见(02 §6),一律从这里导入。
"""

from edu_agent.ingest.artifacts import read_jsonl, validate_record, write_jsonl
from edu_agent.ingest.engines import get_engine
from edu_agent.ingest.errors import IngestError
from edu_agent.ingest.ocr import run_ocr
from edu_agent.ingest.render import render_pdf

__all__ = [
    "IngestError",
    "get_engine",
    "read_jsonl",
    "render_pdf",
    "run_ocr",
    "validate_record",
    "write_jsonl",
]
