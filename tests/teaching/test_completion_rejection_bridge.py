"""C′ stalled-completion mitigation(#423 终裁 2026-09-27,评论 5846062131)。

#453 实证的两类 FN 形态(numeric「每份重0.4kg」答案嵌陈述无模板 / short_text
「结论是无法确定」答案先行理由后置)在 precision-first claim 语法下不产证据
→ gate 拒 → Tutor 否定重置文案(C24)。C′ 三件套断言(零模型、零外部 API,
经公开面驱动,02 §6 测试禁私有导入):

① diagnose_rejection 八条件:正例(#453 两形态,全字段)+ 禁止清单(终裁
  原文四案逐字:猜/否定/多候选/不确定)+ 问句/撤回/连接/值不匹配/无 spec/
  复合面 + 构造期校验(零 authority 的类型面钉死)+ Gate 零精度变化(同一
  输入上 verify_completion 仍 None——C′ 只加诊断不加召回);
② kernel finish() 拒绝路径(e2e):拒因在场 → guard_events 记 rejection_reason
  (additive,仅在场加键)+ Summary 文案换 RESTATED_CLAIM_BRIDGE;state/
  needs_review 终态不动(零状态迁移);下一轮可认证重述 → 原 Gate 正常
  completed;禁止案维持 NEEDS_REVIEW_TEXT(其他 needs_review 场景现文案不动);
③ prompt 侧装配条件注入(completion_signal_fact 同款):reply 轮拒因在场 →
  user 消息携带「结论复述请求」指令(四铁律措辞,无 canonical answer);
  evidence 轮/干净轮未注入;两面互斥。

mutation 面:八条件逐一 canary——经 monkeypatch 摘除对应确定性守卫(纯函数
门,零状态零模型),断言对应禁止案**在摘除后产生** rejection_reason,即各负
例钉在其条件上、非第二守卫偶然拦下(实测教训:「…0.4kg吗」同时被问句门与
撤回窗拦,负例必须选唯一拦截形态)。canary 需要 patch 判定模块内部守卫:
经 monkeypatch 字符串目标触达,不在测试文件里 import 私有模块(02 §6 的
import 字面规则由 check_test_imports 管;canary 钉的正是这些内部接线的
load-bearing 性)。条件①②无可摘守卫(去 spec None 检查即 AttributeError、
去窄面 dispatch 即复合面误入),对应负例测试本身就是 mutation 检测(摘除即红)。
"""

from __future__ import annotations

import json

import pytest

from edu_agent.agents.small_lecturer import (
    NEEDS_REVIEW_TEXT,
    RESTATED_CLAIM_BRIDGE,
    AnswerSpec,
    CompletionRejectionReason,
    LearnerSession,
    diagnose_rejection,
    finish,
    reply,
    start,
    verify_completion,
)

from teachkit import FakeGateway

TURN = 3  # 任意轮号:拒因必须原样携带(与证据同款 turn-scoped 审计面)

NUMERIC_SPEC = AnswerSpec(answer_type="numeric_with_unit", ground_truth="0.4kg")
SHORTTEXT_SPEC = AnswerSpec(answer_type="short_text_exact", ground_truth="无法确定")

NUMERIC_Q = {
    "text": "一袋苹果2kg,平均分成5份,每份重多少?",
    "answer": "0.4kg",
    "answer_spec": {"answer_type": "numeric_with_unit", "ground_truth": "0.4kg"},
    "analysis": "", "knowledge_points": [],
}
SHORTTEXT_Q = {
    "text": "一根绳子剪了几刀后,剩下的段数能确定吗?",
    "answer": "无法确定",
    "answer_spec": {"answer_type": "short_text_exact", "ground_truth": "无法确定"},
    "analysis": "", "knowledge_points": [],
}
# #453 两类 FN 形态逐字(short_text 的理由文本避开疑问/不确定 marker:
# 「无法确定」不含「不确定」子串,消息级门不误触)。
NUMERIC_FN_MESSAGE = "每份重0.4kg。验算:0.4×5=2kg。"
SHORTTEXT_FN_MESSAGE = "结论是无法确定。因为绳长1米和0.5米时,剩余都超过一半。"


