"""内核三函数契约与状态机转移(00 §5.1;03 §4 逐态)。

真 Gateway + FakeOpenAI 假上游(02 §6:零真实模型;tutor 走 json_strict=true
的 grammar 路径,vision 独立角色)。#54 口径:gateway.text 即已验证 JSON,
内核直接解析——假上游直接回合法 JSON 模拟 grammar 强制。
"""

from __future__ import annotations

import json

import pytest
from fake_openai import FakeOpenAI, Reply, completion

from edu_agent.agents.small_lecturer import (
    SessionVersionConflict,
    TerminalStateError,
    finish,
    reply,
    start,
)
from edu_agent.gateway import (
    Gateway,
    GatewayError,
    ModelConfig,
    ModelRegistry,
    ProviderConfig,
    RoleConfig,
)

QUESTION_TEXT = {"text": "解方程 3x+7=25,并说明每一步为什么这样做。"}
LEARNER = {"grade": "六年级"}


def tutor_json(reply_text: str, ready: bool = False,
               cited_numbers: list[float] | None = None) -> str:
    return json.dumps({"reply": reply_text, "ready_to_confirm": ready,
                       "cited_numbers": cited_numbers or []}, ensure_ascii=False)


def vision_json(acceptable: bool, reason: str = "", transcription: str = "") -> str:
    """M3 PR2:vision 响应三字段(schema required 三键),假上游照 schema 出牌。"""
    return json.dumps({"acceptable": acceptable, "reason": reason,
                       "transcription": transcription}, ensure_ascii=False)


def kernel_gateway(facts_dir, tutor_url: str, vision_url: str | None = None) -> Gateway:
    """tutor(json_strict=true,grammar 路径)+ 可选 vision 角色指向假上游。"""
    providers = {"fake_tutor": ProviderConfig("fake_tutor", tutor_url, None, True)}
    models = {"m": ModelConfig("m", "fake_tutor", "fake-model")}
    roles = {"tutor": RoleConfig(
        name="tutor", primary="m", fallback=None, json_strict=True,
        concurrency=2, first_token_timeout_s=2.0, total_timeout_s=5.0,
        max_attempts=2, backoff_base_ms=1, backoff_cap_ms=8,
    )}
    if vision_url is not None:
        providers["fake_vision"] = ProviderConfig("fake_vision", vision_url, None, True)
        models["v"] = ModelConfig("v", "fake_vision", "fake-vision")
        roles["vision"] = RoleConfig(
            name="vision", primary="v", fallback=None, json_strict=True,
            concurrency=2, first_token_timeout_s=2.0, total_timeout_s=5.0,
            max_attempts=2, backoff_base_ms=1, backoff_cap_ms=8,
        )
    return Gateway(ModelRegistry(providers=providers, models=models, roles=roles), facts_dir)


# ---------- start:Preparing → FirstQuestionReady / Failed ----------

