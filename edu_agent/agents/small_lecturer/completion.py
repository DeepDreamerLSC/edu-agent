"""Trusted Completion Gate A 段(#414 设计件 v2 §二/§三,零行为变化)。

CompletionEvidence = 类型化完成事实:**session 迁移到 completed 当且仅当存在
一条 trusted CompletionEvidence;它只能来源于学生本轮消息经确定性 verifier
判定**——LLM 输出/summary/guard 事件/教师转述的学生话都无构造权(设计 §二
不可构造面)。A 段只交付数据结构与六窄面判定函数,**不接 Kernel、不接
generation、不改任何现有模块行为**(§九:B/C 段另开 PR)。

复合题红线(§三审查修正②):多空/复合题**整体不判定**——answer_type 不在
六窄面(如 composite/open)调度即 None;numeric/short_text 的 ground_truth
含 ≥2 个数字 token 也按多槽拒判(「鸡3只兔5只」任何局部槽命中不构造
evidence,未来部分进度另建 ProgressEvidence,不偷「半完成态」)。

fail-closed 姿态贯穿:问句猜答(疑问标记/语气词)不构成证据(与 numeric
._declarative 同口径:问句里的数字不算已述,混合消息整条按问句处理);
命中后紧跟自我否定(「…不对」「…错了」)不构成证据;单位省略仅当题面
schema 显式 optional(审查修正③),同义单位仅维度安全换算、无默认容差。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from .answer_normalizer import (
    equation_candidates,
    halfwidth,
    number_tokens,
    symbol_key,
    text_key,
    unit_scale,
    units_compatible,
)

# 设计 §二三:判定所用窄面。复合/开放式不在其内(整体 needs_review,
# 宁可 needs_review 不让 8B 猜完成态);~67% answer-key 形态可判是
# eligibility upper bound,非运行时完成覆盖率。
ANSWER_TYPES = (
    "numeric_with_unit",
    "choice_letter",
    "true_false",
    "equation_form",
    "ratio_or_expression",
    "short_text_exact",
)

# 问句/犹疑标记(消息级 fail-closed):「是不是25.8度?」「25.8度对吗」「对吧」
# 都不构成证据。口径对齐 numeric._declarative(问句猜答≠已述)+ ER judge
# 的疑问尾词族(吗/呢/什么/多少/哪/怎么/为什么),另收 吧/对不对/是不是。
_QUESTION_MARKERS = ("?", "吗", "呢", "吧", "对不对", "是不是", "是多少",
                     "多少", "什么", "怎么", "为什么", "哪")

# 命中段之后的自我否定/犹疑(剥掉紧邻标点空白后起算):「x-21=35不对」。
_RETRACT_AFTER = ("不对", "不成立", "错了", "错的", "不是", "并不")

_TRUE_RE = re.compile(r"(?<![不没非])对(?![不起吗吧呢])|正确|没错|√|✓|对的|对了")
_FALSE_RE = re.compile(r"不对|不正确|错误|错了|错的|✗|✘|×|(?<![不没])错")
_LETTER_RE = re.compile(r"(?<![A-Za-z])([A-Za-z])(?![A-Za-z])")


@dataclass(frozen=True)
class AnswerSpec:
    """题库 answer 的判定规格(ground_truth 的结构化形态,A 段由调用方组装)。

    answer_type 必须是 ANSWER_TYPES 之一;复合/开放题不造本规格(调度即
    None)。aliases 是**题库显式**声明的同义答案(short_text_exact 专用,
    不扩病例短语表,终裁红线)。unit_optional 是题面 schema 对单位省略的
    显式授权(默认 False:单位不可省)。letter_choices 是题面选项字母表
    (choice_letter 的合法集)。"""

    answer_type: str
    ground_truth: str
    aliases: tuple[str, ...] = ()
    unit_optional: bool = False
    letter_choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceProvenance:
    """证据溯源:指向题库 answer/answer schema(非病例短语)+ 命中原文。"""

    ground_truth_ref: str                  # 题库 answer 原文(判定基准,可追溯)
    matched_span: str                      # 学生消息中命中的原文片段(审计凭证)
    normalization: tuple[str, ...] = ()    # 施加的归一(如千分位/分数形态);空=原样


@dataclass(frozen=True)
class CompletionEvidence:
    """学生本轮消息经确定性 verifier 命中的完成事实(类型化,设计 §二)。

    **生命周期:turn-scoped / ephemeral**——evidence 只对当前 student turn
    生成、当轮消费、跨轮不复用:上一轮已验证的答案在下一轮确认时**不构成**
    证据,该轮需重新命中(§二 v1 显式设计选择,保守口径)。

    不可构造面(运行时红线):source 恒为 "student"、verdict 恒为
    "matched"、answer_type 必须在六窄面内——LLM 输出/summary/guard 事件/
    教师转述均不得构造本类型(A 段以构造期校验钉死,B 段接线时消费侧只认
    verify_completion 产物)。"""

    source: str
    turn_id: int
    answer_type: str
    verdict: str
    verifier: str
    provenance: EvidenceProvenance

    def __post_init__(self) -> None:
        if self.source != "student":
            raise ValueError("CompletionEvidence.source 恒为 student(设计 §二不可构造面)")
        if self.verdict != "matched":
            raise ValueError("CompletionEvidence.verdict 恒为 matched(未匹配即无证据)")
        if self.answer_type not in ANSWER_TYPES:
            raise ValueError(f"CompletionEvidence.answer_type 必须是六窄面之一:{ANSWER_TYPES}")


def _is_question(message: str) -> bool:
    """问句/犹疑消息判定(消息级 fail-closed):末尾问号或含疑问标记。"""
    mapped = halfwidth(message).rstrip()
    return mapped.endswith("?") or any(m in mapped for m in _QUESTION_MARKERS)


def _retracted(message: str, end: int) -> bool:
    """命中段止位之后紧跟自我否定(剥标点空白后):「25.8度,不对」。"""
    tail = re.sub(r"^[\s,，。、;；:：!！?？]+", "", str(message)[end:])
    return bool(tail) and (tail[:2] in _RETRACT_AFTER or tail[0] in "吗吧呢")


def _single_number(ground_truth: str) -> tuple[str, Fraction, str] | None:
    """ground_truth 恰含一个数字 token 时返回(原文形态, 等价类值, 单位);
    0 个=非本窄面,≥2 个=多槽复合(红线:整体不判定),都返回 None。"""
    tokens = [t for t in number_tokens(ground_truth) if t[3] is not None]
    if len(tokens) != 1:
        return None
    span, _start, _end, value, unit, _tags = tokens[0]
    return span, value, unit


def _unit_value_match(truth_unit: str, truth_value: Fraction, unit_optional: bool,
                      value: Fraction, unit: str) -> bool:
    """数值+单位判定:学生带单位 → token 相等或同族维度安全换算(零容差);
    单位省略 → 仅 schema 显式 optional 且数值与题面**原值同口径**相等
    (「2千米」的省略形态是 2,不是 2000——省略不换算,审查修正③)。"""
    if unit:
        return (units_compatible(truth_unit, unit)
                and value * unit_scale(unit) == truth_value * unit_scale(truth_unit))
    if truth_unit and not unit_optional:
        return False
    return value == truth_value


def _numeric_tags(span: str, truth_span: str, tags: list[str],
                  unit: str, truth_unit: str) -> tuple[str, ...]:
    """归一标签:原样命中=空;否则记学生侧数字归一 + 单位判定面。"""
    if span == truth_span:
        return ()
    applied = list(tags)
    if unit and unit != truth_unit:
        applied.append("单位同义换算")
    if not unit and truth_unit:
        applied.append("单位省略(schema授权)")
    return tuple(applied)


def _verify_numeric_with_unit(spec: AnswerSpec, message: str) -> tuple[str, tuple[str, ...]] | None:
    """数值+单位窄面:数字等价类归一(千分位/分数/小数/百分号,零容差)+
    单位判定(相等,或同族维度安全换算;省略仅 schema 显式 optional)。"""
    truth = _single_number(spec.ground_truth)
    if truth is None:
        return None
    truth_span, truth_value, truth_unit = truth
    for span, _start, end, value, unit, tags in number_tokens(message):
        if value is None or not _unit_value_match(
                truth_unit, truth_value, spec.unit_optional, value, unit):
            continue
        if _retracted(message, end):
            continue                      # 「25.8度,不对」:自我否定不构成证据
        return span, _numeric_tags(span, truth_span, tags, unit, truth_unit)
    return None


def _verify_choice_letter(spec: AnswerSpec, message: str) -> tuple[str, tuple[str, ...]] | None:
    """选项字母窄面:字母精确匹配(大小写敏感),合法集=题面选项字母表。"""
    letters = [a for a in halfwidth(spec.ground_truth) if a.isascii() and a.isalpha()]
    if len(letters) != 1:
        return None                       # 非单字母答案:不属本窄面(fail-closed)
    truth_letter = letters[0]
    if spec.letter_choices and truth_letter not in spec.letter_choices:
        return None                       # 答案字母不在题面选项字母表内
    for match in _LETTER_RE.finditer(halfwidth(message)):
        if match.group(1) != truth_letter:
            continue                      # 大小写敏感:小写不是精确匹配
        if _retracted(message, match.end()):
            continue
        span = message[match.start():match.end()]
        tags = ("全半角",) if any(0xFF01 <= ord(c) <= 0xFF5E for c in span) else ()
        return span, tags
    return None


def _true_false_value(text: str) -> bool | None:
    """对/错/√/× 映射:先认否定形(不对/不正确含「对」「正确」字面)。"""
    if _FALSE_RE.search(text):
        return False
    if _TRUE_RE.search(text):
        return True
    return None


def _verify_true_false(spec: AnswerSpec, message: str) -> tuple[str, tuple[str, ...]] | None:
    """判断窄面(题面含「判断」字样):对/错/√/× 映射,否定形先判。"""
    truth = _true_false_value(spec.ground_truth)
    if truth is None:
        return None
    matched = _FALSE_RE.search(message) if not truth else _TRUE_RE.search(message)
    if matched is None:
        return None
    if _retracted(message, matched.end()):
        return None
    return matched.group(0), ()


def _verify_symbolic(spec: AnswerSpec, message: str) -> tuple[str, tuple[str, ...]] | None:
    """equation_form / ratio_or_expression 共用:符号归一后整段字符串等价。

    ×/·→`*`(独立乘法 token,绝不与变量 x 合并);=/＝→==;÷→/;剥空白。
    「3×4=12」与「3x4=12」**不相等**——x 是变量不是乘号(审查修正①)。"""
    truth_key = symbol_key(spec.ground_truth)
    if not truth_key:
        return None
    for span, _start, end in equation_candidates(message):
        if symbol_key(span) != truth_key:
            continue
        if _retracted(message, end):
            continue                      # 「x-21=35不对,应该是…」:已撤回
        tags = () if symbol_key(span) == span else ("符号归一",)
        return span, tags
    return None


def _verify_short_text_exact(spec: AnswerSpec, message: str) -> tuple[str, tuple[str, ...]] | None:
    """短文本窄面:normalized **whole-answer** exact / 题库显式 alias。

    仅无语义归一(全半角/空白/标点);命中必须是消息末段的完整答案断言
    (居中出现=裸 substring,不判);命中前 2 字窗口含 不/没/非/未 = 否定
    (「不是易变形」不得因包含「易变形」命中,审查修正④)。ground_truth
    含 ≥2 数字 token = 多槽复合,整体不判定(红线)。"""
    if len([t for t in number_tokens(spec.ground_truth) if t[3] is not None]) >= 2:
        return None
    key_message, spans = text_key(message)
    for candidate in (spec.ground_truth, *spec.aliases):
        key_candidate, _ = text_key(candidate)
        if not key_candidate or not key_message.endswith(key_candidate):
            continue
        start = len(key_message) - len(key_candidate)
        # 左边界:句首或断言系词(是/为)——「容易变形」不得经后缀包含命中
        # 「易变形」,变体只能走题库显式 alias(whole-answer,非裸 substring)。
        boundary = key_message[start - 1] if start else ""
        if boundary and boundary not in "是为":
            continue
        # 否定窗口:命中前 2 字含 不/没/非/未(「不是易变形」「并非易变形」)。
        if any(n in key_message[max(0, start - 2):start] for n in "不没非未"):
            continue
        begin, last = spans[start][0], spans[-1][1]
        span = str(message)[begin:last]
        tags: list[str] = []
        if any(0xFF01 <= ord(c) <= 0xFF5E for c in span):
            tags.append("全半角")
        if len(span) != len(key_candidate):
            tags.append("剥空白标点")     # 命中段内剥过空白/标点
        return span, tuple(tags)
    return None


_VERIFIERS = {
    "numeric_with_unit": _verify_numeric_with_unit,
    "choice_letter": _verify_choice_letter,
    "true_false": _verify_true_false,
    "equation_form": _verify_symbolic,
    "ratio_or_expression": _verify_symbolic,
    "short_text_exact": _verify_short_text_exact,
}


def verify_completion(spec: AnswerSpec, student_message: str | None,
                      turn_id: int) -> CompletionEvidence | None:
    """六窄面调度:命中返回 CompletionEvidence,否则 None(整体不判定)。

    turn-scoped:只判 student_message(本轮学生原文)——上一轮的证据不进
    本轮,跨轮不复用(§二);turn_id 标记证据归属轮。复合/开放/未知
    answer_type、空消息、问句猜答一律 None(fail-closed,B 段 Kernel 据此
    拒 completed 迁移)。A 段零接线:本函数无调用方,行为变化为零。"""
    if spec.answer_type not in _VERIFIERS:
        return None                       # 复合/开放/未知窄面:整体 needs_review
    message = str(student_message or "")
    if not message.strip() or not spec.ground_truth.strip() or _is_question(message):
        return None
    hit = _VERIFIERS[spec.answer_type](spec, message)
    if hit is None:
        return None
    span, tags = hit
    return CompletionEvidence(
        source="student",
        turn_id=turn_id,
        answer_type=spec.answer_type,
        verdict="matched",
        verifier=spec.answer_type,
        provenance=EvidenceProvenance(
            ground_truth_ref=spec.ground_truth, matched_span=span, normalization=tags),
    )
