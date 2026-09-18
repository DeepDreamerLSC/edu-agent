"""possible_no_progress_cycle 非阻断诊断(#333,裁定 c5725369684 SMART 版)
的参数化回归 + Hypothesis property(#350 已合,PM 追加指令:用户点名结合)。

property 纪律(架构师硬边界):只生成检测器输入的机械结构(turns 文本对,
构造族可解析算出相似度),**不生成完整学生对话、不调模型**。

六面:必火(答过+窗口内换措辞重问)/必不火(新问点,护 M2 三形态)/空转录/
单轮/恰 N 窗与 N+1 窗外/阈值两侧(解析边界)/实体变体/纯函数语义。
"""

from __future__ import annotations

import copy

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from edu_agent.evals import possible_no_progress_cycle  # 公开入口(02 §6)

CI = settings(max_examples=50, derandomize=True, deadline=None)

# 构造族底料:两族互不重叠的问点文本(同族高相似=重问;异族零共享=新问点)。
GEOMETRY = "圆的半径是直径的一半,所以半径等于直径除以二"
ALGEBRA = "解方程时两边同时减去七,再同时除以三就得到 x 的值"


def _turns(pairs: list[tuple[str, str]]) -> dict:
    return {"turns": [{"tutor": t, "student": s} for t, s in pairs]}


# ── 必火:答过 + 窗口内换措辞重问 ──
@CI
@given(n_pad=st.integers(min_value=0, max_value=20),
       window=st.integers(min_value=1, max_value=5))
def test_property_reask_within_window_fires(n_pad, window):
    """学生答 S,tutor 在窗内以 S+少量问句填充重问 → 相似度
    2L/(2L+pad) 解析可算,pad≤20 时必 >0.6 → 必火。"""
    student = GEOMETRY
    pad = "吗?" + "呢" * n_pad
    gap = [("[t]", "[s]") for _ in range(window - 1)]
    turns = _turns(gap + [("", student), (student + pad, "")])
    assert possible_no_progress_cycle({}, turns, window=window), (n_pad, window)


# ── 必不火:新问点(异族零共享),护住 M2 三形态 ──
@CI
@given(prefix=st.integers(min_value=0, max_value=4),
       window=st.integers(min_value=1, max_value=6))
def test_property_new_question_point_silent(prefix, window):
    """学生答几何问点,tutor 在窗内问代数问点(零词面共享)→ 必不火。"""
    gap = [("[t]", "[s]") for _ in range(prefix)]
    turns = _turns(gap + [("", GEOMETRY)] + [(ALGEBRA + "?", "")] * 1)
    assert possible_no_progress_cycle({}, turns, window=window) == []


# ── 恰 N 窗 / N+1 窗外 ──
@CI
@given(offset=st.integers(min_value=1, max_value=7))
def test_property_window_boundary(offset):
    """tutor 原文重问在 i+window 轮(恰窗内最远)必火;i+window+1(窗外)必不火。"""
    student = GEOMETRY
    for window in (1, 3):
        filler = [("[t]", "[s]") for _ in range(offset - 1)]
        turns = _turns([("", student)] + filler + [(student, "")])
        fires = bool(possible_no_progress_cycle({}, turns, window=window))
        assert fires == (offset <= window), (offset, window)


# ── 阈值两侧(解析边界):ratio = 2L/(2L+pad) ──
@CI
@given(half_len=st.integers(min_value=8, max_value=40))
def test_property_threshold_both_sides(half_len):
    """tutor = 学生原文 + pad:pad < 4L/3 → ratio>0.6 必火;
    pad > 4L/3 → ratio<0.6 必不火(解析构造,非实测拟合)。"""
    student = ("半" * half_len)[:len(GEOMETRY)] or GEOMETRY[:half_len]
    L = len(student)
    hot_pad = max(0, int(4 * L / 3) - 2)
    cold_pad = int(4 * L / 3) + 2
    hot = _turns([("", student), (student + "?" * hot_pad, "")])
    cold = _turns([("", student), (student + "?" * cold_pad, "")])
    assert possible_no_progress_cycle({}, hot)
    assert possible_no_progress_cycle({}, cold) == []


# ── 纯函数语义:幂等 + 不改输入 ──
@CI
@given(pairs=st.lists(st.tuples(st.text(min_size=0, max_size=30),
                                st.text(min_size=0, max_size=30)),
                      min_size=0, max_size=8))
def test_property_pure_function_semantics(pairs):
    """任意 turns:两次调用同果(确定性);case/result 不被变异。"""
    case, result = {"id": "x"}, _turns(pairs)
    snapshot = copy.deepcopy((case, result))
    once = possible_no_progress_cycle(case, result)
    assert once == possible_no_progress_cycle(case, result)
    assert (case, result) == snapshot


# ── 参数化钉边(发现的边界=确定性回归)──
@pytest.mark.parametrize("turns,expected_n", [
    # 空转录 / 无 turns 键
    ({"turns": []}, 0),
    ({}, 0),
    # 单轮(学生答了但无后续 tutor 轮可重问)
    (_turns([("", GEOMETRY)]), 0),
    # 实体变体:插入「是不是/呢」仍高相似 → 火
    (_turns([("同学你好", ""),
             ("", "圆的半径是直径的一半"),
             ("那半径是不是直径的一半呢?", "")]), 1),
    # 合理复核:让学生自己讲依据(与已答内容词面差异大)→ 不火(M2 形态①)
    (_turns([("同学你好", ""),
             ("", "圆的半径是直径的一半"),
             ("很好,你自己说说为什么这一步成立,依据是什么?", "")]), 0),
    # 答对换新问点(M2 形态③续问依据的另一面:直接进下一步)→ 不火
    (_turns([("", "先算出了鸡有 3 只"),
             ("很好,接下来兔的数量怎么算?", "")]), 0),
    # 学生文本过短(<4 字)不构成已答问点 → 不火
    (_turns([("", "对"),
             ("对吗?你说对吗?", "")]), 0),
])
def test_no_progress_parametrized_boundaries(turns, expected_n):
    assert len(possible_no_progress_cycle({}, turns)) == expected_n
