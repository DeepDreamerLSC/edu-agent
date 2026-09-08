"""教学合同护栏:答案泄露与单路径教学策略(00 §6 自老仓库 single_path_policy 迁移)。

断言语义逐条保持(参数化用例与期望不变);护栏代码是
edu_agent.agents.small_lecturer.guardrails(00 §6 随测试迁入的实现)。
"""

from __future__ import annotations

import pytest
from fake_openai import FakeOpenAI, completion

from edu_agent.agents.small_lecturer import evaluate_student_visible_question
from edu_agent.gateway import ModelRequest

from teachkit import tutor_gateway


@pytest.mark.parametrize(
    ("reply", "answer_reference", "active_subquestion_text"),
    [
        ("所以这里是几排几号？", "（5，12）", "数对（12，5）表示几排几号？"),
        (
            "先找到单位1，再想想这里该乘还是除？",
            "24",
            "求这批图书共有多少本。",
        ),
        ("我们先看横坐标。它表示什么？", "5", "点C的横坐标是多少？"),
        ("你刚才说第一项表示号，那么第二项表示什么？", "排", "数对第二项表示什么？"),
        ("以谁为中心看西北？", "学校", "小明在学校的什么方向？"),
        ("应表示什么关系？", "猫和老鼠路程之比", "写出猫和老鼠的路程关系。"),
    ],
)
def test_natural_socratic_questions_pass_unchanged(
    reply: str,
    answer_reference: str,
    active_subquestion_text: str,
) -> None:
    evaluation = evaluate_student_visible_question(
        reply,
        answer_reference=answer_reference,
        active_subquestion_text=active_subquestion_text,
    )

    assert evaluation.action == "ALLOW"
    assert evaluation.text == reply


@pytest.mark.parametrize(
    ("reply", "answer_reference"),
    [
        ("答案是B。你能说说理由吗？", "B"),
        ("所以x=3，这就是最终答案。你能回代检查吗？", "x=3"),
        ("先列式，再计算，最后得到当前小问答案为24。你看懂了吗？", "24"),
        ("正确选项就是C。你能解释吗？", "C"),
    ],
)
def test_only_grounded_answer_disclosures_require_fallback(
    reply: str,
    answer_reference: str,
) -> None:
    evaluation = evaluate_student_visible_question(
        reply,
        answer_reference=answer_reference,
        active_subquestion_text="当前小问",
    )

    assert evaluation.action == "FALLBACK"
    assert evaluation.fallback_required is True


def test_unverified_answer_shaped_text_fails_closed() -> None:
    evaluation = evaluate_student_visible_question(
        "答案是B。你为什么这样选择？",
        answer_reference="",
        active_subquestion_text="当前小问",
    )

    assert evaluation.action == "FALLBACK"
    assert evaluation.text == "答案是B。你为什么这样选择？"
    assert "unverified_answer_assertion" in {
        item.finding for item in evaluation.findings
    }


def test_computed_answer_is_blocked_without_authoritative_answer_reference() -> None:
    evaluation = evaluate_student_visible_question(
        "答案是12。你能说说为什么吗？",
        answer_reference="",
        active_subquestion_text="计算3×4。",
    )

    assert evaluation.action == "FALLBACK"
    assert "unverified_answer_assertion" in {
        item.finding for item in evaluation.findings
    }


@pytest.mark.parametrize(
    "reply",
    [
        "应该是东南方向，对吗？",
        "小聪在东南方向，对吗？",
        "正确选项应该是B，对吗？",
        "这里是25米，对吗？",
        "它们成正比例关系，对吗？",
        "你觉得答案是什么？我猜应该是东南方向，对吗？",
    ],
)
def test_unverified_text_answer_confirmation_fails_closed(reply: str) -> None:
    evaluation = evaluate_student_visible_question(
        reply,
        answer_reference="",
        active_subquestion_text="请判断当前小问。",
    )

    assert evaluation.action == "FALLBACK"
    assert "unverified_answer_assertion" in {
        item.finding for item in evaluation.findings
    }


@pytest.mark.parametrize(
    "reply",
    [
        "你觉得答案是什么？",
        "这个结果是怎么得到的？",
        "结果是根据哪个条件得出的？",
        "这个结果是不是满足所有条件？",
        "先两边减7，再除以3，对吗？",
    ],
)
def test_answer_formation_questions_are_not_treated_as_answer_claims(
    reply: str,
) -> None:
    evaluation = evaluate_student_visible_question(
        reply,
        answer_reference="",
        active_subquestion_text="解方程3x+7=25。",
    )

    assert evaluation.action == "ALLOW"


