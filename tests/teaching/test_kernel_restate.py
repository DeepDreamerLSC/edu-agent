"""#112 确定性合同:incorrect 弧线「答对后学生复讲」触发 + 复读循环治疗。

断言零模型(对象注入假 gateway,断言即规格):
  · 答案命中触发:学生陈述的数字集包含已知答案全部数字 → 确定性切 _ELICIT_TEMPLATE,
    零模型调用,不 confirm、不报答案;判据可复算(数字集包含 + 中文数字单字),零文本相似度;
  · 误触护栏:采集轮(incorrect 首轮 = 错答采集,数字对调不算命中)/ correct·unanswered·
    unknown 路径零改动 / 确认态不回复讲 / 复讲内容不再触发(防循环);
  · 复读循环治疗:复读自批评重生成仍复读 → 揭示下一级阶梯(每轮不同、推进教学),
    不再以同款问句兜底自我复读;
  · 代喂命中的处置粒度(#152 follow-up):重生成保留本轮语义 → 失败才确定性脱敏
    (只隐未说词)→ 模板仅末位兜底;埋点留痕(原文 + 命中词 + 处置路径 mode)。
"""

from __future__ import annotations

from edu_agent.agents.small_lecturer import FIRST_QUESTION_COLLECT, reply, start

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
    assert turn.session.guard_events[-1] == {"branch": "elicit", "hint_level": 0, "turn": 2}


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
    """确认态不回复讲:答案陈述走模型路径,不再请复讲。

    (#149 判停闸)确认态须**合法达成**:学生先自己说出答案数字集,模型才允许判停——
    此前靠模型单方面 ready=True 建态的构造按新不变量改写(断言不变)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你现在觉得鸡和兔各有多少只?"),
        _tutor_payload("我们把思路理清楚了。", ready=True),
        _tutor_payload("我们再确认一遍。"),
    ])
    session = _incorrect_session(gateway)
    confirmed = reply(session, "兔有10除以2等于5只,鸡有3只。", gateway=gateway)
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
    assert turn.session.guard_events[-1] == {"branch": "elicit", "hint_level": 0, "turn": 2}


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
    """复读自批评重生成仍复读 → 揭示下一级阶梯(新内容推进),不再同款问句兜底。

    首问可见文本 = 固定模板(start 覆盖),故「复读首问」= 模型复读该模板原文(prev)。"""
    repeated = FIRST_QUESTION_COLLECT
    gateway = FakeGateway(tutor_payloads=[
        _open_payload(repeated),
        _tutor_payload(repeated),   # 模型复读首问模板
        _tutor_payload(repeated),   # 重生成仍复读 → 兜底
    ])
    first = start(dict(CHICKEN_QUESTION), {"grade": "六年级"}, gateway=gateway)
    turn1 = reply(first.session, "嗯,我看看。", gateway=gateway)
    assert turn1.text == "我们从这里入手:先算全部按鸡的脚数。你接着算下一步。"
    assert turn1.session.stuck is True           # 复读打断 = 卡点标记(R6 同款)
    assert turn1.session.hint_level == 1
    # 埋点(#112 评审建议):复读降级路径的阶梯消耗同样记 reveal——此前只有卡壳分支记
    assert {"branch": "reveal", "hint_level": 1, "turn": 1} in turn1.session.guard_events


def test_repeat_fallback_ladder_texts_differ_consecutively():
    """连续两轮复读兜底:内容逐级推进且互不相同(旧兜底同句复读即循环源头)。"""
    question_text = FIRST_QUESTION_COLLECT   # 首问固定模板 = 第一轮被复读的上一轮文本
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


# ---------- #165 WS4 第 2 条:揭示**动作化**(不再把该步算好的结果交给学生) ----------

def _reveal_after_repeat(step_text: str) -> str:
    """走公开路径逼出一次阶梯揭示:模型复读首问模板 → 重生成仍复读 → 兜底揭示下一级。"""
    repeated = FIRST_QUESTION_COLLECT
    gateway = FakeGateway(tutor_payloads=[
        _open_payload(repeated, steps=[{"step": step_text, "value": "x"}]),
        _tutor_payload(repeated),
        _tutor_payload(repeated),   # 重生成仍复读 → 走揭示
    ])
    first = start(dict(CHICKEN_QUESTION), {"grade": "六年级"}, gateway=gateway)
    return reply(first.session, "嗯,我看看。", gateway=gateway).text


def test_reveal_withholds_computed_result_from_plan_step():
    """规划句写成「先算两个数相乘：10 × 6 = 60」时,揭示只给动作,结果收回去(学生自己算)。

    用不含方法词的句子构造:揭示句若含方法词会被代喂护栏接走(#165 第 1 条已改为
    重生成/脱敏,见 PR #168),那是另一条路径,不在本条断言范围。"""
    text = _reveal_after_repeat("先算两个数相乘：10 × 6 = 60")
    assert text == "我们从这里入手:先算两个数相乘。你接着算下一步。"
    assert "60" not in text and "×" not in text


def test_reveal_keeps_step_when_it_is_only_an_expression():
    """整句都是算式(没有动作段)→ 不空揭示,退回原文(宁可少改,不把揭示变空)。"""
    assert _reveal_after_repeat("26-16=10") == "我们从这里入手:26-16=10。你接着算下一步。"


def test_reveal_keeps_step_when_head_is_only_an_ordinal():
    """动作段只是序号(「第二步」)→ 同样退回原文。"""
    assert (_reveal_after_repeat("第二步：10 ÷ 2 = 5 只兔")
            == "我们从这里入手:第二步：10 ÷ 2 = 5 只兔。你接着算下一步。")


def test_reveal_cuts_at_clause_boundary_not_mid_sentence():
    """L 口径实测的残句回归:按「截到算式起始」会切出「8只鸡有。」——
    改为**按分句边界截断**,整段丢掉带结果的分句(「假设全是鸡」)。"""
    text = _reveal_after_repeat("假设全是鸡，8只鸡有 8×2=16 只脚")
    assert text == "我们从这里入手:假设全是鸡。你接着算下一步。"
    assert "16" not in text and "有。" not in text


def test_reveal_keeps_step_when_no_clause_boundary_exists():
    """没有分句边界可切时**原样保留**(宁可直给,不出残句)——不做机械截断。"""
    step = "8只鸡有 8×2=16 只脚"
    assert _reveal_after_repeat(step) == f"我们从这里入手:{step}。你接着算下一步。"


def test_reveal_keeps_step_without_arithmetic_unchanged():
    """无算式结果的规划句原样揭示(条件数字如「8只鸡」不算结果,不动)。"""
    assert (_reveal_after_repeat("假设8只全是鸡，算出脚的总数")
            == "我们从这里入手:假设8只全是鸡，算出脚的总数。你接着算下一步。")


# ---------- 输出面防复读终极不变量(任何兜底不得与上一轮学生可见文本同句) ----------

def test_guard_fallback_repeat_backstop_reveals_ladder():
    """泄露兜底复读:同句兜底将连续出现(复读探针实测修复前 8 连发)→ 阶梯推进。

    首问可见文本恒为固定模板(start 覆盖),故 prev 由**上一轮学生可见文本**给出:
    第 1 轮护栏兜底句达学生面,第 2 轮同句兜底 == prev → 输出面防复读背板接住。"""
    loop_text = "先回到你刚说的「我还是觉得鸡有4只,兔有4只。」——你能从题目里再确认一个已知条件吗?"
    # (#149 ②)护栏答案基线统一走 _known_answer:本题 answer 空 → steps 末值 "10" 成基线,
    # 泄露判定由 unverified 分支转为 grounded 分支(命中答案 + 断言线索才算泄露)。
    leak = "结果是 10,不用再想了。"
    gateway = FakeGateway(tutor_payloads=[
        _open_payload(FIRST_QUESTION_COLLECT),
        _tutor_payload(leak), _tutor_payload(leak),  # 第 1 轮:泄露 + 重生成仍泄露 → 兜底同句
        # 第 2 轮:模型照旧泄露(1)→ 护栏重生成仍泄露(2)→ 复读自批评重生成仍泄露(3)
        # → 背板揭示下一级阶梯(确定性,零模型)
        _tutor_payload(leak), _tutor_payload(leak),
        _tutor_payload(leak), _tutor_payload(leak),
    ])
    first = start({"text": "鸡和兔一共 8 只,共有 26 只脚。鸡和兔各有多少只?说明思路。",
                   "answer": "", "analysis": "", "knowledge_points": []},
                  {"grade": "六年级"}, gateway=gateway)
    looped = reply(first.session, "我还是觉得鸡有4只,兔有4只。", gateway=gateway)
    turn = reply(first.session, "我还是觉得鸡有4只,兔有4只。", gateway=gateway)
    assert looped.text == loop_text          # 第 1 轮:泄露原文被兜底句换下
    assert turn.text == "我们从这里入手:先算全部按鸡的脚数。你接着算下一步。"
    assert turn.text != loop_text           # 不再同句复读
    assert turn.session.stuck is True
    assert turn.ready_to_confirm is False
    assert {"branch": "reveal", "hint_level": 1, "turn": 2} in turn.session.guard_events  # 背板路径同记


def test_elicit_swap_repeat_backstop_reveals_ladder():
    """代喂处置后复读:处置结果与上一轮学生可见文本同句(实测 8 连发)→ 阶梯推进。

    #165 WS4 后处置不再整轮换模板:「脱敏」结果可能与 prev 撞句(上一轮本就是脱敏句),
    输出面防复读背板必须仍然生效。首问可见文本恒为固定模板,故 prev 由第 1 轮的
    脱敏句给出(第 2 轮脱敏结果与它同句)。"""
    masked_prev = "这一步用这种方法就能看出来。"
    hitting = "这一步用底乘高就能看出来。"
    gateway = FakeGateway(tutor_payloads=[
        _open_payload(FIRST_QUESTION_COLLECT),
        _tutor_payload(hitting), _tutor_payload(hitting),  # 第 1 轮:重生成仍点名 → 脱敏句达学生面
        _tutor_payload(hitting), _tutor_payload(hitting),  # 第 2 轮:脱敏结果 == prev → 背板推进
    ])
    first = start({"text": "一个三角形底是10厘米,高是6厘米,面积是多少?",
                   "answer": "", "analysis": "", "knowledge_points": []},
                  {"grade": "六年级"}, gateway=gateway)
    masked = reply(first.session, "我还是觉得面积就是60平方厘米。", gateway=gateway)
    turn = reply(first.session, "我还是觉得面积就是60平方厘米。", gateway=gateway)
    assert masked.text == masked_prev       # 第 1 轮:点名被脱敏,脱敏句即下一轮 prev
    assert turn.text != masked_prev         # 不再同句复读
    assert turn.text.startswith(("我们从这里入手", "下一步是这样"))  # 阶梯推进
    assert turn.session.stuck is True
    assert {"branch": "reveal", "hint_level": 1, "turn": 2} in turn.session.guard_events  # 背板路径同记


# ---------- 代喂命中的处置粒度(#152 follow-up / #165 WS4)+ 埋点 ----------

def test_method_feed_hit_regenerates_and_records_event():
    """命中代喂 → **重生成保留本轮语义**(不整轮换复讲模板);埋点留痕原文/命中词/路径。"""
    repaired = "你说的这个方法很关键,那这一步你打算先算哪一个?"
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你先说说题目给了哪些条件?"),
        _tutor_payload("你用的是假设法,对吧?", ready=True),
        _tutor_payload(repaired),        # 重生成:守住本轮引导语义、不点名
    ])
    first = start(dict(CHICKEN_QUESTION), {"grade": "六年级"}, gateway=gateway)
    turn = reply(first.session, "我先说说我的想法。", gateway=gateway)
    assert turn.text == repaired                # 保留本轮引导,不是复讲模板
    assert "假设法" not in turn.text
    assert turn.session.stuck is False          # 修好 = 非硬降级(不落卡点)
    events = [e for e in turn.session.guard_events if e.get("guard") == "feeds_method"]
    assert events and events[-1]["original"] == "你用的是假设法,对吧?"
    assert events[-1]["rule_ids"] == ["假设法"]
    assert events[-1]["regenerated"] is True
    assert events[-1]["mode"] == "regenerated"


