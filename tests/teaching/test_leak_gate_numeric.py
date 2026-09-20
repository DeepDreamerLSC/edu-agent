"""数值披露门(#184):数字级归因 = 唯一判据,命中即走既有修复漏斗,不误伤合法数字。

口径(断言即规格):
  · 判据 = `_reply_numbers(文本) − _drift_sources(...)[0]`,来源标签池 `answer_pool` 再分
    「泄漏(answer,对话态提前说终答)」与「幻觉(hallucinated,无任何合法来源)」;
  · 两者都拦(Thin Kernel 掩码/纯 block);#382 P0-1 后系统侧处置一律
    **不置 stuck**(guard 降级≠学生卡住,stuck 只由学生本人明确信号写入);
  · 允许集三来源(题面 / steps 值 / 学生已说)及其单步算式;确认轮不引述终答(VERDICT#6)
    结果 —— 原样放行,不替换、不置 stuck(过拦防线);
  · 句级近似判据(guardrails 的 unverified_source_value_disclosure)已删,不存第二套实现。
"""

from __future__ import annotations

from edu_agent.agents.small_lecturer import PURE_BLOCK, reply, start

from teachkit import FakeGateway

# 终答题面:answer 数字(3/5)既不在题面(8/26)也不在 step 值(16/10)里
QUESTION = {"text": "鸡兔同笼,一共 8 只,26 只脚。鸡和兔各有多少只?",
            "answer": "鸡3只兔5只", "analysis": "", "knowledge_points": ["鸡兔同笼"]}
# 全解阶梯(guard-provenance-fix ③ 后口径:模型阶梯须触答案焦点,夹具同步全解)
STEPS = [{"step": "先算鸡脚差", "value": "16"}, {"step": "再算兔脚差", "value": "10"},
         {"step": "兔的只数", "value": "5"}]
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
    ])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)

    # Thin Kernel 掩码:结构逐字保留,仅终答数值 → □;零模型零重生成
    assert turn.text == "对,答案就是鸡 □ 只、兔 □ 只。"
    assert "3" not in turn.text and "5" not in turn.text
    repair = _repairs(turn.session.guard_events)[-1]
    assert repair["rule_ids"] == ["grounded_answer_disclosure",
                                  "source_value_disclosure:answer"]  # 逐字答案 + 数字归因
    assert repair["regenerated"] is False and repair["mode"] == "masked"
    assert turn.session.stuck is not True          # 掩码=干净恢复 → 不置卡点
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
    ])
    turn = start(question, dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)

    assert turn.text == "每根夹角都是 □°,那用「北偏东□°」怎么描述呢?"
    assert "120" not in turn.text                  # 幻觉中间值不达学生面
    assert "30" not in turn.text                   # 答案独有数字也不达学生面
    repair = _repairs(turn.session.guard_events)[-1]
    assert repair["regenerated"] is False and repair["mode"] == "masked"
    assert sorted(repair["rule_ids"]) == [
        "source_value_disclosure:answer", "source_value_disclosure:hallucinated"]
    assert _gate(turn.session.guard_events)[0]["violation_sources"] == [
        {"number": 30.0, "source": "answer"}, {"number": 120.0, "source": "hallucinated"}]
    assert turn.session.stuck is not True
    assert _gate(turn.session.guard_events)[0]["violation_sources"] == [
        {"number": 30.0, "source": "answer"}, {"number": 120.0, "source": "hallucinated"}]


def test_unmaskable_violation_pure_blocks_without_stuck():
    """④纯 block(#382 P0-1 语义修订):带修饰形(前导零「05」)检得出、掩不掉
    ——词边界护体(「05」的 5 被前导 0 挡住)→ round-2 纯 block。系统侧降级
    **不再置 stuck**(guard 降级≠学生卡住,只记 guard_events mode=blocked)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?"),
        _tutor("题目里一共 05 只脚,所以兔子很多。"),
    ])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)

    assert turn.text == PURE_BLOCK
    assert "3" not in turn.text and "5" not in turn.text
    repair = _repairs(turn.session.guard_events)[-1]
    assert repair["regenerated"] is False and repair["mode"] == "blocked"
    assert turn.session.stuck is not True          # #382:纯 block 不写学生卡点
    assert "source_value_disclosure:answer" in repair["rule_ids"]


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


def test_final_answer_in_confirm_state_student_stated_echo_passes():
    """③-确认态终答(guard-provenance-fix ① 翻转 VERDICT#6):学生已述终答
    (5/3)→ 导师转述式确认**原样放行**——确认阶段命根(0.4kg 产线死锁修复);
    ready 语义保持,零修复事件。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?"),
        _tutor("对,就是 5 只兔和 3 只鸡。你讲得很清楚。", ready=True),
    ])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "兔有10除以2等于5只,鸡有3只,验算26只脚。", gateway=gateway)

    # 学生已述豁免:转述式确认原样通过,终答数字可见
    assert turn.text == "对,就是 5 只兔和 3 只鸡。你讲得很清楚。"
    assert turn.state == "ready_to_confirm" and turn.ready_to_confirm is True
    assert turn.session.stuck is not True
    assert _repairs(turn.session.guard_events) == []
    assert _gate(turn.session.guard_events)[-1]["gate"] == "observed"


