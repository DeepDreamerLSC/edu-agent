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

import pytest

from edu_agent.agents.small_lecturer import FIRST_QUESTION_COLLECT, finish, reply, start

from teachkit import FakeGateway

ELICIT = ("我们从头把思路串一遍——"
          "先说说你第一步算了什么、为什么这样算。")  # #179 问题 3:去掌握预设,保留复讲动作
# 裸数字形状整步弃用后的通用兜底句(= kernel.NEEDS_REVIEW_TEXT,规格断言故硬编码)
NEEDS_REVIEW_TEXT = "这一题的学习证据还不够,我们继续——你能说说目前想到的第一步吗?"
# 鸡兔同笼:答案数字(3/5)不在题面(8/26)也不在步骤值(16/10)里,天然隔离
# #382 PR-C:卡壳/复读/揭示面钉 trusted(analysis)阶梯(reveal 只消费 analysis 切片);
# CHICKEN_STEPS 仍由模型照常喂(证明模型阶梯入库/规划辅助不受边界影响)。
_CHICKEN_ANALYSIS = ("先假设8只全是鸡,算出脚的总数8×2=16。再算实际脚数比假设多26-16=10只。"
                     "最后每把一只鸡换成兔脚数多4-2=2只,10÷2=5只兔,鸡有8-5=3只。")
CHICKEN_QUESTION = {"text": "鸡和兔一共 8 只,共有 26 只脚。鸡和兔各有多少只?说明思路。",
                    "answer": "鸡3只兔5只", "analysis": _CHICKEN_ANALYSIS,
                    "knowledge_points": ["鸡兔同笼"]}
CHICKEN_STEPS = [{"step": "先算全部按鸡的脚数", "value": "16"},
                 {"step": "再算脚数差", "value": "10"},
                 {"step": "兔的只数", "value": "5"}]  # 末级触答案焦点(guard-provenance-fix ③ 门契约)


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



def test_confirm_state_blocks_elicit():
    """确认态不回复讲:答案重述走确定性收束(闭环三修 ①),不再请复讲。

    (#149 判停闸)确认态须**合法达成**:学生先自己说出答案数字集,模型才允许判停。
    close-loop-fix ①:确认态下本轮消息即终述(陈述式∧命中焦点)→ 直接走 finish
    语义收束(444a 案:此点模型复读→reveal 重发→永不闭环);无终述的确认态轮
    仍走模型路径(见下方 test_number_free / D 案降态路径)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你现在觉得鸡和兔各有多少只?"),
        _tutor_payload("我们把思路理清楚了。", ready=True),
        {"summary": "你把鸡兔各自只数和验算都讲清楚了,这道题完成。"},
    ])
    session = _incorrect_session(gateway)
    confirmed = reply(session, "兔有10除以2等于5只,鸡有3只。", gateway=gateway)
    assert confirmed.state == "ready_to_confirm"
    turn = reply(session, "兔有10除以2等于5只,鸡有3只。", gateway=gateway)
    assert turn.state == "completed"  # ①:终述即收束(产线 444a 死环修面)
    assert turn.text == "你把鸡兔各自只数和验算都讲清楚了,这道题完成。"
    assert turn.text != ELICIT
    assert turn.session.finished


def test_number_free_answer_never_elicits():
    """无数字答案(纯文字)无法确定性判定 → 模型路径(现状行为,宁漏勿误)。"""
    question = {"text": "同一平面内两条直线的关系有哪几种?", "answer": "相交或平行",
                "analysis": "同一平面内两条直线要么相交要么平行。",
                "knowledge_points": []}
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你先说说你的想法。", steps=[]),
        _tutor_payload("我们再想想。"),
    ])
    session = _incorrect_session(gateway, question)
    turn = reply(session, "我觉得是相交或平行。", gateway=gateway)
    assert turn.text == "我们再想想。"
    assert turn.session.guard_events[-1]["branch"] == "model"



def test_repeat_fallback_advances_ladder():
    """复读自批评重生成仍复读 → 揭示下一级阶梯(新内容推进),不再同款问句兜底。

    首问可见文本 = 固定模板(start 覆盖),故「复读首问」= 模型复读该模板原文(prev)。
    #382 PR-C:揭示的下一级 = analysis 切片(trusted 阶梯)。"""
    repeated = FIRST_QUESTION_COLLECT
    gateway = FakeGateway(tutor_payloads=[
        _open_payload(repeated),
        _tutor_payload(repeated),   # 模型复读首问模板
        _tutor_payload(repeated),   # 重生成仍复读 → 兜底
    ])
    first = start(dict(CHICKEN_QUESTION), {"grade": "六年级"}, gateway=gateway)
    turn1 = reply(first.session, "嗯,我看看。", gateway=gateway)
    assert turn1.text == "我们从这里入手:先假设8只全是鸡,算出脚的总数8×2=16。你接着算下一步。"
    assert turn1.session.stuck is not True      # #382 P0-1:repeat→reveal 不置 stuck(系统≠学生)
    assert turn1.session.hint_level == 1
    # 埋点(#112 评审建议):复读降级路径的阶梯消耗同样记 reveal——此前只有卡壳分支记
    assert {"branch": "reveal", "hint_level": 1, "turn": 1} in turn1.session.guard_events


