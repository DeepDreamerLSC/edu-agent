"""invoke 合同(01 §4、§7、§8):失败类型映射、事实记录全字段、脱敏、路线 1 校验。

共享件(SECRET/SCHEMA/FACT_FIELDS/facts_line/假上游生命周期)在 tests/fixtures/gwkit.py。
"""

from __future__ import annotations

import json

import pytest
from fake_openai import Reply, completion

from edu_agent.gateway import FailureType, GatewayError, ModelRequest, RegistryError

from gwkit import (
    FACT_FIELDS,
    SCHEMA,
    SECRET,
    facts_line,
    fake_gateway,
    registry_for,
)


def test_invoke_ok_records_full_fact(tmp_path):
    with fake_gateway(tmp_path, [completion("答案")]) as (fake, gateway):
        response = gateway.invoke(ModelRequest(
            role="tutor",
            messages=[{"role": "user", "content": SECRET}],
            session_id="sess-1",
            trace_id="trace-9",
        ))
        assert response.text == "答案"
        assert response.finish_reason == "stop"
        assert response.input_tokens == 11 and response.output_tokens == 7
        assert fake.requests[0]["model"] == "fake-model"

        payload = facts_line(tmp_path)
        # 01 §7 字段齐全、不加不减
        assert set(payload) == set(FACT_FIELDS)
        assert payload["edu.outcome"] == "ok"
        assert payload["edu.role"] == "tutor"
        assert payload["edu.attempt"] == 1
        assert payload["edu.session_id"] == "sess-1"
        assert payload["edu.trace_id"] == "trace-9"
        # 无争用 ≠ 严格 0:信号量 acquire 在负载机器上有线程调度延迟(实测 2-3ms)。
        # 放宽为"无排队量级"仍抓得住真排队(真排队是百 ms 起),同时不再随机打红 PR CI。
        assert 0 <= payload["edu.queue_ms"] < 50
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


@pytest.mark.parametrize("reply,expected,detail,kwargs", [
    (Reply(status=429, headers={"Retry-After": "2"}), FailureType.RATE_LIMITED,
     "HTTP 429", {"max_attempts": 1}),
    (Reply(status=500), FailureType.UPSTREAM_5XX, "HTTP 500", {"max_attempts": 1}),
    (Reply(status=503), FailureType.UPSTREAM_5XX, "HTTP 503", {"max_attempts": 1}),
    (Reply(status=404), FailureType.UPSTREAM_4XX, "HTTP 404", {"max_attempts": 1}),
    (Reply(status=400), FailureType.UPSTREAM_4XX, "HTTP 400", {"max_attempts": 1}),
    (Reply(status=200, raw_body="<html>not json</html>"), FailureType.UPSTREAM_5XX,
     None, {"max_attempts": 1}),
    # 截断/内容过滤:不可重试(即使 max_attempts 允许 3 次,attempt 仍为 1)
    (completion("半截", finish_reason="length"), FailureType.TRUNCATED, None, {}),
    (completion("被过滤", finish_reason="content_filter"), FailureType.CONTENT_FILTERED, None, {}),
    (Reply(delay_s=1.2, json_body={}), FailureType.TIMEOUT_TOTAL, None,
     {"total_timeout_s": 0.3, "max_attempts": 1}),
    # 响应体发一半即断:任何环境都是确定性连接中断(不接受响应的代理/直连行为一致)
    (Reply(partial_body='{"choices": [{'), FailureType.CONNECTION, None, {"max_attempts": 1}),
], ids=["rate_limited", "upstream_500", "upstream_503", "upstream_404", "upstream_400",
        "bad_json", "truncated", "content_filtered", "timeout_total", "connection"])
def test_invoke_failure_types_map_with_record(tmp_path, reply, expected, detail, kwargs):
    """失败类型映射 + 事实记录(重试/备选语义见故障注入套件;这里只测类型与台账)。"""
    with fake_gateway(tmp_path, [reply], **kwargs) as (fake, gateway):
        with pytest.raises(GatewayError) as excinfo:
            gateway.invoke(ModelRequest(role="tutor",
                                        messages=[{"role": "user", "content": "hi"}]))
        assert excinfo.value.failure is expected
        if detail:
            assert detail in excinfo.value.detail
        payload = facts_line(tmp_path)
        assert payload["edu.outcome"] == expected.value
        assert payload["edu.attempt"] == 1
        assert "小明" not in json.dumps(payload, ensure_ascii=False)


def test_invoke_schema_route1_violation(tmp_path):
    # 两次都不合规:修复重试恰一次后仍失败
    with fake_gateway(tmp_path, [completion("我答不上来"), completion("还是答不上来")]) as (fake, gateway):
        with pytest.raises(GatewayError) as excinfo:
            gateway.invoke(ModelRequest(
                role="tutor",
                messages=[{"role": "user", "content": SECRET}],
                response_schema=SCHEMA,
            ))
        error = excinfo.value
        assert error.failure is FailureType.SCHEMA_VIOLATION
        assert error.output == "还是答不上来"
        assert len(fake.requests) == 2  # 修复重试恰一次(issue #8)
        # 路线 1:schema 进了 prompt(issue #8)
        sent = fake.requests[0]["messages"]
        assert "JSON Schema" in sent[-1]["content"]
        assert json.dumps(SCHEMA, ensure_ascii=False) in sent[-1]["content"]
        # 失败记录不含违规原文与学生内容
        line = json.dumps(facts_line(tmp_path), ensure_ascii=False)
        assert "我答不上来" not in line and "小明" not in line


