"""教学合同护栏:语气与年级表达(00 §6 自老仓库 tone_guardrails 纯断言迁移)。

断言语义逐条保持;老测试中耦合 DB/agent 装配的部分(_record_tone_risk_event、
_persist_step_output_async)按 00 §6「实现耦合的不迁」未随行,随 M2 内核按新
接口重组。
"""

from __future__ import annotations

import pytest
from fake_openai import completion

from edu_agent.agents.small_lecturer import apply_tone_guardrail
from edu_agent.gateway import ModelRequest

from teachkit import tutor_env


def test_humiliation_is_detected_without_rewriting_the_tutor_reply() -> None:
    result = apply_tone_guardrail(
        reply="这么简单的题你都不会？",
        grade_band="primary_upper",
        interaction_signal="neutral",
        teaching_move="connect_relation",
        ready_to_record=False,
    )

    assert result.applied is True
    assert result.reason_codes == ("tone_humiliation_or_sarcasm",)
    assert result.reply == "这么简单的题你都不会？"


def test_frustration_dismissal_is_detected_without_rewriting_the_reply() -> None:
    result = apply_tone_guardrail(
        reply="别抱怨，这有什么好难的，继续算。",
        grade_band="primary_lower",
        interaction_signal="frustrated",
        teaching_move="support_execution",
        ready_to_record=False,
    )

    assert result.applied is True
    assert "tone_ignored_student_frustration" in result.reason_codes
    assert result.reply == "别抱怨，这有什么好难的，继续算。"


def test_junior_middle_age_mismatch_is_blocked_but_normal_question_is_not() -> None:
    blocked = apply_tone_guardrail(
        reply="小朋友真乖，棒棒哒！再想想答案？",
        grade_band="junior_middle",
        interaction_signal="neutral",
        teaching_move="request_verification",
        ready_to_record=False,
    )
    allowed = apply_tone_guardrail(
        reply="你准备怎样检查这个结果？",
        grade_band="junior_middle",
        interaction_signal="neutral",
        teaching_move="request_verification",
        ready_to_record=False,
    )

    assert blocked.applied is True
    assert blocked.reason_codes == ("tone_severe_age_mismatch",)
    assert allowed.applied is False
    assert allowed.reply == "你准备怎样检查这个结果？"


def test_primary_lower_short_question_is_left_to_the_tutor_model() -> None:
    result = apply_tone_guardrail(
        reply="为什么用除法？",
        grade_band="primary_lower",
        interaction_signal="neutral",
        teaching_move="ask_justification",
        ready_to_record=False,
    )

    assert result.applied is False
    assert result.reason_codes == ()
    assert result.reply == "为什么用除法？"


def test_primary_upper_short_question_is_not_rewritten_in_code() -> None:
    result = apply_tone_guardrail(
        reply="怎么验证结果？",
        grade_band="primary_upper",
        interaction_signal="neutral",
        teaching_move="request_verification",
        ready_to_record=False,
    )

    assert result.applied is False
    assert result.reply == "怎么验证结果？"


@pytest.mark.parametrize(
    "reply",
    [
        "为什么要通分？",
        "怎么确定小数点？",
        "怎么确定小数点位置？",
        "1米等于多少厘米？",
        "为什么先算乘法？",
    ],
)
def test_primary_upper_historical_short_questions_are_not_rewritten(reply: str) -> None:
    result = apply_tone_guardrail(
        reply=reply,
        grade_band="primary_upper",
        interaction_signal="neutral",
        teaching_move="clarify_response",
        ready_to_record=False,
    )

    assert result.applied is False
    assert result.reply == reply


def test_primary_complete_question_is_not_mechanically_expanded() -> None:
    reply = "你已经找到了总数。请结合题目条件，说说两个数量之间是什么关系？"
    result = apply_tone_guardrail(
        reply=reply,
        grade_band="primary_upper",
        interaction_signal="neutral",
        teaching_move="connect_relation",
        ready_to_record=False,
    )

    assert result.applied is False
    assert result.reply == reply


def test_neutral_and_junior_questions_keep_their_concise_expression() -> None:
    for grade_band in ("neutral", "junior_middle"):
        result = apply_tone_guardrail(
            reply="为什么用除法？",
            grade_band=grade_band,
            interaction_signal="neutral",
            teaching_move="ask_justification",
            ready_to_record=False,
        )

        assert result.applied is False
        assert result.reply == "为什么用除法？"


def test_math_context_words_do_not_trigger_personality_or_age_rules() -> None:
    for reply in (
        "这个笨办法计算量很大，我们能换一种更简洁的方法吗？",
        "题目中的小朋友一共有多少人？",
    ):
        result = apply_tone_guardrail(
            reply=reply,
            grade_band="junior_middle",
            interaction_signal="neutral",
            teaching_move="prompt_strategy",
            ready_to_record=False,
        )
        assert result.applied is False


def test_ready_state_tone_risk_is_detected_without_state_repair() -> None:
    result = apply_tone_guardrail(
        reply="这么简单都不会，没救了。",
        grade_band="primary_upper",
        interaction_signal="neutral",
        teaching_move="clarify_response",
        ready_to_record=True,
    )

    assert result.applied is True
    assert result.reason_codes == ("tone_humiliation_or_sarcasm",)
    assert result.reply == "这么简单都不会，没救了。"


def test_tone_guard_gates_model_output_over_fake_upstream(tmp_path):
    """新接口形态(02 §6):假上游产出羞辱性回复,语气护栏在模型输出侧把关。"""
    with tutor_env(tmp_path, [completion("这么简单的题你都不会？")]) as (fake, gateway):
        response = gateway.invoke(ModelRequest(
            role="tutor",
            messages=[{"role": "user", "content": "3+4 等于几?"}],
            session_id="teach-tone-1",
        ))
        result = apply_tone_guardrail(
            reply=response.text,
            grade_band="primary_upper",
            interaction_signal="neutral",
            teaching_move="connect_relation",
            ready_to_record=False,
        )
    assert result.applied is True
    assert result.reason_codes == ("tone_humiliation_or_sarcasm",)
