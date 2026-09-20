"""小讲师(00 §1):内核三函数(M2,00 §5.1)+ 护栏代码与提示词资产(#45)。"""

from .format_guard import FormatGuardResult, evaluate_student_visible_format
from .guardrails import (
    StudentVisibleGuardrailEvaluation,
    StudentVisibleGuardrailFinding,
    evaluate_student_visible_question,
)
# 信号匹配器随包公开:judge 与 B 线测试/匹配器统一口径(02 §6 测试禁私有导入),
# 名下划线是历史成形,judge.py/analyze.py 早已按此消费。
# kernel 段增补(#350):属性测试要直连的确定性私有件随包公开,同款先例见上
# (02 §6 测试禁私有导入,零行为变更纯导出面)。
from .kernel import (
    NEEDS_REVIEW_TEXT,
    SAFE_FALLBACK_TEXT,
    TUTOR_TURN_SCHEMA,
    _STEP_LEADS,
    _UNTRUSTED_LADDER_HINT,
    PURE_BLOCK,
    _answer_leak_span,
    _reveal_stuck_hint,
    _student_signals_stuck,
    finish,
    reply,
    set_ablation_arm,
    start,
)
from .ablation import set_phase2_off  # 二阶段 LOO 词汇表(评测/测试公开入口)
# numeric 确定性纯函数随包公开(#350 属性测试直连;口径归属见 numeric.py 模块头):
# _question_numbers/_spoken_numbers/_reply_numbers/_arithmetic_results/_usable_numbers/
# _answer_numbers/_answer_focus_numbers/_drift_sources——纯函数族,零行为变更。
from .numeric import (
    _answer_focus_numbers,
    _answer_numbers,
    _arithmetic_results,
    _drift_sources,
    _question_numbers,
    _reply_numbers,
    mask_numbers,
    _spoken_numbers,
    _usable_numbers,
)
from .prompting import (
    FIRST_QUESTION_COLLECT,
    FIRST_QUESTION_COLLECT_IMAGE,
    FIRST_QUESTION_CORRECT,
    HEAD_IMAGE,
    HEAD_TEXT,
    OPENING_HINT_CORRECT,
    OPENING_HINT_INCORRECT,
    OPENING_HINT_UNANSWERED,
    TAIL_COLLECT,
    TAIL_CORRECT,
    first_question_text,
    grade_grounding,
    opening_hint,
    style_directives,
    summary_system_prompt,
    system_prompt,
)
from .session import (
    LearnerSession,
    SessionVersionConflict,
    Summary,
    TerminalStateError,
    Turn,
)
from .tone_guardrails import ToneGuardrailResult, apply_tone_guardrail

__all__ = [
    "FIRST_QUESTION_COLLECT",
    "FIRST_QUESTION_COLLECT_IMAGE",
    "FIRST_QUESTION_CORRECT",
    "FormatGuardResult",
    "HEAD_IMAGE",
    "HEAD_TEXT",
    "OPENING_HINT_CORRECT",
    "OPENING_HINT_INCORRECT",
    "OPENING_HINT_UNANSWERED",
    "LearnerSession",
    "SAFE_FALLBACK_TEXT",
    "SessionVersionConflict",
    "StudentVisibleGuardrailEvaluation",
    "StudentVisibleGuardrailFinding",
    "Summary",
    "TAIL_COLLECT",
    "TAIL_CORRECT",
    "TerminalStateError",
    "ToneGuardrailResult",
    "TUTOR_TURN_SCHEMA",
    "Turn",
    "_STEP_LEADS",
    "_UNTRUSTED_LADDER_HINT",
    "_answer_focus_numbers",
    "NEEDS_REVIEW_TEXT",
    "PURE_BLOCK",
    "_answer_leak_span",
    "_answer_numbers",
    "_arithmetic_results",
    "_drift_sources",
    "_question_numbers",
    "_reply_numbers",
    "_reveal_stuck_hint",
    "_spoken_numbers",
    "_student_signals_stuck",
    "_usable_numbers",
    "mask_numbers",
    "apply_tone_guardrail",
    "evaluate_student_visible_format",
    "evaluate_student_visible_question",
    "finish",
    "first_question_text",
    "grade_grounding",
    "opening_hint",
    "reply",
    "set_ablation_arm", "set_phase2_off",
    "start",
    "style_directives",
    "summary_system_prompt",
    "system_prompt",
]
