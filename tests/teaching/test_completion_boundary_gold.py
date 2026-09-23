"""Gate boundary gold 集(#416,B 段接线前置;独立资产,被执行非死文档)。

设计件 v3.1 §三:Phase A verifier 接 Kernel 前须独立 boundary gold——钉
**输入语法边界**(各窄面正/负边界案)。与 C 段 32 案 regression corpus
**分立**:32 案(confirmation 24+ablation 8+负向三案)钉 Kernel/generation
行为回归,本集钉 verify_completion 的可认证/不可认证输入形态,两者用途
不同、互不替代。案集构成:
  · 负例 = #415 审查 P1-2 全部保守拒绝形态(不确定表达/命中前否定/多候选
    或/还是/claim 白名单外猜测/标点三变体/「6 还不确定」/问句猜答)
    + #415 复审 P2-R1(非 numeric 五面猜测词)与 P2-R2(和/与/要么 多候选
    及逗号并列)新形态;
  · 正例 = 裸答案/答案+单位/白名单声明式(设计 §三可认证形态)
    + 「我先猜8。后来算出是26只」正镜像(先猜后述,后继真声明必须放行)
    + 修正后终选与「和」字合法提交——P2 机制误伤面的反向钉。
每案=(窄面, ground_truth, 消息, 期望 verdict, 组装参数),id 前缀即形态
分类(pos-/neg-<形态>-);verdict 只断言 matched/None,span 级断言归 42 项
规格测试(test_completion_gate.py,非本件职责)。全部经公开面
verify_completion 驱动(02 §6:测试只导入公开入口),零模型零外部 API。
"""

from __future__ import annotations

import pytest

from edu_agent.agents.small_lecturer import AnswerSpec, verify_completion

TURN = 4  # 任意轮号:gold 只钉 verdict,turn 语义归规格测试
_ABCD = {"letter_choices": ("A", "B", "C", "D")}

