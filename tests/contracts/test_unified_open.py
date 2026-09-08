"""统一 Open 端点合同(M3 PR-3;老系统文档 small-lecturer-v1 §5 逐条)。

POST /api/prepared-questions/open:字段/长度/严格类型/组合规则照 §5,
pending 恒 false(同步内核),active_session 恒在。零真实模型(桩内核+确定性题源)。
"""

from __future__ import annotations

import httpx
import pytest
from test_api_service import StubTurn, post
from test_conversation_routes import MapSource, RecordingKernel

from edu_agent.api import build_server, build_service


@pytest.fixture
def env():
    kernel = RecordingKernel(["我们先看已知条件,题目要我们求什么?"])
    server = build_server(build_service(kernel, source=MapSource()))
    import threading

    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base, kernel
    server.shutdown()
    server.server_close()


def unified(base: str, body: dict, token: str = "test-token") -> httpx.Response:
    _ = token  # post() 已带 Authorization
    return post(base, "/api/prepared-questions/open", body)


def test_bank_hit_returns_unified_envelope(env):
    """题库命中:复用题干/答案/解析/知识点;pending 恒 false;active_session 恒在。"""
    base, kernel = env
    response = unified(base, {"external_question_id": "equation_subtract",
                              "idempotency_key": "u-001"})
    assert response.status_code == 200
    body = response.json()
    assert body["external_question_id"] == "equation_subtract"
    assert body["pending"] is False
    assert body["answer_correct"] is None
    assert body["answer_correct_provenance"] == "partner_question_bank"  # 题库命中标记来源
    active = body["question"]["active_session"]
    assert body["question"]["package_id"] is None  # v1 题源不带包 id
    assert active["first_question_ready"] is True and active["retry_after_ms"] == 0
    assert active["conversation"] and active["skill_session_id"]
    # 题库命中复用题干(教师侧);学生可见首问来自桩内核
    session = kernel.questions[0]
    assert session["text"].startswith("解方程 3x+7=25")
    assert session["answer"] == "x=6" and session["knowledge_points"] == ["简易方程"]


def test_bank_miss_with_image_goes_vision_path(env):
    """题库未命中但有题图:vision 转写路径(空壳 + image),不 404。"""
    base, kernel = env
    response = unified(base, {"external_question_id": "no_such", "idempotency_key": "u-002",
                              "question_image": "seed-image_x"})
    assert response.status_code == 200
    assert response.json()["pending"] is False
    assert kernel.questions[0] == {"image": "seed-image_x"}