def _open(text):
    return {"reply": text, "acceptable": True, "steps": []}


def _tutor(text, ready=False):
    return {"reason": "引导", "reply": text, "ready_to_confirm": ready,
            "cited_numbers": []}


def _last_user_prompt(gateway: FakeGateway) -> dict:
    content = gateway.requests[-1]["messages"][1]["content"]
    return json.loads(content)


def _ready_session(question, gateway_payloads=None):
    """start + 一轮模型 ready → ready_to_confirm(C24 场景的前置态)。"""
    gateway = FakeGateway(gateway_payloads or [
        _open("我们来看这道题。"), _tutor("好的,你接着算,算完告诉我结果。", ready=True)])
    session = start(dict(question), {"grade": "五年级", "answer_status": "correct"},
                    gateway=gateway).session
    reply(session, "我用2除以5来算", gateway=gateway)
    assert session.state == "ready_to_confirm"
    return session, gateway


# ---------- ① diagnose_rejection:正例(#453 两类 FN 形态) ----------


def test_numeric_fn_form_produces_reason_with_full_fields():
    """#453 FN 形态一(numeric 答案嵌陈述无模板词):值匹配 + 守卫全过 +
    唯一失败=claim 形态 → 拒因产生,四字段照 C′ 类型面。"""
    reason = diagnose_rejection(NUMERIC_SPEC, NUMERIC_FN_MESSAGE, TURN)
    assert reason is not None
    assert reason.reason_type == "value_matched_but_claim_uncertified"
    assert reason.answer_type == "numeric_with_unit"
    assert reason.matched_value == "0.4kg"      # 学生原文片段,非 canonical answer
    assert reason.turn_id == TURN


def test_shorttext_fn_form_produces_reason():
    """#453 FN 形态二(short_text 答案先行理由后置):候选出现 + 守卫全过 +
    唯一失败=命中位形态(非末段整答收尾)→ 拒因产生。"""
    reason = diagnose_rejection(SHORTTEXT_SPEC, SHORTTEXT_FN_MESSAGE, TURN)
    assert reason is not None
    assert reason.reason_type == "value_matched_but_claim_uncertified"
    assert reason.answer_type == "short_text_exact"
    assert reason.matched_value == "无法确定"
    assert reason.turn_id == TURN


def test_certified_claim_forms_produce_no_reason():
    """条件⑧(唯一失败=claim 形态):claim 认证位在场(声明模板/裸答案/
    末段整答收尾)→ 非拒因形态——证据可产,拒因不产(两面互斥的函数面)。"""
    assert diagnose_rejection(NUMERIC_SPEC, "答案是0.4kg", TURN) is None
    assert diagnose_rejection(NUMERIC_SPEC, "0.4kg", TURN) is None
    assert diagnose_rejection(SHORTTEXT_SPEC, "答案是无法确定。", TURN) is None
    assert diagnose_rejection(SHORTTEXT_SPEC, "因为绳长不知道,所以结论是无法确定。",
                              TURN) is None


# ---------- ① 禁止清单(终裁原文四案)+ 同族守卫 ----------


def test_forbidden_guess_negation_alternatives_uncertain():
    """终裁禁止清单逐字:「我猜0.4kg」「不是0.4kg」「0.4kg还是0.5kg」
    「可能是0.4kg」——四案均不得产生 rejection reason(八条件缺一不产生)。"""
    assert diagnose_rejection(NUMERIC_SPEC, "我猜0.4kg", TURN) is None
    assert diagnose_rejection(NUMERIC_SPEC, "不是0.4kg", TURN) is None
    assert diagnose_rejection(NUMERIC_SPEC, "0.4kg还是0.5kg", TURN) is None
    assert diagnose_rejection(NUMERIC_SPEC, "可能是0.4kg", TURN) is None


