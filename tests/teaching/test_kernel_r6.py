"""M2 R6 合同:首问策略分派 + 结构化 summary 通路(#34 人批② + opening_strategy)。

断言零模型:opening 分派用假 gateway 捕获消息;结构化通路断言零模型调用与
模板护栏自洽(语气/格式);物理隔离 = 条件不满足零经过该分支。
Gateway 构造与剧本构造器收拢在 tests/fixtures/teachkit.py。
"""

from __future__ import annotations

import json

from fake_openai import completion

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
# 用户裁逐字文案(2026-09-16)直接字面断言钉死,不经私有导入(02 §6):
FINISH_EVIDENCE_TEXT = "这道题之前已经答对了,我们还需要听你把关键思路讲清楚。"

from teachkit import kernel_env, open_json, tutor_json

# 首问句:首问可见文本恒为固定模板(prompting.first_question_text),这里给模型句只为
# 让假上游序列对齐统一 open 的一次调用(分档模板本身另有回归钉
# tests/teaching/test_kernel_first_question.py)。
_OPENING_TEXT = {
    "correct": "你做对了!还有没有哪里不太确定的地方?",
    None: "这道题要我们求什么?",
}


# ---------- B 端:首问策略分派 ----------

def test_opening_hint_dispatch_by_answer_status(tmp_path):
    """correct/incorrect/unanswered → 对应常量拼在 user 消息开头;unknown → 无提示。"""
    with kernel_env(tmp_path, [completion(open_json("这道题要我们求什么?"))] * 8) as (fake, gateway):
        hints = {}
        for status in ("correct", "incorrect", "unanswered", None):
            before = len(fake.requests)      # 首问违规回落会多耗调用 → 按真实下标取本次请求
            start({"text": "3x+7=25"}, {"grade": "五年级", **({"answer_status": status} if status else {})},
                  gateway=gateway)
            hints[status or "unknown"] = fake.requests[before]["messages"][1]["content"]
    assert hints["correct"].startswith("这道题学生已做对。")
    assert hints["incorrect"].startswith("这道题学生未做对。")
    assert hints["unanswered"].startswith("这道题学生尚未作答。")
    assert "开场" not in hints["unknown"]  # unknown/缺省不加提示(普通首问)
    assert opening_hint("unknown") == "" and opening_hint(None) == ""


def test_opening_hint_constants_semantics():
    """三常量语义:correct 直接问不懂处+懂了复讲;incorrect 教学弧线(采集错误
    答案→诊断→苏格拉底纠错→学生复讲,2026-09-08 人定);unanswered 从第一步起。"""
    assert "不重新教" in OPENING_HINT_CORRECT
    assert "还有没有不懂" in OPENING_HINT_CORRECT and "讲一遍" in OPENING_HINT_CORRECT
    assert "禁止出现任何方法名" in OPENING_HINT_CORRECT  # 复讲不代喂方法名/答案(2026-09-08 人定)
    assert "禁方法名" in OPENING_HINT_INCORRECT
    assert "卡点" in OPENING_HINT_INCORRECT
    for step in ("开场", "选了哪个选项", "怎么想出来的", "正确答案", "讲一遍"):
        assert step in OPENING_HINT_INCORRECT, step
    assert "第一步" in OPENING_HINT_UNANSWERED
    assert opening_hint("correct") == OPENING_HINT_CORRECT


# ---------- A 端:结构化 summary 通路 ----------
# 2026-09-16 用户裁语义修订:撤销 R6「摸底答对+不卡 → 直接 completed」旧规则,
# 完成判定改由会话内讲述证据支持(教学定义:学生自己的表达已包含关键步骤、关键
# 依据和结论,足以让听者理解这道题怎么做;教师说过、学生只附和不算)。finish 先查
# ready_to_confirm;零调用模板仅在确认态 + correct + 无卡点时触达,且只总结学生
# 实际表达(删「每一步都是你自己的思路」「这道题你已经完整讲清楚」无条件断言)。

def test_structured_summary_on_correct_with_ready_state(tmp_path):
    """correct + 已达确认态 → finish 走确定性模板 completed,零模型调用。"""
    with kernel_env(tmp_path, [
        completion(open_json(_OPENING_TEXT["correct"])),
        completion(tutor_json("你自己把做法和检验都说清楚了。", ready=True)),
        completion(json.dumps({"summary": "不该被生成"})),  # 零调用通路不得触达模型(毒饵)
    ]) as (fake, gateway):
        first = start({"text": "解方程 3x+7=25。"}, {"grade": "五年级", "answer_status": "correct"},
                      gateway=gateway)
        reply(first.session, "我想两边都减去7,得到 x=6,代回检验成立。", gateway=gateway)
        assert first.session.state == "ready_to_confirm"   # 完成前提 = 先达确认态
        calls_before_finish = len(fake.requests)
        summary = finish(first.session, gateway=gateway)
        assert summary.status == "completed"
        assert "解方程 3x+7=25" in summary.text and "x=6" in summary.text  # ①②引题面与学生原话
        assert "再做一道" in summary.text                   # ③固定收尾(SKILL 规则 9 的两个动作)
        assert "每一步都是你自己的思路" not in summary.text  # 撤销的无条件断言 1(用户裁)
        assert "已经完整讲清楚" not in summary.text          # 撤销的无条件断言 2(用户裁)
        assert len(fake.requests) == calls_before_finish    # 零调用通路保留
        assert first.session.state == "completed"


