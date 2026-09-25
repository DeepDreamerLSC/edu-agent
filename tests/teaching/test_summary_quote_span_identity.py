"""summary 引用 exact-span identity(用户终裁 2026-09-25 ②)。

_structured_summary(经公开入口 finish 的零调用 completed 通路触达;私有模块
不进测试导入,02 §6)是学生可见的确定性引用面:引号内引用字段必须与被引原文
**逐字符相等**——quoted_first == original_first、quoted_last == original_last。
末轮以尾哨兵收束:任何 [:N]/截断实现都会丢尾哨兵、破坏等式,必红(C41 实况
即末段被截的引用转述)。

只钉引用字段的 exact-span identity,不冻总结措辞(模板句式/收尾语可演化)。
与 ①(test_deterministic_provenance_invariants.py)的分野:①钉四条确定性
替代路径的一般不变量(完整 span/不引原文两态),本文件把 summary 引用字段
钉到逐字符等式。
"""

from __future__ import annotations

import re

from edu_agent.agents.small_lecturer import finish, reply, start
from teachkit import FakeGateway

# Gate B 段(#414 §四)后 completed 迁移需 answer_spec 声明面:末轮「答案是127本」
# 为声明式 claim 形态(A-段白名单),尾接哨兵不破坏 claim 与单位判定
# (单位类 [A-Za-z\u4e00-\u9fa5] 不含下划线,单位仍为「本」)。
LIBRARY_Q = {"text": "图书馆原有120本书,又买来45本,借出38本,现在有多少本?",
             "answer": "127本", "answer_spec": {"answer_type": "numeric_with_unit"}}
TAIL_SENTINEL = "__UNIQUE_TAIL__"


def _open(reply_text: str) -> dict:
    return {"reply": reply_text, "ready_to_confirm": False, "cited_numbers": [],
            "steps": []}


def _tutor(reply_text: str, ready: bool = False) -> dict:
    return {"reply": reply_text, "ready_to_confirm": ready, "cited_numbers": []}


def _completed_zero_call_summary() -> tuple[str, str, str]:
    """correct + ready_to_confirm + 当轮 claim 证据 → finish 走零调用确定性 summary。"""
    first = "先算120加45等于165本。"
    last = f"再算165减38,答案是127本{TAIL_SENTINEL}。"  # 末轮尾哨兵:截断必红
    gateway = FakeGateway(tutor_payloads=[
        _open("这道题要我们求什么?"),
        _tutor("你说说先算的是什么?"),
        _tutor("你把两步都说清楚了。", ready=True),
    ])
    turn = start(dict(LIBRARY_Q), {"grade": "三年级", "name": "小明",
                                   "answer_status": "correct"}, gateway=gateway)
    reply(turn.session, first, gateway=gateway)
    reply(turn.session, last, gateway=gateway)
    summary = finish(turn.session, gateway=gateway)
    return summary.text, first, last


def test_summary_quote_fields_equal_original_spans():
    """引用字段 exact-span:首轮/末轮学生原话逐字符完整入引;截断/改写必红。"""
    text, first, last = _completed_zero_call_summary()
    quoted = re.findall(r"「([^」]*)」", text)  # 引号内引用字段(不冻措辞,只取字段)
    assert first in quoted, "首轮原话未以完整 span 入引(quoted_first != original_first)"
    assert last in quoted, (
        "末轮原话未以完整 span 入引(quoted_last != original_last;"
        "尾哨兵丢失=截断实现再现,C41)")


def test_summary_last_quote_carries_tail_sentinel():
    """末轮尾哨兵确实入引:红机制在位(哨兵既在原文也在引用字段,截断必破坏等式)。"""
    text, _, last = _completed_zero_call_summary()
    assert TAIL_SENTINEL in last
    assert TAIL_SENTINEL in text  # 哨兵经完整引用进入 summary;若被 [:N] 截断即消失
