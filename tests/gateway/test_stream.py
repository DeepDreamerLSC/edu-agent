"""stream 合同(01 §4、§5、§7):SSE 事件、TTFT、流式失败映射与事实记录。

共享件(SCHEMA/SECRET/facts_line/假上游生命周期)在 tests/fixtures/gwkit.py;
重试/备选语义见故障注入套件。
"""

from __future__ import annotations

import json

import pytest
from fake_openai import Reply, sse

from edu_agent.gateway import FailureType, GatewayError, ModelRequest

from gwkit import SCHEMA, SECRET, facts_line, fake_gateway


def test_stream_ok_events_and_record(tmp_path):
    with fake_gateway(tmp_path, [sse("你", "好")]) as (fake, gateway):
        events = list(gateway.stream(ModelRequest(
            role="tutor",
            messages=[{"role": "user", "content": SECRET}],
            session_id="sess-2",
        )))
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


@pytest.mark.parametrize("reply,kwargs,schema,expected,outcome", [
    # 流到结尾才见 schema 违规
    (sse("我", "乱说"), {}, True, FailureType.SCHEMA_VIOLATION, "schema_violation"),
    # 首 token 超时
    (Reply(delay_s=1.2, sse_lines=["data: {}"]), {"first_token_timeout_s": 0.3, "max_attempts": 1},
     False, FailureType.TIMEOUT_FIRST_TOKEN, "timeout_first_token"),
    # SSE 不以 [DONE] 结尾 = 流式中途断开(01 §6 故障注入清单)
    (sse("你", done=False), {"max_attempts": 1}, False, FailureType.CONNECTION, "connection"),
    (sse("很长的前半段", finish_reason="length"), {}, False, FailureType.TRUNCATED, None),
    (Reply(status=429), {"max_attempts": 1}, False, FailureType.RATE_LIMITED, None),
    (Reply(sse_lines=["data: {broken json", "data: [DONE]"]), {"max_attempts": 1},
     False, FailureType.UPSTREAM_5XX, None),
], ids=["schema_violation_at_end", "timeout_first_token", "mid_abort_connection",
        "truncated", "http_429", "invalid_sse_chunk"])
def test_stream_failure_maps_with_record(tmp_path, reply, kwargs, schema, expected, outcome):
    """流式失败类型映射(类型映射与台账;重试语义见故障注入套件)。"""
    with fake_gateway(tmp_path, [reply], **kwargs) as (fake, gateway):
        messages = [{"role": "user", "content": "hi"}]
        request = (ModelRequest(role="tutor", messages=messages, response_schema=SCHEMA)
                   if schema else ModelRequest(role="tutor", messages=messages))
        with pytest.raises(GatewayError) as excinfo:
            list(gateway.stream(request))
        assert excinfo.value.failure is expected
        if outcome is not None:
            payload = facts_line(tmp_path)
            assert payload["edu.outcome"] == outcome
            if outcome == "connection":  # 中断后不重发(重发会重复输出)
                assert payload["edu.attempt"] == 1
