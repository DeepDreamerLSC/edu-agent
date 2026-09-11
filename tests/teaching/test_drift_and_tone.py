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


def test_extracted_numbers_within_allowed_not_stuck():
    # 抽取制:回复文本里的数字全在允许池(题面8/26 + 中间 step 值16)→ 不标卡点;
    # cited_numbers 保留(影子对照),守卫判定改抽 output.reply。
    # 阶梯两级(#157 评审末值边界):无 answer 题面下末级 10 是已知答案兜底,
    # 16 为中间值——引用中间值合法,引用末级见 kernel_invariants 洗白测试
    gateway = FakeGateway(tutor_payloads=[
        {"reply": "先看题面说的 8 只、26 只脚,你打算先算什么?", "ready_to_confirm": False,
         "cited_numbers": [], "steps": [{"step": "鸡脚", "value": "16"},
                                        {"step": "兔脚", "value": "10"}]},
        {"reply": "这一步得到 16。", "ready_to_confirm": False, "cited_numbers": [16]},
    ])
    question = dict(QUESTION)
    turn = start(question, dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "为什么?", gateway=gateway)
    assert turn.session.stuck is not True
    turn_request = [r for r in gateway.requests if r["role"] == "tutor"][0]
    assert "cited_numbers" not in json.dumps(turn_request["messages"])


def test_extracted_hallucinated_number_is_intercepted_not_stuck():
    # #184:幻觉数字 36(允许池只有 8/26/16)→ 拦截并重生成;**修好不置卡点**
    # (stuck 只在修复失败走兜底句时置,否则一次幻觉就把对话推向 needs_review)
    gateway = FakeGateway(tutor_payloads=[
        {"reply": "先看题面说的 8 只、26 只脚,你打算先算什么?", "ready_to_confirm": False,
         "cited_numbers": [], "steps": [{"step": "鸡脚", "value": "16"}]},
        {"reply": "题目里一共 36 只脚,所以兔子很多。", "ready_to_confirm": False,
         "cited_numbers": [36]},
    ])
    question = dict(QUESTION)
    turn = start(question, dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)
    assert "36" not in turn.text            # 幻觉数字不达学生面
    assert turn.session.stuck is not True   # 重生成修好 → 非卡点
    intercepted = [e for e in turn.session.guard_events if e.get("guard") == "answer_leak"]
    assert intercepted and intercepted[-1]["regenerated"] is True
    assert intercepted[-1]["rule_ids"] == ["source_value_disclosure:hallucinated"]


def test_student_echoed_number_is_allowed_not_stuck():
    # #34 裁决落地:学生自己说过的数字进入允许池(学生历史数字),纠偏复述不误标;
    # 旧行为(student 数字 ⊆ 题面 → 误标 stuck)已废弃
    gateway = FakeGateway(tutor_payloads=[
        {"reply": "先看题面说的 8 只、26 只脚,你打算先算什么?", "ready_to_confirm": False, "cited_numbers": []},
        {"reply": "你说 16 只脚,题面一共是 26 只脚。", "ready_to_confirm": False,
         "cited_numbers": [16]},
    ])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "16 只脚对不上", gateway=gateway)
    assert turn.session.stuck is not True  # 学生数字 16 ∈ 允许池,合法回述


def test_question_without_numbers_skips_drift_guard():
    # 题面/回复均无数字 → 无违规数字,不标卡点(几何题等)
    question = {"text": "说明三角形的内角和有什么特点。", "answer": "180 度",
                "analysis": "", "knowledge_points": []}
    gateway = FakeGateway(tutor_payloads=[
        {"reply": "三角形有几个角,你能说说吗?", "ready_to_confirm": False, "cited_numbers": [3]},
    ])
    turn = start(question, dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "三个角", gateway=gateway)
    assert turn.session.stuck is not True


def test_tone_is_prompt_guided_not_hard_guardrail():
    # 语气是 prompt 引导:直白无鼓励的合法教学回复不被硬护栏拦截
    # (首问恒为固定模板,不参与语气判定;语气面在本 reply 轮验证)
    # 数字全在允许池(题面 8/26 + 学生本轮已说的 16)→ 数值门不干预,语气面照常放行
    blunt = "16 只脚对应 8 只鸡,与题面 26 只脚矛盾。"
    gateway = FakeGateway(tutor_payloads=[
        {"reply": "先看题面说的 8 只、26 只脚,你打算先算什么?", "ready_to_confirm": False, "cited_numbers": []},
        {"reply": blunt, "ready_to_confirm": False, "cited_numbers": [16, 26]},
    ])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "我算得 16 只脚", gateway=gateway)
    assert turn.text == blunt  # 无鼓励措辞也照常达学生面(语气靠 prompt,非硬护栏)


def test_tone_directive_in_system_prompt():
    # 语气指令进 system prompt(稳定→cache 友好):亲切温暖/不起名/友好开场/
    # 长度软上限+结构硬要求/基调随对错;方向性指令,不硬编码句子
    from edu_agent.agents.small_lecturer import system_prompt
    system_message = system_prompt("六年级")
    for directive in ("亲切", "温暖", "名字", "开场", "以问题结尾", "基调",
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
