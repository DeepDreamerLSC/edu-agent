"""C41 族一般不变量(用户终裁 2026-09-25 ①):确定性替代输出的引用保真。

C41 实况(calibration 手册案例 C41;同构教训已入 #441 架构教训节):护栏兜底把
学生原话以截断 span 复述——「平均数应该用三次总分除以次数,先算82加88加9」
(截掉「4等于264」),来源 strict prefix 被当完整转述呈现。#441 的定性:
trusted text→[:N]→fake quote,病根是 transformation provenance 丢失。

本文件钉**一般不变量**,不绑任何 [:N] 截断实现(哨兵探测使任意截断长度必红):
  确定性 fallback 的学生可见文本,要么不引来源(固定非转述模板/全新文本),
  要么携带完整授权 span(首尾哨兵俱在——保形变换如数值掩码、方法词脱敏不触
  哨兵);把来源 strict prefix/suffix 当完整事实断言 = 红。

五条 student-visible 确定性替代路径逐一触发:answer leak fallback(掩码/纯
block 两臂)、feeds-method repair(重生成/脱敏两臂)、format·tone thin 直通、
summary 确定性零调用路径(学生首/末轮 + 题面引用字段)、stuck 阶梯回放
(#444:trusted analysis 切片回放 + 终答数字掩码,与掩码臂同族——掩码保形,
哨兵不触)。partial quote 必红由 meta 测试直接证明(喂入 C41 形态的截断文本,
断言检查器本身咬人,含首尾倒置分支)。与 ②(test_summary_quote_span_identity)
的分野:①钉 span 类别(完整/不引),②钉 summary 学生引用字段逐字符等式;
与 #441 的界:本件不碰 anchor/_step_value 取值面,只钉「引用保真」行为不变量。
"""

from __future__ import annotations

import pytest

from edu_agent.agents.small_lecturer import (
    PURE_BLOCK,
    apply_tone_guardrail,
    evaluate_student_visible_format,
    finish,
    reply,
    start,
)
from teachkit import FakeGateway

# 探针哨兵(实现无关):来源 = __UNIQUE_HEAD__<语义头>__UNIQUE_TAIL__。
# 任意 [:N] 截断必丢尾哨兵、任意 [N:] 截断必丢首哨兵;数值掩码(只动数字)与
# 方法词脱敏(只动词表词)都不触哨兵 →「完整授权 span」可判定。
HEAD_SENTINEL = "__UNIQUE_HEAD__"
TAIL_SENTINEL = "__UNIQUE_TAIL__"
# 无哨兵时,来源的 ≥8 连续字符片段不得出现在可见文本(更短片段不构成「呈现来源内容」)
_FRAGMENT_WINDOW = 8

THREE_ROAD_Q = {"text": "三段路分别长82米、88米、94米,这三段总长是多少米?",
                "answer": "264米", "analysis": "", "knowledge_points": ["加法"]}
FRACTION_Q = {"text": "比较 3/4 和 5/8 的大小。", "answer": "3/4大于5/8",
              "analysis": "", "knowledge_points": ["分数的大小比较"]}
# 题面哨兵(#444 P3-b:summary 题面引用字段 span 钉)——`_structured_summary`
# 以「{question}」引题面,截断/改写题面字段时哨兵丢失必红(②只钉学生引用字段)
LIBRARY_Q = {"text": f"{HEAD_SENTINEL}图书馆原有120本书,又买来45本,借出38本,现在有多少本?{TAIL_SENTINEL}",
             "answer": "127本", "answer_spec": {"answer_type": "numeric_with_unit"}}
LEARNER = {"grade": "六年级", "name": "小明"}


def _open(reply_text: str) -> dict:
    return {"reply": reply_text, "ready_to_confirm": False, "cited_numbers": [],
            "steps": []}


def _tutor(reply_text: str, ready: bool = False) -> dict:
    return {"reply": reply_text, "ready_to_confirm": ready, "cited_numbers": []}


