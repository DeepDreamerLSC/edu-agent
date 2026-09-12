"""黄金路径端到端(04 §3.3):M0 版 = gateway 全链路一条用例,走假上游。

链序:request → registry → middleware(ratelimit/retry/fallback/timeout)→
provider(复用故障注入的 FakeOpenAI)→ redact → record,断言事实记录完整
(01 §7 全字段)。内核三函数版(开会话→首问→追问×2→总结,start→reply×2→finish)
M2 随内核重写升级;用例固定,改动需在 PR 描述单独说明(04 §3.3)。
"""

from __future__ import annotations

import json

from fake_openai import FakeOpenAI, completion, sse

from edu_agent.gateway import ModelRequest
from gwkit import FACT_FIELDS, gateway_for

FIRST_QUESTION = "你好,我想请教一道鸡兔同笼题。"
FOLLOW_UP = "那如果一共有 8 个头呢?"


def test_golden_path_gateway_full_chain(tmp_path):
    """一通教学式往返:invoke 首问 → stream 追问,同一 session,事实记录完整。"""
    fake = FakeOpenAI([
        completion("好,先数头和脚。"),
        sse("我们", "逐个", "设未知数。"),
    ]).start()
    # 与旧手工构造逐字段一致:tutor/json_strict/并发2/2s/5s/两次尝试/退避1-8ms
    gateway = gateway_for(fake.url, tmp_path, concurrency=2, first_token_timeout_s=2.0,
                          total_timeout_s=5.0, max_attempts=2)
    try:
        first = gateway.invoke(
            ModelRequest(role="tutor", messages=[{"role": "user", "content": FIRST_QUESTION}],
                         session_id="golden-1", trace_id="golden-trace")
        )
        events = list(gateway.stream(
            ModelRequest(role="tutor", messages=[{"role": "user", "content": FOLLOW_UP}],
                         session_id="golden-1", trace_id="golden-trace")
        ))
    finally:
        gateway.close()
        fake.stop()

    assert first.text == "好,先数头和脚。" and first.finish_reason == "stop"
    tokens = [event.text for event in events if event.kind == "token"]
    assert tokens == ["我们", "逐个", "设未知数。"]

    lines = list(tmp_path.glob("model_calls-*.jsonl"))[0].read_text(encoding="utf-8").splitlines()
    facts = [json.loads(line) for line in lines]
    assert len(facts) == 2  # 每次调用一条事实记录(01 §2.5)
    assert len({payload["edu.call_id"] for payload in facts}) == 2

    invoke_record, stream_record = facts  # 记录次序 = 调用次序
    for payload in facts:
        assert all(field in payload for field in FACT_FIELDS)
        assert payload["edu.outcome"] == "ok" and payload["edu.attempt"] == 1  # 首次成功
        assert payload["edu.session_id"] == "golden-1" and payload["edu.trace_id"] == "golden-trace"
        assert payload["edu.fallback_from"] is None and payload["edu.fallback_to"] is None
        assert payload["gen_ai.provider.name"] == "fake"
        assert payload["gen_ai.request.model"] == "m"
        assert payload["gen_ai.usage.input_tokens"] == 11 and payload["gen_ai.usage.output_tokens"] == 7
        assert payload["gen_ai.response.finish_reasons"] == ["stop"]
        assert payload["edu.error_detail"] is None
        # 学生内容不进记录:只有 role + 长度 + 哈希(01 §7/redact)
        for message in payload["edu.redacted"]:
            assert set(message) == {"role", "len", "sha256"}
        for secret in (FIRST_QUESTION, FOLLOW_UP, "鸡兔同笼"):
            assert secret not in lines[0] and secret not in lines[1]

    assert invoke_record["gen_ai.response.model"] == "fake-model"  # 非流式回显 model
    assert invoke_record["gen_ai.server.time_to_first_token"] is None  # TTFT 仅流式(01 §5)
    assert stream_record["gen_ai.server.time_to_first_token"] is not None
    assert stream_record["edu.total_ms"] >= stream_record["gen_ai.server.time_to_first_token"]