def test_forbidden_question_forms():
    """条件④(非问句):「每份重0.4kg?」(问号收尾)与「每份重0.4kg,对吗」
    (疑问 marker)都不得产生拒因——问句猜答不可认证(与 verifier 同口径)。"""
    assert diagnose_rejection(NUMERIC_SPEC, "每份重0.4kg?", TURN) is None
    assert diagnose_rejection(NUMERIC_SPEC, "每份重0.4kg,对吗", TURN) is None


def test_forbidden_window_guards():
    """条件⑤⑥⑦的逐命中窗:命中后自我撤回(「…,不对」)、候选连接
    (「…。和0.5kg」)、多候选变体(「每份重0.4kg,还是0.5kg」)均不产生。"""
    assert diagnose_rejection(NUMERIC_SPEC, "每份重0.4kg,不对", TURN) is None
    assert diagnose_rejection(NUMERIC_SPEC, "每份重0.4kg。和0.5kg", TURN) is None
    assert diagnose_rejection(NUMERIC_SPEC, "每份重0.4kg,还是0.5kg", TURN) is None
    assert diagnose_rejection(SHORTTEXT_SPEC, "无法确定和容易变形都说得通", TURN) is None


def test_value_must_match_condition():
    """条件③(value_match):值不匹配(0.5≠0.4)、候选不出现 → 无拒因。"""
    assert diagnose_rejection(NUMERIC_SPEC, "每份重0.5kg", TURN) is None
    assert diagnose_rejection(SHORTTEXT_SPEC, "我觉得绳子很长", TURN) is None


def test_no_spec_or_out_of_claim_gate_faces():
    """条件①②:spec None(fail-closed)、复合/开放类型、四面无 claim 门
    (choice/true_false/equation/ratio——值匹配且守卫全过即命中,无「唯一
    失败=claim 形态」形态)、多槽复合红线 → 一律 None。"""
    assert diagnose_rejection(None, NUMERIC_FN_MESSAGE, TURN) is None
    assert diagnose_rejection(
        AnswerSpec(answer_type="composite", ground_truth="鸡3只兔5只"),
        "鸡3只兔5只", TURN) is None
    letters = {"letter_choices": ("A", "B", "C", "D")}
    assert diagnose_rejection(
        AnswerSpec(answer_type="choice_letter", ground_truth="B", **letters),
        "B和D", TURN) is None
    assert diagnose_rejection(
        AnswerSpec(answer_type="true_false", ground_truth="对"), "对和错", TURN) is None
    assert diagnose_rejection(
        AnswerSpec(answer_type="equation_form", ground_truth="x-21=35"),
        "我猜是x-21=35", TURN) is None
    assert diagnose_rejection(
        AnswerSpec(answer_type="numeric_with_unit", ground_truth="鸡3只兔5只"),
        "鸡3只", TURN) is None


def test_reason_construction_guards():
    """零 authority 的类型面钉死(构造期即炸):reason_type 恒单值
    (diagnostic 不得长出新形态)、answer_type 限六窄面。"""
    good = ("value_matched_but_claim_uncertified", "numeric_with_unit", "0.4kg", 2)
    assert CompletionRejectionReason(*good).reason_type == good[0]
    with pytest.raises(ValueError):
        CompletionRejectionReason("trusted_completion", "numeric_with_unit", "0.4kg", 2)
    with pytest.raises(ValueError):
        CompletionRejectionReason("value_matched_but_claim_uncertified",
                                  "composite", "鸡3只兔5只", 2)


def test_gate_precision_unchanged_on_all_faces():
    """零 Gate 精度变化(终裁边界 1):拒因形态上 verify_completion 仍 None
    (FN 面不动,C′ 只加诊断不加召回);认证形态照常出证(Evidence|None
    语义与 #416/#420 既有精度零变化)。"""
    assert verify_completion(NUMERIC_SPEC, NUMERIC_FN_MESSAGE, TURN) is None
    assert verify_completion(SHORTTEXT_SPEC, SHORTTEXT_FN_MESSAGE, TURN) is None
    assert verify_completion(NUMERIC_SPEC, "答案是0.4kg", TURN) is not None
    assert verify_completion(SHORTTEXT_SPEC, "无法确定", TURN) is not None


