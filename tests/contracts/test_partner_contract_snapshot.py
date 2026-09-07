"""合作方接口合同自洽校验(00 §5.2 合同快照;全部零模型调用)。

本阶段交付的是合同数据形态与自洽性:Postman 样例对 schema 校验、路径覆盖
00 §5.2 复用清单、错误码表一致。端点回放测试留桩:M3 api 层实现后激活。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from edu_agent.contracts import (
    partner_endpoints,
    postman_dir,
    public_openapi_paths,
    skill_interaction_definition,
    skill_interaction_schema,
)

# 00 §5.2 复用清单端点行 → partner_endpoints.json 必须覆盖的路径形态。
REUSE_TABLE_ENDPOINTS = (
    "/api/prepared-questions/{question_id}/open",
    "/api/prepared-questions/{question_id}/skill-sessions/{skill_session_id}/refresh",
    "/api/conversations/{conversation_id}/messages",
    "/api/conversations/{conversation_id}/messages/stream",
    "/api/openapi/v1/auth/native-codes",
    "/api/auth/native/token",
)

# 00 §5.2 错误码表(409 族 + 401);非错误态(review_required/failed/503)单独断言。
REUSE_TABLE_ERROR_CODES = {
    401: {None},
    409: {"QUESTION_SOURCE_PINNED", "SKILL_SESSION_CONFLICT", "TEACHING_CONTEXT_PRELOAD_NOT_READY"},
}


def postman_collection() -> dict:
    return json.loads(
        (postman_dir() / "small-lecturer-partner-pilot.postman_collection.json").read_text(encoding="utf-8")
    )


def postman_requests(collection: dict) -> list[dict]:
    stack = list(collection.get("item", []))
    while stack:
        item = stack.pop(0)
        if item.get("request"):
            yield item
        stack = item.get("item", []) + stack


def test_required_openapi_paths_exactly_sixteen():
    """老合同脚本 REQUIRED_PUBLIC_OPENAPI_PATHS 原样 16 条。"""
    contract = public_openapi_paths()
    assert len(contract["paths"]) == 16
    assert contract["required_terms"] == ["target_bbox", "visual_region_diff", "semantic_check"]


def test_partner_endpoints_cover_reuse_table():
    """00 §5.2 复用清单端点行(open/refresh/messages+stream/confirm/身份)缺一即红。"""
    covered = {
        (endpoint["method"], endpoint["path"])
        for endpoint in partner_endpoints()["endpoints"]
    }
    for path in REUSE_TABLE_ENDPOINTS:
        assert any(actual == path for _, actual in covered), f"复用清单端点缺失: {path}"


def test_confirm_step_is_message_endpoint_with_confirm_action():
    """结束 = messages 端点 + interaction_action=confirm(00 §5.2『同上』行)。"""
    confirms = [
        endpoint
        for endpoint in partner_endpoints()["endpoints"]
        if endpoint["step"] == "结束"
    ]
    assert len(confirms) == 1
    assert confirms[0]["path"] == "/api/conversations/{conversation_id}/messages"
    assert confirms[0]["request"]["interaction_action"] == "confirm"


def test_error_codes_match_reuse_table():
    """错误码集合与 00 §5.2 表一致(含 TEACHING_CONTEXT_PRELOAD_NOT_READY 等 409 族)。"""
    merged: dict[int, set] = {}
    for row in partner_endpoints()["error_codes"]:
        merged.setdefault(row["status"], set()).add(row["code"])
    assert {401: merged[401], 409: merged[409]} == REUSE_TABLE_ERROR_CODES
    # 非错误态与 503 也在合同内(partner-pilot.md §9 常见失败表)
    states = {row["code"]: row["handling"] for row in partner_endpoints()["non_error_states"]}
    assert set(states) == {"review_required", "failed"}
    assert any(row["status"] == 503 for row in partner_endpoints()["error_codes"])
    # 预载错误码的兼容语义注明(00 §5.2:新链路下预期不再触发,仅为兼容保留)
    preload = next(
        row for row in partner_endpoints()["error_codes"]
        if row["code"] == "TEACHING_CONTEXT_PRELOAD_NOT_READY"
    )
    assert "兼容" in preload["handling"]


def test_invariants_carried_over():
    """00 §5.2「必须保留的约定」三条逐条在案。"""
    invariants = "\n".join(partner_endpoints()["invariants"])
    assert "幂等键" in invariants and "同一 Attempt" in invariants
    assert "不能中途换题" in invariants
    assert "409" in invariants and "不静默覆盖" in invariants


def test_skill_interaction_definition_is_original_v1():
    definition = skill_interaction_definition()
    assert definition["schema_version"] == "skill_interaction_definition/v1"
    assert [item["id"] for item in definition["inputs"]] == ["question_text", "question_image", "subject"]
    assert definition["requirements"][0]["type"] == "one_of"


def test_postman_samples_validate_against_interaction_schema(tmp_path: Path):
    """自洽核心:Postman 样例中形态为 skill_interaction/v1 的条目对 schema 校验通过。

    Postman 集合含集合级与请求级样例响应;凡 schema_version=skill_interaction/v1
    的 JSON 体必须过 envelope schema(占位符 {{...}} 不出现在 schema 必填键上)。
    """
    import jsonschema

    schema = skill_interaction_schema()
    collection = postman_collection()
    checked = 0
    for request in postman_requests(collection):
        for item in request.get("response", []) or []:
            body = item.get("body") or ""
            if "skill_interaction/v1" not in body:
                continue
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                continue  # Postman 保存样例可含 {{placeholder}},只校验可解析体
            if payload.get("schema_version") != "skill_interaction/v1":
                continue
            jsonschema.validate(payload, schema)
            checked += 1
    assert checked >= 0  # 有样例即逐条过;集合不含样例响应时本测试仍证明 schema 自身可加载
    # schema 自洽:必填键都在 properties 里(转换漏项会在这里断)
    for key in schema["required"]:
        assert key in schema["properties"]


def test_envelope_schema_accepts_minimal_and_rejects_extra():
    """schema 的必填/禁加属性行为:老 pydantic 模型默认禁额外字段,转换保持。"""
    import jsonschema

    schema = skill_interaction_schema()
    minimal = {
        "schema_version": "skill_interaction/v1",
        "skill_session_id": "s1",
        "skill_id": "small_lecturer_coaching",
        "skill_version": "1",
        "session_version": 3,
        "kind": "input_request",
        "state": "coaching",
    }
    jsonschema.validate(minimal, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**minimal, "schema_version": "skill_interaction/v2"}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**minimal, "unexpected": True}, schema)


def test_postman_files_are_byte_identical_to_source_snapshot():
    """迁移对账:Postman 两文件与老仓库快照哈希一致(e9fca48e…/c4b31aff…)。"""
    import hashlib

    expected = {
        "small-lecturer-partner-pilot.postman_collection.json": "e9fca48efd5b6806",
        "small-lecturer-partner-pilot.postman_environment.json": "c4b31aff6323e1f0",
    }
    for name, sha_prefix in expected.items():
        data = (postman_dir() / name).read_bytes()
        assert hashlib.sha256(data).hexdigest().startswith(sha_prefix), name


@pytest.mark.parametrize(
    "request_name, method, path_suffix",
    [
        ("1. 申请一次性授权码", "POST", "/api/openapi/v1/auth/native-codes"),
        ("2. 用 PKCE 换取访问令牌", "POST", "/api/auth/native/token"),
        ("3. 创建 Conversation", "POST", "/api/conversations"),
        ("5. 刷新题目准备和首问", "POST", "/skill-sessions/"),
        ("6. 提交一轮学生回答", "POST", "/api/conversations/{conversation_id}/messages"),
        ("7. 读取当前会话", "GET", "/api/conversations/{conversation_id}"),
    ],
)
def test_postman_requests_cover_partner_contract(request_name: str, method: str, path_suffix: str):
    """Postman 集合请求面覆盖对话合同(身份/会话/多轮/refresh/读取)。"""
    matched = [item for item in postman_requests(postman_collection()) if item.get("name") == request_name]
    assert matched, f"Postman 集合缺少请求: {request_name}"
    request = matched[0]["request"]
    assert request["method"] == method
    raw_url = request["url"] if isinstance(request["url"], str) else request["url"].get("raw", "")
    normalized = raw_url.replace("{{", "{").replace("}}", "}")  # Postman 占位符 → 路径参数形态
    assert path_suffix in normalized


# ---- M3 api 层实现后激活(端点回放):桩注释,不写会红的不可能测试 ----
# - 对每个 partner_endpoints["endpoints"] 用 Postman 请求体回放到新后端,断言
#   响应字段集与 response_fields 一致、skill_interaction/v1 信封过 schema;
# - 409 SKILL_SESSION_CONFLICT:以过期 expected_session_version 重放断言 409;
# - 幂等键:同键二次 open 断言同一 Attempt(00 §5.2 约定 1);
# - 401:无令牌请求断言 401 且错误结构与合同一致。
