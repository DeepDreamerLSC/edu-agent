"""#149 判停闸 + 护栏答案基线:断言即规格(gateway 对象注入,零网络零端口)。

口径要点:
- `ready_to_confirm` 只是模型建议,判停权威在确定性验证层(学生是否已陈述答案数字集);
- 判据与 #112 共用同一套 `_hits_answer_numbers`,不出现第二套;
- fail-open:答案取不到数字(文字/字母类)时不闸;
- 闸后处置走既有 `_regenerate`(不新增学生可见模板、不删词);
- 护栏答案基线统一 `_known_answer`(answer 优先、steps 末值兜底)。
"""

from __future__ import annotations

from edu_agent.agents.small_lecturer import finish, reply, start

from teachkit import FakeGateway


QUESTION = {"text": "图书馆原有120本故事书,又买来45本,借出38本,现在有多少本?",
            "answer": "127本", "analysis": "", "knowledge_points": []}
LEARNER = {"grade": "三年级", "name": "小明"}
OPEN_PAYLOAD = {"reply": "这道题你怎么想?先说说看。", "acceptable": True,
                "steps": [{"step": "先算又买来之后一共有多少本", "value": "165"},
                          {"step": "再减去借出的", "value": "127"}]}
# 学生尚未说出 127(只说「借出要减掉」),模型却提前确认并把答案讲完 —— #149 实测缺口
STUDENT_NOT_YET = "借出表示数量减少,不能也加上38。"
PREMATURE_PAYLOAD = {"reply": "好,你已经完全明白了,这道题我们就到这里。",
                     "ready_to_confirm": True, "cited_numbers": []}
CONTINUE_PAYLOAD = {"reply": "你说得对,借出要减掉。那先算又买来之后一共有多少本?",
                    "ready_to_confirm": False, "cited_numbers": []}


def test_premature_confirm_gate_removed_thin_semantics():
    """Thin Kernel(#333 终裁):premature_confirm 闸已删(拆台者:judge+3/状态翻回/
    介入率减半)——模型判停直通,不再重写;判停质量归 Prompt/Model 面。"""
    gateway = FakeGateway([OPEN_PAYLOAD, PREMATURE_PAYLOAD])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, STUDENT_NOT_YET, gateway=gateway)
    assert turn.state == "ready_to_confirm"        # 判停直通(闸已删)
    assert turn.ready_to_confirm is True
    assert turn.text == PREMATURE_PAYLOAD["reply"]
    assert not any(event.get("guard") == "premature_confirm"
                   for event in turn.session.guard_events)
    assert len([r for r in gateway.requests if r["role"] == "tutor"]) == 2  # 零重生成


def test_gate_allows_confirm_when_student_stated_answer():
    """合法确认仍放行:学生自己已说出命中答案的数字集。"""
    gateway = FakeGateway([
        OPEN_PAYLOAD,
        {"reply": "对,就是 127 本。你讲得很清楚。", "ready_to_confirm": True,
         "cited_numbers": [127]},
    ])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "先算 120 加 45 等于 165,再减 38 等于 127 本。", gateway=gateway)
    assert turn.state == "ready_to_confirm"
    assert turn.ready_to_confirm is True
    assert not any(event.get("guard") == "premature_confirm"
                   for event in turn.session.guard_events)


def test_gate_fail_open_when_answer_has_no_digits():
    """fail-open:答案取不到数字(文字类)→ 不闸,确认照常放行。"""
    question = {"text": "看图说一说,倒出的水量应该选哪一个?", "answer": "选项C",
                "analysis": "", "knowledge_points": []}
    gateway = FakeGateway([
        {"reply": "你觉得先看哪里?", "acceptable": True,
         "steps": [{"step": "读两量杯图", "value": "看剩余水量"}]},
        {"reply": "对,就选这个。", "ready_to_confirm": True, "cited_numbers": []},
    ])
    turn = start(question, dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "我觉得是C。", gateway=gateway)
    assert turn.state == "ready_to_confirm"
    assert not any(event.get("guard") == "premature_confirm"
                   for event in turn.session.guard_events)


def test_shared_judge_core_order_insensitive_via_public_path():
    """抽核判据(#112 触发与判停闸共用):数字集包含、顺序不敏感 —— 公开路径验证。"""
    question = {"text": "鸡和兔一共 8 只,共有 26 只脚。鸡和兔各有多少只?",
                "answer": "鸡3只,兔5只", "analysis": "", "knowledge_points": []}
    learner = {"grade": "六年级", "answer_status": "incorrect"}
    gateway = FakeGateway([OPEN_PAYLOAD,
                           {"reply": "先看脚数特点,你猜猜如果全是鸡脚会是多少只?",
                            "ready_to_confirm": False, "cited_numbers": []}])
    turn = start(question, learner, gateway=gateway)
    turn = reply(turn.session, "我先假设 8 只全是鸡。", gateway=gateway)
    assert turn.state == "dialogue"
    gateway.tutor_queue.append({"reply": "对,你说出了结论。", "ready_to_confirm": True,
                                "cited_numbers": []})
    turn = reply(turn.session, "兔5只,鸡3只。", gateway=gateway)  # 换序说出答案
    assert turn.ready_to_confirm is True  # 陈述在案 → 模型判停直通(elicit 已删)