def test_session_property_is_read_only_view():
    """session.completion_rejection 只读视图:最新学生轮消息拒因在场 + 轮号
    正确;空历史/无声明面 → None(权限分级:diagnostic 视图,非 trusted 信号)。"""
    session = LearnerSession(question=dict(NUMERIC_Q), learner={"grade": "五年级"})
    assert session.completion_rejection is None            # 无学生消息
    session.history.append({"role": "user", "content": NUMERIC_FN_MESSAGE})
    reason = session.completion_rejection
    assert reason is not None and reason.turn_id == 1 and reason.matched_value == "0.4kg"
    bare = LearnerSession(question={"text": "题面"}, learner={})
    bare.history.append({"role": "user", "content": NUMERIC_FN_MESSAGE})
    assert bare.completion_rejection is None               # 无 answer_spec 声明面


# ---------- mutation:八条件逐一 canary(摘守卫 → 禁止案产生) ----------

_GATE_MODULE = "edu_agent.agents.small_lecturer.completion"


def test_mutation_c3_value_match_gate(monkeypatch):
    """条件③摘除(_unit_value_match 恒 True)→ 值不匹配案「每份重0.5kg」
    产生拒因——证明负例钉在值匹配门上。"""
    monkeypatch.setattr(f"{_GATE_MODULE}._unit_value_match", lambda *_a: True)
    assert diagnose_rejection(NUMERIC_SPEC, "每份重0.5kg", TURN) is not None


def test_mutation_c4_question_gate(monkeypatch):
    """条件④摘除(_is_question 恒 False)→ 问句案「每份重0.4kg?」产生拒因
    (该案唯一拦截=问句门:问号被 _retracted 剥标点后不拦,已人工核唯一性)。"""
    monkeypatch.setattr(f"{_GATE_MODULE}._is_question", lambda _m: False)
    assert diagnose_rejection(NUMERIC_SPEC, "每份重0.4kg?", TURN) is not None


def test_mutation_c5_uncertain_gate(monkeypatch):
    """条件⑤摘除(消息级不确定门)→「可能是0.4kg」产生拒因。"""
    monkeypatch.setattr(f"{_GATE_MODULE}._is_uncertain", lambda _m: False)
    assert diagnose_rejection(NUMERIC_SPEC, "可能是0.4kg", TURN) is not None


def test_mutation_c5_guess_window(monkeypatch):
    """条件⑤摘除(逐命中猜测窗)→ 终裁禁止案「我猜0.4kg」产生拒因。"""
    monkeypatch.setattr(f"{_GATE_MODULE}._guessed", lambda *_a: False)
    assert diagnose_rejection(NUMERIC_SPEC, "我猜0.4kg", TURN) is not None


def test_mutation_c6_negation_window(monkeypatch):
    """条件⑥摘除(命中前否定窗)→ 终裁禁止案「不是0.4kg」产生拒因。"""
    monkeypatch.setattr(f"{_GATE_MODULE}._negated", lambda *_a: False)
    assert diagnose_rejection(NUMERIC_SPEC, "不是0.4kg", TURN) is not None


def test_mutation_c6_retraction_window(monkeypatch):
    """条件⑥摘除(命中后撤回窗)→「每份重0.4kg,不对」产生拒因。"""
    monkeypatch.setattr(f"{_GATE_MODULE}._retracted", lambda *_a: False)
    assert diagnose_rejection(NUMERIC_SPEC, "每份重0.4kg,不对", TURN) is not None


def test_mutation_c7_alternatives_gate(monkeypatch):
    """条件⑦摘除(消息级多候选门)→「每份重0.4kg,还是0.5kg」产生拒因。
    变体选择:无逗号形态的「还是」会被数字 token 的单位捕获吞进「kg还是」
    致单位面失配(与 verifier 同款行为,双守卫);逗号分隔让 token 单位干净,
    多候选门即唯一拦截(负例+本 canary 共同钉死)。"""
    monkeypatch.setattr(f"{_GATE_MODULE}._is_alternatives", lambda _m: False)
    assert diagnose_rejection(NUMERIC_SPEC, "每份重0.4kg,还是0.5kg", TURN) is not None