def _guard_modes(session, guard: str) -> list[str]:
    return [event.get("mode") for event in session.guard_events
            if event.get("guard") == guard]


def _assert_full_span_or_no_quote(source: str, visible: str, *, label: str,
                                  head: str = HEAD_SENTINEL,
                                  tail: str = TAIL_SENTINEL) -> None:
    """C41 族不变量断言(不绑截断实现):可见文本要么携带完整授权 span
    (首尾哨兵俱在且有序——保形变换穿过哨兵),要么不引来源的任何有意义片段。

    验收仅两类:不引原文 / 完整授权 span 引用;恰一个哨兵(strict prefix 或
    strict suffix 当完整断言)或无哨兵但含来源 ≥8 连续字符片段,均为红。"""
    if head in visible and tail in visible:
        assert visible.index(head) < visible.index(tail), (
            f"{label}:引用 span 首尾倒置,非完整授权 span(C41 族)")
        return
    for offset in range(len(source) - _FRAGMENT_WINDOW + 1):
        assert source[offset:offset + _FRAGMENT_WINDOW] not in visible, (
            f"{label}:来源片段以截断形态进入学生可见文本"
            f"(head={head in visible},tail={tail in visible})"
            "——strict prefix/suffix 不得当完整事实断言(C41)")


# --------------------------------------------------------------------------- #
# meta:检查器本身咬人(partial quote 必红的直接证明)
# --------------------------------------------------------------------------- #

def test_partial_quote_checker_bites():
    """C41 形态喂给不变量断言,三条全部必红:strict prefix / strict suffix / 中段片段。"""
    source = f"{HEAD_SENTINEL}先算82加88加94等于264{TAIL_SENTINEL},你说下一步?"
    with pytest.raises(AssertionError):  # C41 原形:[:N] 截断当完整转述
        _assert_full_span_or_no_quote(
            source, f"先回到你刚说的「{source[:18]}」——你能说说下一步吗?",
            label="meta/prefix")
    with pytest.raises(AssertionError):  # strict suffix(去头留尾)当完整断言
        _assert_full_span_or_no_quote(
            source, f"你刚才说的是「等于264{TAIL_SENTINEL},你说下一步?」对吗?",
            label="meta/suffix")
    with pytest.raises(AssertionError):  # 无哨兵但泄漏来源中段片段
        _assert_full_span_or_no_quote(
            source, "我们接着看82加88加94等于264这一步。", label="meta/fragment")
    with pytest.raises(AssertionError):  # 首尾倒置:哨兵俱在但换序(拼装/错位)
        _assert_full_span_or_no_quote(    # ≠ 完整授权 span(#444 P3-a 分支咬合)
            source, f"你刚说的是「{TAIL_SENTINEL}先算82加88加94等于264{HEAD_SENTINEL}」吗?",
            label="meta/inverted")


# --------------------------------------------------------------------------- #
# 路径一:answer leak fallback(_guard_output 掩码臂 / 纯 block 臂)
# --------------------------------------------------------------------------- #

def test_answer_leak_masked_fallback_keeps_full_span():
    """掩码臂:仅违规终答数值→□,结构逐字保留——完整授权 span(哨兵俱在)。"""
    probe = f"先把{HEAD_SENTINEL}82加88加94等于264{TAIL_SENTINEL}算出来,你再说说下一步?"
    gateway = FakeGateway(tutor_payloads=[
        _open("这三段路你想怎么算?"),
        _tutor(probe),
    ])
    turn = start(dict(THREE_ROAD_Q), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)

    assert _guard_modes(turn.session, "answer_leak")[-1] == "masked"  # 确走掩码臂
    assert "264" not in turn.text
    _assert_full_span_or_no_quote(probe, turn.text, label="answer_leak/masked")


