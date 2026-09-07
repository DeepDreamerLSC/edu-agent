"""M3 前置 PR2 合同:vision 三字段 schema(acceptable/reason/transcription)、
纯图题转写进题面、answer/analysis 进教师面且泄露护栏对照答案、knowledge_points 锚点。

gateway 用对象注入假实现(零网络零端口,确定性);HTTP 形态的 vision 冒烟
(真 8303+真题图)走本地验证段,不入 CI。
"""

from __future__ import annotations

import json

import pytest

from edu_agent.agents.small_lecturer import (
    TerminalStateError,
    reply,
    start,
)
from edu_agent.gateway import FailureType, GatewayError

ANSWER = "x=6"
ANALYSIS = "等式两边先同时减去 7,得 3x=18,再同时除以 3。"
QUESTION = {"text": "", "image": {"file_id": "seed-image_x"}, "answer": ANSWER,
            "analysis": ANALYSIS, "knowledge_points": ["简易方程", "等式的性质"]}
TEXT_QUESTION = {"text": "解方程 3x+7=25,并说明每一步为什么这样做。", "image": None,
                 "answer": ANSWER, "analysis": ANALYSIS, "knowledge_points": []}


class FakeGateway:
    """对象注入假 gateway:vision 按脚本出牌,tutor 回复固定;记录全部请求。"""

    def __init__(self, *, vision_responses: list[dict] | None = None,
                 tutor_reply: str = "先说说题目给的条件,你觉得第一步做什么?",
                 tutor_error: GatewayError | None = None):
        self.vision_queue = list(vision_responses or [])
        self.tutor_reply = tutor_reply
        self.tutor_error = tutor_error
        self.requests: list[dict] = []

    def invoke(self, request):
        self.requests.append({"role": request.role, "messages": request.messages})
        if request.role == "vision":
            verdict = self.vision_queue.pop(0) if self.vision_queue else \
                {"acceptable": True, "reason": "默认", "transcription": "默认转写"}
            return _response(json.dumps(verdict, ensure_ascii=False))
        if self.tutor_error is not None:
            raise self.tutor_error
        return _response(json.dumps(
            {"reply": self.tutor_reply, "ready_to_confirm": False}, ensure_ascii=False))


def _response(text: str):
    response = type("R", (), {})()
    response.text = text
    return response


def teacher_context(requests: list[dict]) -> dict:
    tutor_calls = [r for r in requests if r["role"] == "tutor"]
    return json.loads(tutor_calls[0]["messages"][-1]["content"]) if tutor_calls else {}


def test_pure_image_question_transcription_enters_teacher_prompt():
    gateway = FakeGateway(vision_responses=[
        {"acceptable": True, "reason": "单题清晰",
         "transcription": "解方程 3x+7=25,并说明每一步为什么这样做。"}])
    question = dict(QUESTION)
    turn = start(question, {"grade": "五年级"}, gateway=gateway)
    # 转写进题面:start 原地更新传入的 question dict(session 持同一引用)
    assert question["text"] == "解方程 3x+7=25,并说明每一步为什么这样做。"
    assert turn.session.question["text"] == question["text"]
    context = teacher_context(gateway.requests)
    assert context["题目"] == "解方程 3x+7=25,并说明每一步为什么这样做。"
    # 教师面三要素 + 追问锚点(PR2)
    assert context["参考答案"] == ANSWER
    assert context["解析"] == ANALYSIS
    assert context["追问锚点"] == ["简易方程", "等式的性质"]
    assert turn.state == "first_question_ready"


def test_answer_leak_guardrail_now_covers_answer_text():
    # 教师面有参考答案后,学生可见 reply 复现答案即被护栏替换(M3 前置 PR2 扩展)
    gateway = FakeGateway(tutor_reply=f"这道题的答案是 {ANSWER},记住了吗?")
    turn = start(dict(TEXT_QUESTION), {"grade": "五年级"}, gateway=gateway)
    assert ANSWER not in turn.text
    assert turn.text.startswith("先回到当前小问")  # 护栏确定性安全问句


def test_vision_response_without_transcription_does_not_inject():
    # schema 的 required 三字段由 gateway 校验层保证(HTTP 形态测试覆盖);
    # 对象注入形态下缺 transcription → 转写为空、不注入,题面维持原样
    gateway = FakeGateway(vision_responses=[{"acceptable": True, "reason": "缺 transcription"}])
    question = dict(QUESTION)
    start(question, {"grade": "五年级"}, gateway=gateway)
    assert question["text"] == ""


def test_text_question_skips_vision():
    gateway = FakeGateway(vision_responses=[{"acceptable": True, "reason": "不该被调",
                                             "transcription": ""}])
    start(dict(TEXT_QUESTION), {"grade": "五年级"}, gateway=gateway)
    assert [r["role"] for r in gateway.requests] == ["tutor"]  # vision 零调用


def test_vision_not_acceptable_fails_closed():
    gateway = FakeGateway(vision_responses=[
        {"acceptable": False, "reason": "图里有多道题", "transcription": "1) 3+4=?"}])
    turn = start(dict(QUESTION), {"grade": "五年级"}, gateway=gateway)
    assert turn.state == "failed"
    assert turn.text.startswith("这张题图我没法安全地开始讲解")
    with pytest.raises(TerminalStateError):
        reply(turn.session, "1", gateway=gateway)