def test_mutation_c7_join_window(monkeypatch):
    """条件⑦摘除(逐命中连接窗)→「每份重0.4kg。和0.5kg」产生拒因。"""
    monkeypatch.setattr(f"{_GATE_MODULE}._joined", lambda *_a: False)
    assert diagnose_rejection(NUMERIC_SPEC, "每份重0.4kg。和0.5kg", TURN) is not None


def test_mutation_c8_numeric_claim_gate(monkeypatch):
    """条件⑧摘除(numeric claim 位检查恒「未认证」)→ 认证形态「答案是
    0.4kg」产生拒因——证明 claim 位过滤是拒因与证据的分界,摘除即互相渗透。"""
    monkeypatch.setattr(f"{_GATE_MODULE}._claim_match", lambda *_a: None)
    assert diagnose_rejection(NUMERIC_SPEC, "答案是0.4kg", TURN) is not None


def test_mutation_c8_shorttext_bounds_gate(monkeypatch):
    """条件⑧摘除(short_text 认证命中位检查恒 None)→ 末段整答收尾形态
    「答案是无法确定。」产生拒因。"""
    monkeypatch.setattr(f"{_GATE_MODULE}._shorttext_bounds", lambda *_a: None)
    assert diagnose_rejection(SHORTTEXT_SPEC, "答案是无法确定。", TURN) is not None


# ---------- ② kernel finish() 拒绝路径(e2e,零模型于拒绝/完成两轮) ----------


def test_finish_rejection_routes_bridge_then_restatement_completes():
    """C24 主路径(numeric FN 形态,ready_to_confirm + 终述收束→finish 拒):
    拒因在场 → Turn 文案=RESTATED_CLAIM_BRIDGE(替换否定重置文案)+ 埋点
    rejection_reason;**state/needs_review 终态不动**;下一轮「答案是0.4kg」
    → 原 Gate 正常出证 → completed(零状态迁移的反向钉,全程零额外模型调用)。"""
    session, gateway = _ready_session(NUMERIC_Q)
    version = session.session_version
    turn = reply(session, NUMERIC_FN_MESSAGE, gateway=gateway)
    assert turn.text == RESTATED_CLAIM_BRIDGE
    assert turn.text != NEEDS_REVIEW_TEXT          # 否定重置文案不再出现
    assert turn.state == "ready_to_confirm"        # 零状态迁移:session 不放行
    assert session.state == "ready_to_confirm" and not session.finished
    assert session.summary is None                 # 不写 summary(拒即拒)
    assert session.guard_events[-1] == {
        "branch": "completion_gate_rejected", "turn": 2,
        "rejection_reason": "value_matched_but_claim_uncertified"}
    assert session.session_version == version + 1  # 唯一推进来自终述入史轮
    final = reply(session, "答案是0.4kg", gateway=gateway)
    assert final.state == "completed" and session.finished
    assert gateway.requests == gateway.requests[:2]  # 拒绝轮/完成轮均零模型调用


def test_forbidden_forms_keep_needs_review_text():
    """禁止四案 + 问句案(同 e2e 场景):无拒因 → 维持 NEEDS_REVIEW_TEXT
    原文案、埋点无 rejection_reason 键(additive,仅在场加)、状态同样不动。"""
    for message in ("我猜0.4kg", "不是0.4kg", "0.4kg还是0.5kg", "可能是0.4kg",
                    "每份重0.4kg,对吗"):
        session, gateway = _ready_session(NUMERIC_Q)
        turn = reply(session, message, gateway=gateway)
        assert turn.text == NEEDS_REVIEW_TEXT, message
        assert turn.state == "ready_to_confirm", message
        assert session.guard_events[-1]["branch"] == "completion_gate_rejected"
        assert "rejection_reason" not in session.guard_events[-1], message


