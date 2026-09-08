"""M2 R6 合同:首问策略分派 + 结构化 summary 通路(#34 人批② + opening_strategy)。

断言零模型:opening 分派用假 gateway 捕获消息;结构化通路断言零模型调用与
模板护栏自洽(语气/格式);物理隔离 = 条件不满足零经过该分支。
"""

from __future__ import annotations

import json

from fake_openai import FakeOpenAI, completion

from edu_agent.agents.small_lecturer import (
    OPENING_HINT_CORRECT,
    OPENING_HINT_INCORRECT,
    OPENING_HINT_UNANSWERED,
    evaluate_student_visible_format,
    finish,
    opening_hint,
    reply,
    start,
)
from edu_agent.gateway import GatewayError

from test_kernel_state_machine import (
    QUESTION_TEXT,
    kernel_gateway,
    tutor_json,
)


class CapturingFake(FakeOpenAI):
    """记录 messages 的假上游(FakeOpenAI.requests 已存请求体,取 messages[0:])。"""

    def system_and_user(self, index: int = 0) -> tuple[str, str]:
        request = self.requests[index]
        messages = request["messages"]
        return messages[0]["content"], messages[1]["content"]


def r6_gateway(tmp_path):
    fake = CapturingFake([completion(tutor_json("我们先确认题意。"))] * 8).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    return gateway, fake


# ---------- B 端:首问策略分派 ----------

def test_opening_hint_dispatch_by_answer_status(tmp_path):
    """correct/incorrect/unanswered → 对应常量拼在 user 消息开头;unknown → 无提示。"""
    gateway, fake = r6_gateway(tmp_path)
    hints = {}
    for status in ("correct", "incorrect", "unanswered", None):
        start({"text": "3x+7=25"}, {"grade": "五年级", **({"answer_status": status} if status else {})},
              gateway=gateway)
        hints[status or "unknown"] = fake.system_and_user(len(hints))[1]
    gateway.close()
    fake.stop()
    assert hints["correct"].startswith("这道题学生已做对。")
    assert hints["incorrect"].startswith("这道题学生未做对。")
    assert hints["unanswered"].startswith("这道题学生尚未作答。")
    assert "开场" not in hints["unknown"]  # unknown/缺省不加提示(普通首问)
    assert opening_hint("unknown") == "" and opening_hint(None) == ""


def test_opening_hint_constants_semantics():
    """三常量语义:correct 直接问不懂处+懂了复讲;incorrect 教学弧线(采集错误
    答案→诊断→苏格拉底纠错→学生复讲,2026-09-08 人定);unanswered 从第一步起。"""
    assert "不要重新教" in OPENING_HINT_CORRECT
    assert "还有没有不懂" in OPENING_HINT_CORRECT and "讲一遍" in OPENING_HINT_CORRECT
    assert "不替他命名方法" in OPENING_HINT_CORRECT  # 复讲不代喂方法名/答案(2026-09-08 人定)
    assert "不替他命名方法" in OPENING_HINT_INCORRECT
    assert "卡点" in OPENING_HINT_INCORRECT
    for step in ("说出他现在认为的答案", "怎么想出来的", "正确答案", "讲一遍"):
        assert step in OPENING_HINT_INCORRECT, step
    assert "第一步" in OPENING_HINT_UNANSWERED
    assert opening_hint("correct") == OPENING_HINT_CORRECT


# ---------- A 端:结构化 summary 通路 ----------

def test_structured_summary_on_correct_with_no_stuck(tmp_path):
    """answer_status=correct + 无卡点 → finish 走确定性模板 completed,零模型调用。"""
    fake = FakeOpenAI([
        completion(tutor_json("我们先确认题意。")),
        completion(tutor_json("很好,继续。")),
        completion(tutor_json("你把每一步都讲清楚了。")),
        completion(json.dumps({"summary": "不该被生成"})),  # 结构化通路不得触达模型(毒饵)
    ]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start({"text": "解方程 3x+7=25。"}, {"grade": "五年级", "answer_status": "correct"},
                  gateway=gateway)
    reply(first.session, "我想两边都减去7。", gateway=gateway)
    reply(first.session, "得到 x=6,代回检验成立。", gateway=gateway)
    calls_before_finish = len(fake.requests)
    summary = finish(first.session, gateway=gateway)
    gateway.close()
    fake.stop()
    assert summary.status == "completed"  # 非 needs_review(人批②的核心)
    assert "解方程 3x+7=25" in summary.text and "x=6" in summary.text  # ①②引题面与学生原话
    assert "再做一道" in summary.text      # ③固定收尾(SKILL 规则 9 的两个动作)
    assert len(fake.requests) == calls_before_finish  # 结构化通路零模型调用
    assert first.session.state == "completed"


def test_structured_summary_quotes_student_words_and_passes_guardrails(tmp_path):
    """模板引用学生原话,且整段过语气/格式护栏(任务书:模板必须过护栏)。"""
    from edu_agent.agents.small_lecturer import apply_tone_guardrail, evaluate_student_visible_format

    gateway, fake = r6_gateway(tmp_path)
    turn = start({"text": "图书馆原有120本书,又买来45本,借出38本,现在有多少本?"},
                 {"grade": "三年级", "answer_status": "correct"}, gateway=gateway)
    reply(turn.session, "先算120加45等于165本。", gateway=gateway)
    reply(turn.session, "再算165减38等于127本,所以现在有127本。", gateway=gateway)
    summary = finish(turn.session, gateway=gateway)
    gateway.close()
    fake.stop()
    assert "「先算120加45等于165本。」" in summary.text or "165" in summary.text  # 引用学生原话
    fmt = evaluate_student_visible_format(summary.text)
    assert fmt.ok is True  # 格式护栏(无 Markdown/LaTeX)
    tone = apply_tone_guardrail(
        reply=summary.text, grade_band="primary_lower", interaction_signal="neutral",
        teaching_move="connect_relation", ready_to_record=True)
    assert tone.applied is False  # 语气护栏(三年级档,无年龄错配)


def test_stuck_mark_blocks_structured_path(tmp_path):
    """物理隔离:对话中出现护栏替换(卡点标记)→ 即使 answer_status=correct 也不走模板。"""
    leak = tutor_json("答案是 x=6。")
    fake = FakeOpenAI([
        completion(tutor_json("我们先确认题意。")),
        completion(leak),                 # 泄露 → 护栏替换 → stuck 标记
    ]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start({"text": "解方程 3x+7=25。"}, {"grade": "五年级", "answer_status": "correct"},
                  gateway=gateway)
    reply(first.session, "我算出 x=6 了。", gateway=gateway)
    assert first.session.stuck is True    # 卡点已标记(泄露未解决)
    summary = finish(first.session, gateway=gateway)
    gateway.close()
    fake.stop()
    assert summary.status == "needs_review"  # 有卡点不走模板(零经过该分支)
