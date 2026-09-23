#!/usr/bin/env python3
"""题库 answer 形态普查(#417):互斥分类分布表 + 输入 fingerprint,一条命令可复现。

设计件 docs/evals/trusted-completion-gate-design-v3.md §三 的「~67% answer-key 形态可判
上限」附了实测口径(263 题分母 + 互斥分类规则);本脚本把该口径钉成仓内可复现实跑:

  uv run python scripts/answer_census.py            # 分布表 + fingerprint
  uv run python scripts/answer_census.py --ids      # 附各类 question_id 清单

互斥分类规则(优先级从高到低,首中即归类;#417 钉死,语义对齐设计件 §三窄面):
  1. numeric_with_unit  数值含单位——整答=单个数值(整数/小数/分数 a/b/百分号/千分位)
                        +可选单位后缀(拉丁/CJK/符号,不含数字与分隔符)+可选句读终止符
  2. choice_letter      选择字母——整答恰为一个选项字母(本题库题面选项字母表 A–D,
                        「字母精确匹配」:A。/B. 15 等字母+标点/内容不属本类,落入后续规则)
  3. true_false         判断——去句读终止符后整答∈{对,错,√,×,✓,✗,正确,错误}
  4. equation_form      方程算式——整答仅由数学 token 构成、含 '='、无分号槽分隔符
                        (x=5/9；x=14 多方程=多槽→composite,同「多空整体 needs_review」)
  5. short_text_exact   短文本≤12字——长度≤12字(按原文字符计)且数值槽≤1
                        (多槽如「鸡3只,兔5只」不属本窄面——设计件 §三)
  6. composite          复合——其余(多值/多空/含叙述)

fingerprint=输入题库文件 sha256 前 16 位 hex:「263 是哪些题」以题库文件字节+本脚本可追溯。
输入缺省=edu_agent/contracts/partner_bank.json(api question_source 的 bank 题源,
263 题,answer 全为字符串);对空题库/异常字段(answer 缺失/非字符串)按缺省处理不崩,
冒烟钉在 tests/evals/test_answer_census.py。只依赖标准库。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

DEFAULT_BANK = (
    Path(__file__).resolve().parents[1] / "edu_agent" / "contracts" / "partner_bank.json"
)

CATEGORY_NUMERIC = "numeric_with_unit"
CATEGORY_CHOICE = "choice_letter"
CATEGORY_TRUE_FALSE = "true_false"
CATEGORY_EQUATION = "equation_form"
CATEGORY_SHORT_TEXT = "short_text_exact"
CATEGORY_COMPOSITE = "composite"
CATEGORY_ORDER = (
    CATEGORY_NUMERIC,
    CATEGORY_CHOICE,
    CATEGORY_TRUE_FALSE,
    CATEGORY_EQUATION,
    CATEGORY_SHORT_TEXT,
    CATEGORY_COMPOSITE,
)

_SHORT_TEXT_MAX_CHARS = 12
_MAX_NUMERIC_SLOTS = 1
_TRUE_FALSE_ANSWERS = frozenset({"对", "错", "√", "×", "✓", "✗", "正确", "错误"})
_TERMINATING_PUNCT = "。；;，,、 \t"
# 数值核心:整数/小数/千分位/百分号/分数,后接可选单位(拉丁/CJK/°℃²³·,不含数字与分隔符)
_NUMERIC_WITH_UNIT_RE = re.compile(
    r"[+-]?\d+(?:,\d{3})*(?:\.\d+)?(?:%|/\d+)?\s*[A-Za-z°℃²³·\u4e00-\u9fff]*"
)
_CHOICE_LETTER_RE = re.compile(r"[A-D]")  # 题面选项字母表(stem 实测仅 A–D)
_SLOT_SEPARATOR_RE = re.compile(r"[；;]")
# 数学 token:数字/变量字母/运算符/括号/比较符/π·°²³/空白/逗号顿号(全半角)
_MATH_TOKENS_RE = re.compile(r"[0-9a-zA-Z.+/×÷=<>＜＞（）()＋－°π·²³\s,，、-]+")
_NUMERIC_RUN_RE = re.compile(r"\d+(?:\.\d+)?(?:%|/\d+)?")


def classify(answer: object) -> str:
    """对单条 answer 互斥分类(首中即归类);非字符串/空 answer 归 composite。"""
    text = answer.strip() if isinstance(answer, str) else ""
    if not text:
        return CATEGORY_COMPOSITE
    body = text.rstrip(_TERMINATING_PUNCT).rstrip()
    if _NUMERIC_WITH_UNIT_RE.fullmatch(body):
        return CATEGORY_NUMERIC
    if _CHOICE_LETTER_RE.fullmatch(text):
        return CATEGORY_CHOICE
    if body in _TRUE_FALSE_ANSWERS:
        return CATEGORY_TRUE_FALSE
    return _tail_category(text, body)


def _tail_category(text: str, body: str) -> str:
    """级联尾段:方程算式→短文本→复合。"""
    if _is_equation_form(body):
        return CATEGORY_EQUATION
    if _is_short_text(text):
        return CATEGORY_SHORT_TEXT
    return CATEGORY_COMPOSITE


def _is_equation_form(body: str) -> bool:
    """方程算式:整答仅数学 token、含 '='、无分号槽分隔(多方程=多槽→composite)。"""
    return bool(
        "=" in body
        and not _SLOT_SEPARATOR_RE.search(body)
        and _MATH_TOKENS_RE.fullmatch(body)
    )


def _is_short_text(text: str) -> bool:
    """短文本≤12字且数值槽≤1(多槽如「鸡3只,兔5只」不属本窄面——设计件 §三)。"""
    return len(text) <= _SHORT_TEXT_MAX_CHARS and (
        len(_NUMERIC_RUN_RE.findall(text)) <= _MAX_NUMERIC_SLOTS
    )


def load_bank(path: Path) -> list[dict]:
    """读题库 JSON 的 records;文件损坏/records 非列表/非 dict 成员→跳过,不崩。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"警告:题库不可读,按空输入处理({error})", file=sys.stderr)
        return []
    records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def fingerprint(path: Path) -> str:
    """输入数据源 sha256 前 16 位 hex(「263 是哪些题」以题库文件字节可追溯)。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def census(records: list[dict]) -> tuple[Counter, dict[str, list[str]]]:
    """逐条分类:(各类计数, 各类 question_id 清单)。answer 缺失→composite(可观测)。"""
    counts: Counter = Counter()
    ids: dict[str, list[str]] = {category: [] for category in CATEGORY_ORDER}
    for record in records:
        category = classify(record.get("answer"))
        counts[category] += 1
        ids[category].append(str(record.get("question_id", "?")))
    return counts, ids


def render_distribution(counts: Counter, total: int) -> list[str]:
    """分布表行:各类计数+占比,末行 total(类别顺序钉死=优先级顺序)。"""
    lines = [f"{'category':<20}{'count':>6}{'share':>9}"]
    for category in CATEGORY_ORDER:
        share = counts[category] / total * 100 if total else 0.0
        lines.append(f"{category:<20}{counts[category]:>6}{share:>8.1f}%")
    lines.append(f"{'total':<20}{total:>6}{100.0 if total else 0.0:>8.1f}%")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="题库 answer 形态普查(#417):互斥分类分布 + fingerprint"
    )
    parser.add_argument(
        "--bank",
        type=Path,
        default=DEFAULT_BANK,
        help="题库 JSON(默认 edu_agent/contracts/partner_bank.json)",
    )
    parser.add_argument(
        "--ids", action="store_true", help="附各类 question_id 清单(哪些题在哪类)"
    )
    args = parser.parse_args(argv)
    if not args.bank.is_file():
        print(f"题库文件不存在:{args.bank}", file=sys.stderr)
        return 2
    records = load_bank(args.bank)
    counts, ids = census(records)
    total = len(records)
    eligible = total - counts[CATEGORY_COMPOSITE]
    upper = eligible / total * 100 if total else 0.0
    print("题库 answer 形态普查(#417;设计件 v3.1 §三实测口径)")
    print(f"输入: {args.bank} (sha256 hex16: {fingerprint(args.bank)})")
    print()
    print("\n".join(render_distribution(counts, total)))
    print()
    print(f"answer-key 形态可判上限(非 composite 占比): {eligible}/{total} = {upper:.1f}%")
    if args.ids:
        for category in CATEGORY_ORDER:
            print(f"\n{category} ({counts[category]}):")
            print("  " + " ".join(ids[category]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