def test_repeat_fallback_ladder_texts_differ_consecutively():
    """连续两轮复读兜底:内容逐级推进且互不相同(旧兜底同句复读即循环源头)。

    第二轮(hint_level>0,#333 泄露网 V1 口径):当前级 value=10 与 answer_pool{3,5}
    无双重身份 → 授权,文本附当前步中间值(「这一步先算,得到 10」);
    首轮(hint_level=0)不给数值,本级 16 不出现。(#382 PR-C:阶梯 = analysis 切片;
    P0-1 后 stuck 语义与学生卡壳信号绑定,此处只钉 hint_level 推进,两轮均不写 session.stuck。)"""
    question_text = FIRST_QUESTION_COLLECT   # 首问固定模板 = 第一轮被复读的上一轮文本
    lead1 = "我们从这里入手:先假设8只全是鸡,算出脚的总数8×2=16。你接着算下一步。"
    lead2 = "下一步是这样:再算实际脚数比假设多26-16=10只。这一步先算,得到 10。你接着算下一步。"
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
    assert "5" not in turn2.text  # 终答部件不上学生面(16 是当前步算式内中间值,照示)
    assert [e for e in turn2.session.guard_events if e.get("branch") == "reveal"][-1]["anchor_numbers"] == [10.0]
    assert turn2.text != turn1.text            # 每轮不同 → 复读循环消失
    assert turn2.session.hint_level == 2


# ---------- #165 WS4 第 2 条:揭示**动作化**(不再把该步算好的结果交给学生) ----------

# #382 PR-C:动作化十二形态用**自造 analysis**驱动(每步一句 + 数字,确定性切片
# 可控;尾句带数字保 ≥2 片切片成立);模型 steps 照喂但不被 reveal 消费。
def _reveal_after_repeat(step_text: str) -> str:
    """走公开路径逼出一次阶梯揭示:模型复读首问模板 → 重生成仍复读 → 兜底揭示下一级。"""
    repeated = FIRST_QUESTION_COLLECT
    analysis = f"{step_text}。最后把结果代回题目检验一遍得15。"
    gateway = FakeGateway(tutor_payloads=[
        _open_payload(repeated, steps=[{"step": step_text, "value": "5"}]),  # 值触焦点过③门(x 无数字会整副被弃)
        _tutor_payload(repeated),
        _tutor_payload(repeated),   # 重生成仍复读 → 走揭示
    ])
    first = start(dict(CHICKEN_QUESTION) | {"analysis": analysis},
                  {"grade": "六年级"}, gateway=gateway)
    return reply(first.session, "嗯,我看看。", gateway=gateway).text


