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
    FIRST_QUESTION_COLLECT,
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


# ---------- #165 WS4 第 5 条:incorrect 弧线第②步(追问思路)轮 ----------

DIAGNOSE_LEARNER = {**LEARNER, "answer_status": "incorrect"}


def _tutor_prompt_blobs(fake) -> list[str]:
    """已记录请求的**全文**(网关在末尾追加 schema 提醒,故不取 messages[-1])。"""
    return ["\n".join(str(m.get("content", "")) for m in (body.get("messages") or []))
            for body in fake.requests if body.get("messages")]


def test_arc_diagnose_hint_only_on_first_reply(tmp_path):
    """只覆盖弧线第②步(首问后的第一次回应);之后轮次不再限制措辞
    (扩到②+③ 的版本经 F 口径实测更差,已回退——见 prompting.py 注释)。"""
    fake = FakeOpenAI([
        completion(open_json("你算出的结果是多少?")),
        completion(tutor_json("你是怎么想到把三个数加在一起的?", ready=False)),
        completion(tutor_json("把这两个条件放在一起看,你觉得哪里会不一样?", ready=False)),
        completion(tutor_json("我们来看看:如果先减38会怎样?", ready=False)),
    ]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start(QUESTION_TEXT, dict(DIAGNOSE_LEARNER), gateway=gateway)
    reply(first.session, "我把三个数直接加在一起。", gateway=gateway)
    reply(first.session, "因为题目说又买来又借出。", gateway=gateway)
    reply(first.session, "那我先算加法试试。", gateway=gateway)
    gateway.close()
    fake.stop()
    prompts = _tutor_prompt_blobs(fake)
    assert "弧线第②步" in prompts[1]                      # 首问后的第一次回应
    assert "弧线第②步" not in prompts[2]                   # 之后不再限制措辞
    assert "弧线第②步" not in prompts[3]


def test_arc_diagnose_hint_absent_without_incorrect_status(tmp_path):
    """correct/unknown(缺省)弧线不受影响:零注入(判据与行为面零改动)。"""
    fake = FakeOpenAI([
        completion(open_json("我们先确认题意:要求什么?")),
        completion(tutor_json("你说说看下一步?", ready=False)),
    ]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start(QUESTION_TEXT, dict(LEARNER), gateway=gateway)
    reply(first.session, "我想先移项。", gateway=gateway)
    gateway.close()
    fake.stop()
    assert all("弧线第" not in p for p in _tutor_prompt_blobs(fake))


# ---------- 第一验收:护栏不过的输出不进入 Turn.text ----------

def test_kernel_replaces_leaking_tutor_output(tmp_path):
    """泄露终答 → 不达学生面:护栏换下原文,首问可见文本恒为固定模板。"""
    leak = open_json("答案是 x=6。你能说说理由吗?")
    fake = FakeOpenAI([completion(leak)]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    assert "x=6" not in turn.text
    assert turn.text == FIRST_QUESTION_COLLECT   # 首问恒为固定模板(prompting.first_question_text)
    events = turn.session.guard_events
    assert [e["guard"] for e in events if e.get("guard")] == ["answer_leak"]
    assert "x=6" in events[0]["original"]                     # 被拦原文在案


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
    """格式护栏命中:Markdown 原文不达学生面,换下的是降级引导句(埋点记 rule_ids)。"""
    dirty = open_json("## 第一步\n先看 **3 和 7**。")
    fake = FakeOpenAI([completion(dirty)]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.text == FIRST_QUESTION_COLLECT and "##" not in turn.text  # 首问恒为固定模板
    assert [e["guard"] for e in turn.session.guard_events if e.get("guard")] == ["format"]


def test_clean_output_passes_through(tmp_path):
    """干净输出过三护栏:零埋点;首问可见文本仍是固定模板。"""
    clean = open_json("题目要我们求什么?先说说你读到了哪些条件。")
    fake = FakeOpenAI([completion(clean)]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.session.guard_events == []           # 护栏零埋点(模板覆盖不是埋点)
    assert turn.text == FIRST_QUESTION_COLLECT


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
    repeat_q = tutor_json(FIRST_QUESTION_COLLECT)      # reply 复读首问模板原文(prev)
    refined = tutor_json("我们换一步,你先说说题目给了哪些条件?")  # 重生成(tutor schema)
    fake = FakeOpenAI([completion(open_q), completion(repeat_q), completion(refined)]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start({"text": "鸡和兔一共有8只,共有26只脚,鸡和兔各有多少只?说明思路。",
                   "answer": "鸡3只,兔5只"}, {"grade": "六年级"}, gateway=gateway)
    turn = reply(first.session, "嗯,我看看。", gateway=gateway)
    gateway.close()
    fake.stop()
    # 首问固定模板被复读一次 → self-refine 打回重生成 → 换成非复读的推进句
    assert turn.text == "我们换一步,你先说说题目给了哪些条件?"
    assert turn.text != FIRST_QUESTION_COLLECT
    assert len(fake.requests) == 3  # start + 首轮 reply + 打回重生成 各一次模型调用


# ---------- #146 M1:reason 规划字段(答案泄露防御,05 §5) ----------

def test_tutor_turn_schema_declares_reason_before_reply():
    """#146 M1:schema 经 json.dumps 进 prompt,声明序即生成序——reason 必须在 reply
    之前(先承诺策略、再回答);不进 required 模型会跳过,防御即失效。"""
    props = list(TUTOR_TURN_SCHEMA["properties"])
    assert props.index("reason") < props.index("reply"), "reason 必须声明在 reply 之前"
    assert "reason" in TUTOR_TURN_SCHEMA["required"]
    assert TUTOR_TURN_SCHEMA["properties"]["reason"] == {"type": "string"}


def test_reason_field_never_read_by_app_code():
    """#146 M1 红线:reason 是规划装置,不是验证装置——应用代码(edu_agent/)任何位置
    不得读取 reason;cited_numbers 前车之鉴:自报字段一进判定逻辑就变成谎报源。
    覆盖 #157 评审加固:索引取值(["reason"]/get)之外的读取面——pop(读取并删除)、
    setdefault(读取并写入)、裸比较(== "reason" / "reason" ==)。vision 的
    reason(转写判定)为独立语义,同样无读取。"""
    pattern = re.compile(
        r"""\[\s*["']reason["']\s*\]"""
        r"""|\.get\(\s*["']reason["']"""
        r"""|\.pop\(\s*["']reason["']"""
        r"""|\.setdefault\(\s*["']reason["']"""
        r"""|==\s*["']reason["']"""
        r"""|["']reason["']\s*==""")
    hits = []
    for path in sorted((REPO_ROOT / "edu_agent").rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{path.relative_to(REPO_ROOT)}:{lineno}")
    assert hits == [], f"reason 被判定/守卫代码读取(违规): {hits}"
