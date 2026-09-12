"""统一 Open 端点合同(M3 PR-3;老系统文档 small-lecturer-v1 §5 逐条)。

POST /api/prepared-questions/open:字段/长度/严格类型/组合规则照 §5,
pending 恒 false(同步内核),active_session 恒在。零真实模型(桩内核+确定性题源)。
"""

from __future__ import annotations

import httpx
import pytest
from partner_api import MapSource, RecordingKernel, post, serving

from edu_agent.api import build_service


@pytest.fixture
def env():
    kernel = RecordingKernel(["我们先看已知条件,题目要我们求什么?"])
    with serving(kernel, source=MapSource()) as base:
        yield base, kernel


def unified(base: str, body: dict) -> httpx.Response:
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


@pytest.mark.parametrize("body", [
    {"question_text": "题干", "question_image": "file-1", "idempotency_key": "u-004"},
    {"question_text": "题干", "external_question_id": "equation_subtract",
     "idempotency_key": "u-005"},
], ids=["test_text_with_image_is_422_conflict",
        "test_text_with_external_question_id_is_422_conflict"])
def test_question_text_conflicts_are_422(env, body):
    """question_text 与其他题源字段互斥(老系统文档:自由材料/题库二选一)。"""
    base, _ = env
    response = unified(base, body)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "PREPARED_QUESTION_SOURCE_CONFLICT"
    assert "question_text" in error["details"]["conflicting_fields"]


def test_answer_correct_three_states_echoed(env):
    """answer_correct 严格三态(true/false/null)回显;显式有值 provenance=partner_open。"""
    base, _ = env
    for value in (True, False, None):
        response = unified(base, {"question_text": "自由题干一", "idempotency_key": f"u-ac-{value}",
                                  "answer_correct": value})
        assert response.status_code == 200, (value, response.text)
        assert response.json()["answer_correct"] is value
        assert response.json()["answer_correct_provenance"] == ("partner_open" if value is not None
                                                                else None)


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
    response = httpx.post(f"{base}/api/prepared-questions/open", json={"idempotency_key": "u"},
                          timeout=5.0, trust_env=False)
    assert response.status_code == 401


def test_per_question_open_route_still_works(env):
    """回归:/api/prepared-questions/{id}/open 不被统一路由吞掉。"""
    base, _ = env
    response = post(base, "/api/prepared-questions/equation_subtract/open",
                    {"idempotency_key": "u-regress"})
    assert response.status_code == 200
    assert response.json()["conversation"]["question_id"] == "equation_subtract"


# ---------- PR-4:answer_correct → 内核 learner.answer_status 接线 ----------

@pytest.mark.parametrize("answer_correct,question_text,idem_key,expected_status", [
    (True, "自由题干八", "u-wire-true", "correct"),
    (False, "自由题干九", "u-wire-false", "incorrect"),
], ids=["test_answer_correct_true_wires_learner_correct",
        "test_answer_correct_false_wires_learner_incorrect"])
def test_answer_correct_wires_learner_status(env, answer_correct, question_text,
                                             idem_key, expected_status):
    """显式 answer_correct → learner.answer_status 映射,provenance=partner_open。"""
    base, kernel = env
    response = unified(base, {"question_text": question_text, "idempotency_key": idem_key,
                              "answer_correct": answer_correct})
    assert response.status_code == 200
    assert kernel.learners[0]["answer_status"] == expected_status
    assert kernel.learners[0]["answer_correct_provenance"] == "partner_open"
    assert response.json()["answer_correct_provenance"] == "partner_open"


@pytest.mark.parametrize("body_extra", [{"answer_correct": None}, {}])
def test_answer_correct_null_or_omitted_maps_assumed_incorrect(env, body_extra):
    """A 线 §8.5(M3 WS1):null/省略 → answer_status="incorrect"(unanswered 默认按做错,
    等价老系统 assumed_incorrect);provenance 缺省(假设不是出处,不标 partner_open)。"""
    base, kernel = env
    body = {"question_text": "自由题干十", "idempotency_key": f"u-wire-{len(body_extra)}",
            **body_extra}
    response = unified(base, body)
    assert response.status_code == 200
    assert kernel.learners[0]["answer_status"] == "incorrect"
    assert kernel.learners[0].get("answer_correct_provenance") is None
    assert response.json()["answer_correct_provenance"] is None


def test_bank_hit_with_client_answer_wins_provenance(env):
    """题库命中 + 客户端显式 answer_correct:客户值覆写题源出处,answer_status 照映射。"""
    base, kernel = env
    response = unified(base, {"external_question_id": "equation_subtract",
                              "idempotency_key": "u-wire-bank", "answer_correct": False})
    assert response.status_code == 200
    learner = kernel.learners[0]
    assert learner["answer_status"] == "incorrect"
    assert learner["answer_correct_provenance"] == "partner_open"  # 客户显式 > 题库来源
    assert response.json()["answer_correct_provenance"] == "partner_open"