def test_bank_miss_without_image_is_404(env):
    base, _ = env
    response = unified(base, {"external_question_id": "no_such", "idempotency_key": "u-003"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "QUESTION_BANK_QUESTION_NOT_FOUND"


def test_text_with_image_is_422_conflict(env):
    base, _ = env
    response = unified(base, {"question_text": "题干", "question_image": "file-1",
                              "idempotency_key": "u-004"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "PREPARED_QUESTION_SOURCE_CONFLICT"
    assert "question_text" in error["details"]["conflicting_fields"]


def test_text_with_external_question_id_is_422_conflict(env):
    base, _ = env
    response = unified(base, {"question_text": "题干", "external_question_id": "equation_subtract",
                              "idempotency_key": "u-005"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PREPARED_QUESTION_SOURCE_CONFLICT"


def test_answer_correct_three_states_echoed(env):
    """answer_correct 严格三态(true/false/null)回显;provenance 标记客户来源。"""
    base, _ = env
    for value in (True, False, None):
        response = unified(base, {"question_text": "自由题干一", "idempotency_key": f"u-ac-{value}",
                                  "answer_correct": value})
        assert response.status_code == 200, (value, response.text)
        assert response.json()["answer_correct"] is value
        assert response.json()["answer_correct_provenance"] is None  # PR-4 起改 partner_open


@pytest.mark.parametrize("bad", ["true", "false", 1, 0, "null"])
def test_answer_correct_non_boolean_rejected(env, bad):
    """严格 JSON 类型:字符串/数字拒绝(合作方老服务端合同)。"""
    base, _ = env
    response = unified(base, {"question_text": "自由题干二", "idempotency_key": "u-bad-ac",
                              "answer_correct": bad})
    assert response.status_code == 422
    assert "answer_correct" in response.json()["error"]["message"]


def test_answer_correct_omitted_defaults_to_null(env):
    base, _ = env
    response = unified(base, {"question_text": "自由题干三", "idempotency_key": "u-ac-omit"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer_correct"] is None and body["answer_correct_provenance"] is None


def test_knowledge_points_flow_into_material(env):
    """非题库路径:客户端 knowledge_points 作追问锚点进题面。"""
    base, kernel = env
    response = unified(base, {"question_text": "自由题干四", "idempotency_key": "u-kp",
                              "knowledge_points": [{"id": "kp-1", "name": "一元一次方程"}]})
    assert response.status_code == 200
    assert kernel.questions[0]["knowledge_points"] == [{"id": "kp-1", "name": "一元一次方程"}]


def test_knowledge_points_item_without_name_is_422(env):
    base, _ = env
    response = unified(base, {"question_text": "自由题干五", "idempotency_key": "u-kp-bad",
                              "knowledge_points": [{"id": "kp-1"}]})
    assert response.status_code == 422
    assert "name" in response.json()["error"]["message"]


def test_knowledge_points_over_20_is_422(env):
    base, _ = env
    response = unified(base, {"question_text": "自由题干六", "idempotency_key": "u-kp-many",
                              "knowledge_points": [{"name": f"k{i}"} for i in range(21)]})
    assert response.status_code == 422


def test_target_subquestion_id_forbidden(env):
    """target_subquestion_id 仅可信评测客户端可提交(文档错误码表 422)。"""
    base, _ = env
    response = unified(base, {"question_text": "自由题干七", "idempotency_key": "u-target",
                              "target_subquestion_id": "sq-1"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "PREPARED_QUESTION_TARGET_SUBQUESTION_FORBIDDEN"
    assert "target_subquestion_id" in error["details"]["conflicting_fields"]


@pytest.mark.parametrize("image", ["http://example.com/q.jpg", "https://example.com/q.jpg",
                                   "data:image/jpeg;base64,AAAA"])
def test_question_image_rejects_url_and_base64(env, image):
    """question_image 只接受已上传 file_id,禁 URL/Base64(§5 字段表)。"""
    base, _ = env
    response = unified(base, {"question_image": image, "idempotency_key": "u-url"})
    assert response.status_code == 422
    assert "file_id" in response.json()["error"]["message"]


def test_field_length_limits_are_422(env):
    base, _ = env
    assert unified(base, {"external_question_id": "x" * 256,
                          "idempotency_key": "u-len-1"}).status_code == 422
    assert unified(base, {"question_image": "x" * 129,
                          "idempotency_key": "u-len-2"}).status_code == 422
    assert unified(base, {"question_text": "x" * 8001,
                          "idempotency_key": "u-len-3"}).status_code == 422
    assert unified(base, {"question_text": "ok",
                          "idempotency_key": "x" * 129}).status_code == 422
    assert unified(base, {"question_text": "ok"}).status_code == 422  # 缺幂等键


def test_unified_open_idempotent_retry_same_conversation(env):
    base, _ = env
    body = {"external_question_id": "equation_subtract", "idempotency_key": "u-idem"}
    first = unified(base, body)
    second = unified(base, body)
    assert first.status_code == second.status_code == 200
    assert (first.json()["question"]["active_session"]["conversation"]
            == second.json()["question"]["active_session"]["conversation"])


def test_unified_open_without_auth_is_401(env):
    base, _ = env
    import httpx as _httpx
    response = _httpx.post(f"{base}/api/prepared-questions/open", json={"idempotency_key": "u"},
                           timeout=5.0, trust_env=False)
    assert response.status_code == 401


def test_per_question_open_route_still_works(env):
    """回归:/api/prepared-questions/{id}/open 不被统一路由吞掉。"""
    base, _ = env
    response = post(base, "/api/prepared-questions/equation_subtract/open",
                    {"idempotency_key": "u-regress"})
    assert response.status_code == 200
    assert response.json()["conversation"]["question_id"] == "equation_subtract"