@pytest.mark.parametrize("step_text,expected_reveal,forbidden", [
    # Thin Kernel(#333 终裁):soften 教学改写删——非答案数字原样保留(含算式结果),
    # 答案数字(focus=答案−题面)一律 □ 掩码;结构逐字保留。
    ("先算两个数相乘：10 × 6 = 60",
     "我们从这里入手:先算两个数相乘：10 × 6 = 60。你接着算下一步。", ()),
    ("26-16=10", "我们从这里入手:26-16=10。你接着算下一步。", ()),
    ("第二步：10 ÷ 2 = 5 只兔",
     "我们从这里入手:第二步：10 ÷ 2 = □ 只兔。你接着算下一步。", ("5",)),
    ("假设全是鸡，8只鸡有 8×2=16 只脚",
     "我们从这里入手:假设全是鸡，8只鸡有 8×2=16 只脚。你接着算下一步。", ()),
    ("8只鸡有 8×2=16 只脚",
     "我们从这里入手:8只鸡有 8×2=16 只脚。你接着算下一步。", ()),
    ("假设8只全是鸡，算出脚的总数",
     "我们从这里入手:假设8只全是鸡，算出脚的总数。你接着算下一步。", ()),
    # 序数形态:第3只 → 第□只(#185 口径:裸数字段检得出就掩)
    ("先算脚数差，第3只开始换成兔",
     "我们从这里入手:先算脚数差，第□只开始换成兔。你接着算下一步。", ("3",)),
    # 导出值形态:得到 5 → 得到 □(句子形状不破)
    ("用脚数差除以 2，得到 5",
     "我们从这里入手:用脚数差除以 2，得到 □。你接着算下一步。", ("5",)),
    ("兔有5只", "我们从这里入手:兔有□只。你接着算下一步。", ("5",)),
    # 全命中改写(复审 ①):同句多处答案数字全掩
    ("兔有5只和3只", "我们从这里入手:兔有□只和□只。你接着算下一步。", ("5", "3")),
    ("3 就是答案", "我们从这里入手:□ 就是答案。你接着算下一步。", ("3",)),
    ("3 为所求", "我们从这里入手:□ 为所求。你接着算下一步。", ("3",)),
    ("还是 3 只", "我们从这里入手:还是 □ 只。你接着算下一步。", ("3",)),
    # 双句号回归(#198):step 自带句号 → 模板只补一个(带数字入梯,#382 PR-C 切片要求)
    ("先看题里给的记法规则,数出间隔是12。",
     "我们从这里入手:先看题里给的记法规则,数出间隔是12。你接着算下一步。", ()),
], ids=["arithmetic_result_kept", "pure_expression_kept", "answer_masked_in_expr",
        "clause_boundary_kept", "no_boundary_kept", "no_arithmetic_kept",
        "ordinal_form_masked", "derived_value_masked", "answer_masked",
        "multi_hit_masked", "disclosure_frame_masked",
        "frame_word_after", "frame_word_before", "trailing_period_not_doubled"])
def test_reveal_actionization(step_text, expected_reveal, forbidden):
    """揭示句构造(#382 PR-C 起由自造 analysis 驱动,trusted 阶梯):该收回的收回、
    该保留的保留(前六 = #165 原用例,中三 = #185 序数/导出值/无边界掩码,
    后三 = #185 复审 框架词 + #198 双句号)。裸数字步整步弃用的 reveal 面
    (#185「3」形态)改由 test_trusted_ladder_boundary.py 钉——切片侧已弃 ≤3 字片。"""
    text = _reveal_after_repeat(step_text)
    assert text == expected_reveal
    for token in forbidden:
        assert token not in text


def test_reveal_keeps_question_numbers_when_answer_falls_back_to_steps_value():
    """#185 复审 ③:生产形态(question.answer 缺失 → 阶梯末值 "8 - 5 = 3" 兜底,
    答案全集 {8,5,3} 混入题面给定的 8)不得把题面数字改掉——判据集用结论数字
    (答案 − 题面,`_answer_focus_numbers`),题面数字照常放行。#382 PR-C:末值
    由自造 analysis 的末级承载(trusted 阶梯),模型 steps 不再兜底进 reveal。"""
    question = {"text": CHICKEN_QUESTION["text"], "answer": "",
                "analysis": "假设8只全是鸡，算出脚的总数8×2=16。最后算鸡有8-5=3只。",
                "knowledge_points": ["鸡兔同笼"]}
    gateway = FakeGateway(tutor_payloads=[
        _open_payload(FIRST_QUESTION_COLLECT, steps=[
            {"step": "假设8只全是鸡，算出脚的总数", "value": "8 - 5 = 3"}]),
        _tutor_payload(FIRST_QUESTION_COLLECT),
        _tutor_payload(FIRST_QUESTION_COLLECT),   # 重生成仍复读 → 揭示
    ])
    first = start(dict(question), {"grade": "六年级"}, gateway=gateway)
    turn = reply(first.session, "嗯,我看看。", gateway=gateway)
    assert turn.text == "我们从这里入手:假设8只全是鸡，算出脚的总数8×2=16。你接着算下一步。"
    assert "几" not in turn.text



