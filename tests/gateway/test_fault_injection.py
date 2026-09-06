"""故障注入合同(01 §6):九种失败类型各一个测试,假 OpenAI 兼容服务器按脚本注入。

断言四件事:落到正确的失败类型、重试次数正确、备选按策略触发、事实记录完整。
"""

from __future__ import annotations

import json
import threading
import time

import pytest
from fake_openai import FakeOpenAI, Reply, completion, sse

from edu_agent.gateway import FailureType, GatewayError, ModelRequest

from gwkit import gateway_for
from test_invoke import SCHEMA, facts_line

MSG = [{"role": "user", "content": "3+4=?"}]


def call(gateway):
    return gateway.invoke(ModelRequest(role="tutor", messages=MSG, session_id="fault-1"))


def facts(tmp_path) -> list[dict]:
    files = list(tmp_path.glob("model_calls-*.jsonl"))
    lines = files[0].read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines]


# ---------- 九种失败类型(01 §4 表逐行对应) ----------


def test_timeout_first_token_stream_retry_recovers(tmp_path):
    # 首 token 超时:可重试;第二次成功 → 成功记录 attempt=2
    fake = FakeOpenAI([
        Reply(delay_s=1.2, sse_lines=["data: [DONE]"]),
        sse("答案"),
    ]).start()
    gateway = gateway_for(fake.url, tmp_path, first_token_timeout_s=0.3, max_attempts=2)
    events = list(gateway.stream(ModelRequest(role="tutor", messages=MSG)))
    gateway.close()
    fake.stop()
    assert [e.text for e in events if e.kind == "token"] == ["答案"]
    assert len(fake.requests) == 2
    payload = facts_line(tmp_path)
    assert payload["edu.outcome"] == "ok" and payload["edu.attempt"] == 2


def test_timeout_total_not_retried(tmp_path):
    # 总时长超时:不可重试 → 只发一次请求
    fake = FakeOpenAI([Reply(delay_s=1.2, json_body={}), completion("不该到达")]).start()
    gateway = gateway_for(fake.url, tmp_path, total_timeout_s=0.3, max_attempts=3)
    with pytest.raises(GatewayError) as excinfo:
        call(gateway)
    gateway.close()
    fake.stop()
    assert excinfo.value.failure is FailureType.TIMEOUT_TOTAL
    assert len(fake.requests) == 1  # 否则重试(01 §4:否)
    assert facts_line(tmp_path)["edu.outcome"] == "timeout_total"


def test_rate_limited_reads_retry_after_and_exhausts(tmp_path):
    fake = FakeOpenAI([
        Reply(status=429, headers={"Retry-After": "0"}),
        Reply(status=429, headers={"Retry-After": "0"}),
    ]).start()
    gateway = gateway_for(fake.url, tmp_path, max_attempts=2)
    with pytest.raises(GatewayError) as excinfo:
        call(gateway)
    gateway.close()
    fake.stop()
    assert excinfo.value.failure is FailureType.RATE_LIMITED
    assert len(fake.requests) == 2  # 重试读 Retry-After=0
    payload = facts_line(tmp_path)
    assert payload["edu.outcome"] == "rate_limited" and payload["edu.attempt"] == 2


def test_upstream_5xx_retries_then_raises(tmp_path):
    fake = FakeOpenAI([Reply(status=500), Reply(status=503)]).start()
    gateway = gateway_for(fake.url, tmp_path, max_attempts=2)
    with pytest.raises(GatewayError) as excinfo:
        call(gateway)
    gateway.close()
    fake.stop()
    assert excinfo.value.failure is FailureType.UPSTREAM_5XX
    assert len(fake.requests) == 2
    payload = facts_line(tmp_path)
    assert payload["edu.outcome"] == "upstream_5xx"
    assert "503" in payload["edu.error_detail"]  # 事后排查靠 error_detail(01 §7)


def test_upstream_4xx_no_retry_no_fallback(tmp_path):
    fake = FakeOpenAI([Reply(status=404), completion("不该到达")]).start()
    gateway = gateway_for(fake.url, tmp_path, max_attempts=3, fallback_url=fake.url)
    with pytest.raises(GatewayError) as excinfo:
        call(gateway)
    gateway.close()
    fake.stop()
    assert excinfo.value.failure is FailureType.UPSTREAM_4XX
    assert len(fake.requests) == 1  # 不重试、不备选(01 §4:否/否)


