"""合作方接口会话语义合同测试(00 §5.2;tests/contracts——api 行为即合同行为)。

确定性假内核(固定教学回合),经 HTTP 打本地测试服务器,零真实模型;断言幂等键、
session_version 乐观并发、题目固定、错误码集与错误信封形态(#48 快照)。
共享助手(ScriptedKernel/_serve/post/open_session)已移入 tests/fixtures/partner_api(决策 1)。
"""

from __future__ import annotations

import pytest

from partner_api import ScriptedKernel, _serve, open_session, post


@pytest.fixture
def api():
    kernel = ScriptedKernel(
        replies=["你列了哪些已知量?", "很好,那两个量之间是什么关系?", "你已经掌握了乘法意义。"],
        ready_at=3,
    )
    base, server = _serve(kernel)
    yield base, kernel
    server.shutdown()
    server.server_close()


# ---------- open:幂等键与题目固定 ----------

def test_open_returns_contract_fields_and_synchronous_first_question(api):
    base, kernel = api
    body = open_session(base)
    assert set(body) >= {"conversation", "skill_session_id", "session_version",
                         "first_question_ready", "retry_after_ms"}  # 00 §5.2 开会话行
    assert body["first_question_ready"] is True and body["retry_after_ms"] == 0
    assert kernel.start_calls == 1


def test_same_idempotency_key_returns_same_attempt(api):
    base, kernel = api
    first = open_session(base, key="idem-x")
    second = open_session(base, key="idem-x")
    assert second == first  # 同键同 Attempt,不创建第二个会话
    assert kernel.start_calls == 1


def test_same_key_different_question_is_pinned(api):
    base, _ = api
    open_session(base, question_id="q-1", key="idem-p")
    response = post(base, "/api/prepared-questions/q-2/open", {"idempotency_key": "idem-p"})
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "QUESTION_SOURCE_PINNED"  # 题目在会话内固定(约定 2)
    assert set(error) == {"code", "message", "request_id", "details"}  # 老仓库 ErrorEnvelope 形态


def test_open_without_idempotency_key_is_422(api):
    base, _ = api
    assert post(base, "/api/prepared-questions/q/open", {}).status_code == 422


# ---------- refresh:两形态同一语义 ----------

@pytest.mark.parametrize("path_template", [
    "/api/prepared-questions/{question_id}/skill-sessions/{sid}/refresh",   # 00 §5.2 表形态
    "/api/conversations/{conversation_id}/skill-sessions/{sid}/refresh",    # Postman 集合形态
])
def test_refresh_returns_first_question_and_version(api, path_template):
    base, _ = api
    opened = open_session(base)
    path = path_template.format(
        question_id=opened["conversation"]["question_id"],
        conversation_id=opened["conversation"]["conversation_id"],
        sid=opened["skill_session_id"],
    )
    response = post(base, path)
    assert response.status_code == 200
    body = response.json()
    # M3 全景 B3:refresh 返回全信封(assistant_message + skill_interaction + agent_run)
    assert body["assistant_message"]["content"] == "我们先看已知条件,题目要我们求什么?"
    assert body["skill_interaction"]["schema_version"] == "skill_interaction/v1"
    assert body["skill_interaction"]["skill_session_id"] == opened["skill_session_id"]
    assert body["agent_run"]["status"] == "completed"
    assert body["session_version"] == opened["session_version"]


# ---------- messages:乐观并发与教学回合 ----------

def test_dialogue_increments_version_and_returns_envelope(api):
    base, _ = api
    opened = open_session(base)
    response = post(base, f"/api/conversations/{opened['conversation']['conversation_id']}/messages", {
        "content": "我先说说已知条件。",
        "skill_id": "small_lecturer_coaching",
        "input": {"skill_session_id": opened["skill_session_id"],
                  "expected_session_version": 1},
    })
    assert response.status_code == 200
    body = response.json()
    assert body["assistant_message"]["content"] == "你列了哪些已知量?"
    assert body["session_version"] == 2
    interaction = body["skill_interaction"]
    assert interaction["schema_version"] == "skill_interaction/v1"
    assert interaction["skill_session_id"] == opened["skill_session_id"]
    assert interaction["session_version"] == 2