def test_dropped_reveal_step_is_flagged_in_guard_events():
    """#185 复审三轮 P2:整步弃用的揭示轮在埋点里可辨识(dropped=True)——
    「阶梯消耗/是否过早烧 bottom-out」指标不把弃用轮计成正常推进;词表收放
    按这份影子数据来(先量再收)。#382 PR-C:裸数字步由自造 analysis 首级承载
    (「350 450」无汉字无算子 → 掩码后读不成句,整步弃用),模型 steps 不进 reveal。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload(FIRST_QUESTION_COLLECT, steps=[
            {"step": "3", "value": "3"}, {"step": "再算脚数差", "value": "10"}]),
        _tutor_payload(FIRST_QUESTION_COLLECT),
        _tutor_payload(FIRST_QUESTION_COLLECT),   # 重生成仍复读 → 揭示
    ])
    first = start(dict(CHICKEN_QUESTION) | {"analysis": "350 450。再算实际脚数比假设多26-16=10只。"},
                  {"grade": "六年级"}, gateway=gateway)
    turn = reply(first.session, "嗯,我看看。", gateway=gateway)
    assert turn.text == NEEDS_REVIEW_TEXT                      # 整步弃用 → 通用兜底
    assert turn.session.guard_events[-1]["branch"] == "reveal"
    assert turn.session.guard_events[-1]["dropped"] is True    # 弃用轮可辨识
    assert turn.session.guard_events[-1]["hint_level"] == 1    # 阶梯仍记消耗


# ---------- 输出面防复读终极不变量(任何兜底不得与上一轮学生可见文本同句) ----------



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


# ---------- 闭环三修(close-loop-fix,PM 2026-09-20:444a/2c85 永不闭环) ----------

def test_close_on_final_statement_zero_model_call():
    """① 收束确定化:ready 态 + 本轮消息即终述 → 直接 finish 语义,零额外模型
    调用(产线 444a:此点模型无可靠收束→复读→reveal 重发→死环)。correct 且
    无卡点 → 零调用模板(summary 引学生原话)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你现在觉得鸡和兔各有多少只?"),
        _tutor_payload("我们把思路理清楚了。", ready=True),
    ])
    session = _correct_session(gateway)
    confirmed = reply(session, "兔有10除以2等于5只,鸡有3只。", gateway=gateway)
    assert confirmed.state == "ready_to_confirm"
    calls_before = len(gateway.requests)
    turn = reply(session, "所以鸡有3只,兔有5只,验算3乘2加5乘4等于26只脚。", gateway=gateway)
    assert turn.state == "completed" and turn.session.finished
    assert len(gateway.requests) == calls_before  # 零模型调用(零调用模板收束)
    assert "3" in turn.text and "26" in turn.text  # 模板引学生原话(首末轮)


