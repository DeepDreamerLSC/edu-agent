"""M3 收官合同:数字漂移守卫 + 教学语气(prompt 引导非硬护栏)。

gateway 对象注入(零网络零端口,确定性);断言即规格。
"""

from __future__ import annotations

import json

from edu_agent.agents.small_lecturer import reply, start


class FakeGateway:
    """对象注入假 gateway:vision/tutor 按脚本出牌,记录全部请求。"""

    def __init__(self, tutor_payloads: list[dict],
                 vision_payloads: list[dict] | None = None):
        self.tutor_queue = list(tutor_payloads)
        self.vision_queue = list(vision_payloads or [])
        self.requests: list[dict] = []

    def invoke(self, request):
        self.requests.append({"role": request.role, "messages": request.messages})
        payload = (self.vision_queue.pop(0) if request.role == "vision" and self.vision_queue
                   else self.tutor_queue.pop(0) if self.tutor_queue
                   else {"reply": "先回到当前小问。", "ready_to_confirm": False,
                         "cited_numbers": []})
        response = type("R", (), {})()
        response.text = json.dumps(payload, ensure_ascii=False)
        return response


# 漂移/语气测试与泄露护栏正交:题面不含 answer/analysis(泄露对照误判数字
# 回复的根因修复走独立 guardrails PR,见 #34)
QUESTION = {"text": "鸡和兔一共 8 只,共有 26 只脚。鸡和兔各有多少只?说明思路。",
            "answer": "", "analysis": "", "knowledge_points": ["鸡兔同笼", "假设法"]}
LEARNER = {"grade": "六年级", "name": "小明"}


def test_cited_numbers_within_face_not_stuck():
    # 模型引用 8/26 都来自题面 → 不标卡点;申报进 schema 输出(模型义务非输入)
    gateway = FakeGateway(tutor_payloads=[
        {"reply": "先看鸡:8×2=16。", "ready_to_confirm": False, "cited_numbers": [8]},
        {"reply": "26-16=10,差值是兔脚。", "ready_to_confirm": False,
         "cited_numbers": [26]},
    ])
    question = dict(QUESTION)
    turn = start(question, dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "16 只脚对不上 26", gateway=gateway)
    assert turn.session.stuck is not True
    turn_request = [r for r in gateway.requests if r["role"] == "tutor"][0]
    assert "cited_numbers" not in json.dumps(turn_request["messages"])


def test_cited_number_outside_face_marks_stuck():
    # 数字漂移:模型把口误数字 36 当题目条件复读(题面只有 8/26)→ stuck
    gateway = FakeGateway(tutor_payloads=[
        {"reply": "先看鸡:8×2=16。", "ready_to_confirm": False, "cited_numbers": [8]},
        {"reply": "题目里一共 36 只脚,所以兔子很多。", "ready_to_confirm": False,
         "cited_numbers": [36]},
    ])
    question = dict(QUESTION)
    turn = start(question, dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "36 只脚?", gateway=gateway)
    assert turn.session.stuck is True  # 下轮提醒(照 R6 卡点模式)


def test_student_echoed_number_currently_marks_stuck():
    # 已知边界(留人裁决,见 #34):学生自己说错的数字被模型纠偏复述时,
    # 按现行字面规则(⊆ 题面)也标 stuck——纠偏场景会误标,待人定扩集口径
    gateway = FakeGateway(tutor_payloads=[
        {"reply": "先看题面:8 只,26 只脚。", "ready_to_confirm": False, "cited_numbers": []},
        {"reply": "你说 16 只脚,如果全是鸡,8×2=16,和 26 矛盾。", "ready_to_confirm": False,
         "cited_numbers": [16]},
    ])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "16 只脚对不上", gateway=gateway)
    assert turn.session.stuck is True  # 现行行为:学生数字同判漂移(边界待裁决)


def test_question_without_numbers_skips_drift_guard():
    # 题面无数字 → 跳过校验(几何题等)
    question = {"text": "说明三角形的内角和有什么特点。", "answer": "180 度",
                "analysis": "", "knowledge_points": []}
    gateway = FakeGateway(tutor_payloads=[
        {"reply": "三角形有三个角。", "ready_to_confirm": False, "cited_numbers": [3]},
    ])
    turn = start(question, dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "三个角", gateway=gateway)
    assert turn.session.stuck is not True


def test_tone_is_prompt_guided_not_hard_guardrail():
    # 语气是 prompt 引导:直白无鼓励的合法教学回复不被硬护栏拦截
    # (start 单步断言;reply 链的额外变量与本合同无关)
    gateway = FakeGateway(tutor_payloads=[
        {"reply": "16 只脚对应 8 只鸡,与题面 26 只脚矛盾。", "ready_to_confirm": False,
         "cited_numbers": [16, 26]},
    ])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    assert turn.text == "16 只脚对应 8 只鸡,与题面 26 只脚矛盾。"


def test_tone_directive_in_system_prompt():
    # 语气指令进 system prompt(稳定→cache 友好):亲切温暖/不起名/友好开场/
    # 40 字上限/基调随对错;方向性指令,不硬编码句子
    from edu_agent.agents.small_lecturer import system_prompt
    system_message = system_prompt("六年级")
    for directive in ("亲切", "温暖", "名字", "开场", "40 字", "基调",
                      "波利亚", "苏格拉底"):
        assert directive in system_message, directive


def test_mission_directive_frames_role_and_forbids_method_names():
    # 角色与方法框架(演示联调定稿):学习指导老师 + 波利亚拆步骤依次引导;
    # 两个方法名只住教师侧,指令明确对话中不出现
    from edu_agent.agents.small_lecturer import system_prompt
    system_message = system_prompt("六年级")
    assert "学习指导老师" in system_message
    assert "依次逐个引导" in system_message
    assert "不出现「波利亚」「苏格拉底」" in system_message


def test_tone_directive_forbids_naming_and_empty_praise():
    # 称呼与激励方向(演示反馈 2026-09-08):不起名/不借题面人名;答错不空夸——
    # 方向性约束写进指令,不写死话术
    from edu_agent.agents.small_lecturer import system_prompt
    system_message = system_prompt("六年级")
    assert "不给学习者起名" in system_message
    assert "题目角色" in system_message
    assert "不空夸" in system_message
    assert "没关系" not in system_message  # 不写死具体话术