def test_method_feed_hit_masks_only_unsaid_tokens():
    """重生成仍点名 → 确定性脱敏:**只**隐去未说出的词,学生已说的词保持点名。"""
    hitting = "你把通分这步做对了,接下来试试假设法!"
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你先说说题目给了哪些条件?"),
        _tutor_payload(hitting),
        _tutor_payload(hitting),        # 重生成仍点名 → 落脱敏
    ])
    first = start(dict(FRACTION_QUESTION), {"grade": "六年级"}, gateway=gateway)
    turn = reply(first.session, "我通分之后把分子相加了。", gateway=gateway)
    assert "假设法" not in turn.text            # 未说词被隐去
    assert "通分" in turn.text                  # 学生已说 → 弧线允许的点名保留
    assert "这种方法" in turn.text
    events = [e for e in turn.session.guard_events if e.get("guard") == "feeds_method"]
    assert events and events[-1]["rule_ids"] == ["假设法"]   # 只记未说词
    assert events[-1]["mode"] == "masked"
    assert events[-1]["regenerated"] is True    # 确定性修好 = 非硬降级


def test_feeds_hit_keeps_confirm_when_student_stated_answer():
    """末轮例外(#152 实测 12 分→3 分):学生**已陈述终答**时,一次方法词命中
    不再强制不确认——本轮确认语义保留,会话照常收束(不推 needs_review)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你先说说题目给了哪些条件?"),
        _tutor_payload("你算得完全对!你用的这个方法和等式性质是一回事。", ready=True),
        _tutor_payload("你算得完全对!每一步都讲清楚了。", ready=True),
    ])
    first = start(dict(CHICKEN_QUESTION), {"grade": "六年级"}, gateway=gateway)
    turn = reply(first.session, "兔有10除以2等于5只,鸡有3只,验算26只脚。", gateway=gateway)
    assert turn.ready_to_confirm is True        # 未被强制关掉
    assert turn.state == "ready_to_confirm"
    assert "等式性质" not in turn.text          # 未说出的词仍不落文本


# ---------- ③ student_evidence 接线(#157 PM 复核裁定 1)+ ④ 补词 ----------

FRACTION_QUESTION = {"text": "计算 3/4 加 1/8,说说你的做法。",
                     "answer": "7/8", "analysis": "", "knowledge_points": ["异分母加法"]}
TRIANGLE_QUESTION = {"text": "一个三角形底是10厘米,高是6厘米,面积是多少?",
                     "answer": "30平方厘米", "analysis": "", "knowledge_points": ["三角形面积"]}


def test_student_said_method_name_not_swapped():
    """③:学生复讲里已自己说出「通分」→ 教师复述定名是弧线允许的点名,不换
    (#148 §6.3 的 4 次误伤形态——R/fraction「你把通分和分子相加这一步都做对了」)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你先说说题目给了哪些条件?"),
        _tutor_payload("你把通分和分子相加这一步都做对了,真棒!"),
    ])
    first = start(dict(FRACTION_QUESTION), {"grade": "六年级"}, gateway=gateway)
    turn = reply(first.session, "我先把它们通分,再把分子相加。", gateway=gateway)
    assert turn.text == "你把通分和分子相加这一步都做对了,真棒!"  # 原文放行
    assert not [e for e in turn.session.guard_events if e.get("guard") == "feeds_method"]


