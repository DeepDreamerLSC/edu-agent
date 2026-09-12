"""数字守卫抽取制 + 来源标签池(M2 闭环 #113/#34)+ 确定性路径不变量。

覆盖:①意图分类器对抗样例(c2 实弹:越来越不懂 / 不会吧?!,走 reply 路由断言);
②数字守卫抽取制(c1 合法三例不卡 / 幻觉数字卡 / 对话态说终答卡);
③guard_events 落盘(模型路径 {自报集,抽取集,来源标签} + 确定性 {branch,hint_level});
(首问可见文本恒为固定模板,本文件的首问句只为对齐统一 open 的假上游序列);
④终答披露只走 bottom-out / finish / ready_to_confirm 三路径。
"""

from __future__ import annotations

import pytest

from edu_agent.agents.small_lecturer import reply, start

from test_drift_and_tone import LEARNER
from teachkit import FakeGateway

# 终答题面:answer 数字(3/5)既不在题面(8/26)也不在 step 值(16/10)里,天然
# 隔离「终答」来源标签,不与题面/步骤数字混淆。
ANSWERED_QUESTION = {"text": "鸡兔同笼,一共 8 只,26 只脚。鸡和兔各有多少只?",
                     "answer": "鸡3只兔5只", "analysis": "", "knowledge_points": ["鸡兔同笼"]}
STEPS = [{"step": "先算鸡脚", "value": "16"}, {"step": "再算兔脚", "value": "10"}]


def _open(reply_text: str, steps: list[dict] | None = None) -> dict:
    payload = {"reply": reply_text, "ready_to_confirm": False, "cited_numbers": []}
    if steps is not None:
        payload["steps"] = steps
    return payload


def _drift_event(turn) -> dict:
    """本轮模型路径的数字守卫埋点:优先返回**带违规归因**的那条(#184 起每轮至少一条:
    候选文本与重生成文本各判一次,只有前者可能带 violation_sources)。"""
    events = [e for e in turn.session.guard_events if e.get("branch") == "model"]
    assert events, "缺少模型路径数字守卫埋点"
    return next((e for e in events if e.get("violation_sources")), events[-1])


def _route_branch(session, phrase: str, gateway) -> str:
    turn = reply(session, phrase, gateway=gateway)
    return turn.session.guard_events[-1].get("branch")


# --------------------------------------------------------------------------- #
# c2:意图分类器对抗样例(负向断言补全,含两条实弹)——经 reply 路由断言
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("phrase,is_elicit", [
    ("都懂了", True),
    ("我懂了", True),
    ("明白了", True),
    ("我会了", True),
    ("没有不懂", True),
    ("没问题", True),
    ("我越来越不懂了", False),  # 实弹1:不懂了 ≠ 懂 → 揭示,非请讲
    ("我不会了", False),
])
def test_understanding_routes_to_elicit(phrase, is_elicit):
    gateway = FakeGateway(tutor_payloads=[_open("先看题面说的 8 只、26 只脚,你打算先算什么?", STEPS)])
    session = start(dict(ANSWERED_QUESTION), dict(LEARNER), gateway=gateway).session
    branch = _route_branch(session, phrase, gateway)
    assert (branch == "elicit") is is_elicit


@pytest.mark.parametrize("phrase,is_stuck", [
    ("我不太会", True),
    ("我猜不出来", True),
    ("我不知道", True),
    ("我不会做", True),
    ("没思路", True),
    ("我不会了", True),
    ("我越来越不懂了", True),       # 实弹1:越来越不懂 = 卡住
    ("这题我不会吧", True),
    ("不会吧?!这也能算对?", False),  # 实弹2:反诘惊讶 ≠ 卡住 → 模型,非揭示
    ("我会的", False),
    ("我不会吧?!", False),   # 「我不会(?!吧)」保留反诘语义(裸「我不会」不吞掉)
    # #198 检测器覆盖轮:D 卡 1 漏检 8 条原文(2026-09-12 10:41,#198)逐条钉住
    ("不知道", True),                      # ① 裸「不知道」
    ("我有点不会", True),                    # ② 「有点」隔断
    ("我还是不知道怎么想,一点思路都没有。", True),   # ③ 「还是」隔断(306de47 明知重开)
    ("方向怎么定不会", True),                 # ④ 非第一人称「怎么…不会」
    ("真的想不出来,要不你直接告诉我答案吧。", True),  # ⑤ 「想不出」无「我」前缀
    ("老师,这道题我不会。", True),             # ⑥ 裸「我不会」(306de47 明知重开)
    ("老师,这题方向绕来绕去的,我看不懂。", True),     # ⑦ 「看不懂」
    ("还是不会,能再提示一点吗?", True),          # ⑧ 「还是不会」(306de47 明知重开)
    # 守卫反钉(11/11 零翻转的两条真实 stability t1;306de47 教训:「还/但」紧邻的
    # 「不知道」是进展后局部卡点,进表曾把评测打红——前置 lookbehind 只放行被隔断形态)
    ("我还不知道怎么同时算两种动物。", False),
    ("我用53除以6，但不知道余数怎么解释。", False),
])
def test_stuck_routes_to_reveal(phrase, is_stuck):
    gateway = FakeGateway(tutor_payloads=[_open("先看题面说的 8 只、26 只脚,你打算先算什么?", STEPS)])
    session = start(dict(ANSWERED_QUESTION), dict(LEARNER), gateway=gateway).session
    branch = _route_branch(session, phrase, gateway)
    assert (branch == "reveal") is is_stuck


