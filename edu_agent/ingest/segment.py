"""segment 阶段(08 §3):elements.jsonl → questions.jsonl。v1 规则锚定(题号+版面位置),纯函数。

LLM 归属(08 §4 question_segment 角色)是 ING-2 增强项;v1 边界质量由 golden 门禁度量。
"""

from __future__ import annotations

import re
from typing import Any
from pathlib import Path

from edu_agent.ingest.artifacts import read_jsonl, validate_record, write_jsonl
from edu_agent.ingest.errors import IngestError

_QUESTION_ANCHOR = re.compile(r"^\s*([0-9]{1,3})[.、．](?![0-9])\s*\S")
_HEADER_KINDS = frozenset({"header", "footer"})


def _union(bboxes: list[list[int]]) -> list[int]:
    return [
        min(box[0] for box in bboxes),
        min(box[1] for box in bboxes),
        max(box[2] for box in bboxes),
        max(box[3] for box in bboxes),
    ]


def segment_page(page_elements: dict[str, Any], *, top_strip_px: int = 70) -> list[dict[str, Any]]:
    """单页元素 → 题目记录列表。

    规则:题号锚点行开启新题,其后行归属该题直到下一锚点;**首个锚点之上的行全部排除**
    (锚点之前=页眉/栏目/标题区,golden Q1:章节页栏目不在顶部条带);另排除 y < top_strip_px
    的行与 header/footer 视觉块;无锚点页产出单条 needs_review(题号 0)。
    """
    lines = list(enumerate(page_elements.get("lines", [])))
    anchors_y = [
        int(line["bbox"][1])
        for _, line in lines
        if _QUESTION_ANCHOR.match(str(line.get("text", "")))
    ]
    first_anchor_y = min(anchors_y) if anchors_y else None
    excluded = {
        index
        for index, line in lines
        if int(line["bbox"][1]) < top_strip_px
        or (first_anchor_y is not None and int(line["bbox"][3]) <= first_anchor_y)
    }
    header_blocks = [
        index
        for index, block in enumerate(page_elements.get("visual_blocks", []))
        if block.get("kind") in _HEADER_KINDS
    ]
    members: dict[int, list[int]] = {}
    anchors: dict[int, int] = {}
    current: int | None = None
    for index, line in lines:
        if index in excluded:
            continue
        match = _QUESTION_ANCHOR.match(str(line.get("text", "")))
        if match:
            current = int(match.group(1))
            anchors[current] = index
            members.setdefault(current, [])
        elif current is not None:
            members[current].append(index)
    if not members:
        body = [index for index, _ in lines if index not in excluded]
        if not body:
            return []
        return [_question(page_elements, 0, body, sorted(excluded) + header_blocks, "needs_review")]
    questions = []
    for number in sorted(members):
        ids = sorted({anchors[number], *members[number]})
        questions.append(_question(page_elements, number, ids, sorted(excluded) + header_blocks, "accepted"))
    return questions


def _question(
    page_elements: dict[str, Any],
    number: int,
    target_ids: list[int],
    excluded_ids: list[int],
    status: str,
) -> dict[str, Any]:
    lines = page_elements.get("lines", [])
    bbox = _union([lines[index]["bbox"] for index in target_ids])
    return {
        "version": "ingest_questions_v1",
        "run_id": page_elements["run_id"],
        "page_no": int(page_elements["page_no"]),
        "question_no": number,
        "target_block_ids": target_ids,
        "question_bbox": bbox,
        "excluded_block_ids": excluded_ids,
        "status": status,
    }


def run_segment(elements_jsonl: Path, stage_dir: Path) -> Path:
    """segment 阶段入口:逐页切题,逐条 schema 校验,写 stage_dir/questions.jsonl。"""
    questions: list[dict[str, Any]] = []
    for page_elements in read_jsonl(elements_jsonl):
        questions.extend(segment_page(page_elements))
    if not questions:
        raise IngestError("segment_empty", f"no questions from {elements_jsonl}")
    for question in questions:
        validate_record(question)
    stage_dir.mkdir(parents=True, exist_ok=True)
    return write_jsonl(stage_dir / "questions.jsonl", questions)