def test_schema_violation_repairs_once_then_raises(tmp_path):
    fake = FakeOpenAI([completion("我不会"), completion("还是不会")]).start()
    gateway = gateway_for(fake.url, tmp_path, max_attempts=3)
    with pytest.raises(GatewayError) as excinfo:
        gateway.invoke(ModelRequest(
            role="tutor", messages=MSG, response_schema=SCHEMA, session_id="fault-1",
        ))
    gateway.close()
    fake.stop()
    assert excinfo.value.failure is FailureType.SCHEMA_VIOLATION
    assert len(fake.requests) == 2  # 修复重试恰一次,不受 max_attempts=3 影响
    # 修复重试带上第一次的违规原文与修复提示(路线 1,issue #8)
    retry_messages = fake.requests[1]["messages"]
    assert retry_messages[-2]["role"] == "assistant" and retry_messages[-2]["content"] == "我不会"
    assert "JSON Schema" in retry_messages[-1]["content"]
    assert facts_line(tmp_path)["edu.outcome"] == "schema_violation"


def test_schema_violation_repair_recovers(tmp_path):
    fake = FakeOpenAI([completion("瞎说"), completion(json.dumps({"answer": "7"}, ensure_ascii=False))]).start()
    gateway = gateway_for(fake.url, tmp_path)
    response = gateway.invoke(ModelRequest(
        role="tutor", messages=MSG, response_schema=SCHEMA, session_id="fault-1",
    ))
    gateway.close()
    fake.stop()
    assert json.loads(response.text) == {"answer": "7"}
    payload = facts_line(tmp_path)
    assert payload["edu.outcome"] == "ok" and payload["edu.attempt"] == 2


def test_truncated_no_retry(tmp_path):
    fake = FakeOpenAI([completion("半截", finish_reason="length"), completion("不该到达")]).start()
    gateway = gateway_for(fake.url, tmp_path, max_attempts=3)
    with pytest.raises(GatewayError) as excinfo:
        call(gateway)
    gateway.close()
    fake.stop()
    assert excinfo.value.failure is FailureType.TRUNCATED
    assert len(fake.requests) == 1


def test_content_filtered_no_retry(tmp_path):
    fake = FakeOpenAI([completion("被过滤", finish_reason="content_filter")]).start()
    gateway = gateway_for(fake.url, tmp_path, max_attempts=3)
    with pytest.raises(GatewayError) as excinfo:
        call(gateway)
    gateway.close()
    fake.stop()
    assert excinfo.value.failure is FailureType.CONTENT_FILTERED
    assert len(fake.requests) == 1


def test_connection_retried_then_raises(tmp_path):
    fake = FakeOpenAI([Reply(partial_body="{"), Reply(partial_body="{")]).start()
    gateway = gateway_for(fake.url, tmp_path, max_attempts=2)
    with pytest.raises(GatewayError) as excinfo:
        call(gateway)
    gateway.close()
    fake.stop()
    assert excinfo.value.failure is FailureType.CONNECTION
    assert len(fake.requests) == 2
    assert facts_line(tmp_path)["edu.outcome"] == "connection"


# ---------- 备选与限流策略(01 §4"触发备选"列 / 01 §3 ratelimit) ----------


def test_fallback_immediate_on_connection(tmp_path):
    # connection:第一次失败即切备选(01 §4:是)
    primary = FakeOpenAI([Reply(partial_body="{")]).start()
    backup = FakeOpenAI([completion("备选答案")]).start()
    gateway = gateway_for(primary.url, tmp_path, fallback_url=backup.url)
    response = call(gateway)
    gateway.close()
    primary.stop()
    backup.stop()
    assert response.text == "备选答案"
    assert len(primary.requests) == 1 and len(backup.requests) == 1
    payload = facts_line(tmp_path)
    assert payload["edu.outcome"] == "ok"
    assert payload["edu.fallback_from"] == "m" and payload["edu.fallback_to"] == "b"
    assert payload["gen_ai.request.model"] == "m" and payload["gen_ai.response.model"] == "fake-model"