# --------------------------------------------------------------------------- #
# 数字守卫:抽取制 + 来源标签池
# --------------------------------------------------------------------------- #

def test_ordinal_numbers_in_reply_not_flagged_as_drift():
    # 抽取制排除「第N」序数:「第2步」的 2 不算数字引用;step 值 16 合法
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?", STEPS),
        {"reply": "第2步我们得到16。", "ready_to_confirm": False, "cited_numbers": [16]},
    ])
    turn = start(dict(ANSWERED_QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "为什么?", gateway=gateway)
    assert turn.session.stuck is not True
    assert _drift_event(turn)["extracted"] == [16.0]  # 序数 2 被排除


def test_step_value_in_reply_is_legal_not_stuck():
    # 合法例1:回复引用 step 值(16 ∈ steps)
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?", STEPS),
        {"reply": "这一步得到 16。", "ready_to_confirm": False, "cited_numbers": [16]},
    ])
    turn = start(dict(ANSWERED_QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "为什么?", gateway=gateway)
    assert turn.session.stuck is not True
    assert _drift_event(turn)["violation_sources"] == []


def test_student_number_in_reply_is_legal_not_stuck():
    # 合法例2:回复复述学生数字(16 ∈ 学生历史数字)
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?", STEPS),
        {"reply": "你算的 16 和题面 26 对不上。", "ready_to_confirm": False,
         "cited_numbers": [16, 26]},
    ])
    turn = start(dict(ANSWERED_QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "我算得 16", gateway=gateway)
    assert turn.session.stuck is not True
    assert _drift_event(turn)["violation_sources"] == []


def test_final_answer_in_confirm_state_is_legal_not_stuck():
    # 合法例3:ready_to_confirm 态说终答(3/5 ∈ 终答池并入允许集)
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?", STEPS),
        {"reply": "对,就是 3 只鸡和 5 只兔。", "ready_to_confirm": True,
         "cited_numbers": [3, 5]},
        {"reply": "你再想想。", "ready_to_confirm": False, "cited_numbers": []},
    ])
    turn = start(dict(ANSWERED_QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "答案是 3 和 5 吗?", gateway=gateway)
    assert turn.session.stuck is not True
    assert _drift_event(turn)["violation_sources"] == []


def test_hallucinated_number_is_intercepted_but_not_stuck():
    # #184:幻觉数字(36)不在任何来源池 → 拦截 + 来源标签 hallucinated;
    # **重生成修好 = 不置卡点**(stuck 只在修复失败落兜底句时置)
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?", STEPS),
        {"reply": "题目里一共 36 只脚。", "ready_to_confirm": False, "cited_numbers": [36]},
    ])
    turn = start(dict(ANSWERED_QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)
    assert "36" not in turn.text
    assert turn.session.stuck is not True
    assert _drift_event(turn)["violation_sources"] == [{"number": 36.0, "source": "hallucinated"}]
    assert _drift_event(turn)["gate"] == "blocked"


def test_final_answer_in_dialogue_state_is_intercepted():
    # 对话态(ready_to_confirm=false)说终答:终答数字在终答池但不在允许集 →
    # 来源标签 "answer"(提前说终答) → 同一漏斗拦下;检测到且修好 → 不置卡点
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?", STEPS),
        {"reply": "答案是 3 只鸡和 5 只兔。", "ready_to_confirm": False,
         "cited_numbers": [3, 5]},
        {"reply": "你再想想。", "ready_to_confirm": False, "cited_numbers": []},
    ])
    turn = start(dict(ANSWERED_QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)
    assert turn.text == "你再想想。" and turn.session.stuck is not True
    assert _drift_event(turn)["violation_sources"] == [
        {"number": 3.0, "source": "answer"}, {"number": 5.0, "source": "answer"}]
    assert _drift_event(turn)["gate"] == "blocked"
    leak = [e for e in turn.session.guard_events if e.get("guard") == "answer_leak"][-1]
    assert leak["regenerated"] is True
    assert leak["rule_ids"] == ["source_value_disclosure:answer"]


def test_selfreported_ladder_answer_not_whitelisted_but_intercepted():
    # #157 评审发现1(洗白半边):无 answer 题面(评测帧口径,KernelSubject 不传答案),
    # 阶梯末级 = 模型自报答案;对话态照抄末级数字(整段演算)必须被抓——
    # "自报进白名单"与 cited_numbers 同病。修复:终答数字按值从 steps 允许集剥离。
    question = {"text": "鸡兔同笼,一共 8 只,26 只脚。鸡和兔各有多少只?", "answer": ""}
    ladder = [*STEPS, {"step": "结论", "value": "鸡3只兔5只"}]
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?", ladder),
        {"reply": "剩下的就是鸡:8-5=3只,兔5只。", "ready_to_confirm": False,
         "cited_numbers": [8, 5, 3]},
        {"reply": "你再想想。", "ready_to_confirm": False, "cited_numbers": []},
    ])
    turn = start(question, dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)
    assert turn.session.stuck is not True        # #184:修好不置卡点
    assert _drift_event(turn)["violation_sources"] == [
        {"number": 3.0, "source": "answer"}, {"number": 5.0, "source": "answer"}]
    assert "3" not in turn.text and "5" not in turn.text  # 末值答案数字不达学生面


