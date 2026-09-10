"""#149 判停闸 + 护栏答案基线:断言即规格(gateway 对象注入,零网络零端口)。

口径要点:
- `ready_to_confirm` 只是模型建议,判停权威在确定性验证层(学生是否已陈述答案数字集);
- 判据与 #112 共用同一套 `_hits_answer_numbers`,不出现第二套;
- fail-open:答案取不到数字(文字/字母类)时不闸;
- 闸后处置走既有 `_regenerate`(不新增学生可见模板、不删词);
- 护栏答案基线统一 `_known_answer`(answer 优先、steps 末值兜底)。
"""

from __future__ import annotations

import json

from edu_agent.agents.small_lecturer import reply, start


class FakeGateway:
    """按脚本出牌的假 gateway(与 test_drift_and_tone 同款对象注入)。"""

    def __init__(self, tutor_payloads: list[dict]):
        self.tutor_queue = list(tutor_payloads)
        self.requests: list[dict] = []

    def invoke(self, request):
        self.requests.append({"role": request.role, "messages": request.messages})
        payload = (self.tutor_queue.pop(0) if self.tutor_queue
                   else {"reply": "先说说你的下一步准备算什么?", "ready_to_confirm": False,
                         "cited_numbers": []})
        response = type("R", (), {})()
        response.text = json.dumps(payload, ensure_ascii=False)
        return response


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


def test_gate_blocks_premature_confirm_and_rewrites():
    """学生未陈述答案 → 判停被闸,状态回 dialogue,答案不进学生可见文本。"""
    gateway = FakeGateway([OPEN_PAYLOAD, PREMATURE_PAYLOAD, CONTINUE_PAYLOAD])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, STUDENT_NOT_YET, gateway=gateway)
    assert turn.state == "dialogue"                # 不判停:复讲步/后续步骤还有机会
    assert turn.ready_to_confirm is False
    assert turn.text == CONTINUE_PAYLOAD["reply"]  # 原「收尾」被重写成继续引导
    assert any(event.get("guard") == "premature_confirm"
               for event in turn.session.guard_events)
    # 处置 = 既有 refiner 路径(第二次 tutor 调用带重写指令),不是新增模板替换
    assert len([r for r in gateway.requests if r["role"] == "tutor"]) == 3


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
    turn = reply(turn.session, "兔5只,鸡3只。", gateway=gateway)  # 换序说出答案
    assert turn.ready_to_confirm is False                          # 不判停:转确定性复讲
    assert any(event.get("branch") == "elicit" for event in turn.session.guard_events)


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
