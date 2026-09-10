"""#112 确定性合同:incorrect 弧线「答对后学生复讲」触发 + 复读循环治疗。

断言零模型(对象注入假 gateway,断言即规格):
  · 答案命中触发:学生陈述的数字集包含已知答案全部数字 → 确定性切 _ELICIT_TEMPLATE,
    零模型调用,不 confirm、不报答案;判据可复算(数字集包含 + 中文数字单字),零文本相似度;
  · 误触护栏:采集轮(incorrect 首轮 = 错答采集,数字对调不算命中)/ correct·unanswered·
    unknown 路径零改动 / 确认态不回复讲 / 复讲内容不再触发(防循环);
  · 复读循环治疗:复读自批评重生成仍复读 → 揭示下一级阶梯(每轮不同、推进教学),
    不再以同款问句兜底自我复读;
  · 代喂替换埋点:静默替换留痕(原文 + 命中词),供残留度量与护栏路径对照。
"""

from __future__ import annotations

from edu_agent.agents.small_lecturer import reply, start

from test_drift_and_tone import FakeGateway

ELICIT = ("很好,你已经懂了。那请你从头讲讲你的思路——"
          "先说说你第一步算了什么、为什么这样算。")
# 鸡兔同笼:答案数字(3/5)不在题面(8/26)也不在步骤值(16/10)里,天然隔离
CHICKEN_QUESTION = {"text": "鸡和兔一共 8 只,共有 26 只脚。鸡和兔各有多少只?说明思路。",
                    "answer": "鸡3只兔5只", "analysis": "", "knowledge_points": ["鸡兔同笼"]}
CHICKEN_STEPS = [{"step": "先算全部按鸡的脚数", "value": "16"},
                 {"step": "再算脚数差", "value": "10"}]


def _open_payload(reply_text: str, steps: list[dict] | None = None) -> dict:
    return {"acceptable": True, "transcription": "", "steps": steps or CHICKEN_STEPS,
            "reply": reply_text}


def _tutor_payload(reply_text: str, ready: bool = False) -> dict:
    return {"reply": reply_text, "ready_to_confirm": ready, "cited_numbers": []}


def _incorrect_session(gateway: FakeGateway, question: dict | None = None) -> object:
    first = start(dict(question or CHICKEN_QUESTION),
                  {"grade": "六年级", "answer_status": "incorrect"}, gateway=gateway)
    return first.session


# ---------- 答案命中触发(确定性,零模型) ----------

def test_answer_hit_elicits_restatement_without_model():
    """incorrect 弧线第 2+ 轮:学生说出已知答案 → 确定性请复讲,零模型调用。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你现在觉得鸡和兔各有多少只?"),
        _tutor_payload("好,那我们一步步来看这 26 只脚。"),
    ])
    session = _incorrect_session(gateway)
    reply(session, "我觉得鸡有5只,兔有3只。", gateway=gateway)  # 采集轮(见下一条测试)
    calls = len(gateway.requests)
    turn = reply(session, "我重算了:兔有10除以2等于5只,鸡有3只,验算26只脚。", gateway=gateway)
    assert turn.text == ELICIT
    assert turn.state == "dialogue" and turn.ready_to_confirm is False
    assert len(gateway.requests) == calls  # 确定性分支不调模型
    assert turn.session.guard_events[-1] == {"branch": "elicit", "hint_level": 0}


def test_collection_turn_number_clash_does_not_elicit():
    """采集轮护栏:incorrect 首轮是错答采集,数字对调(5/3 vs 3/5)撞答案数字集也不触发。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你现在觉得鸡和兔各有多少只?"),
        _tutor_payload("我们先看看脚数。"),
    ])
    session = _incorrect_session(gateway)
    turn = reply(session, "我觉得鸡有5只,兔有3只。", gateway=gateway)
    assert turn.text == "我们先看看脚数。"  # 走模型路径
    assert turn.session.guard_events[-1]["branch"] == "model"


def test_correct_and_unknown_status_never_elicit_on_answer_hit():
    """correct 路径零回归(红线):同样的答案陈述,correct/unanswered/unknown 一律模型路径。"""
    for status in ("correct", "unanswered", None):
        gateway = FakeGateway(tutor_payloads=[
            _open_payload("我们先确认题意。"),
            _tutor_payload("你来说说你的思路。"),
            _tutor_payload("我们再看下一步。"),
        ])
        learner = {"grade": "六年级", **({"answer_status": status} if status else {})}
        first = start(dict(CHICKEN_QUESTION), learner, gateway=gateway)
        reply(first.session, "我先算了一部分。", gateway=gateway)
        turn = reply(first.session, "兔有10除以2等于5只,鸡有3只。", gateway=gateway)
        assert turn.text != ELICIT, f"status={status} 不应触发复讲"
        assert turn.session.guard_events[-1]["branch"] == "model"


