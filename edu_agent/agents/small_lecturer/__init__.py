"""小讲师(00 §1):内核三函数(M2,00 §5.1)+ 护栏代码与提示词资产(#45)。"""

# completion(Gate A 段)确定性面随包公开(同 #350 先例:02 §6 测试禁私有
# 导入,零行为变更纯导出面;B 段起 kernel 接线消费,verifier 规格本体不动)。
from .completion import (
    ANSWER_TYPES,
    AnswerSpec,
    CompletionEvidence,
    EvidenceProvenance,
    verify_completion,
)
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
    _analysis_steps,  # B′(#441):oracle 切片漂移哨兵直连(生产切梯口径)
    _answer_leak_span,
    _answer_spec,  # Gate B 段:组装方契约 fail-closed 面测试直连(零行为变更纯导出)
    _completion_authorized,  # Gate B 段:turn-scoped 门判据测试直连(同上)
    _current_step_anchor_numbers,  # B′(#441):census before 面(七条件门)测试直连
    _is_repeat,  # #382 PR-D:事故回归电池直连(复读判定口径钉;零行为变化纯导出)
    _reveal_stuck_hint,
    _student_signals_stuck,
    finish,
    reply,
    start,
)
# numeric 确定性纯函数随包公开(#350 属性测试直连;口径归属见 numeric.py 模块头):
# _question_numbers/_spoken_numbers/_reply_numbers/_arithmetic_results/_usable_numbers/
# _answer_numbers/_answer_focus_numbers/_drift_sources——纯函数族,零行为变更。
# B′(#441):result_evidence/ResultEvidence(result-assertion proof,纯函数)同款直连。
from .numeric import (
    ResultEvidence,
    _answer_focus_numbers,
    _answer_numbers,
    _arithmetic_results,
    _drift_sources,
    _question_numbers,
    _reply_numbers,
    result_evidence,
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
    "ANSWER_TYPES",
    "AnswerSpec",
    "CompletionEvidence",
    "EvidenceProvenance",
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
    "ResultEvidence",
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
    "_analysis_steps",
    "_answer_focus_numbers",
    "_answer_spec",
    "_completion_authorized",
    "_current_step_anchor_numbers",
    "NEEDS_REVIEW_TEXT",
    "PURE_BLOCK",
    "_answer_leak_span",
    "_answer_numbers",
    "_arithmetic_results",
    "_drift_sources",
    "_is_repeat",
    "_question_numbers",
    "_reply_numbers",
    "_reveal_stuck_hint",
    "_spoken_numbers",
    "_student_signals_stuck",
    "_usable_numbers",
    "mask_numbers",
    "result_evidence",
    "apply_tone_guardrail",
    "evaluate_student_visible_format",
    "evaluate_student_visible_question",
    "finish",
    "first_question_text",
    "grade_grounding",
    "opening_hint",
    "reply",
    "start",
    "style_directives",
    "summary_system_prompt",
    "system_prompt",
    "verify_completion",
]