def test_leak_guard_baseline_falls_back_to_steps_value():
    """② 护栏基线统一:`answer` 空时取 steps 末值 → 评测侧(只传题面)护栏也能生效。"""
    question = {"text": "图书馆原有120本故事书,又买来45本,借出38本,现在有多少本?",
                "answer": "", "analysis": "", "knowledge_points": []}
    gateway = FakeGateway([
        OPEN_PAYLOAD,
        {"reply": "答案是 127 本。", "ready_to_confirm": False, "cited_numbers": [127]},
        CONTINUE_PAYLOAD,
    ])
    turn = start(question, dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "我把三个数直接加在一起。", gateway=gateway)
    assert "127" not in turn.text
    assert any(event.get("guard") == "answer_leak" for event in turn.session.guard_events)


# ---------- #165 WS4 第 1 条:守卫粒度(末轮已陈述终答不推 needs_review) ----------

# 实测复现(run 34502985698,chicken_rabbit):模型阶梯末级 value 是**算式**
# 「8 - 5 = 3」→ 答案数字 {3,5,8};8 是题面已给的总数,学生收束轮不会再复述它。
CHICKEN_QUESTION_EVAL = {"text": "鸡和兔一共 8 只,共有 26 只脚。鸡和兔各有多少只?",
                         "answer": "", "analysis": "", "knowledge_points": []}
CHICKEN_OPEN = {"reply": "你已经知道鸡和兔一共有8只,脚数是26只,对吗?",
                "acceptable": True,
                "steps": [{"step": "假设全是鸡,算脚的总数", "value": "8 × 2 = 16"},
                          {"step": "算实际多出的脚", "value": "26 - 16 = 10"},
                          {"step": "算兔有几只", "value": "10 ÷ 2 = 5"},
                          {"step": "算鸡有几只", "value": "8 - 5 = 3"}]}
CHICKEN_STATED = "所以兔有10除以2等于5只,鸡有3只,检查5乘4加3乘2等于26。"
CHICKEN_CONFIRM = {"reply": "你算得完全对!5只兔和3只鸡,脚数正好是26,这方法真棒!",
                   "ready_to_confirm": True, "cited_numbers": [5, 3, 26]}


def test_gate_allows_confirm_when_student_stated_conclusion_numbers():
    """答案数字里的**题面给定数字不计入**「是否已陈述」判据:学生末轮说出结论(兔5鸡3、
    验算26)即可收束 —— 不要求复述题面已给的 8(实测该缺口让闸门在收束轮误触发)。"""
    gateway = FakeGateway([CHICKEN_OPEN, CHICKEN_CONFIRM])
    turn = start(dict(CHICKEN_QUESTION_EVAL), {"grade": "六年级"}, gateway=gateway)
    turn = reply(turn.session, CHICKEN_STATED, gateway=gateway)
    assert turn.state == "ready_to_confirm"        # 闸未触发:合法确认放行
    assert turn.ready_to_confirm is True
    assert not any(event.get("guard") == "premature_confirm"
                   for event in turn.session.guard_events)


def test_finish_completes_instead_of_needs_review_after_stated_answer():
    """验收:学生已陈述终答的末轮 → 会话正常收束 completed,不再落 needs_review。"""
    gateway = FakeGateway([
        CHICKEN_OPEN,
        # Thin Kernel:引述终答(5/3)→ 确定性掩码(转述式确认,零重生成)
        CHICKEN_CONFIRM,
        {"summary": "你假设全是鸡,算出脚数差,再把兔子换出来——讲得很清楚。"},
    ])
    turn = start(dict(CHICKEN_QUESTION_EVAL), {"grade": "六年级"}, gateway=gateway)
    turn = reply(turn.session, CHICKEN_STATED, gateway=gateway)
    summary = finish(turn.session, gateway=gateway)
    assert summary.status == "completed"
    assert summary.status != "needs_review"


def test_given_number_restatement_no_kernel_intervention():
    """Thin Kernel:只说题面数字 → 无确定性干预(闸已删),模型判停照走;
    「题面数不算陈述」判据本身仍活在 numeric(_answer_focus_numbers),单元面钉。"""
    gateway = FakeGateway([CHICKEN_OPEN, CHICKEN_CONFIRM])
    turn = start(dict(CHICKEN_QUESTION_EVAL), {"grade": "六年级"}, gateway=gateway)
    turn = reply(turn.session, "题目说一共 8 只、26 只脚。", gateway=gateway)
    # 学生未陈述终答 → 模型引述 5/3 被掩码护住(A 类);判停本身直通(pc 闸已删)
    assert turn.text == "你算得完全对!□只兔和□只鸡,脚数正好是26,这方法真棒!"
    assert not any("premature_confirm" in str(e) for e in turn.session.guard_events)
