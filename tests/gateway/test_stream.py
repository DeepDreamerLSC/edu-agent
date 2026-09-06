"""stream 合同(01 §4、§5、§7):SSE 事件、TTFT、流式失败映射与事实记录。"""

from __future__ import annotations

import json

import pytest
from fake_openai import FakeOpenAI, Reply, sse

from edu_agent.gateway import FailureType, GatewayError, ModelRequest

from gwkit import gateway_for
from test_invoke import SCHEMA, SECRET, facts_line


def collect(stream) -> list:
    return list(stream)


@pytest.fixture
def fake():
    server = FakeOpenAI([sse("你", "好")]).start()
    yield server
    server.stop()


def test_stream_ok_events_and_record(tmp_path, fake):
    gateway = gateway_for(fake.url, tmp_path)
    events = collect(gateway.stream(ModelRequest(
        role="tutor",
        messages=[{"role": "user", "content": SECRET}],
        session_id="sess-2",
    )))
    gateway.close()
    tokens = [event for event in events if event.kind == "token"]
    done = [event for event in events if event.kind == "done"]
    assert [event.text for event in tokens] == ["你", "好"]
    assert len(done) == 1
    response = done[0].response
    assert response.text == "你好"
    assert response.finish_reason == "stop"
    assert response.input_tokens == 11 and response.output_tokens == 7
    # 流式请求体带上 stream_options.include_usage(issue #3:mlx/DeepSeek 流式 usage 口径)
    assert fake.requests[0]["stream"] is True

    payload = facts_line(tmp_path)
    assert payload["edu.outcome"] == "ok"
    assert payload["edu.session_id"] == "sess-2"
    assert payload["gen_ai.server.time_to_first_token"] >= 0  # 仅流式有值(01 §7)
    assert "小明" not in json.dumps(payload, ensure_ascii=False)
    assert payload["edu.redacted"][-1]["role"] == "assistant"  # 响应也只留长度+哈希


def test_stream_schema_violation_at_end(tmp_path):
    fake = FakeOpenAI([sse("我", "乱说")]).start()
    gateway = gateway_for(fake.url, tmp_path)
    with pytest.raises(GatewayError) as excinfo:
        collect(gateway.stream(ModelRequest(
            role="tutor", messages=[{"role": "user", "content": "hi"}], response_schema=SCHEMA,
        )))
    gateway.close()
    fake.stop()
    assert excinfo.value.failure is FailureType.SCHEMA_VIOLATION
    assert facts_line(tmp_path)["edu.outcome"] == "schema_violation"


def test_stream_timeout_first_token(tmp_path):
    fake = FakeOpenAI([Reply(delay_s=1.2, sse_lines=["data: {}"])]).start()
    gateway = gateway_for(fake.url, tmp_path, first_token_timeout_s=0.3, max_attempts=1)
    with pytest.raises(GatewayError) as excinfo:
        collect(gateway.stream(ModelRequest(role="tutor", messages=[{"role": "user", "content": "hi"}])))
    gateway.close()
    fake.stop()
    assert excinfo.value.failure is FailureType.TIMEOUT_FIRST_TOKEN
    assert facts_line(tmp_path)["edu.outcome"] == "timeout_first_token"


def test_stream_mid_abort_is_connection(tmp_path):
    # SSE 不以 [DONE] 结尾 = 流式中途断开(01 §6 故障注入清单)
    fake = FakeOpenAI([sse("你", done=False)]).start()
    gateway = gateway_for(fake.url, tmp_path, max_attempts=1)
    with pytest.raises(GatewayError) as excinfo:
        collect(gateway.stream(ModelRequest(role="tutor", messages=[{"role": "user", "content": "hi"}])))
    gateway.close()
    fake.stop()
    assert excinfo.value.failure is FailureType.CONNECTION
    payload = facts_line(tmp_path)
    assert payload["edu.outcome"] == "connection"
    assert payload["edu.attempt"] == 1


def test_stream_truncated(tmp_path):
    fake = FakeOpenAI([sse("很长的前半段", finish_reason="length")]).start()
    gateway = gateway_for(fake.url, tmp_path)
    with pytest.raises(GatewayError) as excinfo:
        collect(gateway.stream(ModelRequest(role="tutor", messages=[{"role": "user", "content": "hi"}])))
    gateway.close()
    fake.stop()
    assert excinfo.value.failure is FailureType.TRUNCATED


def test_stream_http_error_maps(tmp_path):
    fake = FakeOpenAI([Reply(status=429)]).start()
    gateway = gateway_for(fake.url, tmp_path)
    with pytest.raises(GatewayError) as excinfo:
        collect(gateway.stream(ModelRequest(role="tutor", messages=[{"role": "user", "content": "hi"}])))
    gateway.close()
    fake.stop()
    assert excinfo.value.failure is FailureType.RATE_LIMITED


def test_stream_invalid_sse_chunk(tmp_path):
    bad_lines = ["data: {broken json", "data: [DONE]"]
    fake = FakeOpenAI([Reply(sse_lines=bad_lines)]).start()
    gateway = gateway_for(fake.url, tmp_path)
    with pytest.raises(GatewayError) as excinfo:
        collect(gateway.stream(ModelRequest(role="tutor", messages=[{"role": "user", "content": "hi"}])))
    gateway.close()
    fake.stop()
    assert excinfo.value.failure is FailureType.UPSTREAM_5XX
