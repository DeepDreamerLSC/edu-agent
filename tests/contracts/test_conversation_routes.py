"""合作方会话入口与状态查询路由合同(M3 PR-1;老系统统一 Open 字段子集)。

POST /api/conversations:{external_question_id?|question_text?|question_image?,
idempotency_key 必填}——external_question_id 走题源,question_text/question_image
自由材料二选一(题图空壳由内核 vision 处理);GET /api/conversations/{id} 状态视图。
请求走 test_api_service 的 SSRF 边界守卫(只允许 127.0.0.1 本地测试服务器)。
"""

from __future__ import annotations

import httpx
import pytest
from test_api_service import StubTurn, _assert_local_base, post

from edu_agent.api import build_server, build_service


class RecordingKernel:
    """确定性内核桩:记录收到的题面 dict,固定回复序列。"""

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.questions: list[dict] = []

    def start(self, question: dict, learner: dict) -> StubTurn:
        self.questions.append(question)
        reply = self.replies[min(len(self.questions) - 1, len(self.replies) - 1)]
        return StubTurn(reply)

    def reply(self, session: object, student_message: str) -> StubTurn:
        return StubTurn("思路对。")

    def finish(self, session: object) -> StubTurn:
        return StubTurn("总结")


class MapSource:
    """确定性题源:命中返回 seed 同构面,未命中 KeyError(题库未命中信号)。"""

    def resolve(self, question_id: str) -> dict:
        if question_id != "equation_subtract":
            raise KeyError(f"题源不含 question_id:{question_id}")
        return {"text": "解方程 3x+7=25,并说明每一步为什么这样做。", "answer": "x=6",
                "analysis": "等式两边先同时减去 7。", "image": None,
                "knowledge_points": ["简易方程"], "grade": "五年级",
                "answer_correct_provenance": "partner_question_bank"}


@pytest.fixture
def env():
    kernel = RecordingKernel(["我们先看已知条件,题目要我们求什么?"])
    service = build_service(kernel, source=MapSource())
    server = build_server(service)
    import threading

    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base, kernel
    server.shutdown()
    server.server_close()


def get(base: str, path: str) -> httpx.Response:
    """GET 形态;SSRF 边界守卫与 post() 同款(test_api_service)。"""
    _assert_local_base(base)
    headers = {"Authorization": "Bearer test-token"}
    return httpx.get(f"{base}{path}", headers=headers, timeout=5.0, trust_env=False)


def test_create_then_get_roundtrip(env):
    """POST(external_question_id 题库命中)→ GET 状态视图 roundtrip。"""
    base, _ = env
    response = post(base, "/api/conversations", {
        "external_question_id": "equation_subtract",
        "idempotency_key": "route-001",
    })
    assert response.status_code == 201
    payload = response.json()
    conversation_id = payload["conversation_id"]
    assert set(payload) == {"conversation_id", "skill_session_id", "session_version",
                            "first_question_ready", "first_question", "retry_after_ms"}
    assert payload["skill_session_id"] and payload["session_version"] == 1
    assert payload["first_question_ready"] is True and payload["first_question"]
    assert payload["retry_after_ms"] == 0

    view = get(base, f"/api/conversations/{conversation_id}")
    assert view.status_code == 200
    body = view.json()
    assert body == {
        "conversation_id": conversation_id,
        "state": "first_question_ready",
        "session_version": 1,
        "question_id": "equation_subtract",
        "created_at": body["created_at"],  # 动态字段与自身比对保键存在
        "turn_count": 0,
    }
    assert body["created_at"]  # ISO 时间戳由创建写入


def test_idempotent_retry_returns_same_conversation(env):
    base, _ = env
    body = {"external_question_id": "equation_subtract", "idempotency_key": "route-002"}
    first = post(base, "/api/conversations", body)
    second = post(base, "/api/conversations", body)
    assert first.status_code == second.status_code == 201
    assert first.json()["conversation_id"] == second.json()["conversation_id"]


def test_bank_miss_is_404_question_not_found(env):
    """题库未命中(无图):404 QUESTION_BANK_QUESTION_NOT_FOUND(老系统错误码表)。"""
    base, _ = env
    response = post(base, "/api/conversations", {
        "external_question_id": "no_such_question", "idempotency_key": "route-miss"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "QUESTION_BANK_QUESTION_NOT_FOUND"


def test_text_material_creates_without_bank(env):
    """自由文本:不走题源,内核收到 {"text": 题干};question_id 记空串。"""
    base, kernel = env
    response = post(base, "/api/conversations", {
        "question_text": "小明有 12 本书,借出 5 本,还剩几本?", "idempotency_key": "route-text"})
    assert response.status_code == 201
    assert response.json()["first_question"]
    assert kernel.questions[0] == {"text": "小明有 12 本书,借出 5 本,还剩几本?"}
    view = get(base, f"/api/conversations/{response.json()['conversation_id']}")
    assert view.json()["question_id"] == ""


def test_image_material_goes_vision_shell(env):
    """题图空壳(file_id):question dict 走 {"image": file_id},内核 vision 处理。"""
    base, kernel = env
    response = post(base, "/api/conversations", {
        "question_image": "seed-image_x", "idempotency_key": "route-image"})
    assert response.status_code == 201
    assert kernel.questions[0] == {"image": "seed-image_x"}


def test_text_and_image_together_is_422(env):
    """自由材料互斥(老系统文档:question_text 与 question_image 不能同时提交)。"""
    base, _ = env
    response = post(base, "/api/conversations", {
        "question_text": "题干", "question_image": "file-1", "idempotency_key": "route-both"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PREPARED_QUESTION_SOURCE_CONFLICT"


def test_no_material_is_422(env):
    """未提供任何题目来源:422 PREPARED_QUESTION_SOURCE_MISSING(老系统错误码表)。"""
    base, _ = env
    response = post(base, "/api/conversations", {"idempotency_key": "route-empty"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PREPARED_QUESTION_SOURCE_MISSING"


def test_unknown_conversation_is_404(env):
    base, _ = env
    response = get(base, "/api/conversations/conv_missing")
    assert response.status_code == 404
    assert "error" in response.json()


def test_forbidden_client_fields_are_403(env):
    """00 §5.2 约定 4:answer/analysis/mastery_status 客户端不得提交(403,拦截在创建前)。"""
    base, kernel = env
    for field in ("answer", "analysis", "mastery_status"):
        response = post(base, "/api/conversations", {
            "external_question_id": "equation_subtract",
            "idempotency_key": f"route-{field}", field: "客户端伪造"})
        assert response.status_code == 403, (field, response.text)
        assert "不得提交" in response.json()["error"]["message"]
    assert kernel.questions == []  # 拦截在创建之前:未产生任何内核调用