def test_mixed_hits_record_only_unsaid_tokens():
    """③ 埋点精度:同一句里学生已说(通分)与未说(假设法)并存 → 只换、只记未说的。"""
    hitting = "你把通分这步做对了,接下来试试假设法!"
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你先说说题目给了哪些条件?"),
        _tutor_payload(hitting),
        _tutor_payload(hitting),        # 重生成仍点名 → 脱敏只隐未说词
    ])
    first = start(dict(FRACTION_QUESTION), {"grade": "六年级"}, gateway=gateway)
    turn = reply(first.session, "我通分之后把分子相加了。", gateway=gateway)
    assert "假设法" not in turn.text                 # 未说词被隐去
    assert "通分" in turn.text                       # 已说词保留点名
    events = [e for e in turn.session.guard_events if e.get("guard") == "feeds_method"]
    assert events and events[-1]["rule_ids"] == ["假设法"]  # 只记未说词


def test_area_formula_token_swapped():
    """④:面积公式 补入 _METHOD_TOKENS(#148 §5 阶梯揭示句原样漏出的词)。"""
    # 数字门在代喂护栏之前:命中句里的数字必须是允许池内的(题面 10/6),否则先被
    # 数值披露门接走(那条路径见 test_leak_gate_numeric.py),测不到代喂分支
    hitting = "我们从这里入手:先写出三角形面积公式,再看底乘高这一步。"
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你先说说题目给了哪些条件?"),
        _tutor_payload(hitting),
        _tutor_payload(hitting),        # 重生成仍点名 → 脱敏
    ])
    first = start(dict(TRIANGLE_QUESTION), {"grade": "六年级"}, gateway=gateway)
    turn = reply(first.session, "我想想。", gateway=gateway)
    assert "面积公式" not in turn.text                # 学生未说 → 不落文本
    events = [e for e in turn.session.guard_events if e.get("guard") == "feeds_method"]
    assert events and sorted(events[-1]["rule_ids"]) == ["底乘高", "面积公式"]  # 词表序,非文本序