def test_close_skipped_on_ack_and_question_form_and_dialogue():
    """① 判据边界:附和(「是的,我真棒」)/问句猜答/非 ready 态 → 不收束,
    走模型路径(收束是快路径不是唯一出口;复读死环由 ② 断)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你现在觉得鸡和兔各有多少只?"),
        _tutor_payload("我们把思路理清楚了。", ready=True),
        _tutor_payload("我们再确认一遍。"),
        _tutor_payload("你想再试试吗?"),
        _tutor_payload("我们继续。"),
    ])
    session = _incorrect_session(gateway)
    confirmed = reply(session, "兔有10除以2等于5只,鸡有3只。", gateway=gateway)
    assert confirmed.state == "ready_to_confirm"
    ack = reply(session, "是的,我真棒。", gateway=gateway)  # 附和:无焦点数字
    assert ack.state != "completed" and not ack.session.finished
    guess = reply(session, "答案是3只鸡和5只兔吗?", gateway=gateway)  # 问句≠终述
    assert guess.state != "completed" and not guess.session.finished


def test_repeat_in_confirm_stage_passes_through_without_reveal():
    """② 状态感知:confirm 阶段模型复读 ≠ 卡住——不重生成、不触发 reveal,
    复读直达学生面;埋点 repeat_confirm_pass(产线 444a/2c85 死环燃料即此链)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你现在觉得鸡和兔各有多少只?"),
        _tutor_payload("我们把思路理清楚了。", ready=True),
        _tutor_payload("我们把思路理清楚了。", ready=True),  # 复读上一句
    ])
    session = _incorrect_session(gateway)
    confirmed = reply(session, "兔有10除以2等于5只,鸡有3只。", gateway=gateway)
    assert confirmed.state == "ready_to_confirm"
    calls_before = len(gateway.requests)
    turn = reply(session, "嗯,我看看。", gateway=gateway)
    assert turn.text == "我们把思路理清楚了。"  # 复读原文直达
    assert len(gateway.requests) == calls_before + 1  # 无重生成(单调用)
    events = turn.session.guard_events
    assert events[-1]["branch"] == "repeat_confirm_pass"  # turn 戳由提交统一打
    assert not any(e.get("branch") == "reveal" for e in events)
    assert turn.session.stuck is not True


# ---------- #382 PR-B:收束失败原子性(P0-2,2026-09-20 产线实录) ----------

from copy import deepcopy

from edu_agent.gateway import FailureType, GatewayError


class _ExplodingGateway(FakeGateway):
    """按调用序号注入 GatewayError 的假 gateway(冒充某次 tutor 调用失败)。"""

    def __init__(self, tutor_payloads, fail_indices: set[int]):
        super().__init__(tutor_payloads)
        self.fail_indices = fail_indices   # tutor 调用序号(0 起)命中即抛

    def invoke(self, request):
        if request.role != "vision" and len(self.requests) in self.fail_indices:
            self.requests.append({"role": request.role, "messages": request.messages})
            raise GatewayError(FailureType.UPSTREAM_5XX, "服务暂不可用")
        return super().invoke(request)


class _GarbledGateway(FakeGateway):
    """按调用序号返回非法 JSON 文本的假 gateway(finish 内 json.loads 当场崩——
    非 GatewayError 的真实注入面;#388 件1:原第三测名承诺「json 解析错」却未注入)。"""

    def __init__(self, tutor_payloads, garble_indices: set[int]):
        super().__init__(tutor_payloads)
        self.garble_indices = garble_indices   # tutor 调用序号(0 起)命中即返回非法 JSON

    def invoke(self, request):
        if request.role != "vision" and len(self.requests) in self.garble_indices:
            self.requests.append({"role": request.role, "messages": request.messages})
            response = type("R", (), {})()
            response.text = "{'summary': 截断"   # 单引号 + 截断:json.loads 必抛
            return response
        return super().invoke(request)


def _session_snapshot(session: object) -> dict:
    """验收口径:history/state/summary/session_version/hint_level 逐字段。"""
    return {
        "history": deepcopy(session.history),
        "state": session.state,
        "summary": deepcopy(session.summary),
        "session_version": session.session_version,
        "hint_level": session.hint_level,
    }


FINAL_STATEMENT = "所以鸡有3只,兔有5只,验算3乘2加5乘4等于26只脚。"


def _ready_incorrect_session(gateway: FakeGateway):
    """开一个 ready_to_confirm 的 incorrect 会话(incorrect+stuck 语义:finish 走
    模型总结,正好覆盖 GatewayError 注入位;同款会话上面的 ① 测试也在用)。"""
    session = _incorrect_session(gateway)
    confirmed = reply(session, "兔有10除以2等于5只,鸡有3只。", gateway=gateway)
    assert confirmed.state == "ready_to_confirm"
    return session


def test_close_on_gateway_error_rolls_back_session_fields():
    """#382 P0-2 验收:收束路径 GatewayError → session 逐字段回到调用前状态,
    异常原样冒泡(内核不吞、不包 retry)。产线实录:同句重发×2+GatewayError×2
    ——半提交让 history 已变而 version 未变、assistant 未提交。"""
    gateway = _ExplodingGateway(tutor_payloads=[
        _open_payload("你现在觉得鸡和兔各有多少只?"),
        _tutor_payload("我们把思路理清楚了。", ready=True),
    ], fail_indices={2})  # 第3次调用=收束轮 finish 的模型总结,这一次失败
    session = _ready_incorrect_session(gateway)
    before = _session_snapshot(session)
    with pytest.raises(GatewayError) as excinfo:
        reply(session, FINAL_STATEMENT, gateway=gateway)
    assert excinfo.value.failure.value == "upstream_5xx"
    assert _session_snapshot(session) == before   # 逐字段一致(含 history 全量)