def test_start_text_question_skips_vision(tmp_path):
    """纯文本题跳过 vision(00 §5.1);首问就绪,Turn 携带 session 供后续调用。"""
    fake = FakeOpenAI([completion(tutor_json("题目要我们求什么?先说说已知条件。"))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.state == "first_question_ready" and turn.text == "题目要我们求什么?先说说已知条件。"
    assert turn.session is not None and turn.session.state == "first_question_ready"
    assert len(fake.requests) == 1  # 只有 tutor 一次,vision 未被调


def test_start_image_untrusted_fails_closed_without_tutor(tmp_path):
    """Preparing → Failed:题图不可信,fail closed 不调 tutor(03 §4)。"""
    vision = FakeOpenAI([completion(vision_json(False, "疑似多题混入"))]).start()
    tutor = FakeOpenAI([completion(tutor_json("不该被调用"))]).start()
    gateway = kernel_gateway(tmp_path, tutor.url, vision_url=vision.url)
    turn = start({"image": "file:photo-123"}, LEARNER, gateway=gateway)
    gateway.close()
    vision.stop()
    tutor.stop()
    assert turn.state == "failed" and "题图" in turn.text
    assert len(tutor.requests) == 0 and len(vision.requests) == 1
    with pytest.raises(TerminalStateError):  # Failed 终态:不可再推进(校验先于模型调用)
        reply(turn.session, "继续")


def test_start_image_trusted_proceeds_to_first_question(tmp_path):
    vision = FakeOpenAI([completion(vision_json(True, "单题清晰"))]).start()
    tutor = FakeOpenAI([completion(tutor_json("我们先确认题意:这道题要我们求什么?"))]).start()
    gateway = kernel_gateway(tmp_path, tutor.url, vision_url=vision.url)
    turn = start({"image": "file:photo-123"}, LEARNER, gateway=gateway)
    gateway.close()
    vision.stop()
    tutor.stop()
    assert turn.state == "first_question_ready"
    assert len(vision.requests) == 1 and len(tutor.requests) == 1


def test_start_vision_infrastructure_error_bubbles(tmp_path):
    """GatewayError 按失败类型冒泡,内核不吞(00 §5.1)。"""
    vision = FakeOpenAI([Reply(status=500), Reply(status=500)]).start()
    tutor = FakeOpenAI([]).start()
    gateway = kernel_gateway(tmp_path, tutor.url, vision_url=vision.url)
    with pytest.raises(GatewayError) as excinfo:
        start({"image": "file:photo-x"}, LEARNER, gateway=gateway)
    gateway.close()
    vision.stop()
    tutor.stop()
    assert excinfo.value.failure.value == "upstream_5xx"


# ---------- reply:Dialogue 自旋 / Conflict / ReadyToConfirm ----------

def test_reply_appends_history_and_increments_version(tmp_path):
    fake = FakeOpenAI([
        completion(tutor_json("题目要我们求什么?")),
        completion(tutor_json("很好,那两个量之间是什么关系?")),
    ]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    turn = reply(first.session, "我先两边同时减去7。", gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.state == "dialogue" and turn.session_version == 2
    assert first.session.history == [
        {"role": "user", "content": "我先两边同时减去7。"},
        {"role": "assistant", "content": "很好,那两个量之间是什么关系?"},
    ]


def test_reply_stale_version_conflicts_without_advancing(tmp_path):
    """Dialogue ⇄ Conflict(03 §4):旧 expected_session_version 不推进、不覆盖。"""
    fake = FakeOpenAI([completion(tutor_json("第一问?")), completion(tutor_json("第二问?"))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    reply(first.session, "回答一", gateway=gateway)  # version 1 → 2
    with pytest.raises(SessionVersionConflict):
        reply(first.session, "旧页面重发", gateway=gateway, expected_session_version=1)
    gateway.close()
    fake.stop()
    assert first.session.session_version == 2  # 冲突不推进
    assert len(fake.requests) == 2              # 冲突不发模型调用


def test_reply_ready_signal_enters_ready_to_confirm(tmp_path):
    fake = FakeOpenAI([
        completion(tutor_json("第一问?")),
        completion(tutor_json("你已经说清了每一步的依据。", ready=True)),
    ]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    turn = reply(first.session, "我算出 x=6,并回代检验了。", gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.state == "ready_to_confirm" and turn.ready_to_confirm is True


# ---------- finish:Completed 不可变 / needs_review ----------

def test_finish_before_ready_returns_needs_review_without_model(tmp_path):
    """证据不足(00 §5.1):不调模型、确定性文案、不写 summary。"""
    fake = FakeOpenAI([completion(tutor_json("第一问?"))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    summary = finish(first.session, gateway=gateway)
    gateway.close()
    fake.stop()
    assert summary.status == "needs_review" and "继续" in summary.text
    assert len(fake.requests) == 1            # 只有首问那一次,finish 未调模型
    assert first.session.summary is None and first.session.state == "first_question_ready"


def test_finish_ready_writes_immutable_summary(tmp_path):
    fake = FakeOpenAI([
        completion(tutor_json("第一问?")),
        completion(tutor_json("掌握了", ready=True)),
        completion(json.dumps({"summary": "你用等式性质解出 x=6,并回代检验。"}, ensure_ascii=False)),
        completion(json.dumps({"summary": "不该再次生成"}, ensure_ascii=False)),
    ]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    reply(first.session, "x=6,检验通过。", gateway=gateway)
    summary = finish(first.session, gateway=gateway)
    again = finish(first.session, gateway=gateway)  # completed 终态:幂等返回同一 Summary
    gateway.close()
    fake.stop()
    assert summary.status == "completed" and "x=6" in summary.text
    assert again == summary
    assert len(fake.requests) == 3               # 第二次 finish 不再调模型(不可变)
    with pytest.raises(TerminalStateError):      # Completed 终态:不可再 reply
        reply(first.session, "再问一句", gateway=gateway)


# ---------- 三函数契约(#54 后的 text 即已验证内容) ----------

def test_kernel_consumes_validated_text_directly(tmp_path):
    """#54 口径:gateway.text 即已验证 JSON(grammar/路线 1 归一),内核直接 json.loads
    不二次剥壳——带围栏输出经 gateway 归一后内核同样直解析。"""
    fenced = "```json\n" + tutor_json("我们先确认题意。") + "\n```"
    fake = FakeOpenAI([completion(fenced), completion(tutor_json("第二问?", ready=True))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    turn = reply(first.session, "知道了。", gateway=gateway)
    gateway.close()
    fake.stop()
    assert first.text == "我们先确认题意。" and turn.state == "ready_to_confirm"