def test_tutor_may_confirm_answer_candidate_already_said_by_student() -> None:
    evaluation = evaluate_student_visible_question(
        "你刚才说小聪在东南方向，对吗？",
        answer_reference="",
        active_subquestion_text="小聪在小马的什么方向？",
        student_evidence=["我觉得小聪在东南方向。"],
    )

    assert evaluation.action == "ALLOW"


def test_unverified_correction_cannot_supply_a_new_value_from_the_question() -> None:
    evaluation = evaluate_student_visible_question(
        "题目中C岛是北偏东75°，不是30°。请再看一遍，C岛的角度是多少？",
        answer_reference="",
        active_subquestion_text=(
            "以灯塔为观测点，C岛在灯塔北偏东75°方向；"
            "D岛在灯塔南偏西40°方向。"
        ),
        student_evidence=["30度"],
    )

    assert evaluation.action == "FALLBACK"
    assert "unverified_source_value_disclosure" in {
        item.finding for item in evaluation.findings
    }


def test_unverified_tutor_may_repeat_a_value_the_student_already_stated() -> None:
    evaluation = evaluate_student_visible_question(
        "你说C岛是北偏东75°。接下来D岛在哪个方向？",
        answer_reference="",
        active_subquestion_text=(
            "以灯塔为观测点，C岛在灯塔北偏东75°方向；"
            "D岛在灯塔南偏西40°方向。"
        ),
        student_evidence=["C岛是北偏东75度"],
    )

    assert evaluation.action == "ALLOW"


def test_unverified_tutor_cannot_supply_a_new_compound_direction() -> None:
    evaluation = evaluate_student_visible_question(
        "C岛方向确认了。D岛在灯塔南偏西多少度？",
        answer_reference="",
        active_subquestion_text=(
            "以灯塔为观测点，C岛在灯塔北偏东75°方向；"
            "D岛在灯塔南偏西40°方向。"
        ),
        student_evidence=["C岛是北偏东75度"],
    )

    assert evaluation.action == "FALLBACK"
    assert "unverified_source_value_disclosure" in {
        item.finding for item in evaluation.findings
    }


def test_unverified_tutor_may_point_to_a_known_condition_without_correcting() -> None:
    evaluation = evaluate_student_visible_question(
        "题目中给出了C岛的方向和角度。你先说说观察点是谁？",
        answer_reference="",
        active_subquestion_text="以灯塔为观测点，C岛在灯塔北偏东75°方向。",
        student_evidence=[],
    )

    assert evaluation.action == "ALLOW"


def test_single_grounded_analysis_step_is_not_mistaken_for_a_full_solution() -> None:
    reply = "你刚才说先在等式两边同时减去7，为什么两边要做相同运算？"
    evaluation = evaluate_student_visible_question(
        reply,
        analysis_reference="先在等式两边同时减去7，得到3x=18；再同时除以3，得到x=6。",
    )

    assert evaluation.action == "ALLOW"
    assert evaluation.text == reply


def test_discourse_marker_plus_known_number_is_not_treated_as_answer_disclosure() -> None:
    reply = "所以先找到24这个已知量，再想想这里该乘还是除？"

    evaluation = evaluate_student_visible_question(
        reply,
        answer_reference="24",
        active_subquestion_text="求这批图书共有多少本。",
    )

    assert evaluation.action == "ALLOW"
    assert evaluation.text == reply


def test_tutor_may_confirm_an_answer_the_student_already_stated() -> None:
    reply = "所以x=3，你准备怎样检验？"

    evaluation = evaluate_student_visible_question(
        reply,
        answer_reference="x=3",
        active_subquestion_text="解方程。",
        student_evidence=["我算出x=3"],
    )

    assert evaluation.action == "ALLOW"
    assert evaluation.text == reply


def test_tutor_may_confirm_a_solution_path_the_student_already_stated() -> None:
    student_reply = "我先在等式两边同时减去7，再同时除以3，最后回代检查。"
    tutor_reply = "你说先同时减7、再同时除以3，最后回代检查；检验式怎么写？"

    evaluation = evaluate_student_visible_question(
        tutor_reply,
        answer_reference="x=6",
        analysis_reference="先在等式两边同时减去7，再同时除以3，最后回代检查。",
        student_evidence=[student_reply],
    )

    assert evaluation.action == "ALLOW"
    assert evaluation.text == tutor_reply


