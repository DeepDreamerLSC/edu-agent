"""report 渲染合同(C 线任务 1):单文件自包含 HTML,多版本设计单版本成立。"""

from __future__ import annotations

import pytest

from edu_agent.evals import render_html

BASE_CASES = {
    "case-a": {"total": 8, "verdict": "review"},
    "case-b": {"total": 3, "verdict": "fail"},
}
DIM_AVG = {"first_question": 1.8, "socratic_followup": 0.6, "grade_fit": 1.7,
           "pacing": 0.6, "summary_mastery": 0.4, "termination": 0.6}
EXAMPLES = [{"title": "示例:分数乘整数", "messages": [("小讲师", "先数圆片"), ("学生", "12")]}]


def test_single_version_renders_baseline():
    html = render_html(
        [{"label": "baseline", "cases": BASE_CASES, "dim_averages": DIM_AVG}],
        EXAMPLES, baseline_label="baseline",
    )
    assert html.startswith("<!doctype html>")
    assert "baseline" in html and "逐场景分数" in html and "示例对话" in html
    # 内联样式与内联 SVG,零外部依赖(无脚本/外链标签;svg 的 xmlns 命名空间除外)
    assert "<style>" in html and "<svg" in html
    for forbidden in ("<script", "<link", "<iframe", 'src="http', 'href="http'):
        assert forbidden not in html
    # 六维中文标签与分数出现
    assert "首问质量" in html and "1.80" in html
    # 示例对话(转义后的文本)
    assert "先数圆片" in html


def test_multi_version_marks_over_tolerance(tmp_path=None):
    tuned_cases = {"case-a": {"total": 10, "verdict": "pass"},
                   "case-b": {"total": 4, "verdict": "fail"}}
    html = render_html(
        [{"label": "baseline", "cases": BASE_CASES, "dim_averages": DIM_AVG},
         {"label": "tuning-1", "cases": tuned_cases,
          "dim_averages": DIM_AVG, "note": "调优轮 1"}],
        EXAMPLES, baseline_label="baseline", tolerance=1,
    )
    # case-a: 10-8=+2 > 容差 1 → 标红;case-b: +1 不标
    assert 'class="over-tolerance"' in html
    assert ">+2<" in html and ">+1<" in html
    assert "调优轮 1" in html
    # verdict 着色类
    assert 'class="pass"' in html and 'class="fail"' in html


def test_missing_case_renders_placeholder():
    html = render_html(
        [{"label": "baseline", "cases": BASE_CASES, "dim_averages": DIM_AVG},
         {"label": "tuning-1", "cases": {"case-a": {"total": 9, "verdict": "pass"}},
          "dim_averages": DIM_AVG}],
        [], baseline_label="baseline",
    )
    assert "<td>—</td>" in html  # tuning 未覆盖的场景显示占位


def test_requires_versions_and_known_baseline():
    with pytest.raises(ValueError):
        render_html([], EXAMPLES, baseline_label="baseline")
    with pytest.raises(ValueError):
        render_html([{"label": "v1", "cases": {}, "dim_averages": {}}],
                    EXAMPLES, baseline_label="nope")
