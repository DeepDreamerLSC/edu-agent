"""真内核接入合同(M3 前置 PR1):SmallLecturerKernel(假 gateway)+ question_source。

CI 零真实模型:gateway 注入确定性假响应;真 gateway+真模型的验证走本地冒烟段(不入 CI)。
"""

from __future__ import annotations

import json

import pytest

from edu_agent.api import (
    SeedQuestionSource,
    SmallLecturerKernel,
    build_service,
)
from edu_agent.gateway import FailureType, GatewayError


class FakeGateway:
    """确定性假 gateway:按角色出牌(tutor 回合 JSON / vision 检查 JSON)。"""

    def __init__(self, ready_to_confirm: bool = False):
        self.ready_to_confirm = ready_to_confirm
        self.requests: list = []

    def invoke(self, request):
        self.requests.append(request)
        if request.role == "vision":
            text = json.dumps({"acceptable": True, "reason": "单题清晰"})
        else:
            text = json.dumps({"reply": "你先说说题目给了哪些条件?",
                               "ready_to_confirm": self.ready_to_confirm},
                              ensure_ascii=False)
        response = type("R", (), {})()
        response.text = text
        return response


class FakeSource:
    """确定性题源:seed bank 同构输出面。"""

    def resolve(self, question_id):
        return {"text": "解方程 3x+7=25,并说明每一步为什么这样做。", "answer": "x=6",
                "analysis": "等式两边先同时减去 7。", "image": None,
                "knowledge_points": ["简易方程"], "grade": "五年级",
                "answer_correct_provenance": "partner_question_bank"}


@pytest.fixture
def service():
    service = build_service(SmallLecturerKernel(FakeGateway()))
    service.source = FakeSource()
    return service


def test_real_kernel_start_uses_question_source(service):
    response = service.open("equation_subtract", "idem-real-1", learner={})
    assert response["first_question_ready"] is True
    conversation = service._conversation_or_404(response["conversation"]["conversation_id"])
    # 出处走 answer_correct_provenance(审查 P1:answer_status 是正确性字段,题源不碰)
    assert conversation.extras["learner"]["answer_correct_provenance"] == "partner_question_bank"
    assert "answer_status" not in conversation.extras["learner"]
    assert conversation.extras["learner"]["grade"] == "五年级"
    # 内核面最小化:text/image 进内核,answer/analysis 存 extras(学生可见面不含答案)
    assert conversation.extras["question_detail"]["answer"] == "x=6"
    kernel_session = conversation.extras["kernel_session"]
    assert kernel_session.question["text"].startswith("解方程")
    assert kernel_session.learner["answer_correct_provenance"] == "partner_question_bank"


def test_real_kernel_dialogue_and_version_conflict(service):
    first = service.open("equation_subtract", "idem-real-2", learner={})
    conversation_id = first["conversation"]["conversation_id"]
    version = first["session_version"]
    body = {"content": "3x 等于 18 吗?",
            "input": {"skill_session_id": first["skill_session_id"],
                      "expected_session_version": version}}
    response = service.send(conversation_id, body)
    assert "条件" in response["assistant_message"]["content"]
    # 内核 reply 推进版本;旧版本提交 → 409 合同码
    stale = dict(body, input={**body["input"], "expected_session_version": version})
    with pytest.raises(Exception) as excinfo:
        service.send(conversation_id, stale)
    assert getattr(excinfo.value, "status_code", None) == 409


def test_gateway_failure_maps_to_503():
    from edu_agent.gateway import Gateway

    class ExplodingGateway:
        def invoke(self, request):
            raise GatewayError(FailureType.UPSTREAM_5XX, "上游 5xx")

    service = build_service(SmallLecturerKernel(ExplodingGateway()))
    service.source = FakeSource()
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