def test_final_answer_in_confirm_state_unstated_still_masked():
    """③-确认态终答·首次披露对照(guard-provenance-fix ①):学生**未**述终答
    (只说了中间值)→ 导师引述终答照旧掩码——豁免只覆盖「学生已述」,首次
    披露禁令不动(掩码版转述式确认,ready 语义保持)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?"),
        _tutor("对,就是 5 只兔和 3 只鸡。你讲得很清楚。", ready=True),
    ])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "嗯,我觉得思路是对的,然后呢?", gateway=gateway)

    # 学生未述任何数字,终答 5/3 属首次披露 → 引述即掩
    assert turn.text == "对,就是 □ 只兔和 □ 只鸡。你讲得很清楚。"
    assert turn.state == "ready_to_confirm" and turn.ready_to_confirm is True
    assert "3" not in turn.text and "5" not in turn.text
    repair = _repairs(turn.session.guard_events)[-1]
    assert repair["regenerated"] is False and repair["mode"] == "masked"
    assert _gate(turn.session.guard_events)[0]["gate"] == "blocked"


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


def test_method_repair_in_confirm_state_paraphrases():
    """③-确认态 + 代喂修复(VERDICT#6 更新):方法词代喂重生成与终答引述拦截并存,
    重生成为转述式确认(无方法名、无终答数字)——两修复都不被连坐。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("先看题面说的 8 只、26 只脚,你打算先算什么?"),
        _tutor("你讲得很好,用的就是假设法,5 只兔和 3 只鸡都对。", ready=True),
        _tutor("你的思路很完整,验算也对。最后请你自己完整说一遍结论。", ready=True),
    ])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "兔有10除以2等于5只,鸡有3只,验算26只脚。", gateway=gateway)

    assert turn.text == "你的思路很完整,验算也对。最后请你自己完整说一遍结论。"
    assert turn.state == "ready_to_confirm" and turn.ready_to_confirm is True
    assert turn.session.stuck is not True
    assert "假设法" not in turn.text  # 方法名不再出现(重生成版本)
    # guard-provenance-fix ①:学生已述终答(5/3)→ 数值门零事件(转述合法);
    # 方法词代喂修复独立在案(feeds_method),不再与终答掩码连坐
    assert _repairs(turn.session.guard_events) == []
    assert any(e.get("guard") == "feeds_method" for e in turn.session.guard_events)




# --------------------------------------------------------------------------- #
# guard-provenance-fix(2026-09-19 产线事故修单):②题给已知数入池 / ③外题阶梯门
# --------------------------------------------------------------------------- #

QUESTION_25KM = {
    "text": "汽车的初始位置是(2,2),3小时后位置在(11,2)。在图中标出A、B,并求平均速度。",
    "answer": "A(2,2),B(11,2);平均75千米/时;1小时后到(11,5)。",
    "analysis": "每格25km,3小时走9格。",
    "knowledge_points": [],
}
QUESTION_EQUATION = {
    "text": "解方程 3x+7=25,并说明每一步为什么这样做。",
    "answer": "x=6",
    "analysis": "两边同时减7得3x=18,再两边除以3得x=6。",
    "knowledge_points": ["简易方程"],
}
FOREIGN_LADDER = [
    {"step": "先画出起点,然后按第一个方向走30米,标出第一个位置。", "value": "第一个位置在起点北偏西45°方向30米处。"},
    {"step": "再从第一个位置按第二个方向走30米,标出最终位置。", "value": "最终位置在第一个位置西偏南45°方向30米处。"},
    {"step": "观察最终位置相对于起点的方向,判断是哪个选项。", "value": "最终位置在起点的西南方向。"},
]