def test_restatement_after_elicit_does_not_re_elicit():
    """防循环:复讲引导之后的学生消息(复讲内容,含答案数字)不再触发,交模型路径。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你现在觉得鸡和兔各有多少只?"),
        _tutor_payload("我们先看看脚数。"),
        _tutor_payload("你讲得很完整。"),
    ])
    session = _incorrect_session(gateway)
    reply(session, "我觉得鸡有5只,兔有3只。", gateway=gateway)
    elicited = reply(session, "兔有10除以2等于5只,鸡有3只。", gateway=gateway)
    assert elicited.text == ELICIT
    turn = reply(session, "我从头讲:先假设全是鸡16只脚,差10只,每换一只多2只,兔5只鸡3只。",
                 gateway=gateway)
    assert turn.text == "你讲得很完整。"  # 复讲内容 → 模型路径,不再请复讲
    assert turn.session.guard_events[-1]["branch"] == "model"


def test_confirm_state_blocks_elicit():
    """确认态不回复讲:模型已置 ready_to_confirm 后,答案陈述走模型路径。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你现在觉得鸡和兔各有多少只?"),
        _tutor_payload("我们把思路理清楚了。", ready=True),
        _tutor_payload("我们再确认一遍。"),
    ])
    session = _incorrect_session(gateway)
    confirmed = reply(session, "我觉得可以按脚数差来算。", gateway=gateway)
    assert confirmed.state == "ready_to_confirm"
    turn = reply(session, "兔有10除以2等于5只,鸡有3只。", gateway=gateway)
    assert turn.text != ELICIT and turn.session.guard_events[-1]["branch"] == "model"


def test_number_free_answer_never_elicits():
    """无数字答案(纯文字)无法确定性判定 → 模型路径(现状行为,宁漏勿误)。"""
    question = {"text": "同一平面内两条直线的关系有哪几种?", "answer": "相交或平行",
                "analysis": "", "knowledge_points": []}
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你先说说你的想法。", steps=[]),
        _tutor_payload("我们再想想。"),
    ])
    session = _incorrect_session(gateway, question)
    turn = reply(session, "我觉得是相交或平行。", gateway=gateway)
    assert turn.text == "我们再想想。"
    assert turn.session.guard_events[-1]["branch"] == "model"


def test_steps_value_fallback_as_known_answer():
    """答案源兜底:question.answer 为空 → 阶梯末级 value 作已知答案(与 bottom-out 同源)。"""
    question = {"text": "解方程 3x+7=25。", "answer": "", "analysis": "", "knowledge_points": []}
    steps = [{"step": "两边减7", "value": "18"}, {"step": "得 x", "value": "6"}]
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你想从哪一步开始?", steps=steps),
        _tutor_payload("我们一步一步来。"),
    ])
    session = _incorrect_session(gateway, question)
    reply(session, "我先两边减7。", gateway=gateway)
    turn = reply(session, "得到x等于6,代回去是对的。", gateway=gateway)
    assert turn.text == ELICIT
    assert turn.session.guard_events[-1] == {"branch": "elicit", "hint_level": 0}


def test_cjk_spoken_numbers_hit():
    """中文数字单字:「八分之七」含 7/8,命中答案 7/8(参考答案侧仍按 ASCII)。"""
    question = {"text": "计算四分之三加八分之一,并说明为什么这样算。", "answer": "7/8",
                "analysis": "", "knowledge_points": []}
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你先说说你的想法。", steps=[{"step": "通分", "value": "6/8"}]),
        _tutor_payload("我们看看分母。"),
    ])
    session = _incorrect_session(gateway, question)
    reply(session, "我先把两个分数都变成八分之几。", gateway=gateway)
    turn = reply(session, "通分后分子相加,得到八分之七。", gateway=gateway)
    assert turn.text == ELICIT  # 学生口述含「八」「七」→ 数字集 {8,7} ⊇ {7,8}


# ---------- 复读循环治疗(兜底不再同句复读) ----------

def test_repeat_fallback_advances_ladder():
    """复读自批评重生成仍复读 → 揭示下一级阶梯(新内容推进),不再同款问句兜底。"""
    repeated = "兔子有几只呢?"
    gateway = FakeGateway(tutor_payloads=[
        _open_payload(repeated),
        _tutor_payload(repeated),   # 模型复读首问
        _tutor_payload(repeated),   # 重生成仍复读 → 兜底
    ])
    first = start(dict(CHICKEN_QUESTION), {"grade": "六年级"}, gateway=gateway)
    turn1 = reply(first.session, "嗯,我看看。", gateway=gateway)
    assert turn1.text == "我们从这里入手:先算全部按鸡的脚数。你接着算下一步。"
    assert turn1.session.stuck is True           # 复读打断 = 卡点标记(R6 同款)
    assert turn1.session.hint_level == 1


