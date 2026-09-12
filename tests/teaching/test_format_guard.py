"""教学合同护栏:输出格式降级(02 §6 点名;断言源 = SKILL.md 第 11/12 条)。

老仓库此语义只有 SKILL 条款无确定性断言,本文件是首次成文(00 §6);护栏代码
edu_agent.agents.small_lecturer.format_guard。
"""

from __future__ import annotations

import pytest
from fake_openai import completion

from edu_agent.agents.small_lecturer import evaluate_student_visible_format
from edu_agent.gateway import ModelRequest

from teachkit import tutor_env


@pytest.mark.parametrize(
    "reply",
    [
        "我们先看横坐标。它表示什么？",
        "算式写成 12×5=60，先算乘法再算加法，对吗？",   # SKILL 11:× 是可直接阅读符号
        "两边同时除以 3，得到 x≤6 与 x≥3 的交集。",      # ≤ ≥ 白名单
        "根号下的数要非负，即 √(16)=4，÷ 与 × 同级。",   # √ ÷ × 白名单
    ],
)
def test_plain_text_with_readable_math_symbols_passes(reply: str) -> None:
    result = evaluate_student_visible_format(reply)
    assert result.ok is True
    assert result.findings == ()
    assert result.downgrade_prompt is None


@pytest.mark.parametrize(
    ("reply", "finding"),
    [
        ("## 第一步\n我们看已知条件。", "markdown_structure"),
        ("**注意**单位要统一。", "markdown_structure"),
        ("- 先通分\n- 再相加", "markdown_structure"),
        ("1. 第一步找单位1 2. 再列式", "markdown_structure"),
        ("这个分数写作 `1/2`。", "markdown_structure"),
        ("详见[提示](http://example.com)。", "markdown_structure"),
        ("面积公式是 $S=\\pi r^2$。", "dollar_formula_boundary"),
        ("含分式的式子是 \\sqrt{2} 加 \\frac{x+1}{2}。", "latex_command"),
    ],
)
def test_markdown_latex_and_dollar_boundaries_are_flagged(reply: str, finding: str) -> None:
    result = evaluate_student_visible_format(reply)
    assert result.ok is False
    assert finding in result.findings
    assert result.reply == reply


def test_latex_fraction_normalized_to_plain_text():
    """LaTeX 双修(任务包2步2):简单数值分数 \\frac{a}{b} 归一化为 a/b,不判 latex_command。"""
    result = evaluate_student_visible_format("\\frac{1}{2} 加 \\frac{1}{3}。")
    assert result.ok is True
    assert result.findings == ()
    assert result.reply == "1/2 加 1/3。"


def test_downgrade_prompt_is_provided_for_unsafe_format():
    """SKILL 12:无法安全转换的格式必须降级为重新说明提示(检测先行,转换器 M2 按需)。"""
    result = evaluate_student_visible_format("所以 x 的解是 $x=\\frac{18}{3}$。")
    assert result.ok is False
    assert result.downgrade_prompt and "重新" in result.downgrade_prompt


def test_format_guard_gates_model_output_over_fake_upstream(tmp_path):
    """新接口形态(02 §6):假上游产出带 Markdown/LaTeX 的回复,格式护栏在输出侧把关。"""
    with tutor_env(tmp_path, [
        completion("## 解题步骤\n1. 先算 **3×4**\n2. 得 $x=\\frac{12}{1}$"),
    ]) as (fake, gateway):
        response = gateway.invoke(ModelRequest(
            role="tutor",
            messages=[{"role": "user", "content": "计算 18÷3。"}],
            session_id="teach-format-1",
        ))
        result = evaluate_student_visible_format(response.text)
        # LaTeX 双修:\frac{12}{1} 归一化为 12/1(不再是 latex_command);Markdown 结构与 $...$ 边界仍需降级
        assert result.ok is False
        assert "markdown_structure" in result.findings
        assert "dollar_formula_boundary" in result.findings
        assert "latex_command" not in result.findings