def test_invoke_schema_ok_passes(tmp_path):
    with fake_gateway(tmp_path, [completion(json.dumps({"answer": "3+4=7"}, ensure_ascii=False))]) as (fake, gateway):
        response = gateway.invoke(ModelRequest(
            role="tutor", messages=[{"role": "user", "content": "3+4?"}], response_schema=SCHEMA,
        ))
        assert json.loads(response.text) == {"answer": "3+4=7"}
        assert facts_line(tmp_path)["edu.outcome"] == "ok"


def test_invoke_schema_tolerates_code_fence(tmp_path):
    # Markdown 围栏是包装噪声,不是结构违规(实测 DeepSeek 独立评分恒带围栏);
    # 剥壳后内容合法即通过,非 JSON 仍拒(schema_violation 语义不变)。
    # text 口径(#54 PM 规格,校验与消费同源):schema 调用返回剥壳后的已验证
    # 内容;无 schema 的普通调用仍为模型原文(见下)。
    fenced = "```json\n" + json.dumps({"answer": "3+4=7"}, ensure_ascii=False) + "\n```"
    with fake_gateway(tmp_path, [completion(fenced), completion("你好,世界")]) as (fake, gateway):
        response = gateway.invoke(ModelRequest(
            role="tutor", messages=[{"role": "user", "content": "3+4?"}], response_schema=SCHEMA,
        ))
        assert json.loads(response.text) == {"answer": "3+4=7"}
        assert "```" not in response.text  # 剥壳内容即消费内容,围栏不进 text
        assert facts_line(tmp_path)["edu.outcome"] == "ok"

        plain = gateway.invoke(ModelRequest(  # 无 schema:普通调用原文直通
            role="tutor", messages=[{"role": "user", "content": "讲讲"}],
        ))
        assert plain.text == "你好,世界"

    with fake_gateway(tmp_path, [
        completion("```json\n不是 JSON\n```"),
        completion("```json\n不是 JSON\n```"),  # 修复重试恰一次(#32);第二次仍违规才落 schema_violation
    ], max_attempts=1) as (rejected, gateway2):
        with pytest.raises(GatewayError) as excinfo:
            gateway2.invoke(ModelRequest(
                role="tutor", messages=[{"role": "user", "content": "3+4?"}], response_schema=SCHEMA,
            ))
        assert excinfo.value.failure is FailureType.SCHEMA_VIOLATION


def test_schema_request_rejected_for_non_strict_role(tmp_path):
    with fake_gateway(tmp_path, [], json_strict=False) as (fake, gateway):
        with pytest.raises(RegistryError, match="json_strict"):
            gateway.invoke(ModelRequest(
                role="tutor", messages=[{"role": "user", "content": "hi"}], response_schema=SCHEMA,
            ))
        assert fake.requests == []  # 不发给不支持的服务端(01 §8)


# ---------- 多模态(images 渲染为 OpenAI image_url 内容块) ----------

def test_images_render_as_content_parts_on_first_user_message(tmp_path):
    """vision 多模态:第一条 user 消息(任务文本)转 [text, image_url] 内容块,图片不进文本。"""
    with fake_gateway(tmp_path, [completion("答案")]) as (fake, gateway):
        gateway.invoke(ModelRequest(
            role="tutor",
            messages=[{"role": "user", "content": "看这张题图"},
                      {"role": "user", "content": "判断是否单题"}],
            images=["data:image/png;base64,QUJD"],
        ))
        messages = fake.requests[0]["messages"]
        parts = messages[0]["content"]
        assert [p["type"] for p in parts] == ["text", "image_url"]
        assert parts[0]["text"] == "看这张题图"
        assert parts[1]["image_url"]["url"] == "data:image/png;base64,QUJD"
        assert messages[1]["content"] == "判断是否单题"  # 其余消息不受影响


def test_images_with_schema_keeps_instruction_plain_text(tmp_path):
    """schema 指令以纯文本 user 消息追加在内容块之后(混合形态,服务端均接受)。"""
    with fake_gateway(tmp_path, [completion(json.dumps({"answer": "ok"}))]) as (fake2, gateway):
        gateway.invoke(ModelRequest(
            role="tutor",
            messages=[{"role": "user", "content": "看图答题"}],
            response_schema=SCHEMA, images=["data:image/png;base64,QUJD"],
        ))
        messages = fake2.requests[0]["messages"]
        assert isinstance(messages[0]["content"], list)  # 原消息转内容块
        assert isinstance(messages[-1]["content"], str)  # schema 指令保持纯文本
        assert "JSON Schema" in messages[-1]["content"]


def test_no_images_leaves_messages_unchanged(tmp_path):
    """images 缺省:消息原样(纯文本路径零变化)。"""
    with fake_gateway(tmp_path, [completion("答案")]) as (fake, gateway):
        gateway.invoke(ModelRequest(
            role="tutor", messages=[{"role": "user", "content": "纯文本"}]))
        assert fake.requests[0]["messages"][0]["content"] == "纯文本"


def test_api_key_missing_fails_fast(tmp_path):
    from edu_agent.gateway import Gateway, ProviderConfig
    registry = registry_for("http://127.0.0.1:9")
    registry.providers["fake"] = ProviderConfig("fake", "http://127.0.0.1:9", "NO_SUCH_KEY_ENV", True)
    gateway = Gateway(registry, tmp_path)
    with pytest.raises(RegistryError, match="NO_SUCH_KEY_ENV"):
        gateway.invoke(ModelRequest(role="tutor", messages=[{"role": "user", "content": "hi"}]))
    gateway.close()