def test_finish_correct_without_narration_needs_review(tmp_path):
    """验收矩阵(用户裁):零发言 / 只报答案 / 两轮空泛回应 → 不能完成(needs_review,
    correct 档专项文案,finish 零模型调用)。answer_status=correct 不再绕过确认态。"""
    question = {"text": "解方程 3x+7=25。"}
    learner = {"grade": "五年级", "answer_status": "correct"}
    with kernel_env(tmp_path, [completion(open_json(_OPENING_TEXT["correct"]))]) as (fake, gateway):
        first = start(question, learner, gateway=gateway)   # 零发言
        summary = finish(first.session, gateway=gateway)
        assert summary.status == "needs_review" and summary.text == FINISH_EVIDENCE_TEXT
        assert len(fake.requests) == 1                      # finish 不调模型
        assert first.session.summary is None
    with kernel_env(tmp_path, [
        completion(open_json(_OPENING_TEXT["correct"])),
        completion(tutor_json("你是怎么算出 x=6 的?把你的做法讲给我听。")),
    ]) as (fake, gateway):
        first = start(question, learner, gateway=gateway)   # 只报答案
        reply(first.session, "x=6。", gateway=gateway)
        assert first.session.state == "dialogue"            # 无讲述证据 → 未达确认态
        summary = finish(first.session, gateway=gateway)
        assert summary.status == "needs_review" and summary.text == FINISH_EVIDENCE_TEXT
    with kernel_env(tmp_path, [
        completion(open_json(_OPENING_TEXT["correct"])),
        completion(tutor_json("你先说说这道题要求什么?")),
        completion(tutor_json("那关键的一步是怎么想的?")),
    ]) as (fake, gateway):
        first = start(question, learner, gateway=gateway)   # 两轮空泛回应
        reply(first.session, "好像还行吧。", gateway=gateway)
        reply(first.session, "就那样算的呗。", gateway=gateway)
        summary = finish(first.session, gateway=gateway)
        assert summary.status == "needs_review" and summary.text == FINISH_EVIDENCE_TEXT


def test_finish_correct_ready_but_stuck_uses_model_summary(tmp_path):
    """原条件保留:correct + 已达确认态但有卡点标记 → 模型总结(零调用模板不适用)。

    卡点走确定性卡壳路径(学生「我不会」→ 阶梯揭示 → stuck,零 gateway 依赖)。"""
    with kernel_env(tmp_path, [
        completion(open_json(_OPENING_TEXT["correct"])),
        completion(tutor_json("你自己把两边减 7、再除以 3 讲清楚了。", ready=True)),
        completion(json.dumps({"summary": "模型总结:你把两步思路都讲清楚了。"}, ensure_ascii=False)),
    ]) as (fake, gateway):
        first = start({"text": "解方程 3x+7=25。"}, {"grade": "五年级", "answer_status": "correct"},
                      gateway=gateway)
        reply(first.session, "我不会,这道题太难了。", gateway=gateway)  # 卡壳 → 揭示 → stuck
        assert first.session.stuck is True
        reply(first.session, "两边同时减 7 得 18,再除以 3 得 x=6,代回检验成立。", gateway=gateway)
        assert first.session.state == "ready_to_confirm"
        summary = finish(first.session, gateway=gateway)
        assert summary.status == "completed" and "模型总结" in summary.text


def test_structured_summary_quotes_student_words_and_passes_guardrails(tmp_path):
    """模板引用学生原话,且整段过语气/格式护栏(任务书:模板必须过护栏)。"""
    from edu_agent.agents.small_lecturer import apply_tone_guardrail

    with kernel_env(tmp_path, [
        completion(open_json(_OPENING_TEXT["correct"])),
        completion(tutor_json("你说说先算的是什么?")),          # 首轮:引导(不复读首问)
        completion(tutor_json("你把两步都说清楚了。", ready=True)),  # 末轮:确认收束
    ]) as (fake, gateway):
        turn = start({"text": "图书馆原有120本书,又买来45本,借出38本,现在有多少本?"},
                     {"grade": "三年级", "answer_status": "correct"}, gateway=gateway)
        reply(turn.session, "先算120加45等于165本。", gateway=gateway)
        reply(turn.session, "再算165减38等于127本,所以现在有127本。", gateway=gateway)
        summary = finish(turn.session, gateway=gateway)
        assert "「先算120加45等于165本。」" in summary.text or "165" in summary.text  # 引用学生原话
    fmt = evaluate_student_visible_format(summary.text)
    assert fmt.ok is True  # 格式护栏(无 Markdown/LaTeX)
    tone = apply_tone_guardrail(
        reply=summary.text, grade_band="primary_lower", interaction_signal="neutral",
        teaching_move="connect_relation", ready_to_record=True)
    assert tone.applied is False  # 语气护栏(三年级档,无年龄错配)


def test_stuck_mark_blocks_structured_path(tmp_path):
    """物理隔离:对话中出现护栏替换(卡点标记)→ 即使 answer_status=correct 也不走模板。"""
    leak = tutor_json("答案是 x=06。")  # 前导零:检得出掩不掉 → 纯 block(未解决)
    with kernel_env(tmp_path, [
        completion(open_json(_OPENING_TEXT["correct"])),
        completion(leak),                 # 泄露 → 护栏替换 → stuck 标记
    ]) as (fake, gateway):
        first = start({"text": "解方程 3x+7=25。"}, {"grade": "五年级", "answer_status": "correct"},
                      gateway=gateway)
        reply(first.session, "我算出来了。", gateway=gateway)  # 学生未先给出 x=6 → tutor 报答案为泄露
        assert first.session.stuck is True    # 卡点已标记(泄露未解决)
        summary = finish(first.session, gateway=gateway)
        assert summary.status == "needs_review"  # 有卡点不走模板(零经过该分支)