def test_bank_hit_without_client_answer_keeps_bank_provenance(env):
    """题库命中且客户端未带 answer_correct:provenance 保持题库来源;answer_status 走
    A 线 assumed_incorrect 映射(省略 ≠ unknown——R6 首问策略信号源要求默认值落地)。"""
    base, kernel = env
    response = unified(base, {"external_question_id": "equation_subtract",
                              "idempotency_key": "u-wire-bank-plain"})
    assert response.status_code == 200
    assert kernel.learners[0].get("answer_correct_provenance") == "partner_question_bank"
    assert kernel.learners[0]["answer_status"] == "incorrect"  # A 线:省略按做错
    assert response.json()["answer_correct_provenance"] == "partner_question_bank"


# ---------- A 线 §8.5(M3 WS1):per-question open 请求体 → learner ----------

def test_per_question_open_receives_answer_correct_and_knowledge_points(env):
    """per-question open(App 主路径,#55):answer_correct/knowledge_points 从请求体
    接收 → learner 映射;替换原写死 learner={}。三分支(true/false/省略)各一例。"""
    base, kernel = env
    for key, extra, expected in [
            ("t", {"answer_correct": True}, "correct"),
            ("f", {"answer_correct": False}, "incorrect"),
            ("o", {}, "incorrect")]:
        response = post(base, "/api/prepared-questions/equation_subtract/open",
                        {"idempotency_key": f"pq-ac-{key}",
                         "knowledge_points": [{"id": "kp-9", "name": "简易方程"}],
                         "grade": "六年级", **extra})
        assert response.status_code == 200, (key, response.text)
        learner = kernel.learners[-1]
        assert learner["answer_status"] == expected
        assert learner["knowledge_points"] == [{"id": "kp-9", "name": "简易方程"}]
        # 非合同字段照旧透传且优先于题源(同统一 open:equation_subtract 题源为五年级)
        assert learner["grade"] == "六年级"
        assert learner["answer_correct_provenance"] == (
            "partner_open" if extra else "partner_question_bank")


def test_per_question_open_forbidden_fields_rejected(env):
    """约定 4(00 §5.2)与统一 open 同款:客户端提交 answer/analysis/mastery_status → 403。"""
    base, kernel = env
    response = post(base, "/api/prepared-questions/equation_subtract/open",
                    {"idempotency_key": "pq-forbidden", "analysis": "先移项再合并"})
    assert response.status_code == 403
    assert "analysis" in response.json()["error"]["message"]
    assert kernel.learners == []  # 未产生内核调用


def test_per_question_open_missing_idempotency_key_is_422(env):
    base, kernel = env
    response = post(base, "/api/prepared-questions/equation_subtract/open",
                    {"answer_correct": True})
    assert response.status_code == 422
    assert "idempotency_key" in response.json()["error"]["message"]
    assert kernel.learners == []


def test_bank_hit_with_client_image_merges_into_question():
    """同题组合(§5):题库命中 + 客户端题图 → 文答用题库的,题图用客户端的。"""
    kernel = RecordingKernel(["题图已合并。"])
    service = build_service(kernel, source=MapSource(),
                            image_resolver=lambda fid: f"data:image/png;base64,{fid}")
    with serving(service=service) as base:
        response = post(base, "/api/prepared-questions/open", {
            "external_question_id": "equation_subtract", "idempotency_key": "u-img-merge",
            "question_image": "file_abc123"})
        assert response.status_code == 200
        question = kernel.questions[0]
        # 文答以题库为准;题图 = 客户端 file_id 经解析器翻译的 data URL
        assert question["text"].startswith("解方程 3x+7=25")
        assert question["answer"] == "x=6"
        assert question["image"] == "data:image/png;base64,file_abc123"


def test_unresolvable_image_file_id_is_early_422():
    """解析器注入时 file_id 不存在 → 422 FILE_NOT_READY(坏引用不进模型层变 503)。"""
    kernel = RecordingKernel(["不该被调用"])
    service = build_service(kernel, source=MapSource(), image_resolver=lambda fid: None)
    with serving(service=service) as base:
        response = post(base, "/api/prepared-questions/open", {
            "external_question_id": "equation_subtract", "idempotency_key": "u-img-bad",
            "question_image": "file_gone"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "FILE_NOT_READY"
        assert kernel.questions == []  # 未产生内核调用
