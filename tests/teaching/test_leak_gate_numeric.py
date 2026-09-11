"""数值披露门(#184):数字级归因 = 唯一判据,命中即走既有修复漏斗,不误伤合法数字。

口径(断言即规格):
  · 判据 = `_reply_numbers(文本) − _drift_sources(...)[0]`,来源标签池 `answer_pool` 再分
    「泄漏(answer,对话态提前说终答)」与「幻觉(hallucinated,无任何合法来源)」;
  · 两者都拦(重生成 → 兜底),`stuck` **只在修复失败落兜底句时**置;
  · 允许集四来源(题面 / steps 值 / 学生已说 / ready_to_confirm 态终答)及其单步算式
    结果 —— 原样放行,不替换、不置 stuck(过拦防线);
  · 句级近似判据(guardrails 的 unverified_source_value_disclosure)已删,不存第二套实现。
"""

from __future__ import annotations

from edu_agent.agents.small_lecturer import reply, start

from test_drift_and_tone import FakeGateway

# 终答题面:answer 数字(3/5)既不在题面(8/26)也不在 step 值(16/10)里
QUESTION = {"text": "鸡兔同笼,一共 8 只,26 只脚。鸡和兔各有多少只?",
            "answer": "鸡3只兔5只", "analysis": "", "knowledge_points": ["鸡兔同笼"]}
STEPS = [{"step": "先算鸡脚", "value": "16"}, {"step": "再算兔脚", "value": "10"}]
LEARNER = {"grade": "六年级", "name": "小明"}
# 学生说过的中间值 4(题面/阶梯都没有)→ 「学生已说」这一来源的专门载体
STUDENT_SAID = "我觉得鸡有4只。"
# 学生验算(5乘4、3乘2)→ 算式结果 20/6 属「学生已说」的算式结果
STUDENT_CHECK = "验算:5乘4等于20,加3乘2等于26。"


def _open(reply_text: str, steps: list[dict] | None = None) -> dict:
    return {"reply": reply_text, "ready_to_confirm": False, "cited_numbers": [],
            "steps": steps if steps is not None else STEPS}


def _tutor(reply_text: str, ready: bool = False) -> dict:
    return {"reply": reply_text, "ready_to_confirm": ready, "cited_numbers": []}


def _gate(events: list[dict], branch: str = "model") -> list[dict]:
    return [event for event in events if event.get("branch") == branch]


def _repairs(events: list[dict]) -> list[dict]:
    return [event for event in events if event.get("guard") == "answer_leak"]


# --------------------------------------------------------------------------- #
# ①/② 泄漏与幻觉都要拦,且事件带 rule_ids / regenerated 且能分辨来源
# --------------------------------------------------------------------------- #