def test_tutor_cannot_fill_in_a_missing_answer_after_correct_student_steps() -> None:
    evaluation = evaluate_student_visible_question(
        "你先同时减7、再同时除以3得到x=6，检验式怎么写？",
        answer_reference="x=6",
        analysis_reference="先在等式两边同时减去7，再同时除以3，最后回代检查。",
        student_evidence=["我先同时减7，再同时除以3，最后回代检查。"],
    )

    assert evaluation.action == "FALLBACK"
    assert "grounded_answer_disclosure" in {
        item.finding for item in evaluation.findings
    }


def test_multiple_questions_are_left_to_prompt_and_offline_review() -> None:
    evaluation = evaluate_student_visible_question(
        "你先找到了什么？接下来准备怎么算？",
        answer_reference="24",
        active_subquestion_text="求总数。",
    )

    assert evaluation.action == "ALLOW"
    assert evaluation.text == "你先找到了什么？接下来准备怎么算？"


def test_missing_primary_question_is_not_a_content_safety_failure() -> None:
    evaluation = evaluate_student_visible_question(
        "我们先回到当前小问。",
        answer_reference="24",
        active_subquestion_text="求总数。",
    )

    assert evaluation.action == "ALLOW"
    assert evaluation.fallback_required is False


def test_full_answer_phrase_is_blocked() -> None:
    # answer 完整短语出现在回复 → 拦截
    reply = "答案就是:鸡 3 只,兔 5 只。"
    evaluation = evaluate_student_visible_question(
        reply, answer_reference="鸡 3 只,兔 5 只",
        active_subquestion_text="鸡和兔一共 8 只,共有 26 只脚。",
    )
    assert evaluation.action == "FALLBACK"


def test_digit_subset_of_answer_is_allowed() -> None:
    # 回复含"36 只脚"(answer 里的 3 是其子集) → 放行:数字子集不是泄露
    reply = "题目里一共 36 只脚,所以兔子很多。"
    evaluation = evaluate_student_visible_question(
        reply, answer_reference="鸡 3 只,兔 5 只",
        active_subquestion_text="鸡和兔一共 8 只,共有 26 只脚。",
    )
    assert evaluation.action == "ALLOW"


def test_analysis_key_sentence_is_blocked() -> None:
    # analysis 关键结论句被逐字复述(紧凑连续窗口)+有序 cue → 拦截
    reply = "用等式两边先同时减去 7,得 3x=18,再同时除以 3,就得到答案了。"
    evaluation = evaluate_student_visible_question(
        reply,
        answer_reference="",
        analysis_reference="等式两边先同时减去 7,得 3x=18,再同时除以 3。",
        active_subquestion_text="鸡和兔一共 8 只,共有 26 只脚。",
    )
    assert evaluation.action == "FALLBACK"


def test_intermediate_step_is_allowed() -> None:
    # 中间计算步骤(非关键结论句连续窗口)→ 放行
    reply = "先假设全是鸡:2×8=16 只脚,比 26 少 10。"
    evaluation = evaluate_student_visible_question(
        reply,
        answer_reference="鸡 3 只,兔 5 只",
        analysis_reference="等式两边先同时减去 7,得 3x=18,再同时除以 3。",
        active_subquestion_text="鸡和兔一共 8 只,共有 26 只脚。",
    )
    assert evaluation.action == "ALLOW"


def test_guardrail_gates_model_output_over_fake_upstream(tmp_path):
    """新接口形态(02 §6):假上游经 gateway tutor 角色产出回复,护栏在模型输出侧把关。"""
    fake = FakeOpenAI([completion("答案就是24。你能说说怎么来的吗？")]).start()
    gateway = tutor_gateway(fake.url, tmp_path)
    try:
        response = gateway.invoke(ModelRequest(
            role="tutor",
            messages=[{"role": "user", "content": "求这批图书共有多少本。"}],
            session_id="teach-leak-1",
        ))
    finally:
        gateway.close()
        fake.stop()
    evaluation = evaluate_student_visible_question(
        response.text, answer_reference="24", active_subquestion_text="求这批图书共有多少本。",
    )
    assert evaluation.action == "FALLBACK"
    assert "grounded_answer_disclosure" in {item.finding for item in evaluation.findings}