def test_last_step_value_not_answer_stays_legal():
    # 修复按**值**而非按位置(steps[:-1])剥离:阶梯末级未必是答案(题库口径:
    # 16/10 阶梯、答案 3/5)——诚实引用末级中间值(10)不误伤(#113 初衷)。
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?", STEPS),
        {"reply": "这一步得到 10。", "ready_to_confirm": False, "cited_numbers": [10]},
    ])
    turn = start(dict(ANSWERED_QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "为什么?", gateway=gateway)
    assert turn.session.stuck is not True
    assert _drift_event(turn)["violation_sources"] == []


# --------------------------------------------------------------------------- #
# guard_events 落盘:模型路径 + 确定性分支
# --------------------------------------------------------------------------- #

def test_model_branch_records_shadow_event():
    # 模型路径埋点含 {branch, cited(自报集), extracted(抽取集), violation_sources(来源标签),
    # gate(#184:检测到≠拦下,blocked/observed)}
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?", STEPS),
        {"reply": "题目里一共 36 只脚。", "ready_to_confirm": False, "cited_numbers": [36]},
    ])
    turn = start(dict(ANSWERED_QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)
    event = _drift_event(turn)
    assert event["branch"] == "model"
    assert event["cited"] == [36.0]      # 自报集(影子对照)
    assert event["extracted"] == [36.0]  # 抽取集
    assert event["violation_sources"] == [{"number": 36.0, "source": "hallucinated"}]


def test_deterministic_branches_record_guard_events():
    # 确定性分支埋点:elicit/reveal 记 {branch, hint_level}
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?", STEPS),
    ])
    turn = start(dict(ANSWERED_QUESTION), dict(LEARNER), gateway=gateway)
    assert turn.session.guard_events == []  # start 不跑数字守卫/分支埋点
    turn = reply(turn.session, "都懂了", gateway=gateway)
    assert turn.session.guard_events[-1] == {"branch": "elicit", "hint_level": 0, "turn": 1}
    turn = reply(turn.session, "我不太会", gateway=gateway)
    assert turn.session.guard_events[-1] == {"branch": "reveal", "hint_level": 1, "turn": 2}


# --------------------------------------------------------------------------- #
# c1 不变量:终答披露只走三条路径
# --------------------------------------------------------------------------- #

def test_final_answer_only_disclosed_via_bottomout_not_elicit_or_step_reveal():
    # elicit(请讲思路)/ 阶梯揭示(给步骤)确定性文本均不含终答;阶梯耗尽才 bottom-out 给终答。
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?", STEPS),
    ])
    turn = start(dict(ANSWERED_QUESTION), dict(LEARNER), gateway=gateway)
    elicit = reply(turn.session, "都懂了", gateway=gateway)
    assert "鸡3只兔5只" not in elicit.text  # elicit 不披露终答
    reveal1 = reply(elicit.session, "我不太会", gateway=gateway)
    assert "鸡3只兔5只" not in reveal1.text  # 第一级阶梯只给步骤,不给终答
    reveal2 = reply(reveal1.session, "我不知道", gateway=gateway)
    assert "鸡3只兔5只" not in reveal2.text  # 第二级阶梯仍只给步骤
    bottomout = reply(reveal2.session, "我猜不出来", gateway=gateway)
    assert "鸡3只兔5只" in bottomout.text  # 阶梯耗尽 → bottom-out 披露终答