def test_answer_only_number_is_intercepted_and_repaired():
    """①泄漏:回复含「答案独有数字」3/5(题面与阶梯都没有)→ 不达学生面 + 事件留痕。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?"),
        _tutor("对,答案就是鸡 3 只、兔 5 只。"),
        _tutor("不错,那这一步你打算先算哪一个?"),
    ])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)

    assert turn.text == "不错,那这一步你打算先算哪一个?"  # 泄漏原文被重生成换下
    assert "3" not in turn.text and "5" not in turn.text
    repair = _repairs(turn.session.guard_events)[-1]
    assert repair["rule_ids"] == ["grounded_answer_disclosure",
                                  "source_value_disclosure:answer"]  # 逐字答案 + 数字归因
    assert repair["regenerated"] is True           # 走了既有漏斗:重生成修好
    assert turn.session.stuck is not True          # 修好 → 不置卡点(改动 3)
    observed = _gate(turn.session.guard_events)[0]
    assert observed["gate"] == "blocked"           # 检测 ≠ 放行:同一份归因即门
    assert observed["violation_sources"] == [
        {"number": 3.0, "source": "answer"}, {"number": 5.0, "source": "answer"}]


def test_hallucinated_number_is_intercepted_like_issue_184():
    """②幻觉:#184 实弹形态——老师引入学生从未说过的中间值(120°),同样拦住。"""
    question = {"text": "等边三角形,每边 20m。说出三条边的方位。",
                "answer": "北偏西30°20m;北偏东30°20m", "analysis": "",
                "knowledge_points": ["方位"]}
    # 阶梯只到「先定一个方向」:30 是**答案独有**数字(不在题面/阶梯/学生话里)
    steps = [{"step": "先定夹角", "value": "20m"}, {"step": "再定方向", "value": "先看一条边"}]
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面给的 20m,你打算从哪里入手?", steps),
        # 复刻 #184 实弹:同一轮里「答案级」30°(北偏东30°)与「推理级」120°同时出现
        _tutor("每根夹角都是 120°,那用「北偏东30°」怎么描述呢?"),
        _tutor("先定一个方向,你打算先看哪根?"),
    ])
    turn = start(question, dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)

    assert turn.text == "先定一个方向,你打算先看哪根?"
    assert "120" not in turn.text                  # 幻觉中间值不达学生面
    assert "30" not in turn.text                   # 答案独有数字也不达学生面
    repair = _repairs(turn.session.guard_events)[-1]
    assert repair["regenerated"] is True
    assert sorted(repair["rule_ids"]) == [
        "source_value_disclosure:answer", "source_value_disclosure:hallucinated"]
    assert _gate(turn.session.guard_events)[0]["violation_sources"] == [
        {"number": 30.0, "source": "answer"}, {"number": 120.0, "source": "hallucinated"}]
    assert turn.session.stuck is not True
    assert _gate(turn.session.guard_events)[0]["violation_sources"] == [
        {"number": 30.0, "source": "answer"}, {"number": 120.0, "source": "hallucinated"}]


def test_violation_without_repair_falls_back_and_marks_stuck():
    """④兜底才置 stuck:重生成仍越界 → 落兜底句,此时才是卡点(埋点 regenerated=False)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?"),
        _tutor("题目里一共 36 只脚,所以兔子很多。"),
        _tutor("题目里一共 36 只脚,兔子就是 9 只。"),  # 重生成仍越界 → 兜底
        _tutor("那我们先回到题目条件上,你打算先算哪一个?"),
    ])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)

    assert "36" not in turn.text and "9" not in turn.text
    repair = _repairs(turn.session.guard_events)[-1]
    assert repair["regenerated"] is False          # 兜底句(修复失败)
    assert turn.session.stuck is True              # 只有这条路径置卡点
    assert "hallucinated" in repair["rule_ids"][0]


# --------------------------------------------------------------------------- #
# ③ 不误伤:四个来源 + 学生算式结果,全部原样放行(不替换、不置 stuck)
# --------------------------------------------------------------------------- #

def test_question_statement_numbers_pass_unchanged():
    """③-题面数字:回复复述题面条件(8/26)→ 原样达学生面,零拦截事件。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?"),
        _tutor("题目里有 8 只、26 只脚。你想先算哪一个?"),
    ])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)

    assert turn.text == "题目里有 8 只、26 只脚。你想先算哪一个?"  # 未被替换
    assert turn.session.stuck is not True
    assert _repairs(turn.session.guard_events) == []
    assert len(gateway.requests) == 2              # 无额外重生成调用
    assert _gate(turn.session.guard_events)[0]["violation_sources"] == []