def test_fallback_from_second_rate_limited(tmp_path):
    # rate_limited:第二次起才切备选 → 主选收到 2 次,备选 1 次,共 3 次尝试
    primary = FakeOpenAI([
        Reply(status=429, headers={"Retry-After": "0"}),
        Reply(status=429, headers={"Retry-After": "0"}),
    ]).start()
    backup = FakeOpenAI([completion("备选")]).start()
    gateway = gateway_for(primary.url, tmp_path, fallback_url=backup.url, max_attempts=3)
    response = call(gateway)
    gateway.close()
    primary.stop()
    backup.stop()
    assert response.text == "备选"
    assert len(primary.requests) == 2 and len(backup.requests) == 1
    payload = facts_line(tmp_path)
    assert payload["edu.attempt"] == 3 and payload["edu.fallback_to"] == "b"


def test_fallback_on_total_timeout(tmp_path):
    # timeout_total:不可重试但触发备选(01 §4:否/是)
    primary = FakeOpenAI([Reply(delay_s=1.2, json_body={})]).start()
    backup = FakeOpenAI([completion("备选")]).start()
    gateway = gateway_for(primary.url, tmp_path, fallback_url=backup.url,
                          total_timeout_s=0.3, max_attempts=3)
    response = call(gateway)
    gateway.close()
    primary.stop()
    backup.stop()
    assert response.text == "备选"
    assert facts_line(tmp_path)["edu.fallback_to"] == "b"


def test_no_fallback_for_schema_violation(tmp_path):
    # schema_violation:不触发备选(01 §4:否)
    primary = FakeOpenAI([completion("不会"), completion("还是不会")]).start()
    backup = FakeOpenAI([completion(json.dumps({"answer": "7"}))]).start()
    gateway = gateway_for(primary.url, tmp_path, fallback_url=backup.url)
    with pytest.raises(GatewayError) as excinfo:
        gateway.invoke(ModelRequest(role="tutor", messages=MSG, response_schema=SCHEMA))
    gateway.close()
    primary.stop()
    backup.stop()
    assert excinfo.value.failure is FailureType.SCHEMA_VIOLATION
    assert len(backup.requests) == 0


def test_ratelimit_records_queue_ms(tmp_path):
    # 并发 1:第二个调用排队,queue_ms 分离排队与上游延迟(01 §7)
    fake = FakeOpenAI([Reply(delay_s=0.8, json_body=completion("一").json_body), completion("二")]).start()
    gateway = gateway_for(fake.url, tmp_path, concurrency=1)
    results: list = []

    def invoke_once():
        results.append(gateway.invoke(ModelRequest(role="tutor", messages=MSG)))

    first = threading.Thread(target=invoke_once)
    first.start()
    time.sleep(0.2)  # 第一个调用已占住并发槽
    second = threading.Thread(target=invoke_once)
    second.start()
    first.join(10)
    second.join(10)
    gateway.close()
    fake.stop()
    assert [r.text for r in results] == ["一", "二"]
    queued = [p for p in facts(tmp_path) if p["edu.queue_ms"] > 0]
    assert len(queued) == 1 and queued[0]["edu.queue_ms"] >= 100


def test_stream_retries_before_first_event(tmp_path):
    # 流式在未吐出任何事件前可重试;重试后事件只出现一次
    fake = FakeOpenAI([Reply(status=500), sse("你", "好")]).start()
    gateway = gateway_for(fake.url, tmp_path, max_attempts=2)
    events = list(gateway.stream(ModelRequest(role="tutor", messages=MSG)))
    gateway.close()
    fake.stop()
    assert [e.text for e in events if e.kind == "token"] == ["你", "好"]
    assert len(fake.requests) == 2


def test_stream_no_retry_after_first_event(tmp_path):
    # 已吐出 token 后中断:不可重试(会重复输出),直接失败
    fake = FakeOpenAI([sse("你", done=False)]).start()
    gateway = gateway_for(fake.url, tmp_path, max_attempts=3)
    collected = []
    with pytest.raises(GatewayError) as excinfo:
        for event in gateway.stream(ModelRequest(role="tutor", messages=MSG)):
            collected.append(event)
    gateway.close()
    fake.stop()
    assert [e.text for e in collected] == ["你"]
    assert excinfo.value.failure is FailureType.CONNECTION
    assert len(fake.requests) == 1
    assert facts_line(tmp_path)["edu.outcome"] == "connection"
