"""PR2:提示词装配与护栏对齐(00 §8.4 阶段 1 prompt 项 + 阶段 2 第一验收)。

断言即规格:tests/teaching 的既有护栏断言零改动;本文件验证内核侧的装配与
护栏接线——system 消息含 SKILL/风格/攻守指令,tutor 输出经三护栏替换。
零真实模型(假上游)。
"""

from __future__ import annotations

import json

from fake_openai import FakeOpenAI, completion

from edu_agent.agents.small_lecturer import (
    SAFE_FALLBACK_TEXT,
    finish,
    reply,
    start,
    style_directives,
    summary_system_prompt,
    system_prompt,
)

from test_kernel_state_machine import LEARNER, QUESTION_TEXT, kernel_gateway, tutor_json


# ---------- 装配:SKILL + 风格档案 + 攻守图 ----------

def test_system_prompt_carries_skill_rules_style_and_tactics():
    prompt = system_prompt("六年级")
    assert "苏格拉底式追问" in prompt           # SKILL.md 剪裁版规则(#45 资产原样)
    assert "不向学生输出 Markdown" in prompt      # SKILL 规则 12
    assert "六年级" in prompt and "术语" in prompt  # 风格档案 primary_upper 展开
    assert "最小认知步骤" in prompt                # 攻守图·攻(节奏)
    assert "绝不判断答案" in prompt                # 攻守图·守(首问不泄露)


def test_style_directives_follow_grade_band():
    assert "只用具体事物" in style_directives("二年级")   # primary_lower → concrete
    assert "抽象推理" in style_directives("初三")         # junior_middle → abstract_reasoning
    assert "精炼" in style_directives("五年级")           # primary_upper → concise
    assert "表达完整" in style_directives("")             # 未知年级 → neutral(standard)兜底


def test_summary_prompt_uses_summary_instruction():
    assert "不补写他未说过的标准解法" in summary_system_prompt("六年级")
    assert "教学策略(必须遵守)" not in summary_system_prompt("六年级")  # 总结路径不带对话攻守策略


# ---------- 内核接线:system 消息真实下发 ----------

def test_kernel_sends_assembled_system_message(tmp_path):
    fake = FakeOpenAI([completion(tutor_json("我们先确认题意:要求什么?"))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    start(QUESTION_TEXT, LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    system_message = fake.requests[0]["messages"][0]
    assert system_message["role"] == "system"
    assert "苏格拉底式追问" in system_message["content"]
    assert "六年级" in system_message["content"]


# ---------- 第一验收:护栏不过的输出不进入 Turn.text ----------

def test_kernel_replaces_leaking_tutor_output(tmp_path):
    """泄露终答 → 确定性安全问句(M2 阶段 2;断言即规格,改内核不改测试)。"""
    leak = tutor_json("答案是 x=6。你能说说理由吗?")
    fake = FakeOpenAI([completion(leak)]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.text == SAFE_FALLBACK_TEXT
    assert "x=6" not in turn.text


def test_kernel_replaces_abusive_tone(tmp_path):
    rude = tutor_json("这么简单的题你都不会?")
    fake = FakeOpenAI([completion(tutor_json("第一问?")), completion(rude)]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    turn = reply(first.session, "我不会。", gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.text == SAFE_FALLBACK_TEXT  # 语气护栏命中,原文不达学生可见面


def test_kernel_replaces_markdown_output_with_downgrade(tmp_path):
    dirty = tutor_json("## 第一步\n先算 **3×4**。")
    fake = FakeOpenAI([completion(dirty)]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    assert "重新" in turn.text and "##" not in turn.text  # SKILL 规则 11/12:格式降级提示


def test_clean_output_passes_through(tmp_path):
    clean = tutor_json("题目要我们求什么?先说说你读到了哪些条件。")
    fake = FakeOpenAI([completion(clean)]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.text == "题目要我们求什么?先说说你读到了哪些条件。"


def test_guarded_reply_context_matches_student_visible_text(tmp_path):
    """护栏替换后,history 记录安全文本(下一轮模型上下文 = 学生实际所见)。"""
    leak = tutor_json("答案是 x=6,就是这样。")
    fake = FakeOpenAI([completion(tutor_json("第一问?")), completion(leak),
                       completion(tutor_json("你刚才回到了条件本身,很好。"))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    turn = reply(first.session, "不知道。", gateway=gateway)
    assert turn.text == SAFE_FALLBACK_TEXT
    follow = reply(first.session, "题目说 3x 加 7 等于 25。", gateway=gateway)
    gateway.close()
    fake.stop()
    assert follow.text == "你刚才回到了条件本身,很好。"
    assistant_turns = [m["content"] for m in first.session.history if m["role"] == "assistant"]
    assert assistant_turns == [SAFE_FALLBACK_TEXT, "你刚才回到了条件本身,很好。"]