def test_retry_same_message_after_gateway_error_no_duplicate_history():
    """#382 P0-2 验收:GatewayError 后同消息重试 → 成功收束,history 零重复
    (终述只记一次,不因失败重试双记;version 只 +1)。"""
    gateway = _ExplodingGateway(tutor_payloads=[
        _open_payload("你现在觉得鸡和兔各有多少只?"),
        _tutor_payload("我们把思路理清楚了。", ready=True),
        {"summary": "你自己讲清了鸡兔同笼的思路。"},  # 重试时 finish 的模型总结
    ], fail_indices={2})  # 第3次调用(收束轮 finish)失败;重试的第4次成功
    session = _ready_incorrect_session(gateway)
    with pytest.raises(GatewayError):
        reply(session, FINAL_STATEMENT, gateway=gateway)
    turn = reply(session, FINAL_STATEMENT, gateway=gateway)  # 同句重发(用户视角)
    assert turn.state == "completed" and session.finished
    student_turns = [m["content"] for m in session.history if m["role"] == "user"]
    assert student_turns.count(FINAL_STATEMENT) == 1   # 终述零重复
    assert turn.session_version == session.session_version  # version 只 +1


def test_close_on_other_exception_rolls_back_and_finish_paths_safe():
    """#382 P0-2 验收:非 GatewayError 异常(如 json 解析错)同样回滚;且
    needs_review / 零调用模板两条不调模型的 finish 路径不推进 Session 状态位
    (零调用收束照常 completed,历史无半提交)。

    #388 件1(审查者 P3①):真注入——收束轮 finish 的模型总结返回非法 JSON →
    json.loads 抛 JSONDecodeError(ValueError 子类,非 GatewayError),同样逐字段回滚、
    原样冒泡(注入位在 finish 置态之前,回滚面与 GatewayError 测同口径)。"""
    garbled = _GarbledGateway(tutor_payloads=[
        _open_payload("你现在觉得鸡和兔各有多少只?"),
        _tutor_payload("我们把思路理清楚了。", ready=True),
    ], garble_indices={2})  # 第3次调用=收束轮 finish 的模型总结,这次返回非法 JSON
    garbled_session = _ready_incorrect_session(garbled)
    garbled_before = _session_snapshot(garbled_session)
    with pytest.raises(ValueError) as excinfo:
        reply(garbled_session, FINAL_STATEMENT, gateway=garbled)
    assert not isinstance(excinfo.value, GatewayError)   # 非 GatewayError(json 解析错)
    assert _session_snapshot(garbled_session) == garbled_before  # 逐字段回滚
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你现在觉得鸡和兔各有多少只?"),
        _tutor_payload("我们把思路理清楚了。", ready=True),
    ])
    # 证据不足路径:非 ready 会话不触达 _close_on_final_statement,直接量 finish
    session = _incorrect_session(gateway)
    summary = finish(session, gateway=gateway)
    assert summary.status == "needs_review"
    assert session.state == "first_question_ready" and session.summary is None
    # 零调用模板路径(correct 且无卡点):收束成功,history 各一条、version+1
    ok_gateway = FakeGateway(tutor_payloads=[
        _open_payload("你现在觉得鸡和兔各有多少只?"),
        _tutor_payload("我们把思路理清楚了。", ready=True),
    ])
    ok_session = _correct_session(ok_gateway)
    confirmed = reply(ok_session, "兔有10除以2等于5只,鸡有3只。", gateway=ok_gateway)
    assert confirmed.state == "ready_to_confirm"
    turn = reply(ok_session, FINAL_STATEMENT, gateway=ok_gateway)
    assert turn.state == "completed" and ok_session.finished
    assert len(ok_session.history) == 4   # 两轮(user+assistant 各二),无半提交
    assert ok_session.session_version == 3


