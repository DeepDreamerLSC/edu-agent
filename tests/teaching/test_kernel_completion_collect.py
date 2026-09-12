"""完成表达盲区修(#178 判停分析→PR-2):「我算出来了」不带数字 → 确定性追问答案。

断言零模型(对象注入假 gateway,断言即规格):
  · 触发:完成表达(实录集)且学生未陈述答案数字 → 确定性追问 ASK_FINAL_ANSWER,
    零模型调用,不 confirm、不判对错、不预设掌握,埋点 {branch: answer_collect};
  · 全链路:追问 → 学生报数 → 答案命中 → 复讲请求 → 复讲带数字 → 模型置 ready →
    判停闸校验 _student_stated_answer 已真 → ready_to_confirm 可达(本修的目的地);
  · 分工:完成≠理解,不触发复讲(elicit 埋点不出现);带数字的完成表达走答案命中;
  · 频次:一次会话至多追问一次(对齐 _ask_restatement 先例),再来走模型路径;
  · 负例:「算不出来了」(否定词插中间)不触发;correct 档同样追问(采集与作答档正交)。
"""

from __future__ import annotations

import pytest

from edu_agent.agents.small_lecturer import reply, start

from teachkit import FakeGateway

ASK = "你算出的是多少?把答案说出来,我们对一对。"   # = prompting.ASK_FINAL_ANSWER,规格断言故硬编码
ELICIT = ("我们从头把思路串一遍——"
          "先说说你第一步算了什么、为什么这样算。")
# 鸡兔同笼:答案数字(3/5)不在题面(8/26)也不在步骤值(16/10)里,天然隔离
CHICKEN_QUESTION = {"text": "鸡和兔一共 8 只,共有 26 只脚。鸡和兔各有多少只?说明思路。",
                    "answer": "鸡3只兔5只", "analysis": "", "knowledge_points": ["鸡兔同笼"]}
CHICKEN_STEPS = [{"step": "先算全部按鸡的脚数", "value": "16"},
                 {"step": "再算脚数差", "value": "10"}]


def _open_payload(reply_text: str) -> dict:
    return {"acceptable": True, "transcription": "", "steps": CHICKEN_STEPS, "reply": reply_text}


def _tutor_payload(reply_text: str, ready: bool = False) -> dict:
    return {"reply": reply_text, "ready_to_confirm": ready, "cited_numbers": []}


def _incorrect_session(gateway: FakeGateway) -> object:
    first = start(dict(CHICKEN_QUESTION),
                  {"grade": "六年级", "answer_status": "incorrect"}, gateway=gateway)
    return first.session


@pytest.mark.parametrize("phrase", [
    "我算出来了,确认一下。",   # 实录原句(httpab×4)
    "这次算好了。",             # 实录原句(dlg2)
    "我算完了，你看对吗?",     # 实录原句(审查补扫,P2:原正则漏此形态)
])
def test_completion_without_digits_triggers_deterministic_ask(phrase):
    """完成表达 + 未陈述答案 → 确定性追问(零模型),不 confirm、不判对错、不触发复讲。"""
    gateway = FakeGateway(tutor_payloads=[_open_payload("你现在觉得鸡和兔各有多少只?")])
    session = _incorrect_session(gateway)
    calls = len(gateway.requests)
    turn = reply(session, phrase, gateway=gateway)
    assert turn.text == ASK
    assert turn.state == "dialogue" and turn.ready_to_confirm is False
    assert len(gateway.requests) == calls                   # 确定性分支零模型调用
    assert turn.session.guard_events[-1]["branch"] == "answer_collect"
    assert not any(e.get("branch") == "elicit" for e in turn.session.guard_events)  # 完成≠理解