def test_answer_leak_pure_block_fallback_is_fixed_non_quote_template():
    """纯 block 臂:无可掩形态(前导零)→ 固定非转述模板,不引原文任何片段。"""
    probe = f"总长就是{HEAD_SENTINEL}82加88加94等于0264{TAIL_SENTINEL}米,你算算看?"
    gateway = FakeGateway(tutor_payloads=[
        _open("这三段路你想怎么算?"),
        _tutor(probe),
    ])
    turn = start(dict(THREE_ROAD_Q), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)

    assert turn.text == PURE_BLOCK
    assert _guard_modes(turn.session, "answer_leak")[-1] == "blocked"
    _assert_full_span_or_no_quote(probe, turn.text, label="answer_leak/blocked")


# --------------------------------------------------------------------------- #
# 路径二:feeds-method repair(_repair_feeds_method 重生成臂 / 脱敏臂)
# --------------------------------------------------------------------------- #

def test_feeds_method_regenerated_replacement_does_not_quote_source():
    """重生成臂:修复文本为全新内容,不得复现来源的任何截断片段。"""
    probe = (f"下一步用通分,先把{HEAD_SENTINEL}3/4和5/8化成同分母"
             f"{TAIL_SENTINEL}再比,你来试试?")
    gateway = FakeGateway(tutor_payloads=[
        _open("这两个分数你想怎么比?"),
        _tutor(probe),
        _tutor("你先把这两个分数变一变,再说说你的想法?", ready=True),
    ])
    turn = start(dict(FRACTION_Q), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)

    assert _guard_modes(turn.session, "feeds_method") == ["regenerated"]
    _assert_full_span_or_no_quote(probe, turn.text, label="feeds_method/regenerated")


def test_feeds_method_masked_replacement_keeps_full_span():
    """脱敏臂:命中方法词→「这种方法」,结构逐字保留——完整授权 span(哨兵俱在)。"""
    probe = (f"下一步用通分,先把{HEAD_SENTINEL}3/4和5/8化成同分母"
             f"{TAIL_SENTINEL}再比,你来试试?")
    gateway = FakeGateway(tutor_payloads=[
        _open("这两个分数你想怎么比?"),
        _tutor(probe),
        _tutor(""),  # 重生成失败(空回复)→ 脱敏臂
    ])
    turn = start(dict(FRACTION_Q), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)

    assert _guard_modes(turn.session, "feeds_method") == ["masked"]
    assert "通分" not in turn.text and "这种方法" in turn.text
    _assert_full_span_or_no_quote(probe, turn.text, label="feeds_method/masked")


# --------------------------------------------------------------------------- #
# 路径三:format·tone fallback(thin 直通;若日后接入截断式降级必红)
# --------------------------------------------------------------------------- #

def test_format_violation_fallback_keeps_full_original_span():
    """格式命中(Markdown)不处置:学生可见文本仍是完整原文 span。"""
    probe = f"先看{HEAD_SENTINEL}**82加88加94这三个数**{TAIL_SENTINEL},你打算先算什么?"
    assert evaluate_student_visible_format(probe).ok is False  # 探针确为格式违规
    gateway = FakeGateway(tutor_payloads=[
        _open("这三段路你想怎么算?"),
        _tutor(probe),
    ])
    turn = start(dict(THREE_ROAD_Q), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)

    _assert_full_span_or_no_quote(probe, turn.text, label="format/thin")


def test_tone_violation_fallback_keeps_full_original_span():
    """语气命中(羞辱形态)不处置:学生可见文本仍是完整原文 span。"""
    probe = f"这么简单都不会?先看{HEAD_SENTINEL}82加88加94{TAIL_SENTINEL},你打算先算什么?"
    tone = apply_tone_guardrail(
        reply=probe, grade_band="primary_upper", interaction_signal="neutral",
        teaching_move="connect_relation", ready_to_record=False)
    assert tone.applied is True  # 探针确为语气违规
    gateway = FakeGateway(tutor_payloads=[
        _open("这三段路你想怎么算?"),
        _tutor(probe),
    ])
    turn = start(dict(THREE_ROAD_Q), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)

    _assert_full_span_or_no_quote(probe, turn.text, label="tone/thin")