def test_finish_malformed_summary_payload_keyerror_pins_current_contract():
    """#388 件2(审查者 P3③):Gateway 返回畸形 payload(缺 summary 键)→ finish()
    KeyError 裸崩——内核不吞、不包 retry(§11 禁令,本测只钉现状供契约面追溯)。

    现状钉版(实证 2026-09-21,不改产品行为):_close_on_final_statement 的回滚
    接住终述入史(history/version/summary/hint_level 逐字段回调用前);但 finish
    先置 state="completed" 再取 output["summary"] → KeyError 时 state 已半提交,
    会话就此 finished 而 summary 仍 None(重试将 TerminalStateError)。若后续裁定
    修置态次序,本测红即契约变更信号——届时按新契约改断言,不静默。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你现在觉得鸡和兔各有多少只?"),
        _tutor_payload("我们把思路理清楚了。", ready=True),
        {"no_summary": True},   # 收束轮 finish 的模型总结:缺 summary 键(畸形 payload)
    ])
    session = _ready_incorrect_session(gateway)
    before = _session_snapshot(session)
    with pytest.raises(KeyError) as excinfo:
        reply(session, FINAL_STATEMENT, gateway=gateway)
    assert str(excinfo.value) == "'summary'"       # KeyError 原样冒泡(不包不吞)
    after = _session_snapshot(session)
    assert after["history"] == before["history"]   # 终述入史被回滚
    assert after["summary"] is None                # summary 未落
    assert after["session_version"] == before["session_version"]   # 版本未推进
    assert after["hint_level"] == before["hint_level"]
    assert session.state == "completed"            # 现状:state 半提交(置态先于取键)
    assert session.finished                        # 会话就此终态(summary 缺席)


def _correct_session(gateway: FakeGateway, question: dict | None = None) -> object:
    first = start(dict(question or CHICKEN_QUESTION),
                  {"grade": "六年级", "answer_status": "correct"}, gateway=gateway)
    return first.session


def test_reveal_skips_completed_subgoal():
    """③ 内容约束:reveal 不得重发已完成子目标(2c85 反面教材:「再算第二周」
    ——该步 value 数字学生早已算出)。跨消息并集判定({8,3,4} 与 {6} 分列两轮)。
    #382 PR-C:阶梯由 analysis 切片承载(trusted),模型 steps 只喂不揭示。"""
    question = {"text": "妈妈打算绣一幅面积为20dm²的十字绣。第一周绣了2/5,第二周绣的是"
                        "第一周的3/4,妈妈第二周绣了多少dm²?",
                "answer": "6dm²",
                "analysis": "先算第一周绣了20×2/5=8平方分米。再按第一周的3/4求第二周,"
                            "算第二周面积8×3/4=6平方分米。最后验算:6加8等于两周进度,"
                            "合计是14平方分米。",
                "knowledge_points": []}
    steps = [{"step": "先算第一周绣了多少平方分米", "value": "20 × 2/5 = 8"},
             {"step": "再算第二周是第一周的3/4,求第二周面积", "value": "8 × 3/4 = 6"},
             {"step": "验算:6 加 8 是否等于两周进度", "value": "8 + 6 = 14"}]
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你先说说你的想法。", steps=[dict(s) for s in steps]),
        _tutor_payload("我们先把第一周算出来。"),
        _tutor_payload("好,第二周呢?"),
        _tutor_payload("我们看下一步。"),
    ])
    session = _incorrect_session(gateway, question)
    reply(session, "第一周是20乘2/5等于8。", gateway=gateway)   # 完成子目标1
    reply(session, "第二周就8乘3/4。", gateway=gateway)         # 子目标2 数字齐(前半)
    reply(session, "是6。", gateway=gateway)                    # 子目标2 数字齐(后半)
    turn4 = reply(session, "还是不会。", gateway=gateway)        # 首次卡住 → 揭示
    skips = [e for e in turn4.session.guard_events if e.get("branch") == "reveal_step_skipped"]
    assert {e.get("hint_level") for e in skips} == {1, 2}  # 已完成的1/2级均被跳过
    assert "验算" in turn4.text  # 直达第3级(唯一未完成子目标)
    assert "第一周" not in turn4.text and "3/4" not in turn4.text  # 不重发已完成文本