def test_repeat_fallback_ladder_texts_differ_consecutively():
    """连续两轮复读兜底:内容逐级推进且互不相同(旧兜底同句复读即循环源头)。"""
    question_text = "兔子有几只呢?"
    lead1 = "我们从这里入手:先算全部按鸡的脚数。你接着算下一步。"
    lead2 = "下一步是这样:再算脚数差。你接着算下一步。"
    gateway = FakeGateway(tutor_payloads=[
        _open_payload(question_text),
        _tutor_payload(question_text), _tutor_payload(question_text),  # 第一轮:复读首问×2
        _tutor_payload(lead1), _tutor_payload(lead1),                  # 第二轮:复读已揭示文本×2
    ])
    first = start(dict(CHICKEN_QUESTION), {"grade": "六年级"}, gateway=gateway)
    turn1 = reply(first.session, "嗯,我看看。", gateway=gateway)
    turn2 = reply(turn1.session, "嗯,我看看。", gateway=gateway)
    assert turn1.text == lead1
    assert turn2.text == lead2
    assert turn2.text != turn1.text            # 每轮不同 → 复读循环消失
    assert turn2.session.hint_level == 2


# ---------- 输出面防复读终极不变量(任何兜底不得与上一轮学生可见文本同句) ----------

def test_guard_fallback_repeat_backstop_reveals_ladder():
    """泄露兜底复读:同句兜底将连续出现(复读探针实测修复前 8 连发)→ 阶梯推进。"""
    loop_text = "先回到你刚说的「我还是觉得鸡有4只,兔有4只。」——你能从题目里再确认一个已知条件吗?"
    leak = "不对,我们来看 26 只脚该怎么分。"
    gateway = FakeGateway(tutor_payloads=[
        _open_payload(loop_text),            # 首问即该兜底句(构造 prev)
        _tutor_payload(leak), _tutor_payload(leak),  # 泄露 + 重生成仍泄露 → 兜底同句
    ])
    first = start({"text": "鸡和兔一共 8 只,共有 26 只脚。鸡和兔各有多少只?说明思路。",
                   "answer": "", "analysis": "", "knowledge_points": []},
                  {"grade": "六年级"}, gateway=gateway)
    turn = reply(first.session, "我还是觉得鸡有4只,兔有4只。", gateway=gateway)
    assert turn.text == "我们从这里入手:先算全部按鸡的脚数。你接着算下一步。"
    assert turn.text != loop_text           # 不再同句复读
    assert turn.session.stuck is True
    assert turn.ready_to_confirm is False


def test_elicit_swap_repeat_backstop_reveals_ladder():
    """代喂替换复读:上一轮已是复讲引导,本轮替换会再现同句(实测 8 连发)→ 阶梯推进。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload(ELICIT),              # 上一轮学生可见文本即复讲引导(构造 prev)
        _tutor_payload("你用的是底乘高的方法,对吧?"),
    ])
    first = start({"text": "一个三角形底是10厘米,高是6厘米,面积是多少?",
                   "answer": "", "analysis": "", "knowledge_points": []},
                  {"grade": "六年级"}, gateway=gateway)
    turn = reply(first.session, "我还是觉得面积就是60平方厘米。", gateway=gateway)
    assert turn.text != ELICIT              # 不再同句复讲引导
    assert turn.text.startswith(("我们从这里入手", "下一步是这样"))  # 阶梯推进
    assert turn.session.stuck is True


# ---------- 代喂替换埋点(残留度量语料来源) ----------

def test_method_feed_swap_records_original_event():
    """代喂替换留痕:{guard, rule_ids, original, regenerated}——不再静默换文本。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你先说说题目给了哪些条件?"),
        _tutor_payload("你用的是假设法,对吧?", ready=True),
    ])
    first = start(dict(CHICKEN_QUESTION), {"grade": "六年级"}, gateway=gateway)
    turn = reply(first.session, "我先说说我的想法。", gateway=gateway)
    assert turn.text == ELICIT                  # 替换为请讲引导
    assert turn.session.stuck is True
    events = [e for e in turn.session.guard_events if e.get("guard") == "feeds_method"]
    assert events and events[-1]["original"] == "你用的是假设法,对吧?"
    assert "假设法" in events[-1]["rule_ids"]
    assert events[-1]["regenerated"] is False