# --------------------------------------------------------------------------- #
# 路径四:summary 确定性路径(_structured_summary 零调用模板)
# --------------------------------------------------------------------------- #

def test_structured_summary_quotes_carry_complete_student_spans():
    """零调用 summary 引用学生原话与题面:各引用字段携带完整 span。分轮哨兵使
    任何引用字段(题面/首轮/末轮)的截断必红——与 ② 的逐字符等式断言互补。"""
    turn1 = "__T1_HEAD__先算120加45等于165本__T1_TAIL__。"
    turn2 = "__T2_HEAD__再算165减38,答案是127本__T2_TAIL__。"
    gateway = FakeGateway(tutor_payloads=[
        _open("这道题要我们求什么?"),
        _tutor("你说说先算的是什么?"),
        _tutor("你把两步都说清楚了。", ready=True),
    ])
    turn = start(dict(LIBRARY_Q), {"grade": "三年级", "name": "小明",
                                   "answer_status": "correct"}, gateway=gateway)
    reply(turn.session, turn1, gateway=gateway)
    reply(turn.session, turn2, gateway=gateway)
    assert turn.session.state == "ready_to_confirm"
    calls_before = len(gateway.requests)
    summary = finish(turn.session, gateway=gateway)

    assert summary.status == "completed"
    assert len(gateway.requests) == calls_before  # 确定性零调用路径(非模型总结)
    _assert_full_span_or_no_quote(LIBRARY_Q["text"], summary.text, label="summary/question")
    _assert_full_span_or_no_quote(turn1, summary.text, label="summary/first",
                                  head="__T1_HEAD__", tail="__T1_TAIL__")
    _assert_full_span_or_no_quote(turn2, summary.text, label="summary/last",
                                  head="__T2_HEAD__", tail="__T2_TAIL__")


# --------------------------------------------------------------------------- #
# 路径五:stuck 阶梯回放(_reveal_stuck_hint trusted analysis 切片,#444)
# --------------------------------------------------------------------------- #

def test_stuck_ladder_replay_keeps_full_span_with_answer_masked():
    """阶梯回放:卡住兜底把 trusted(analysis)切片回放给学生——与掩码臂同族
    (终答数字→□,保形变换;其余逐字)。哨兵钉死「回放=完整授权 span」:
    未来该路径接任何 [:N] 截断(既有钉子均为子串断言,不咬截断)必红。"""
    analysis = (f"第一步算{HEAD_SENTINEL}82加88等于170{TAIL_SENTINEL}。"
                f"第二步算{HEAD_SENTINEL}170加94得到264{TAIL_SENTINEL}。")
    question = {"text": "三段路分别长82米、88米、94米,这三段总长是多少米?",
                "answer": "264米", "analysis": analysis, "knowledge_points": ["加法"]}
    gateway = FakeGateway(tutor_payloads=[
        _open("这三段路你想怎么算?"),
    ])
    turn = start(dict(question), dict(LEARNER), gateway=gateway)
    assert [s["provenance"] for s in turn.session.steps] == ["analysis", "analysis"]
    calls_before = len(gateway.requests)

    first = reply(turn.session, "不知道。", gateway=gateway)      # 首次卡住 → 揭第 1 级
    assert first.session.guard_events[-1]["branch"] == "reveal"
    assert first.session.hint_level == 1
    assert len(gateway.requests) == calls_before                  # 确定性零调用
    _assert_full_span_or_no_quote(turn.session.steps[0]["step"], first.text,
                                  label="reveal/ladder-plain")

    second = reply(turn.session, "还是不会。", gateway=gateway)   # 再次卡住 → 第 2 级
    assert second.session.guard_events[-1]["branch"] == "reveal"
    assert second.session.hint_level == 2
    assert "264" not in second.text and "□" in second.text        # 终答数字掩码(保形)
    assert len(gateway.requests) == calls_before
    _assert_full_span_or_no_quote(turn.session.steps[1]["step"], second.text,
                                  label="reveal/ladder-masked")
