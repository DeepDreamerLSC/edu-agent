"""真内核接入合同(M3 前置 PR1):SmallLecturerKernel(假 gateway)+ question_source。

CI 零真实模型:gateway 注入确定性假响应;真 gateway+真模型的验证走本地冒烟段(不入 CI)。
"""

from __future__ import annotations

import json

import pytest

from edu_agent.api import (
    ConversationService,
    SeedQuestionSource,
    SmallLecturerKernel,
    SnapshotQuestionSource,
    build_service,
)
from edu_agent.agents.small_lecturer import (
    FIRST_QUESTION_COLLECT,
    OPENING_HINT_CORRECT,
    OPENING_HINT_INCORRECT,
)
from edu_agent.gateway import FailureType, GatewayError
from partner_api import VISION_OK, MapSource, text_response


class FakeGateway:
    """确定性假 gateway:按角色出牌(tutor 回合 JSON / vision 检查 JSON)。"""

    def __init__(self, ready_to_confirm: bool = False):
        self.ready_to_confirm = ready_to_confirm
        self.requests: list = []

    def invoke(self, request):
        self.requests.append(request)
        if request.role == "vision":
            text = json.dumps(VISION_OK)
        else:
            # 首问轮(reply 轮带「对话记录」段)用不同句:首问恒为固定模板,reply 轮若与
            # 首问同句会撞上输出面防复读背板(阶梯推进)——那是另一条路径的语义,本条合同
            # 只钉「无护栏命中的模型文本达学生面 + 版本推进」。
            first_turn = not any("对话记录" in str(m.get("content") or "")
                                 for m in request.messages)
            reply_text = "你打算先算哪一步?" if first_turn else "你刚才说的那一步很关键。"
            text = json.dumps({"reply": reply_text,
                               "ready_to_confirm": self.ready_to_confirm},
                              ensure_ascii=False)
        return text_response(text)


@pytest.fixture
def service():
    service = build_service(SmallLecturerKernel(FakeGateway()))
    service.source = MapSource()
    return service


def test_real_kernel_start_uses_question_source(service):
    response = service.open("equation_subtract", "idem-real-1", learner={})
    assert response["first_question_ready"] is True
    conversation = service._conversation_or_404(response["conversation"]["conversation_id"])
    # 出处走 answer_correct_provenance(审查 P1:answer_status 是正确性字段,题源不碰)
    assert conversation.extras["learner"]["answer_correct_provenance"] == "partner_question_bank"
    assert "answer_status" not in conversation.extras["learner"]
    assert conversation.extras["learner"]["grade"] == "五年级"
    # answer/analysis 进内核面=教师侧 prompt(M3 PR2);extras 副本仍供 judge
    assert conversation.extras["question_detail"]["answer"] == "x=6"
    kernel_session = conversation.extras["kernel_session"]
    assert kernel_session.question["text"].startswith("解方程")
    assert kernel_session.question["answer"] == "x=6"
    assert kernel_session.question["knowledge_points"] == ["简易方程"]
    assert kernel_session.learner["answer_correct_provenance"] == "partner_question_bank"


def test_real_kernel_dialogue_and_version_conflict(service):
    first = service.open("equation_subtract", "idem-real-2", learner={})
    conversation_id = first["conversation"]["conversation_id"]
    version = first["session_version"]
    body = {"content": "3x 等于 18 吗?",
            "input": {"skill_session_id": first["skill_session_id"],
                      "expected_session_version": version}}
    response = service.send(conversation_id, body)
    # 首问可见文本恒为固定模板(prompting.first_question_text);reply 轮的模型文本无护栏命中、
    # 也不是复读 → 照常达学生面。复读/阶梯兜底由 tests/teaching 按公开路径覆盖。
    assert first["first_question_ready"] is True
    conversation = service._conversation_or_404(conversation_id)
    assert conversation.extras["kernel_session"].first_question == FIRST_QUESTION_COLLECT
    assert response["assistant_message"]["content"] == "你刚才说的那一步很关键。"
    # 内核 reply 推进版本;旧版本提交 → 409 合同码
    stale = dict(body, input={**body["input"], "expected_session_version": version})
    with pytest.raises(Exception) as excinfo:
        service.send(conversation_id, stale)
    assert getattr(excinfo.value, "status_code", None) == 409


def test_gateway_failure_maps_to_503():
    class ExplodingGateway:
        def invoke(self, request):
            raise GatewayError(FailureType.UPSTREAM_5XX, "上游 5xx")

    service = build_service(SmallLecturerKernel(ExplodingGateway()))
    service.source = MapSource()
    with pytest.raises(Exception) as excinfo:
        service.open("equation_subtract", "idem-real-3", learner={})
    assert getattr(excinfo.value, "status_code", None) == 503


def test_seed_source_resolves_published_question():
    source = SeedQuestionSource()  # 仓库内真实 seed bank
    resolved = source.resolve("equation_subtract")
    assert resolved["text"].startswith("解方程 3x+7=25")
    assert resolved["answer"] == "x=6"
    assert resolved["grade"] == "五年级"
    assert resolved["answer_correct_provenance"] == "partner_question_bank"
    with pytest.raises(KeyError):
        source.resolve("no_such_question")


# ---------- A 线 §8.5(M3 WS1):真内核 open → message → finish 端到端 ----------

class SequencedGateway:
    """序列假 gateway:按调用次序出牌(open steps+首问 → reply → finish 总结)。

    回复选词避开任何数字(守卫只对答案数字计数),消息文本走学生已知量。"""

    def __init__(self, replies: list[dict]):
        self.replies = list(replies)
        self.requests: list = []

    def invoke(self, request):
        self.requests.append(request)
        return text_response(json.dumps(self.replies.pop(0), ensure_ascii=False))


