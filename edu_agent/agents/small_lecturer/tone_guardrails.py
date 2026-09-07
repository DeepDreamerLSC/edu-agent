"""Deterministic hard safety checks for the user-visible tutor expression.

00 §6 资产迁移:自老仓库 learning_dialogue/tone_guardrails.py 原样迁入(零依赖纯函数);
老测试中耦合 DB/agent 装配的部分未随行(实现耦合不迁),纯护栏断言见 tests/teaching/。
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

GradeBand = Literal["primary_lower", "primary_upper", "junior_middle", "neutral"]
InteractionSignal = Literal[
    "neutral",
    "requesting_support",
    "requesting_direct_answer",
    "frustrated",
    "stopping",
]


@dataclass(frozen=True)
class ToneGuardrailResult:
    reply: str
    applied: bool
    reason_codes: tuple[str, ...]


_HUMILIATION_PATTERNS = (
    re.compile(r"(?:这么|那么|这点|这种)?简单(?:的题)?(?:你)?都不会"),
    re.compile(r"(?:你)?怎么(?:会|还)?这么笨"),
    re.compile(r"(?:你(?:真|太|好)?笨|真笨|太笨了?)(?:啊|呀|了|！|!|。|$)"),
    re.compile(r"(?:你)?(?:没救了|真没用|太差劲了|可笑)"),
)
_BLAME_PATTERNS = (
    re.compile(r"你(?:就是|总是|怎么老是)(?:不认真|太粗心|不动脑|没听讲)"),
    re.compile(r"(?:都是|就是)你(?:不认真|粗心|不动脑)(?:造成|导致|的问题)?"),
)
_INTERROGATION_PATTERNS = (
    re.compile(r"你到底(?:会不会|懂不懂|有没有听)"),
    re.compile(r"我(?:不是|都)(?:已经)?说过(?:多少次|了)"),
    re.compile(r"(?:还|又)错[了]?[，,。！! ]*(?:怎么|为什么)(?:还|又)"),
)
_FRUSTRATION_DISMISSAL_PATTERNS = (
    re.compile(r"(?:别|不要)(?:矫情|抱怨|找借口)"),
    re.compile(r"这有什么(?:好)?难的"),
    re.compile(r"(?:不许|别再)说不会"),
)
_JUNIOR_AGE_MISMATCH_PATTERNS = (
    re.compile(
        r"(?:^|[，,。！？!?])(?:小朋友|(?:小)?宝宝|乖乖)"
        r"(?:[，,。！？!?]|你|先|再)"
    ),
    re.compile(r"(?:棒棒哒|真乖)(?:[，,！!。]|$)"),
)


def apply_tone_guardrail(
    *,
    reply: str,
    grade_band: GradeBand,
    interaction_signal: InteractionSignal,
    teaching_move: str,
    ready_to_record: bool,
) -> ToneGuardrailResult:
    """Detect severe tone risks without rewriting Tutor pedagogy."""

    del teaching_move, ready_to_record

    normalized = " ".join(reply.split())
    reasons: list[str] = []
    if _matches_any(normalized, _HUMILIATION_PATTERNS):
        reasons.append("tone_humiliation_or_sarcasm")
    if _matches_any(normalized, _BLAME_PATTERNS):
        reasons.append("tone_blame_or_personality_label")
    if _matches_any(normalized, _INTERROGATION_PATTERNS):
        reasons.append("tone_interrogation_or_repeated_negation")
    if (
        interaction_signal == "frustrated"
        and _matches_any(normalized, _FRUSTRATION_DISMISSAL_PATTERNS)
    ):
        reasons.append("tone_ignored_student_frustration")
    if (
        grade_band == "junior_middle"
        and _matches_any(normalized, _JUNIOR_AGE_MISMATCH_PATTERNS)
    ):
        reasons.append("tone_severe_age_mismatch")
    if not reasons:
        return ToneGuardrailResult(reply=reply, applied=False, reason_codes=())
    return ToneGuardrailResult(
        reply=reply,
        applied=True,
        reason_codes=tuple(dict.fromkeys(reasons)),
    )


def _matches_any(value: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(value) for pattern in patterns)