def test_stale_session_version_is_409_conflict(api):
    base, _ = api
    opened = open_session(base)
    conversation_id = opened["conversation"]["conversation_id"]
    post(base, f"/api/conversations/{conversation_id}/messages", {
        "content": "第一轮",
        "input": {"skill_session_id": opened["skill_session_id"], "expected_session_version": 1},
    })
    stale = post(base, f"/api/conversations/{conversation_id}/messages", {
        "content": "旧页面重发",
        "input": {"skill_session_id": opened["skill_session_id"], "expected_session_version": 1},
    })
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "SKILL_SESSION_CONFLICT"  # 约定 3:不静默覆盖


# ---------- confirm:完成与不可变 summary ----------

def test_confirm_completes_and_summary_is_immutable(api):
    base, kernel = api
    opened = open_session(base)
    conversation_id = opened["conversation"]["conversation_id"]
    for expected in (1, 2, 3):  # ready_at=3:第三轮后进入 ready_to_confirm
        post(base, f"/api/conversations/{conversation_id}/messages", {
            "content": f"第{expected}轮回答",
            "input": {"skill_session_id": opened["skill_session_id"],
                      "expected_session_version": expected},
        })
    confirm = post(base, f"/api/conversations/{conversation_id}/messages", {
        "content": "确认结束",
        "skill_id": "small_lecturer_coaching",
        "input": {"interaction_action": "confirm",
                  "skill_session_id": opened["skill_session_id"]},
    })
    assert confirm.status_code == 200
    body = confirm.json()
    assert body["status"] == "completed" and body["ready_to_confirm"] is True
    assert body["summary"] == {"status": "completed"}
    # completed 后再 messages → 409(终态不可续)
    after = post(base, f"/api/conversations/{conversation_id}/messages", {
        "content": "再问一句", "input": {"skill_session_id": opened["skill_session_id"]},
    })
    assert after.status_code == 409


def test_confirm_before_ready_returns_needs_review(api):
    base, kernel = api
    opened = open_session(base)
    response = post(base, f"/api/conversations/{opened['conversation']['conversation_id']}/messages", {
        "content": "确认", "input": {"interaction_action": "confirm"},
    })
    assert response.json()["status"] == "needs_review"  # 证据不足,不写 summary(00 §5.2 结束行)
    assert kernel.finish_calls == 1


# ---------- 401 / 503 / 404 ----------

def test_missing_authorization_is_401(api):
    base, _ = api
    response = post(base, "/api/prepared-questions/q/open", {"idempotency_key": "k"}, auth=False)
    assert response.status_code == 401
    assert response.json()["error"]["code"] is None


def test_kernel_infrastructure_failure_maps_to_503():
    kernel = ScriptedKernel([], start_error=RuntimeError("模型服务不可用"))
    base, server = _serve(kernel)
    response = post(base, "/api/prepared-questions/q/open", {"idempotency_key": "k"})
    server.shutdown()
    server.server_close()
    assert response.status_code == 503
    assert response.json()["error"]["code"] is None


def test_unknown_path_and_session_are_404(api):
    base, _ = api
    assert post(base, "/api/unknown").status_code == 404
    assert post(base, "/api/conversations/missing/messages", {"content": "x"}).status_code == 404


def test_preload_not_ready_is_in_contract_error_family():
    """PRELOAD_NOT_READY(#48 错误码表,兼容保留):新链路同步出首问预期不触发,
    错误族在册可映射——端到端触发路径随 PR2 异步语义(如需)。"""
    from edu_agent.api import ApiError

    error = ApiError(409, "TEACHING_CONTEXT_PRELOAD_NOT_READY", "最小题意尚未准备完成")
    assert (error.status_code, error.code) == (409, "TEACHING_CONTEXT_PRELOAD_NOT_READY")
