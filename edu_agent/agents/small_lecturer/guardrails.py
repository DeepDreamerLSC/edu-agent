"""学生可见对话护栏(00 §6 自老仓库 learning_dialogue/guardrails.py 移植,v8 口径原样)。

证据接地的窄判定:答案形状的语言本身不拦截,只有候选值确实包含权威答案
(或复制受保护解析片段)时才 fallback——普通苏格拉底问句不进策略路径,
反泄露边界窄且可审计。老仓库的 apply_guardrails 耦合 TeachingDecision
(引擎装配),按 00 §6「实现耦合的不迁」未随行;M2 内核按新接口重组。
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
_ANSWER_SUBJECT_PROPOSITION = re.compile(
    r"(?:答案|结果|结论|正确选项|应选项|最终答案|未知数(?:的值)?)"
    r"\s*(?:应该|应当)?\s*(?:就是|即为|等于|是|为|：|:|=)\s*"
    r"(?P<candidate>[^，。；;！？?]{1,48})",
    re.I,
)
_ANSWER_OBJECT_PROPOSITION = re.compile(
    r"(?P<candidate>[^，。；;！？?]{1,48}?)\s*"
    r"(?:就是|即为|是|为)\s*(?:答案|结果|结论|正确选项|最终答案)",
    re.I,
)
_CONFIRMATION_SUFFIX = re.compile(
    r"(?:对吗|是吗|没错吧|正确吗)[？?]?\s*$",
    re.I,
)
_CANDIDATE_VALUE_CUE = re.compile(
    r"(?:[东南西北](?:偏[东南西北])?方向|东北|东南|西北|西南|"
    r"(?:选项|选择|应选)\s*[A-HＡ-Ｈ]|"
    r"(?<![A-Za-z])[A-HＡ-Ｈ](?![A-Za-z])|"
    r"[-+]?\d+(?:\.\d+)?\s*(?:米|千米|厘米|毫米|元|角|分|个|只|本|人|"
    r"千克|克|吨|秒|分钟|小时|度|°|%|％)|"
    r"[A-Za-z]?\s*=\s*[-+]?\d|"
    r"正比例|反比例|平行|垂直|相等|不相等|倍数关系|和差关系)",
    re.I,
)
_QUESTION_FACT_ATTRIBUTION = re.compile(
    r"(?:题目|题干|图中|表中)\s*(?:说|给出|写着|标明|显示)|已知",
    re.I,
)
_INTERROGATIVE_CANDIDATE = re.compile(
    r"^(?:什么|多少|哪(?:个|一项|种)|怎么|如何|为什么|根据(?:哪个|什么)|"
    r"从哪|由什么|是否|是不是|能否|(?:不(?:是)?|否)(?:满足|符合|成立))",
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
_UNVERIFIED_CORRECTION_CUE = re.compile(
    r"(?:不是|不对|答错|错误|正确|应该|应当|再看|重新|改成|而是)",
    re.I,
)
_SOURCE_VALUE_TOKEN = re.compile(
    r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?(?:°|度|%|％)?(?![A-Za-z0-9])"
)
_SOURCE_DIRECTION_TOKEN = re.compile(r"[东南西北]偏[东南西北]")


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
    elif not answer_reference.strip():
        if _discloses_new_unverified_source_value(
            normalized,
            active_subquestion_text=active_subquestion_text,
            student_evidence=student_evidence,
        ):
            findings.append(
                StudentVisibleGuardrailFinding(
                    rule_id="unverified_source_value_disclosure",
                    finding="unverified_source_value_disclosure",
                    action="FALLBACK",
                    repair_strategy="authoritative_subquestion_fallback",
                )
            )
        elif not allow_solution_output and _is_unverified_answer_assertion(
            normalized,
            active_subquestion_text=active_subquestion_text,
            student_evidence=student_evidence,
        ):
            findings.append(
                StudentVisibleGuardrailFinding(
                    rule_id="unverified_answer_assertion",
                    finding="unverified_answer_assertion",
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


def _is_unverified_answer_assertion(
    reply: str,
    *,
    active_subquestion_text: str,
    student_evidence: Sequence[str],
) -> bool:
    """Separate a proposed answer from a question about forming an answer.

    The guardrail intentionally does not infer correctness. It only detects a
    concrete candidate answer that the Tutor is asserting or asking the learner
    to confirm. Questions that ask how to obtain an unspecified answer remain
    ordinary Socratic prompts.
    """

    candidates = _answer_claim_candidates(reply)
    asserted = bool(candidates)
    if not asserted and _CONFIRMATION_SUFFIX.search(reply):
        asserted = bool(_CANDIDATE_VALUE_CUE.search(reply))
        if asserted:
            candidates = _concrete_candidate_tokens(reply)
    if not asserted:
        return False

    evidence_text = "\n".join(student_evidence)
    if _candidate_occurs_in_source(candidates, evidence_text):
        return False
    if (
        _QUESTION_FACT_ATTRIBUTION.search(reply)
        and _candidate_occurs_in_source(candidates, active_subquestion_text)
    ):
        return False
    return True


def _answer_claim_candidates(reply: str) -> tuple[str, ...]:
    candidates = [
        match.group("candidate")
        for pattern in (
            _ANSWER_SUBJECT_PROPOSITION,
            _ANSWER_OBJECT_PROPOSITION,
        )
        for match in pattern.finditer(reply)
    ]
    return tuple(
        candidate.strip(" ，,:：。；;！？?")
        for candidate in candidates
        if candidate.strip(" ，,:：。；;！？?")
        and not _INTERROGATIVE_CANDIDATE.search(
            candidate.strip(" ，,:：。；;！？?")
        )
    )


def _concrete_candidate_tokens(text: str) -> tuple[str, ...]:
    return tuple(
        match.group(0).strip()
        for match in _CANDIDATE_VALUE_CUE.finditer(text)
        if match.group(0).strip()
    )


def _candidate_occurs_in_source(
    candidates: Sequence[str],
    source: str,
) -> bool:
    source_compact = _compact_for_grounding(source)
    if not source_compact:
        return False
    return any(
        candidate_compact
        and candidate_compact in source_compact
        for candidate in candidates
        if (candidate_compact := _compact_for_grounding(candidate))
    )


def _contains_authoritative_answer(reply: str, answer_reference: str) -> bool:
    reply_compact = _compact_for_grounding(reply)
    if not reply_compact:
        return False
    return any(
        _reference_occurs(reply, reply_compact, candidate)
        for candidate in _answer_reference_candidates(answer_reference)
    )


def _discloses_new_unverified_source_value(
    reply: str,
    *,
    active_subquestion_text: str,
    student_evidence: Sequence[str],
) -> bool:
    """Reject new answer-shaped values copied from an unverified source."""

    source_directions = _source_direction_tokens(active_subquestion_text)
    reply_directions = _source_direction_tokens(reply)
    student_directions = {
        token
        for evidence in student_evidence
        for token in _source_direction_tokens(evidence)
    }
    if (source_directions & reply_directions) - student_directions:
        return True
    if not _UNVERIFIED_CORRECTION_CUE.search(reply):
        return False
    source_values = _source_value_tokens(active_subquestion_text)
    reply_values = _source_value_tokens(reply)
    student_values = {
        token
        for evidence in student_evidence
        for token in _source_value_tokens(evidence)
    }
    return bool((source_values & reply_values) - student_values)


def _normalize_source_value_token(value: str) -> str:
    return _compact_for_grounding(value.replace("度", "°"))


def _source_value_tokens(value: str) -> set[str]:
    return {
        _normalize_source_value_token(item)
        for item in _SOURCE_VALUE_TOKEN.findall(value)
    }


def _source_direction_tokens(value: str) -> set[str]:
    return {
        _compact_for_grounding(item)
        for item in _SOURCE_DIRECTION_TOKEN.findall(value)
    }


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