def test_full_chain_ask_then_report_then_restate_reaches_ready():
    """全链路钉(#178 判停分析的目的地):追问 → 报数 → 复讲 → 模型 ready → 闸放行。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你现在觉得鸡和兔各有多少只?"),
        _tutor_payload("你讲得很完整,答案也对。", ready=True),  # 复讲轮的模型判定:可确认
        _tutor_payload("对,收尾没问题。", ready=True),          # 确认态后的模型轮:保持 ready
    ])
    session = _incorrect_session(gateway)
    t1 = reply(session, "我得出最终答案了,确认结束。", gateway=gateway)  # 实录原句(dlg3)
    assert t1.text == ASK                                       # ① 完成无数字 → 追问(零模型)
    t2 = reply(session, "鸡有3只,兔有5只。", gateway=gateway)
    assert t2.text == ELICIT                                    # ② 报数 → 答案命中 → 请复讲(零模型)
    t3 = reply(session, "我从头讲:假设全是鸡16只脚,差10只,每换一只多2只,兔5只鸡3只。",
               gateway=gateway)
    assert t3.text == "你讲得很完整,答案也对。"                 # ③ 复讲内容 → 模型轮
    assert t3.ready_to_confirm is True and t3.state == "ready_to_confirm"  # ④ 闸放行(报数轮已满足判据)
    t4 = reply(session, "我算出来了。", gateway=gateway)
    assert t4.text != ASK                                       # 确认态不追问(不把 ready 降级)
    assert t4.state == "ready_to_confirm"


def test_completion_with_digits_goes_answer_hit_not_ask():
    """带答案数字的完成表达:答案命中优先(复讲,00 §8.5 弧线),不走追问。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你现在觉得鸡和兔各有多少只?"),
        _tutor_payload("我们先看看脚数。"),
    ])
    session = _incorrect_session(gateway)
    reply(session, "我觉得鸡有5只,兔有3只。", gateway=gateway)   # 采集轮(数字对调不命中)
    turn = reply(session, "我算出来了:兔有10除以2等于5只,鸡有3只。", gateway=gateway)
    assert turn.text == ELICIT and turn.session.guard_events[-1]["branch"] == "elicit"


def test_ask_fires_once_per_session():
    """频次对齐 elicit 先例:追问过一次后,再次完成表达 → 模型路径,不重复追问。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你现在觉得鸡和兔各有多少只?"),
        _tutor_payload("好,你说说思路。"),                       # 第二次完成表达 → 模型轮消费
    ])
    session = _incorrect_session(gateway)
    reply(session, "我算出来了。", gateway=gateway)
    turn = reply(session, "这次算好了。", gateway=gateway)       # 实录原句(dlg2)
    assert turn.text == "好,你说说思路。"
    assert turn.session.guard_events[-1]["branch"] == "model"


@pytest.mark.parametrize("phrase", ["我算不出来了。", "我没算完。", "我算不完了。"])
def test_negated_completion_does_not_fire(phrase):
    """否定形态(否定词插中间)不触发追问——归卡壳侧,检测器互不越界。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你现在觉得鸡和兔各有多少只?"),
        _tutor_payload("没关系,我们一步步来。"),
    ])
    session = _incorrect_session(gateway)
    turn = reply(session, phrase, gateway=gateway)
    assert turn.text != ASK and turn.session.guard_events[-1]["branch"] == "model"


def test_correct_status_keeps_model_path():
    """correct 档完成表达不追问(对齐答案命中分支的 incorrect-only 先例;r6 结构化总结
    钉着 correct 档完成表达走模型路径,泄漏护栏面在那)→ 交模型,埋点 model。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("这道题你做对啦。"),
        _tutor_payload("那你跟大家讲讲你的思路吧。"),
    ])
    first = start(dict(CHICKEN_QUESTION), {"grade": "六年级", "answer_status": "correct"},
                  gateway=gateway)
    turn = reply(first.session, "我得出结果了,对吗?", gateway=gateway)  # 实录原句(dlg1)
    assert turn.text == "那你跟大家讲讲你的思路吧。" and turn.text != ASK
    assert turn.session.guard_events[-1]["branch"] == "model"