def test_open_message_finish_e2e_real_kernel_with_bank_image():
    """A 线验收:open → message → finish 端到端(真内核 + 快照题库真题图)。

    open 省略 answer_correct → A 线 assumed_incorrect(learner 由
    open_request_learner 构造,与 server.py per-question open 同款装配);题图经
    image_resolver 解析为 data URL 后作为 images 直传模型调用(不进 messages 文本);
    教师侧题面带参考答案/解析/追问锚点;学生首轮陈述答案(守卫 ③ 首轮撞集不判命中)
    → 模型判停 → confirm 出模型总结。"""
    gateway = SequencedGateway([
        {"acceptable": True, "transcription": "", "steps": [
            {"step": "假设全是鸡,算出脚数", "value": "十六只"},
            {"step": "与实际脚数的差", "value": "十只"}],
         "reply": "你好,我们一起看看这道题。你算出的鸡和兔各有几只?"},
        {"reply": "很好,你已经把两种数量都算出来了。", "ready_to_confirm": True},
        {"summary": "你能独立说明假设思路,数量也已验证,这题过关。"},
    ])
    service = build_service(
        SmallLecturerKernel(gateway),
        source=SnapshotQuestionSource(),
        image_resolver=lambda fid: f"data:image/png;base64,{fid}",
    )
    # 与 server.py 同款装配:请求体 → open_request_learner → service.open
    learner, echoed, _ = ConversationService.open_request_learner(
        {"idempotency_key": "e2e-img-1"},
        frozenset({"idempotency_key"}) | ConversationService._OPEN_LEARNER_FIELDS)
    assert echoed is None and learner == {"answer_status": "incorrect"}  # A 线:省略按做错
    opened = service.open("chicken_rabbit", "e2e-img-1", learner)
    assert opened["first_question_ready"] is True
    conversation = service._conversation_or_404(opened["conversation"]["conversation_id"])
    kernel_session = conversation.extras["kernel_session"]
    # 题库含图题:快照 file_id → data URL,经 ModelRequest.images 直传(不进 messages 文本)
    assert kernel_session.question["image"].startswith("data:image/png;base64,seed-image_")
    first_call = gateway.requests[0]
    assert first_call.images == [kernel_session.question["image"]]
    assert all("data:image" not in str(m) for m in first_call.messages)
    # 题库命中:参考答案/解析进教师侧题面;知识点作追问锚点
    user_prompt = first_call.messages[1]["content"]
    assert "鸡3只，兔5只" in user_prompt and "鸡兔同笼" in user_prompt
    # A 线:assumed_incorrect → 首问带 incorrect 弧线提示
    assert OPENING_HINT_INCORRECT in user_prompt
    # message:学生首轮给出与终答一致的答案 → 模型判停 → ready_to_confirm
    turn = service.send(conversation.conversation_id, {
        "content": "我算出鸡有3只,兔有5只。",
        "input": {"skill_session_id": opened["skill_session_id"],
                  "expected_session_version": opened["session_version"]}})
    assert turn["skill_interaction"]["state"] == "ready_to_confirm"
    # finish:confirm → completed,总结带模型文本(真内核三函数全走,恰好三次模型调用)
    summary = service.send(conversation.conversation_id, {
        "input": {"interaction_action": "confirm",
                  "skill_session_id": opened["skill_session_id"]}})
    assert summary["status"] == "completed"
    assert summary["summary"]["text"].startswith("你能独立说明假设思路")
    assert len(gateway.requests) == 3  # open → reply → finish(真内核三函数全走)


@pytest.mark.parametrize("answer_correct,expected_status,expected_hint", [
    (True, "correct", OPENING_HINT_CORRECT),
    (False, "incorrect", OPENING_HINT_INCORRECT),
    (None, "incorrect", OPENING_HINT_INCORRECT),   # A 线:null 按做错(assumed_incorrect)
    ("omitted", "incorrect", OPENING_HINT_INCORRECT),  # A 线:省略按做错
])
def test_answer_correct_three_branches_wire_opening_strategy(
        answer_correct, expected_status, expected_hint):
    """A 线映射三分支(true/false/null|省略)各一例:open_request_learner 构造的
    learner 决定真内核首问策略提示(per-question open 与 server.py 同款装配)。"""
    gateway = SequencedGateway([
        {"acceptable": True, "transcription": "", "steps": [], "reply": "先说说你的想法。"},
    ])
    service = build_service(SmallLecturerKernel(gateway), source=SeedQuestionSource())
    body = {"idempotency_key": f"branch-{answer_correct}"}
    if answer_correct != "omitted":
        body["answer_correct"] = answer_correct
    learner, echoed, _ = ConversationService.open_request_learner(
        body, frozenset({"idempotency_key"}) | ConversationService._OPEN_LEARNER_FIELDS)
    # 与 server.py per-question open 同款调用形(kernel.start 收映射后的 learner)
    assert echoed == (None if answer_correct == "omitted" else answer_correct)
    assert learner["answer_status"] == expected_status
    assert learner.get("answer_correct_provenance") == (
        None if answer_correct is None or answer_correct == "omitted" else "partner_open")
    service.open("equation_subtract", body["idempotency_key"], learner)
    user_prompt = gateway.requests[0].messages[1]["content"]
    assert expected_hint in user_prompt
    # 其余分支的提示不串台
    other = OPENING_HINT_CORRECT if expected_status == "incorrect" else OPENING_HINT_INCORRECT
    assert other not in user_prompt
