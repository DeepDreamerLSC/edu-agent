"""PR2:提示词装配与护栏对齐(00 §8.4 阶段 1 prompt 项 + 阶段 2 第一验收)。

断言即规格:tests/teaching 的既有护栏断言零改动;本文件验证内核侧的装配与
护栏接线——system 消息含 SKILL/风格/攻守指令,tutor 输出经三护栏替换。
零真实模型(假上游)。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fake_openai import FakeOpenAI, completion

from edu_agent.agents.small_lecturer import (
    SAFE_FALLBACK_TEXT,
    TUTOR_TURN_SCHEMA,
    finish,
    reply,
    start,
    style_directives,
    summary_system_prompt,
    system_prompt,
)

from test_kernel_state_machine import LEARNER, QUESTION_TEXT, kernel_gateway, open_json, tutor_json

REPO_ROOT = Path(__file__).resolve().parents[2]


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
    fake = FakeOpenAI([completion(open_json("我们先确认题意:要求什么?"))]).start()
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
    leak = open_json("答案是 x=6。你能说说理由吗?")
    fake = FakeOpenAI([completion(leak)]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.text == SAFE_FALLBACK_TEXT
    assert "x=6" not in turn.text


def test_kernel_replaces_abusive_tone(tmp_path):
    rude = tutor_json("这么简单的题你都不会?")
    fake = FakeOpenAI([completion(open_json("第一问?")), completion(rude)]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    # 「我不会」现路由确定性揭示(#157 评审卡壳修复)→ 语气护栏用中性话术走模型路径
    turn = reply(first.session, "这题好难。", gateway=gateway)
    gateway.close()
    fake.stop()
    # 任务包2步2兜底句情境化:语气护栏命中,原文不达学生面,换接学生原话的引导句(非万能句)
    assert turn.text == "先回到你刚说的「这题好难。」——你能从题目里再确认一个已知条件吗?"


def test_kernel_replaces_markdown_output_with_downgrade(tmp_path):
    dirty = open_json("## 第一步\n先算 **3×4**。")
    fake = FakeOpenAI([completion(dirty)]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    assert "重新" in turn.text and "##" not in turn.text  # SKILL 规则 11/12:格式降级提示


def test_clean_output_passes_through(tmp_path):
    clean = open_json("题目要我们求什么?先说说你读到了哪些条件。")
    fake = FakeOpenAI([completion(clean)]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.text == "题目要我们求什么?先说说你读到了哪些条件。"


def test_guarded_reply_context_matches_student_visible_text(tmp_path):
    """护栏命中 → 修复重生成优先:重调 tutor 拿到干净回复,学生所见/记录是它而非泄露原文。"""
    leak = tutor_json("答案是 x=6,就是这样。")
    regen_clean = tutor_json("你刚才回到了条件本身,很好。")
    follow_clean = tutor_json("我们接着看,你能说出题目给的一个条件吗?")
    fake = FakeOpenAI([completion(open_json("第一问?")), completion(leak),
                       completion(regen_clean), completion(follow_clean)]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    # 「不知道」现路由确定性揭示(#157 评审卡壳修复)→ 护栏链用中性话术走模型路径
    turn = reply(first.session, "我再看看。", gateway=gateway)
    assert turn.text == "你刚才回到了条件本身,很好。"  # 泄露 → 重生成成功 → 用重生成文本
    assert "x=6" not in turn.text
    follow = reply(first.session, "题目说 3x 加 7 等于 25。", gateway=gateway)
    gateway.close()
    fake.stop()
    assert follow.text == json.loads(follow_clean)["reply"]
    assistant_turns = [m["content"] for m in first.session.history if m["role"] == "assistant"]
    # 泄露回复不达学生面:history 记的是重生成后的干净文本,下一轮模型上下文 = 学生实际所见
    assert assistant_turns == ["你刚才回到了条件本身,很好。", json.loads(follow_clean)["reply"]]


def test_repeat_self_refine_replaces_repeated_question(tmp_path):
    """复读自批评(self-refine):学生卡住时 tutor 复读同一问句 → 打回重生成一次换一句推进。"""
    open_q = open_json("兔子有几只呢?")          # start 首问(open schema)
    repeat_q = tutor_json("兔子有几只呢?")        # reply 复读同一问句(tutor schema)
    refined = tutor_json("我们换一步,你先说说题目给了哪些条件?")  # 重生成(tutor schema)
    fake = FakeOpenAI([completion(open_q), completion(repeat_q), completion(refined)]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start({"text": "鸡和兔一共有8只,共有26只脚,鸡和兔各有多少只?说明思路。",
                   "answer": "鸡3只,兔5只"}, {"grade": "六年级"}, gateway=gateway)
    turn = reply(first.session, "嗯,我看看。", gateway=gateway)
    gateway.close()
    fake.stop()
    # 首问「兔子有几只呢?」被复读一次 → self-refine 打回重生成 → 换成非复读的推进句
    assert turn.text == "我们换一步,你先说说题目给了哪些条件?"
    assert "兔子有几只呢" not in turn.text
    assert len(fake.requests) == 3  # start + 首轮 reply + 打回重生成 各一次模型调用


# ---------- #146 M1:reason 规划字段(答案泄露防御,05 §5) ----------

def test_tutor_turn_schema_declares_reason_before_reply():
    """#146 M1:schema 经 json.dumps 进 prompt,声明序即生成序——reason 必须在 reply
    之前(先承诺策略、再回答);不进 required 模型会跳过,防御即失效。"""
    props = list(TUTOR_TURN_SCHEMA["properties"])
    assert props.index("reason") < props.index("reply"), "reason 必须声明在 reply 之前"
    assert "reason" in TUTOR_TURN_SCHEMA["required"]
    assert TUTOR_TURN_SCHEMA["properties"]["reason"] == {"type": "string"}


def test_system_prompt_includes_reason_planning_instruction():
    """#146 M1:输出契约含 reason 规划指令——先写引导计划再写 reply,学生只见 reply。"""
    prompt = system_prompt("六年级")
    assert "reason" in prompt
    assert "含 reason 字段时" in prompt          # schema 作用域限定(start 调用无该字段,指令不生效)
    assert "用提问让他自己算" in prompt
    assert "学生只会看到 reply" in prompt


def test_reason_field_never_read_by_app_code():
    """#146 M1 红线:reason 是规划装置,不是验证装置——应用代码(edu_agent/)任何位置
    不得索引读取 reason(["reason"] / .get("reason"));cited_numbers 前车之鉴:
    自报字段一进判定逻辑就变成谎报源。vision 的 reason(转写判定)为独立语义,
    同样无索引读取。"""
    pattern = re.compile(r"""\[\s*["']reason["']\s*\]|\.get\(\s*["']reason["']""")
    hits = []
    for path in sorted((REPO_ROOT / "edu_agent").rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{path.relative_to(REPO_ROOT)}:{lineno}")
    assert hits == [], f"reason 被判定/守卫代码读取(违规): {hits}"
