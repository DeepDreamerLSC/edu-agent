#!/usr/bin/env python3
"""D6/D7 matched-surface adapter(#464 终裁 5892600320):Human Pass 1 实际信息面 → Judge 输入。

输入面合同(input-surface adapter;不改 rubric 语义——SYSTEM_PROMPT/S2_SCHEMA/
gateway 参数随引擎冻结件零改动):
- 同一题面表示:逐字取自冻结 pass1-pack.md 的「**题面**」行(含 5 案 dict 形态
  {text, answer} 的答案暴露——原样复现,不清洗不删案);
- 同一回看窗、截止同一锚轮、不给锚后轮(pack 内本就无锚后轮);
- 不给 session/case/stratum/run identity;不给任何旧 Judge/AI 输出;
- 判定锚以非对话行【判定锚】给出(与人类任务框架一致;对话内容零污染)。

确定性:零网络零模型。输入 = 冻结 pack + human gold(已含盲化映射解盲结果);
输出 jsonl 逐案 {case_id, user_prompt, answer_exposed, gold}——gold 随行仅供
后续 scorer,模型边界只过 user_prompt(镜像 battery P1-2 期望值防火墙)。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path

from edu_agent.evals.s2_judge import _USER_INSTRUCTIONS

_SECTION = re.compile(r"^## (P\d-\d\d)$")
_QUESTION = re.compile(r"^\*\*题面\*\*:(.*)$")
_GRADE = re.compile(r"^\*\*年级\*\*:(.*)$")
_TURN_STU = re.compile(r"^- \[轮(\d+)·学生\] (.*)$")
_TURN_TUT = re.compile(r"^- \[轮(\d+)·Tutor\]( ▶ \*\*判定锚\*\*)? (.*)$")
_LEAK_PATTERNS = ("P1-", "P2-", "kernel_", "session_id", "case_id", "stratum",
                  "small_lecturer", "manifest", "blind", "slice_id")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_pack(pack_text: str) -> dict[str, dict]:
    """冻结 pack → {case_id: {question, grade, turns}};turn=(轮号, 角色, 原文, 是否锚)。

    pack 逐行形态已核验(439 行全匹配已知模式,turn 均单行);未匹配行静默略过
    (注释/分隔/略行说明属版式元信息,非证据)。
    """
    cases: dict[str, dict] = {}
    current: dict | None = None
    for line in pack_text.splitlines():
        head = _SECTION.match(line)
        if head:
            current = {"question": "", "grade": "", "turns": []}
            cases[head.group(1)] = current
            continue
        if current is None:
            continue
        if match := _QUESTION.match(line):
            current["question"] = match.group(1)
        elif match := _GRADE.match(line):
            current["grade"] = match.group(1)
        elif match := _TURN_STU.match(line):
            current["turns"].append((int(match.group(1)), "user",
                                     match.group(2), False))
        elif match := _TURN_TUT.match(line):
            current["turns"].append((int(match.group(1)), "assistant",
                                     match.group(3), bool(match.group(2))))
    return cases


def render_user_prompt(case: dict) -> str:
    """matched-surface user prompt:题面/年级(逐字)+ 对话记录(引擎行格式)+ 判定锚框架行。"""
    assert any(turn[3] for turn in case["turns"]), "pack 案缺判定锚"
    lines = [f"【题面】{case['question']}"]
    if case["grade"]:
        lines.append(f"【年级】{case['grade']}")
    lines.append("【对话记录】")
    anchor_no = 0
    for no, role, content, is_anchor in case["turns"]:
        lines.append(f"{'学生' if role == 'user' else '小讲师'}(轮{no}):{content}")
        if is_anchor:
            anchor_no = no
    lines.append(f"【判定锚】判定对象 = 小讲师(轮{anchor_no})的本轮回应"
                 "(与其紧邻的学生话语配对);逐轮原文如上。")
    lines += _USER_INSTRUCTIONS
    return "\n".join(lines)


def answer_exposed(question: str) -> bool:
    """题面为 dict 形态且含 answer 键 → 答案暴露(pack 原样渲染了该 dict)。"""
    try:
        parsed = ast.literal_eval(question)
    except (ValueError, SyntaxError):
        return False
    return isinstance(parsed, dict) and "answer" in parsed


def build_rows(pack_cases: dict[str, dict], gold: dict) -> list[dict]:
    """pack × gold → 逐案行;gold 标签只随行供 scorer,不进 user_prompt。"""
    rows = []
    for case in gold["cases"]:
        pack_case = pack_cases[case["blind_id"]]
        rows.append({
            "case_id": case["blind_id"],
            "user_prompt": render_user_prompt(pack_case),
            "answer_exposed": answer_exposed(pack_case["question"]),
            "gold": {"s2a": case["s2a"], "s2b": case["s2b"]},
        })
    return rows


def assert_surface(rows: list[dict]) -> None:
    """机械面检查:案数守恒、每案恰一锚框架行、身份/AI 输出泄漏零命中。"""
    for row in rows:
        assert row["user_prompt"].count("【判定锚】") == 1, row["case_id"]
        for pattern in _LEAK_PATTERNS:
            assert pattern not in row["user_prompt"], (row["case_id"], pattern)


def main() -> int:
    parser = argparse.ArgumentParser(description="D6/D7 matched-surface renderer")
    parser.add_argument("--pack", required=True, type=Path,
                        help="冻结 pass1-pack.md")
    parser.add_argument("--gold", required=True, type=Path,
                        help="human-gold-v0.1.json(已解盲)")
    parser.add_argument("--out", required=True, type=Path, help="输出 jsonl")
    args = parser.parse_args()

    pack_cases = parse_pack(args.pack.read_text(encoding="utf-8"))
    gold = json.loads(args.gold.read_text(encoding="utf-8"))
    rows = build_rows(pack_cases, gold)
    assert len(rows) == len(gold["cases"]), "gold 案数不匹配"
    assert_surface(rows)
    with args.out.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    exposed = [row["case_id"] for row in rows if row["answer_exposed"]]
    print(f"matched-surface rows: {len(rows)} → {args.out}")
    print(f"answer_exposed: {len(exposed)} {exposed}")
    print(f"pack sha256={_sha(args.pack)}")
    print(f"gold sha256={_sha(args.gold)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