def test_external_finish_rejection_routes_bridge_shorttext():
    """第二路径(short_text FN 形态,外部直调 finish):消息先走模型轮
    (答案无数字,判停闸不收束)→ finish 拒 → 拒因在场 → Summary 文案=
    bridge、status 仍 needs_review、session_version 不动、state 不动。"""
    gateway = FakeGateway([_open("我们来看这道题。"),
                           _tutor("你把结论完整说一句。", ready=True)])
    session = start(dict(SHORTTEXT_Q), {"grade": "五年级", "answer_status": "correct"},
                    gateway=gateway).session
    reply(session, SHORTTEXT_FN_MESSAGE, gateway=gateway)
    assert session.state == "ready_to_confirm"
    version = session.session_version
    summary = finish(session, gateway=gateway)
    assert summary.text == RESTATED_CLAIM_BRIDGE
    assert summary.status == "needs_review"
    assert summary.session_version == version
    assert session.state == "ready_to_confirm" and not session.finished
    assert session.guard_events[-1]["rejection_reason"] == \
        "value_matched_but_claim_uncertified"


# ---------- ③ prompt 侧条件注入(completion_signal_fact 同款) ----------


def test_reply_prompt_carries_bridge_directive_on_rejection_form():
    """reply 轮拒因形态(short_text FN)→ 装配 user 消息携带「结论复述请求」
    指令:四铁律措辞在位(不宣告对错/不说出答案/不重新教学/不从头重做);
    指令不含 canonical answer;「完成判定」不在场(两面互斥)。"""
    gateway = FakeGateway([_open("我们来看这道题。"), _tutor("你把结论完整说一句。")])
    session = start(dict(SHORTTEXT_Q), {"grade": "五年级"}, gateway=gateway).session
    reply(session, SHORTTEXT_FN_MESSAGE, gateway=gateway)
    prompt = _last_user_prompt(gateway)
    assert "结论复述请求" in prompt and "完成判定" not in prompt
    directive = prompt["结论复述请求"]
    for marker in ("已经包含一个结果", "最终结论", "允许同义改写",
                   "不宣告对错", "不重新教学", "不要求从头重做", "不重置已有进展"):
        assert marker in directive, marker
    assert "无法确定" not in directive        # 无 canonical answer(学生原文已有)


def test_bridge_directive_mutually_exclusive_with_signal():
    """互斥钉:evidence 轮(裸整答「无法确定」)→「完成判定」在场、无
    「结论复述请求」;干净轮 → 两面都不在场(未注入即未注入,零扰动)。"""
    gateway = FakeGateway([_open("我们来看这道题。"), _tutor("你把结论完整说一句。")])
    session = start(dict(SHORTTEXT_Q), {"grade": "五年级"}, gateway=gateway).session
    reply(session, "无法确定", gateway=gateway)          # 裸整答 → 当轮证据
    evidence_prompt = _last_user_prompt(gateway)
    assert evidence_prompt["完成判定"] == {"verified_complete": True,
                                          "evidence_turn_id": 1}
    assert "结论复述请求" not in evidence_prompt
    reply(session, "这题有点难", gateway=gateway)          # 干净轮
    neutral_prompt = _last_user_prompt(gateway)
    assert "结论复述请求" not in neutral_prompt
    assert "完成判定" not in neutral_prompt


def test_first_question_and_summary_prompts_not_perturbed():
    """首问/总结装配零扰动:extra 无「学生本轮回答」键 → 注入恒不发生
    (C′ 指令只出现在 reply 轮,与 completion_signal_fact 同款边界)。"""
    gateway = FakeGateway([_open("我们来看这道题。"),
                           _tutor("我们把思路理清楚了。", ready=True),
                           {"summary": "你自己讲清了做法,完成。"}])
    session = start(dict(NUMERIC_Q),
                    {"grade": "五年级", "answer_status": "incorrect"},
                    gateway=gateway).session
    assert "结论复述请求" not in gateway.requests[0]["messages"][1]["content"]
    reply(session, "答案是0.4kg", gateway=gateway)        # 证据轮:完成判定在场
    finish(session, gateway=gateway)                      # 证据+ready → 模型总结
    assert "结论复述请求" not in gateway.requests[-1]["messages"][1]["content"]
    assert "完成判定" in json.loads(gateway.requests[1]["messages"][1]["content"])
