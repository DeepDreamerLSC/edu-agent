"""Hypothesis 属性测试:现有确定性不变量(#350;架构师裁定 c5724777246)。

只测现状(deterministic pure-ish 逻辑):①`mask_numbers` 掩码输出不漏答案数字
(Thin Kernel #333:soften 删,protective core 由掩码继承);②答案集合归因(允许集里的答案数字只能来自题面);③数字表示等价类
(现有解析已支持的形态);④numeric 纯函数任意输入全且稳定;⑤`_reveal_stuck_hint`
阶梯边界。**不预实现 V1 语义**——现状缺口记 FINDINGS(模块尾参数化回归+PR 说明),
不硬造应然、不顺手修产品代码。

设置纪律(CI 确定性,不慢化三道关卡):全部 property 共用 CI_SETTINGS
(derandomize=True + max_examples=50 有界 + deadline=None 防 CI 限速抖动)。
property 失败 shrink 出的最小反例固化进文末「发现的边界」参数化段——
发现的边界=新增确定性回归。
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from edu_agent.agents.small_lecturer import (
    NEEDS_REVIEW_TEXT,
    _STEP_LEADS,
    LearnerSession,
    _answer_focus_numbers,
    _answer_leak_span,
    _arithmetic_results,
    _drift_sources,
    _question_numbers,
    _reply_numbers,
    _reveal_stuck_hint,
    _spoken_numbers,
    mask_numbers,
)

CI_SETTINGS = settings(
    max_examples=50,
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.filter_too_much],
)

# ── 策略:数字与文本 ──
# 答案数字:非负小整数/一位小数(典型数学答案域;负数现有 _ASCII_NUMBER 不含
# 符号,不进生成域——现状缺口见 FINDINGS-6 注)。
ANSWER_NUM = st.one_of(
    st.integers(min_value=0, max_value=9999),
    st.integers(min_value=1, max_value=999).map(lambda n: n + 0.5),
)
ANSWER_SET = st.sets(ANSWER_NUM, min_size=1, max_size=4)

# 改写域上下文:汉字+空白+分句边界(，,、:：;；)+句号。**刻意无数字无运算符**——
# 数字会与答案集撞值生假失败;运算符会拐进 _STEP_ARITHMETIC_RE 算式路径
# (该路径的现状缺口是 FINDINGS-1,由文末定向参数化覆盖,不混进本 property)。
_CJK = "鸡兔同笼先算每只脚共有再算假设全部走路需要分钟转化小数为你想想看看这题问问好吗对吗呢啊呀吧"
_SEPS = "，,、:：;；"
_CTX_ALPHABET = _CJK + _SEPS + "。 \t"
CONTEXT = st.text(alphabet=_CTX_ALPHABET, min_size=0, max_size=30)
SEPARATOR = st.sampled_from(list(_SEPS))


def _num_forms(numbers: set[float]) -> str:
    """数字集的 ASCII 写形(整数不带小数点),供埋进文本。"""
    return "、".join(repr(n) if n % 1 else str(int(n)) for n in numbers)


def _make_session(text: str, answer: str, values: list[str],
                  history: list[str]) -> LearnerSession:
    return LearnerSession(
        question={"text": text, "answer": answer},
        learner={},
        steps=[{"step": "s", "value": v} for v in values],
        history=[{"role": "user", "content": c} for c in history],
    )


# ── ① mask_numbers:掩码输出永不包含答案数字(Thin Kernel 掩码继承 soften 内核)──
@CI_SETTINGS
@given(numbers=ANSWER_SET, before=CONTEXT, after=CONTEXT, sep=SEPARATOR)
def test_mask_output_never_contains_answer(numbers, before, after, sep):
    """含答案数字的 step 文本 → 掩码后学生可见文本里检不出任何答案数字;
    掩码幂等(二次掩码同果);非答案数字逐字保留(结构保持 by construction)。"""
    text = sep.join([before, _num_forms(numbers), after])
    out = mask_numbers(text, numbers)
    assert _answer_leak_span(out, frozenset(numbers)) is None, out
    assert mask_numbers(out, numbers) == out  # 幂等


# ── ② 答案集合归因:允许集里的答案数字只能来自题面 ──
@CI_SETTINGS
@given(
    q_nums=ANSWER_SET,
    a_nums=ANSWER_SET,
    step_txt=st.text(alphabet=_CJK + "，。0123456789×= ", min_size=0, max_size=20),
    hist_txt=st.text(alphabet=_CJK + "，。0123456789×= ", min_size=0, max_size=20),
)
def test_drift_answer_numbers_only_from_question(q_nums, a_nums, step_txt, hist_txt):
    """现状归因语义:allowed ∩ answer ⊆ 题面数字。steps/学生历史里的答案数字
    一律剥出允许集(防「自报洗白」#157;ready_to_confirm 不入允许池 VERDICT#6,
    允许集与确认态无关也在本断言覆盖内);算式结果同样剥(防「8-5=3」洗白)。"""
    qtext = "题:" + _num_forms(q_nums)
    answer = "答:" + _num_forms(a_nums)
    session = _make_session(qtext, answer, [step_txt, step_txt], [hist_txt])
    allowed, answer_pool = _drift_sources(session, hist_txt)
    assert answer_pool == _question_numbers(answer)
    leaked = allowed & answer_pool - _question_numbers(qtext)
    assert not leaked, (leaked, qtext, answer, step_txt, hist_txt)


# ── ③ 数字表示等价类(现有解析已支持的形态)──
@CI_SETTINGS
@given(n=st.integers(min_value=0, max_value=9999))
def test_number_forms_equivalent(n):
    """整数/前导零/「.0」后缀三种写法解析到同一数值集合(现有 _ASCII_NUMBER
    语义);千分位/百分号/分数值等价类现状不支持,缺口记 FINDINGS-2/3/4。"""
    expected = {float(n)}
    assert _question_numbers(str(n)) == expected
    assert _question_numbers(f"{n:05d}") == expected
    assert _question_numbers(f"{n}.0") == expected


# ── ④ numeric 纯函数:任意输入下全且稳定(确定性/fail-closed)──
@CI_SETTINGS
@given(text=st.text(min_size=0, max_size=60))
def test_numeric_pure_functions_total_and_stable(text):
    """纯函数任意文本不抛异常且幂等(两次调用同果)——fail-closed 语义稳定。"""
    for fn in (_question_numbers, _spoken_numbers, _reply_numbers,
               _arithmetic_results):
        once = fn(text)
        assert once == fn(text)
        assert isinstance(once, set)


@CI_SETTINGS
@given(q_nums=ANSWER_SET, extra=ANSWER_SET)
def test_answer_focus_numbers_fail_closed(q_nums, extra):
    """剔除题面后为空 → 退回原集(不放行任何判定);题面未给的结论数字照常剔除。"""
    qtext = "题:" + "、".join(str(int(n)) for n in q_nums if not n % 1)
    answer = "答:" + _num_forms(q_nums | extra)
    session = _make_session(qtext, answer, [], [])
    focus = _answer_focus_numbers(session)
    if _question_numbers(answer) - _question_numbers(qtext):
        assert focus == _question_numbers(answer) - _question_numbers(qtext)
    else:
        assert focus == _question_numbers(answer)  # fail-closed:空 → 原集


# ── ⑤ _reveal_stuck_hint:阶梯边界(越界/空 steps/bottom-out)──
@CI_SETTINGS
@given(
    answer=st.sampled_from(["答:12", ""]),
    n_steps=st.integers(min_value=0, max_value=4),
    start_level=st.integers(min_value=0, max_value=7),
)
def test_reveal_boundaries_total_and_recorded(answer, n_steps, start_level):
    """调用方现状可达域(hint_level≥0)与空 steps 下不抛异常、恒返回 str、
    每调记 {branch: reveal}。负值越界(空 steps→IndexError/非空→尾部重访)
    是现状缺口 FINDINGS-7/8,由文末定向探针锁现状。"""
    session = _make_session("题: 1", answer,
                            [f"{i + 1}0" for i in range(n_steps)], [])
    session.hint_level = start_level
    events_before = len(session.guard_events)
    out = _reveal_stuck_hint(session)
    assert isinstance(out, str)
    assert len(session.guard_events) == events_before + 1
    last = session.guard_events[-1]
    assert last.get("branch") == "reveal" and "hint_level" in last
    if not session.steps and answer:
        assert "12" not in out  # Thin Kernel:梯尽不披露终答(终答只在 finish)


@given(n_steps=st.integers(min_value=1, max_value=4))
@CI_SETTINGS
def test_reveal_ladder_monotonic_exhaustion_no_disclosure(n_steps):
    """从 0 级起:恰好 n_steps 次阶梯推进(不重复);梯尽 → NEEDS_REVIEW_TEXT,
    终答不披露(Thin Kernel #333:终答唯一披露点=finish)。"""
    session = LearnerSession(
        question={"text": "题: 1", "answer": "答:42"}, learner={},
        steps=[{"step": f"第{i}步算 {i + 2}", "value": str(i + 2)}
               for i in range(n_steps)],
        history=[])
    seen: list[str] = []
    for _ in range(n_steps):
        out = _reveal_stuck_hint(session)
        assert out.split(":", 1)[0] in _STEP_LEADS
        assert out not in seen  # 阶梯逐级,不重复
        seen.append(out)
    final = _reveal_stuck_hint(session)
    assert "42" not in final and final == NEEDS_REVIEW_TEXT


# ── 发现的边界(定向探针固化;发现的边界=确定性回归,现状缺口记 FINDINGS)──
@pytest.mark.parametrize("text,answer_set,expected", [
    # Thin Kernel 掩码(#333):答案数字一律 □,不分句形/算式/序数——结构逐字保留
    ("先算 10 × 6 = 60", frozenset({60.0}), "先算 10 × 6 = □"),
    ("先算底乘高，10 × 6 = 60", frozenset({60.0}), "先算底乘高，10 × 6 = □"),
    ("第13次必形成规律", frozenset({13.0}), "第□次必形成规律"),
    ("转化为小数得到 0.8", frozenset({0.8}), "转化为小数得到 □"),
    # 词边界:非答案数字部分命中不误伤(FINDINGS-4 千分位逗号仍切断解析,掩码面同)
    ("2025 年 2025 字", frozenset({25.0}), "2025 年 2025 字"),
])
def test_mask_directed_boundaries(text, answer_set, expected):
    assert mask_numbers(text, answer_set) == expected


@pytest.mark.parametrize("text,expected", [
    # FINDINGS-2:百分号不换算值(50% → 50 而非 0.5;V1 等价类候选)
    ("50%", {50.0}),
    # FINDINGS-3:分数按两个数字(「1/2」→ {1,2} 而非 0.5;与口算习惯一致,docstring 明示)
    ("1/2", {1.0, 2.0}),
    # FINDINGS-4:千分位逗号切断(「1,000」→ {1,0};V1 等价类候选)
    ("1,000", {1.0, 0.0}),
    # FINDINGS-5:中文复合数字不解析(十五 → _question_numbers 空;_spoken_numbers
    # 单字映射 {10,5} 而非 15;宁漏勿误,docstring 明示)
    ("十五", set()),
    # 负号不在 _ASCII_NUMBER(「-5」→ {5};FINDINGS-6:负数答案现状不可判定)
    ("-5", {5.0}),
])
def test_number_parsing_current_gaps(text, expected):
    assert _question_numbers(text) == expected


def test_spoken_composite_chinese_current_gap():
    # FINDINGS-5(补):中文单字映射只在 _spoken_numbers 侧(学生口述),值为单字值
    assert _spoken_numbers("十五") == {10.0, 5.0}


def test_reveal_negative_level_out_of_range_current_gaps():
    # FINDINGS-8:空 steps + 负 hint_level → _next_step 里 steps[-1] IndexError
    # (现状缺口,锁现状;V1 修掉时本断言改向)
    empty = _make_session("题: 1", "答:12", [], [])
    empty.hint_level = -1
    with pytest.raises(IndexError):
        _reveal_stuck_hint(empty)
    # FINDINGS-7:非空 steps + 负 hint_level → 从尾部索引重访(不崩,重访语义现状)
    filled = _make_session("题: 1", "答:12", ["第0步", "第1步"], [])
    filled.hint_level = -1
    out = _reveal_stuck_hint(filled)
    assert isinstance(out, str)


# FINDINGS 汇总(现状缺口,报 PM 不顺手修;V1 语义合并后另有补 property 单):
# 1. (已删)soften 三路径 → Thin Kernel 掩码一等继承;千分位逗号切断面见 #4
# 2. 百分号不换算值(50% → 50)
# 3. 分数按两个数字,不解析为值
# 4. 千分位逗号切断数字
# 5. 中文复合数字不解析(单字映射,宁漏勿误)
# 6. 负号不在数字模式内,负数答案不可判定(学生说「-5」只见 5)
# 7. _next_step 负 hint_level 从尾部索引重访 steps(调用方现状只用 0 起)
# 8. _next_step 空 steps + 负 hint_level → steps[-1] IndexError(property 实测
#    发现,调用方现状不可达;产品侧缺口报 PM)