def test_analysis_given_numbers_pass_unchanged():
    """②-题给已知数(产线 6a61af03):图题给定值只在图与解析里(题面文本无 25),
    学生已数出 9 格 → 导师复述「每格代表25千米」原样放行(修复前被误判
    hallucinated 掩成 □,题目无解)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("你看到题目里的格子了吗?先说说你数出了几格。", steps=[]),
        _tutor("你数对了9格,这说明汽车3小时走了9格,每格代表25千米,那速度怎么算呢?"),
    ])
    turn = start(dict(QUESTION_25KM), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "有9格", gateway=gateway)

    assert turn.text == "你数对了9格,这说明汽车3小时走了9格,每格代表25千米,那速度怎么算呢?"
    assert _repairs(turn.session.guard_events) == []


def test_analysis_answer_value_not_whitelisted():
    """②-边界:解析文本里写出的终答(「得x=6」的 6)按值剥出允许集——analysis
    非学生可见面,不得经解析把终答洗白;学生未述 6 时导师引述照旧掩码。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("我们来看这个方程,两边各是什么?", steps=[]),
        _tutor("两边同时减7再除以3,所以x=6,你验证一下。"),
    ])
    turn = start(dict(QUESTION_EQUATION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "嗯,我先试试。", gateway=gateway)

    assert "x=6" not in turn.text and "6" not in turn.text.replace("26", "").replace("16", "")
    assert _repairs(turn.session.guard_events)[-1]["mode"] == "masked"


def test_foreign_ladder_dropped_and_reveal_falls_back():
    """③-外题阶梯门(产线 6a61af03):open-solve 生成他题阶梯(45°/30米/选项
    判定,终值不含任何答案焦点数字)→ 整副弃用;卡住轮 reveal 走兜底问句,
    30/45 不出现在任何导师文本(修复前 reveal 回放「按第一个方向走30米」串题)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("你先说说打算怎么找A和B的位置。", steps=[dict(s) for s in FOREIGN_LADDER]),
    ])
    turn = start(dict(QUESTION_25KM), dict(LEARNER), gateway=gateway)

    assert turn.session.steps == []
    dropped = [e for e in turn.session.guard_events if e.get("branch") == "foreign_ladder_dropped"]
    assert dropped and "30" not in dropped[0]["terminal_value"] or dropped  # 事件在案

    turn = reply(turn.session, "我不会", gateway=gateway)
    assert "30" not in turn.text and "45" not in turn.text
    assert turn.session.steps == []


def test_legit_ladder_terminal_value_kept():
    """③-对照:终值抵达答案焦点数字的阶梯照常保留(0.4kg 案合法阶梯
    「计算2×1/5的结果」终值 0.4 = 答案焦点)——门只弃外题阶梯,不误伤。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("你先说说打算怎么算。", steps=[
            {"step": "先把水的总重量2kg看作单位1", "value": "2 kg"},
            {"step": "求它的1/5,就是用2kg乘以1/5", "value": "2 × 1/5"},
            {"step": "计算2×1/5的结果", "value": "0.4 kg"},
        ]),
    ])
    question = {"text": "一瓶水重2kg,求它的1/5是多少重。", "answer": "0.4kg",
                "analysis": "求一个数的几分之几。", "knowledge_points": []}
    turn = start(question, dict(LEARNER), gateway=gateway)

    assert len(turn.session.steps) == 3
    assert not [e for e in turn.session.guard_events if e.get("branch") == "foreign_ladder_dropped"]


def test_question_form_guess_not_stated_boundary():
    """追加边界(PM 追加令探针 1):学生问句猜答「是不是0.4千克?」≠ 陈述已述
    ——数字不入学生池,导师直 confirm 引述=首次披露,照旧掩码;对照:同数字
    陈述式说出(「那就是0.4千克。」)→ 转述放行(上方翻转测试)。"""
    question = {"text": "一瓶水重2kg,求它的1/5是多少重。", "answer": "0.4kg",
                "analysis": "", "knowledge_points": []}
    gateway = FakeGateway(tutor_payloads=[
        _open("你先说说你的想法。", steps=[]),
        _tutor("对,就是 0.4 千克,你猜对了。", ready=True),
    ])
    turn = start(dict(question), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "答案是不是0.4千克呢?", gateway=gateway)

    assert turn.text == "对,就是 □ 千克,你猜对了。"
    repair = _repairs(turn.session.guard_events)[-1]
    assert repair["regenerated"] is False and repair["mode"] == "masked"


def test_mid_dialogue_authoritative_string_echo_student_stated_passes():
    """guard-provenance-fix ① 值级补全(A/B 跑面揭出):学生说「0.4千克」(陈述),
    权威答案串是「0.4kg」——字符串粒度豁免漏放,学生刚答完还吃「不能直接给出」。
    值级注入后:对话态复述权威串不再句级拦截(数字池早已放行,两门口径对齐)。"""
    question = {"text": "一瓶水重2kg,求它的1/5是多少重。", "answer": "0.4kg",
                "analysis": "", "knowledge_points": []}
    gateway = FakeGateway(tutor_payloads=[
        _open("你先说说你的想法。", steps=[]),
        _tutor("你用2000克除以5得到400克,这个换算和计算都没问题!", ready=False),
        _tutor("你刚才说2kg等于2000克,除以5得400克,再换算成0.4kg,这三步都对!",
               ready=False),
    ])
    turn = start(dict(question), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "2千克就是2000克,然后除以5得到了400。", gateway=gateway)
    turn = reply(turn.session, "那就是0.4千克。", gateway=gateway)

    assert turn.text == "你刚才说2kg等于2000克,除以5得400克,再换算成0.4kg,这三步都对!"
    assert _repairs(turn.session.guard_events) == []