# (id, answer_type, ground_truth, message, expect_matched, spec_kwargs)
# expect_matched=True → CompletionEvidence(verdict=matched);False → None。
_CASES = [
    # ---------- 正例:可认证白名单形态(v3.1 §三) ----------
    ("pos-numeric-bare", "numeric_with_unit", "6", "6", True, {}),
    ("pos-numeric-unit", "numeric_with_unit", "25.8度", "25.8度", True, {}),
    ("pos-numeric-declarative-suoyishi", "numeric_with_unit", "0.5m", "所以是0.5m", True, {}),
    ("pos-numeric-declarative-suanchushi", "numeric_with_unit", "26只", "算出是26只", True, {}),
    ("pos-numeric-guess-then-commit", "numeric_with_unit", "26只", "我先猜8。后来算出是26只", True, {}),
    ("pos-numeric-join-leading", "numeric_with_unit", "8", "3和5相加,答案是8", True, {}),
    ("pos-numeric-join-preposition", "numeric_with_unit", "6", "答案是6。和同桌的一样", True, {}),
    ("pos-choice-bare", "choice_letter", "B", "B", True, _ABCD),
    ("pos-choice-select", "choice_letter", "B", "选B", True, _ABCD),
    ("pos-choice-correction-commit", "choice_letter", "B", "A不对,是B", True, _ABCD),
    ("pos-choice-negate-then-commit", "choice_letter", "A", "不选B,选A", True, _ABCD),
    ("pos-truefalse-bare", "true_false", "对", "对", True, {}),
    ("pos-equation-bare", "equation_form", "x-21=35", "x-21=35", True, {}),
    ("pos-equation-declarative-yinggaishi", "equation_form", "x-21=35", "应该是x-21=35", True, {}),
    ("pos-ratio-bare", "ratio_or_expression", "3/4", "3/4", True, {}),
    ("pos-shorttext-bare", "short_text_exact", "易变形", "易变形", True, {}),
    ("pos-shorttext-declarative", "short_text_exact", "易变形", "答案是易变形。", True, {}),
    ("pos-shorttext-alias", "short_text_exact", "易变形", "容易变形", True,
     {"aliases": ("容易变形",)}),

    # ---------- 负例:不确定表达(P1-2,消息级 fail-closed) ----------
    ("neg-uncertain-numeric", "numeric_with_unit", "6", "可能 是 6", False, {}),
    ("neg-uncertain-numeric-still", "numeric_with_unit", "6", "还不确定,我觉得是6", False, {}),
    ("neg-uncertain-numeric-tail", "numeric_with_unit", "6", "6 还不确定", False, {}),
    ("neg-uncertain-numeric-approx", "numeric_with_unit", "6", "大概是6", False, {}),
    ("neg-uncertain-choice", "choice_letter", "B", "可能是B", False, _ABCD),
    ("neg-uncertain-choice-maybe", "choice_letter", "B", "也许是B", False, _ABCD),
    ("neg-uncertain-truefalse", "true_false", "对", "可能是对", False, {}),
    ("neg-uncertain-truefalse-hedge", "true_false", "对", "对,不过我不确定", False, {}),
    ("neg-uncertain-equation", "equation_form", "x-21=35", "可能是x-21=35", False, {}),
    ("neg-uncertain-ratio", "ratio_or_expression", "3/4", "可能是3/4", False, {}),
    ("neg-uncertain-shorttext", "short_text_exact", "易变形", "可能是易变形", False, {}),
    ("neg-uncertain-shorttext-declarative", "short_text_exact", "易变形", "答案可能是易变形", False, {}),

    # ---------- 负例:命中前否定(P1-2,六窄面通用否定窗) ----------
    ("neg-negation-numeric", "numeric_with_unit", "6", "不是6,是5", False, {}),
    ("neg-negation-choice", "choice_letter", "B", "不是B", False, _ABCD),
    ("neg-negation-choice-wobuxuan", "choice_letter", "B", "我不选B", False, _ABCD),
    ("neg-negation-choice-buxuan-others", "choice_letter", "B", "不选B,选A", False, _ABCD),
    ("neg-negation-truefalse", "true_false", "对", "不是对", False, {}),
    ("neg-negation-equation", "equation_form", "x-21=35", "不是x-21=35", False, {}),
    ("neg-negation-ratio", "ratio_or_expression", "3/4", "不是3/4", False, {}),
    ("neg-negation-shorttext", "short_text_exact", "易变形", "不是易变形", False, {}),

    # ---------- 负例:多候选 或/还是(P1-2,消息级 fail-closed) ----------
    ("neg-alt-choice-or", "choice_letter", "B", "B或D", False, _ABCD),
    ("neg-alt-choice-haishi", "choice_letter", "B", "选B还是D", False, _ABCD),
    ("neg-alt-numeric", "numeric_with_unit", "7", "6 还是 7", False, {}),
    ("neg-alt-equation", "equation_form", "x-21=35", "x-21=35 还是 x+21=35", False, {}),

    # ---------- 负例:claim 白名单外猜测(P1-2「我先猜8」型,numeric) ----------
    ("neg-nonclaim-guess-numeric", "numeric_with_unit", "8", "我先猜8。后来算出是26只", False, {}),

    # ---------- 负例:标点三变体(P1-2,逗号/句号/顿号) ----------
    ("neg-punct-comma", "numeric_with_unit", "6", "不是6,我觉得是5", False, {}),
    ("neg-punct-period", "numeric_with_unit", "6", "不是6。我觉得是5", False, {}),
    ("neg-punct-enumeration", "numeric_with_unit", "6", "不是6、我觉得是5", False, {}),

    # ---------- 负例:问句猜答(设计 §三不可认证形态) ----------
    ("neg-question-probe", "numeric_with_unit", "25.8度", "是不是25.8度?", False, {}),
    ("neg-question-tail", "numeric_with_unit", "25.8度", "25.8度对吗", False, {}),

    # ---------- 负例:P2-R1 非 marker 猜测词(非 numeric 五面) ----------
    ("neg-guess-choice", "choice_letter", "B", "我猜是B", False, _ABCD),
    ("neg-guess-choice-bare", "choice_letter", "B", "我猜B", False, _ABCD),
    ("neg-guess-choice-estimate", "choice_letter", "B", "估计是B", False, _ABCD),
    ("neg-guess-truefalse", "true_false", "对", "我猜是对", False, {}),
    ("neg-guess-truefalse-estimate", "true_false", "对", "估计是对", False, {}),
    ("neg-guess-equation", "equation_form", "x-21=35", "我猜是x-21=35", False, {}),
    ("neg-guess-ratio", "ratio_or_expression", "3/4", "我猜是3/4", False, {}),
    ("neg-guess-shorttext", "short_text_exact", "易变形", "我猜是易变形", False, {}),
    ("neg-guess-shorttext-estimate", "short_text_exact", "易变形", "估计是易变形", False, {}),
    # numeric 缝钉:claim 白名单已挡「我猜是8」(前缀非声明式模板),机制不重复
    ("neg-guess-numeric-seam", "numeric_with_unit", "8", "我猜是8", False, {}),

    # ---------- 负例:P2-R2 或/还是外的多候选(和/与/要么/逗号并列) ----------
    ("neg-join-choice-he", "choice_letter", "B", "B和D", False, _ABCD),
    ("neg-join-choice-yu", "choice_letter", "B", "B与D", False, _ABCD),
    ("neg-join-choice-list", "choice_letter", "B", "B,D", False, _ABCD),
    ("neg-either-choice", "choice_letter", "B", "要么B要么D", False, _ABCD),
    ("neg-join-numeric", "numeric_with_unit", "6", "6和7", False, {}),
    ("neg-join-numeric-declarative", "numeric_with_unit", "6", "答案是6和7", False, {}),
    ("neg-join-numeric-period", "numeric_with_unit", "6", "答案是6。和7", False, {}),
    ("neg-join-equation", "equation_form", "x-21=35", "x-21=35和x+21=35", False, {}),
    ("neg-join-ratio", "ratio_or_expression", "3/4", "3/4和3:4", False, {}),
    ("neg-join-truefalse", "true_false", "对", "对和错", False, {}),
    # 要么并入消息级多候选 marker:各面通吃(numeric 此案原由 claim 白名单挡)
    ("neg-either-numeric", "numeric_with_unit", "7", "要么6要么7", False, {}),
]


@pytest.mark.parametrize(
    "case_id,answer_type,ground_truth,message,expect,spec_kwargs",
    [pytest.param(*case, id=case[0]) for case in _CASES],
)
def test_boundary_gold(case_id, answer_type, ground_truth, message, expect, spec_kwargs):
    """逐案执行 gold 集:期望 matched 的案必须出 CompletionEvidence 且
    verdict/窄面正确;期望 None 的案必须整条不判(保守拒绝,宁 needs_review)。"""
    assert case_id.startswith(("pos-", "neg-"))   # id 前缀=形态分类,防误行
    evidence = verify_completion(
        AnswerSpec(answer_type=answer_type, ground_truth=ground_truth, **spec_kwargs),
        message, TURN)
    if expect:
        assert evidence is not None
        assert evidence.verdict == "matched"
        assert evidence.answer_type == answer_type
    else:
        assert evidence is None