def test_step_value_numbers_pass_unchanged():
    """③-阶梯值数字:回复引用 steps 值(16)→ 原样放行。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?"),
        _tutor("这一步我们得到 16。接着算哪一步?"),
    ])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)

    assert turn.text == "这一步我们得到 16。接着算哪一步?"
    assert turn.session.stuck is not True
    assert _repairs(turn.session.guard_events) == []
    assert len(gateway.requests) == 2


def test_student_utterance_numbers_pass_unchanged():
    """③-学生已说数字:4 既不在题面也不在阶梯,但学生本轮说过 → 原样放行。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?"),
        _tutor("你说鸡有 4 只,那兔就是 4 只。这个思路我们看看。"),
    ])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, STUDENT_SAID, gateway=gateway)

    assert turn.text == "你说鸡有 4 只,那兔就是 4 只。这个思路我们看看。"
    assert turn.session.stuck is not True
    assert _repairs(turn.session.guard_events) == []
    assert len(gateway.requests) == 2


def test_student_arithmetic_results_pass_unchanged():
    """③-学生算式结果:学生验算 5乘4/3乘2(学生已写出的算式结果 20/6)不算幻觉。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?"),
        _tutor("你验算的 20 和 6 没问题,我们接着看下一步。"),
    ])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, STUDENT_CHECK, gateway=gateway)

    assert turn.text == "你验算的 20 和 6 没问题,我们接着看下一步。"
    assert turn.session.stuck is not True
    assert _repairs(turn.session.guard_events) == []
    assert len(gateway.requests) == 2


def test_final_answer_in_confirm_state_passes_unchanged():
    """③-确认态终答:学生已陈述答案 → 模型判停确认(5/3 在允许集)→ 原样放行。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?"),
        _tutor("对,就是 5 只兔和 3 只鸡。你讲得很清楚。", ready=True),
    ])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "兔有10除以2等于5只,鸡有3只,验算26只脚。", gateway=gateway)

    assert turn.text == "对,就是 5 只兔和 3 只鸡。你讲得很清楚。"
    assert turn.state == "ready_to_confirm" and turn.ready_to_confirm is True
    assert turn.session.stuck is not True
    assert _repairs(turn.session.guard_events) == []
    assert len(gateway.requests) == 2


# --------------------------------------------------------------------------- #
# 单源:门与「来源允许集」是同一份计算(#184「禁止出现第二套判据」)
# --------------------------------------------------------------------------- #

def test_gate_and_repair_rule_ids_come_from_one_computation():
    """单源:拦截 `rule_ids` 的来源标签 = 观测事件 `violation_sources` 的来源(同一份归因)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?"),
        _tutor("题目里一共 36 只脚。"),
        _tutor("先看题目给的 26 只脚,你觉得该先算什么?"),
    ])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)
    events = turn.session.guard_events
    observed = _gate(events)[0]
    repair = _repairs(events)[-1]

    assert observed["extracted"] == [36.0]                       # 抽取口径(唯一一处)
    assert observed["violation_sources"] == [{"number": 36.0, "source": "hallucinated"}]
    assert repair["rule_ids"] == ["source_value_disclosure:hallucinated"]  # 同源标签
    assert "36" not in turn.text


def test_method_repair_keeps_confirm_state_pool():
    """③-确认态 + 代喂修复:模型点名方法词时走代喂重生成,该次判定仍按确认态取池
    (学生已说终答 → 5/3 合法),不再误判成 answer 违规 → 确认语义不被连坐丢掉。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?"),
        _tutor("你讲得很好,用的就是假设法,5 只兔和 3 只鸡都对。", ready=True),
        _tutor("对,就是 5 只兔和 3 只鸡,你讲得很清楚。", ready=True),
    ])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "兔有10除以2等于5只,鸡有3只,验算26只脚。", gateway=gateway)

    assert turn.text == "对,就是 5 只兔和 3 只鸡,你讲得很清楚。"
    assert turn.state == "ready_to_confirm" and turn.ready_to_confirm is True
    assert turn.session.stuck is not True
    assert _repairs(turn.session.guard_events) == []      # 数值门未误伤确认轮
    repair = [e for e in turn.session.guard_events if e.get("guard") == "feeds_method"][-1]
    assert repair["mode"] == "regenerated"                # 重生成修好,不落脱敏
