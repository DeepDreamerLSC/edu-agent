"""invoke 合同(01 §4、§7、§8):失败类型映射、事实记录全字段、脱敏、路线 1 校验。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fake_openai import FakeOpenAI, Reply, completion

from edu_agent.gateway import FailureType, GatewayError, ModelRequest, RegistryError

from gwkit import gateway_for, registry_for

SECRET = "学生姓名是小明,就读三年级二班"
SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}


def facts_line(facts_dir: Path) -> dict:
    files = list(Path(facts_dir).glob("model_calls-*.jsonl"))
    assert len(files) == 1, "事实记录按天切分,单次调用应只有一个文件"
    lines = files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


@pytest.fixture
def fake():
    server = FakeOpenAI([completion("答案")]).start()
    yield server
    server.stop()


def test_invoke_ok_records_full_fact(tmp_path, fake):
    gateway = gateway_for(fake.url, tmp_path)
    response = gateway.invoke(ModelRequest(
        role="tutor",
        messages=[{"role": "user", "content": SECRET}],
        session_id="sess-1",
        trace_id="trace-9",
    ))
    gateway.close()
    assert response.text == "答案"
    assert response.finish_reason == "stop"
    assert response.input_tokens == 11 and response.output_tokens == 7
    assert fake.requests[0]["model"] == "fake-model"

    payload = facts_line(tmp_path)
    # 01 §7 字段齐全、不加不减
    assert set(payload) == {
        "edu.call_id", "edu.ts", "edu.role", "edu.attempt", "edu.outcome",
        "edu.session_id", "edu.fallback_from", "edu.fallback_to", "edu.redacted", "edu.trace_id",
        "edu.queue_ms", "edu.error_detail",
        "gen_ai.provider.name", "gen_ai.request.model", "gen_ai.response.model",
        "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
        "gen_ai.usage.cache_read.input_tokens", "gen_ai.response.finish_reasons",
        "gen_ai.server.time_to_first_token", "edu.total_ms",
    }
    assert payload["edu.outcome"] == "ok"
    assert payload["edu.role"] == "tutor"
    assert payload["edu.attempt"] == 1
    assert payload["edu.session_id"] == "sess-1"
    assert payload["edu.trace_id"] == "trace-9"
    assert payload["edu.queue_ms"] == 0
    assert payload["edu.error_detail"] is None
    assert payload["gen_ai.provider.name"] == "fake"
    assert payload["gen_ai.request.model"] == "m"
    assert payload["gen_ai.response.model"] == "fake-model"
    assert payload["gen_ai.usage.input_tokens"] == 11
    assert payload["gen_ai.usage.output_tokens"] == 7
    assert payload["gen_ai.response.finish_reasons"] == ["stop"]
    assert payload["gen_ai.server.time_to_first_token"] is None  # 非流式无首 token 事件(01 §5)
    assert payload["edu.total_ms"] >= 0
    # 脱敏(01 §7):学生内容只以长度+哈希进入记录,原文绝不出现
    line = json.dumps(payload, ensure_ascii=False)
    assert "小明" not in line and SECRET not in line
    digest = payload["edu.redacted"][0]
    assert digest["role"] == "user" and digest["len"] == len(SECRET) and len(digest["sha256"]) == 16


@pytest.mark.parametrize("reply,expected,detail", [
    (Reply(status=429, headers={"Retry-After": "2"}), FailureType.RATE_LIMITED, "HTTP 429"),
    (Reply(status=500), FailureType.UPSTREAM_5XX, "HTTP 500"),
    (Reply(status=503), FailureType.UPSTREAM_5XX, "HTTP 503"),
    (Reply(status=404), FailureType.UPSTREAM_4XX, "HTTP 404"),
    (Reply(status=400), FailureType.UPSTREAM_4XX, "HTTP 400"),
    (Reply(status=200, raw_body="<html>not json</html>"), FailureType.UPSTREAM_5XX, None),
])
def test_invoke_http_failures_map_to_types(tmp_path, reply, expected, detail):
    fake = FakeOpenAI([reply]).start()
    gateway = gateway_for(fake.url, tmp_path)
    with pytest.raises(GatewayError) as excinfo:
        gateway.invoke(ModelRequest(role="tutor", messages=[{"role": "user", "content": "hi"}]))
    gateway.close()
    fake.stop()
    assert excinfo.value.failure is expected
    if detail:
        assert detail in excinfo.value.detail
    payload = facts_line(tmp_path)
    assert payload["edu.outcome"] == expected.value
    assert payload["edu.attempt"] == 1
    assert "小明" not in json.dumps(payload, ensure_ascii=False)


def test_invoke_truncated_and_content_filtered(tmp_path):
    for finish, expected in [("length", FailureType.TRUNCATED), ("content_filter", FailureType.CONTENT_FILTERED)]:
        fake = FakeOpenAI([completion("半截", finish_reason=finish)]).start()
        gateway = gateway_for(fake.url, tmp_path)
        with pytest.raises(GatewayError) as excinfo:
            gateway.invoke(ModelRequest(role="tutor", messages=[{"role": "user", "content": "hi"}]))
        gateway.close()
        fake.stop()
        assert excinfo.value.failure is expected


def test_invoke_timeout_total(tmp_path):
    fake = FakeOpenAI([Reply(delay_s=1.2, json_body={})]).start()
    gateway = gateway_for(fake.url, tmp_path, total_timeout_s=0.3, max_attempts=1)
    with pytest.raises(GatewayError) as excinfo:
        gateway.invoke(ModelRequest(role="tutor", messages=[{"role": "user", "content": "hi"}]))
    gateway.close()
    fake.stop()
    assert excinfo.value.failure is FailureType.TIMEOUT_TOTAL
    assert facts_line(tmp_path)["edu.outcome"] == "timeout_total"


def test_invoke_connection_dropped(tmp_path):
    # 响应体发一半即断:任何环境都是确定性连接中断(不接受响应的代理/直连行为一致)
    fake = FakeOpenAI([Reply(partial_body='{"choices": [{')]).start()
    gateway = gateway_for(fake.url, tmp_path, max_attempts=1)
    with pytest.raises(GatewayError) as excinfo:
        gateway.invoke(ModelRequest(role="tutor", messages=[{"role": "user", "content": "hi"}]))
    gateway.close()
    fake.stop()
    assert excinfo.value.failure is FailureType.CONNECTION
    assert facts_line(tmp_path)["edu.outcome"] == "connection"


def test_invoke_schema_route1_violation(tmp_path):
    fake = FakeOpenAI([completion("我答不上来")]).start()  # 非法 JSON → schema_violation
    gateway = gateway_for(fake.url, tmp_path)  # json_strict=True
    with pytest.raises(GatewayError) as excinfo:
        gateway.invoke(ModelRequest(
            role="tutor",
            messages=[{"role": "user", "content": SECRET}],
            response_schema=SCHEMA,
        ))
    gateway.close()
    fake.stop()
    error = excinfo.value
    assert error.failure is FailureType.SCHEMA_VIOLATION
    assert error.output == "我答不上来"  # 违规原文保留,供修复重试(PR2)
    # 路线 1:schema 进了 prompt(issue #8)
    sent = fake.requests[0]["messages"]
    assert "JSON Schema" in sent[-1]["content"]
    assert json.dumps(SCHEMA, ensure_ascii=False) in sent[-1]["content"]
    # 失败记录不含违规原文与学生内容
    line = json.dumps(facts_line(tmp_path), ensure_ascii=False)
    assert "我答不上来" not in line and "小明" not in line


def test_invoke_schema_ok_passes(tmp_path):
    fake = FakeOpenAI([completion(json.dumps({"answer": "3+4=7"}, ensure_ascii=False))]).start()
    gateway = gateway_for(fake.url, tmp_path)
    response = gateway.invoke(ModelRequest(
        role="tutor", messages=[{"role": "user", "content": "3+4?"}], response_schema=SCHEMA,
    ))
    gateway.close()
    fake.stop()
    assert json.loads(response.text) == {"answer": "3+4=7"}
    assert facts_line(tmp_path)["edu.outcome"] == "ok"


def test_schema_request_rejected_for_non_strict_role(tmp_path):
    fake = FakeOpenAI([]).start()
    gateway = gateway_for(fake.url, tmp_path, json_strict=False)
    with pytest.raises(RegistryError, match="json_strict"):
        gateway.invoke(ModelRequest(
            role="tutor", messages=[{"role": "user", "content": "hi"}], response_schema=SCHEMA,
        ))
    gateway.close()
    fake.stop()
    assert fake.requests == []  # 不发给不支持的服务端(01 §8)


def test_api_key_missing_fails_fast(tmp_path):
    from edu_agent.gateway import Gateway, ProviderConfig
    registry = registry_for("http://127.0.0.1:9")
    registry.providers["fake"] = ProviderConfig("fake", "http://127.0.0.1:9", "NO_SUCH_KEY_ENV", True)
    gateway = Gateway(registry, tmp_path)
    with pytest.raises(RegistryError, match="NO_SUCH_KEY_ENV"):
        gateway.invoke(ModelRequest(role="tutor", messages=[{"role": "user", "content": "hi"}]))
    gateway.close()
