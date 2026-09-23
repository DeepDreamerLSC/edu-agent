#!/usr/bin/env python3
"""题库 answer_spec 声明面编译器(用户裁令⑥ 2026-09-23):只编 eligible 候选池,确定性可复算。

给 docs/evals/trusted-completion-gate-design-v3.md §三 的 answer 声明面填数据:kernel 侧
_answer_spec(PR #422)只认 question["answer_spec"] **显式声明面**、缺面即 fail-closed——
本脚本就是该声明面的编译器。规则全部确定性(零模型、零语义猜测),同一输入永远同一
输出(幂等:先剥旧 answer_spec 再全量重算),每记录产物可独立人审。

编译规则(与 scripts/answer_census.py #417 的互斥分类同源,逐条钉死):

  1. eligibility:answer_census.classify(answer) 互斥分类(首中即归类)。
     composite → **不编**(用户裁令② 2026-09-23:112 条复合不加声明面——加了也是
     needs_review,纯噪声;任何局部槽命中不构造 evidence 是设计件 §三红线)。
  2. choice_letter 的 letter_choices 来源判定(题库无结构化 options 字段,只能从
     stem 确定性识别):
       a. 选项标记 = stem 内「字母 + 半角点/全角点/顿号」形态,按出现序提取
          (正则见 _OPTION_MARKER_RE;标记前粘连字母数字的不算,如「3A.」);
       b. 标记序列必须恰为 'A' 起的字母表连续前缀(无缺号/跳号/重复/不从 A 起);
       c. 答案字母必须在识别集合内;
       d. 全满足 → letter_choices = 识别字母表;否则**整条留空**(用户裁令①:
          151 是 census eligibility upper bound 不是必须成功的指标——选项列表
          不可靠(在题图里/缺失)就留空 fail-closed,不得为凑数从题面自由文本猜)。
  3. 其余 eligible 面(numeric_with_unit / short_text_exact / equation_form /
     true_false)→ 组装:
       answer_type  = census 分类(answer_type 来自 schema 声明,声明面在此构造);
       ground_truth = **answer 原文**(逐字,不归一——等价形态识别交给 A 段
                     verifier,声明面只存权威答案);
       aliases      = [] 显式空(题库无别名数据;不扩病例短语表是终裁红线);
       unit_optional= false 显式(题库无单位省略授权;单位省略仅 schema 显式
                     optional,设计件 §三审查修正③)。
  4. 编译验收门(可复算):verify_completion(spec, answer 原文自回喂) 必须命中
     ——权威答案喂给 A 段六窄面 verifier 都判不中的 spec 是死数据,该记录留空
     fail-closed,原因 verifier_incompatible_original(裁令①:不凑数)。A 段
     verifier 演进(如符号归一剥句读)后重跑本脚本即可恢复编入。

输出:统计 + 留空清单(原因分类)。默认 dry-run,--write 才落盘;写回保持原 JSON
格式(ensure_ascii=False / indent=1 / 无尾换行,roundtrip 复现),answer_spec 键插在
answer 之后。只依赖标准库 + answer_census + edu_agent 公开面(agents.small_lecturer)。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from answer_census import DEFAULT_BANK, classify, load_bank

from edu_agent.agents.small_lecturer import AnswerSpec, verify_completion

# stem 选项标记:单字母 A–D 紧跟 . / ． / 、 ;标记前粘连字母/数字的不算
# (防「3A.」「m²A」类误收)。题面选项字母表实测仅 A–D(answer_census 同口径)。
_OPTION_MARKER_RE = re.compile(r"(?<![A-Za-z0-9])([A-D])[.．、]")

REASON_COMPOSITE = "composite_not_compiled"
REASON_CHOICE = "choice_no_reliable_letter_choices"
REASON_INCOMPATIBLE = "verifier_incompatible_original"
REASON_ORDER = (REASON_COMPOSITE, REASON_CHOICE, REASON_INCOMPATIBLE)


def choice_letter_choices(stem: object, answer: object) -> tuple[str, ...] | None:
    """从 stem 确定性识别选项字母表;不可识别/不完整/答案不在集内 → None(留空)。"""
    markers = _OPTION_MARKER_RE.findall(str(stem or ""))
    consecutive = markers and markers == [chr(65 + i) for i in range(len(markers))]
    letters = [a for a in str(answer or "").strip() if a.isascii() and a.isalpha()]
    if not (consecutive and len(letters) == 1 and letters[0] in markers):
        return None
    return tuple(markers)


def compile_spec(record: dict) -> tuple[dict | None, str | None]:
    """单记录编译:(answer_spec 声明面, 留空原因)——spec 非 None 时原因恒 None。"""
    answer = record.get("answer")
    category = classify(answer)
    if category == "composite":
        return None, REASON_COMPOSITE
    extra: dict = {}
    if category == "choice_letter":
        letters = choice_letter_choices(record.get("stem"), answer)
        if letters is None:
            return None, REASON_CHOICE
        extra["letter_choices"] = list(letters)
    spec = {
        "answer_type": category,
        "ground_truth": str(answer),
        "aliases": [],
        "unit_optional": False,
    }
    spec.update(extra)
    if verify_completion(_as_answer_spec(spec), str(answer), 1) is None:
        return None, REASON_INCOMPATIBLE       # 权威答案自回喂不命中:死数据,不编
    return spec, None


def _as_answer_spec(spec: dict) -> AnswerSpec:
    """声明面 dict → A 段 AnswerSpec(与 kernel _answer_spec 同字段口径)。"""
    return AnswerSpec(
        answer_type=spec["answer_type"],
        ground_truth=spec["ground_truth"],
        aliases=tuple(spec.get("aliases") or ()),
        unit_optional=bool(spec.get("unit_optional", False)),
        letter_choices=tuple(spec.get("letter_choices") or ()),
    )


def compile_bank(records: list[dict]) -> tuple[list[dict], Counter, dict[str, list[str]]]:
    """全库重算(幂等):(编译后 records, 留空原因计数, 留空 id 清单)。

    先剥旧 answer_spec 再按规则 1–4 重算——answer/ stem/ census 规则是唯一
    事实源,重跑不叠加。"""
    compiled: list[dict] = []
    reasons: Counter = Counter()
    left: dict[str, list[str]] = {reason: [] for reason in REASON_ORDER}
    for record in records:
        spec, reason = compile_spec(record)
        rebuilt: dict = {}
        for key, value in record.items():
            if key == "answer_spec":
                continue                        # 剥旧声明面(幂等重算)
            rebuilt[key] = value
            if key == "answer":
                if spec is not None:
                    rebuilt["answer_spec"] = spec
                else:
                    left[reason].append(str(record.get("question_id", "?")))
                    reasons[reason] += 1
        compiled.append(rebuilt)
    return compiled, reasons, left


def render_stats(records: list[dict], reasons: Counter, left: dict[str, list[str]],
                 total: int, ids: bool) -> list[str]:
    """统计输出行(编译数按窄面 / 留空按原因 / composite 单列)。"""
    compiled_types = Counter(
        str(r["answer_spec"]["answer_type"]) for r in records if "answer_spec" in r)
    n_compiled = sum(compiled_types.values())
    lines = [
        "answer_spec 声明面编译(用户裁令⑥ 2026-09-23;eligible 候选池=151 上限,非指标)",
        f"records: {total}(eligible 上限 = total − composite {reasons[REASON_COMPOSITE]})",
        f"编译: {n_compiled} "
        + " / ".join(f"{cat} {compiled_types.get(cat, 0)}"
                     for cat in ("numeric_with_unit", "short_text_exact",
                                 "choice_letter", "equation_form", "true_false")),
        f"留空: {sum(v for k, v in reasons.items() if k != REASON_COMPOSITE)}",
    ]
    labels = {REASON_COMPOSITE: "composite 不编(裁令②)",
              REASON_CHOICE: "choice 选项列表不可靠(裁令①)",
              REASON_INCOMPATIBLE: "自回喂不命中,A 段口径外原文(裁令①)"}
    for reason in REASON_ORDER:
        lines.append(f"  - {reason}({labels[reason]}): {reasons[reason]}")
    if ids:
        for reason in REASON_ORDER:
            if left[reason]:
                lines.append(f"  {reason} 清单: {' '.join(left[reason])}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="题库 answer_spec 声明面编译器(裁令⑥;确定性、幂等、可复算)")
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK,
                        help="题库 JSON(默认 edu_agent/contracts/partner_bank.json)")
    parser.add_argument("--write", action="store_true",
                        help="落盘(默认 dry-run 只打印统计)")
    parser.add_argument("--ids", action="store_true", help="附留空记录清单")
    args = parser.parse_args(argv)
    if not args.bank.is_file():
        print(f"题库文件不存在:{args.bank}", file=sys.stderr)
        return 2
    records = load_bank(args.bank)
    compiled, reasons, left = compile_bank(records)
    print("\n".join(render_stats(compiled, reasons, left, len(records), args.ids)))
    if not args.write:
        print("\n(dry-run;--write 落盘)")
        return 0
    raw = args.bank.read_text(encoding="utf-8")
    data = json.loads(raw)
    data["records"] = compiled
    out = json.dumps(data, ensure_ascii=False, indent=1)
    if json.loads(out) != data:
        print("内部错误:序列化 roundtrip 不一致,不落盘", file=sys.stderr)
        return 2
    args.bank.write_text(out, encoding="utf-8")  # 无尾换行(与原文件格式一致)
    print(f"\n已写回 {args.bank}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
