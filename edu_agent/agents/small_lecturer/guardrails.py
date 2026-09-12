"""学生可见对话护栏(00 §6 自老仓库 learning_dialogue/guardrails.py 移植,v8 口径原样)。

证据接地的窄判定:答案形状的语言本身不拦截,只有候选值确实包含权威答案
(或复制受保护解析片段)时才 fallback——普通苏格拉底问句不进策略路径,
反泄露边界窄且可审计。老仓库的 apply_guardrails 耦合 TeachingDecision
(引擎装配),按 00 §6「实现耦合的不迁」未随行;M2 内核按新接口重组。

**本模块不含「未经验证的源值披露/答案断言」判据**(#184):句级近似判据(候选值/
方向词与参考源比对)是与内核数字归因并行的**第二套判据**,且有参考答案时恒不可达
→ 泄露系统性漏放。该判据的唯一实现在 `kernel._guard_check`(数字级归因
`_drift_sources` + `answer_pool`,命中即走既有修复漏斗),本模块不再重复实现。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal, Sequence

STUDENT_VISIBLE_GUARDRAIL_POLICY_VERSION = "small_lecturer_visible_guardrail/v8"
GuardrailAction = Literal["ALLOW", "REPAIR", "FALLBACK"]


@dataclass(frozen=True, slots=True)
class StudentVisibleGuardrailFinding:
    rule_id: str
    finding: str
    action: GuardrailAction
    repair_strategy: str = ""


@dataclass(frozen=True, slots=True)
class StudentVisibleGuardrailEvaluation:
    text: str
    findings: tuple[StudentVisibleGuardrailFinding, ...]

    @property
    def action(self) -> GuardrailAction:
        rank: dict[GuardrailAction, int] = {"ALLOW": 0, "REPAIR": 1, "FALLBACK": 2}
        return max(
            (item.action for item in self.findings),
            key=rank.__getitem__,
            default="ALLOW",
        )

    @property
    def fallback_required(self) -> bool:
        return self.action == "FALLBACK"

    @property
    def repaired(self) -> bool:
        return self.action == "REPAIR"


_ANSWER_ASSERTION_CUE = re.compile(
    r"(?:答案|结果|结论|正确选项|应选|最终|就是|即为|等于|应该|应当|未知数|=)",
    re.I,
)
_ORDERED_SOLUTION_CUES = re.compile(
    r"(?:先|首先).{0,80}(?:再|然后|接着|最后).{0,80}"
    r"(?:列式|计算|代入|求出|得到|得出|答案|结果)",
    re.I,
)
_REFERENCE_PREFIX = re.compile(
    r"^(?:参考)?(?:正确)?(?:答案|结果|结论|选项)\s*(?:是|为|：|:|=)?\s*",
    re.I,
)


def evaluate_student_visible_question(
    reply: str,
    *,
    answer_reference: str = "",
    active_subquestion_text: str = "",
    analysis_reference: str = "",
    student_evidence: Sequence[str] = (),
    allow_solution_output: bool = False,
) -> StudentVisibleGuardrailEvaluation:
    """Evaluate only facts that the runtime can verify deterministically.

    Answer-shaped language is not a blocker by itself. It becomes a fallback only
    when the candidate actually contains the authoritative answer (or copies a
    protected analysis span). This keeps ordinary Socratic questions out of the
    policy path while retaining a narrow, auditable anti-leak boundary.

    **不在本模块判定「未经验证的源值披露」**(#184):句级近似判据(取值/方向词
    与参考源比对)已删除——它是与内核数字归因(`_drift_sources` + `answer_pool`)
    并行的第二套判据,且有参考答案时恒不可达(泄露系统性漏放)。该判据的唯一实现
    在内核 `_guard_check`(整数级抽取 + 来源标签池),命中即走同一修复漏斗。
    """

    normalized = reply.strip()
    findings: list[StudentVisibleGuardrailFinding] = []

    answer_present = _contains_authoritative_answer(normalized, answer_reference)
    answer_asserted = bool(_ANSWER_ASSERTION_CUE.search(normalized))
    answer_already_stated_by_student = any(
        _contains_authoritative_answer(item, answer_reference)
        for item in student_evidence
    )
    solution_path_already_stated_by_student = any(
        _contains_long_protected_overlap(item, analysis_reference)
        for item in student_evidence
    )
    if not allow_solution_output and answer_present and answer_asserted:
        if not answer_already_stated_by_student:
            findings.append(
                StudentVisibleGuardrailFinding(
                    rule_id="grounded_answer_disclosure",
                    finding="grounded_answer_disclosure",
                    action="FALLBACK",
                    repair_strategy="authoritative_subquestion_fallback",
                )
            )
        if (
            _ORDERED_SOLUTION_CUES.search(normalized)
            and not solution_path_already_stated_by_student
        ):
            findings.append(
                StudentVisibleGuardrailFinding(
                    rule_id="grounded_solution_path_disclosure",
                    finding="grounded_solution_path_disclosure",
                    action="FALLBACK",
                    repair_strategy="authoritative_subquestion_fallback",
                )
            )
    if (
        not allow_solution_output
        and analysis_reference.strip()
        and _ORDERED_SOLUTION_CUES.search(normalized)
        and _contains_long_protected_overlap(normalized, analysis_reference)
        and not solution_path_already_stated_by_student
        and not any(
            item.finding == "grounded_solution_path_disclosure"
            for item in findings
        )
    ):
        findings.append(
            StudentVisibleGuardrailFinding(
                rule_id="grounded_solution_path_disclosure",
                finding="grounded_solution_path_disclosure",
                action="FALLBACK",
                repair_strategy="authoritative_subquestion_fallback",
            )
        )

    return StudentVisibleGuardrailEvaluation(
        text=normalized,
        findings=tuple(findings),
    )


def _contains_authoritative_answer(reply: str, answer_reference: str) -> bool:
    reply_compact = _compact_for_grounding(reply)
    if not reply_compact:
        return False
    return any(
        _reference_occurs(reply, reply_compact, candidate)
        for candidate in _answer_reference_candidates(answer_reference)
    )


def _answer_reference_candidates(answer_reference: str) -> tuple[str, ...]:
    raw = unicodedata.normalize("NFKC", answer_reference).strip()
    if not raw:
        return ()
    candidates: list[str] = [raw]
    for part in re.split(r"[\n；;。]", raw):
        stripped = _REFERENCE_PREFIX.sub("", part.strip()).strip()
        if stripped:
            candidates.append(stripped)
    compact_candidates = {
        compact
        for candidate in candidates
        if (compact := _compact_for_grounding(candidate))
    }
    return tuple(sorted(compact_candidates, key=len, reverse=True))


def _reference_occurs(reply: str, reply_compact: str, reference_compact: str) -> bool:
    if not reference_compact:
        return False
    if re.fullmatch(r"[a-d]", reference_compact, re.I):
        normalized_reply = unicodedata.normalize("NFKC", reply)
        return bool(
            re.search(
                rf"(?<![A-Za-z]){re.escape(reference_compact)}(?:项)?(?![A-Za-z])",
                normalized_reply,
                re.I,
            )
        )
    return reference_compact in reply_compact


def _contains_long_protected_overlap(reply: str, analysis_reference: str) -> bool:
    reply_compact = _compact_for_grounding(reply)
    reference_compact = _compact_for_grounding(analysis_reference)
    window_size = 18
    if len(reply_compact) < window_size or len(reference_compact) < window_size:
        return False
    return any(
        reference_compact[index : index + window_size] in reply_compact
        for index in range(0, len(reference_compact) - window_size + 1, 7)
    )


def _compact_for_grounding(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum() or character in "=+-*/.%")
