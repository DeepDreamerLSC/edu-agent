"""Trusted Completion Gate C 段:generation 只读消费的结构断言(#414 §五,零模型)。

三面钉法(任务书口径——行为用结构断言,不调任何模型):
- **注入信号的存在性**:reply 轮当轮 evidence 成立 → 装配出的 user 消息携带
  「完成判定」:{verified_complete: true, evidence_turn_id: N};无证据/非 reply
  轮(首问/总结/未命中)→ 未注入(§五「注入或未注入」,不注入 verified=false);
- **无 canonical answer**:信号事实恰两键(verified_complete/evidence_turn_id),
  不含答案文本——学生原文模型已有(「学生本轮回答」),塞答案=新 answer-leak 面
  (参考答案进教师侧 prompt 是 M3 PR2 既有面,与本注入无关,对照断言钉住增量);
- **终局指引在位性**:system_prompt 稳定段含 §二 verified 后同轮终局指引
  (承认+可选非交互式解释+收束;不再就答案槽确认性重问),措辞不称结构性禁止
  (§五降格:trusted-signal-assisted generation);
- **恒等性**:prompt 侧重演事实 == session.verified_signal(kernel 预算冻结,
  信号在装配侧由同一 verifier/同一组装方契约重演——单一实现,不是第二套判据)。
"""

from __future__ import annotations

import json

from edu_agent.agents.small_lecturer import (
    LearnerSession,
    finish,
    reply,
    start,
    system_prompt,
)

from teachkit import FakeGateway

# 声明面在场的选择题(干净正例):学生裸选项字母 → 当轮 evidence
CHOICE_Q = {
    "text": "下面哪个数是质数? A.9 B.11 C.15 D.21",
    "answer": "B",
    "answer_spec": {"answer_type": "choice_letter",
                    "letter_choices": ["A", "B", "C", "D"]},
    "analysis": "", "knowledge_points": [],
}


def _open(text):
    return {"reply": text, "acceptable": True, "steps": []}


def _tutor(text, ready=False):
    return {"reason": "引导", "reply": text, "ready_to_confirm": ready,
            "cited_numbers": []}


def _last_user_prompt(gateway: FakeGateway) -> dict:
    """最后一次 tutor 请求的 user 消息(装配 JSON)解析回 dict。"""
    content = gateway.requests[-1]["messages"][1]["content"]
    return json.loads(content)


def _reply_and_capture(question, messages, gateway_payloads):
    gateway = FakeGateway(gateway_payloads)
    session = start(question, {"grade": "五年级"}, gateway=gateway).session
    for message in messages:
        reply(session, message, gateway=gateway)
    return session, gateway


# ---------- 注入信号的存在性 ----------

def test_verified_signal_injected_on_evidence_turn():
    """reply 轮学生裸答案「B」→ 当轮 evidence → 装配 prompt 携带完成判定事实。"""
    session, gateway = _reply_and_capture(
        dict(CHOICE_Q), ["B"],
        [_open("我们来看这道题。"), _tutor("你说说你的选择。")])
    prompt = _last_user_prompt(gateway)
    assert prompt["完成判定"] == {"verified_complete": True, "evidence_turn_id": 1}
    assert session.verified_signal == {"verified_complete": True,
                                       "evidence_turn_id": 1}


def test_signal_not_injected_without_evidence():
    """学生未命中(答错字母 C)→ 无 evidence → 未注入(无 verified=false 形态)。"""
    session, gateway = _reply_and_capture(
        dict(CHOICE_Q), ["C"],
        [_open("我们来看这道题。"), _tutor("我们再看看选项。")])
    assert "完成判定" not in _last_user_prompt(gateway)
    assert session.verified_signal is None


def test_signal_turn_scoped_on_prompt_side_too():
    """t1 命中(B)、t2 未再说答案 → t2 装配无完成判定(turn-scoped 重演,
    与 kernel 每轮覆写语义一致;上一轮事实不跨轮复用,§二)。"""
    _, gateway = _reply_and_capture(
        dict(CHOICE_Q), ["B", "我做完了"],
        [_open("我们来看这道题。"), _tutor("你说说你的选择。"),
         _tutor("我们继续。")])
    assert "完成判定" not in _last_user_prompt(gateway)


def test_signal_absent_without_declaration_face():
    """无 answer_spec 声明面(现网题库形态)→ 组装 fail-closed → 恒未注入。"""
    question = dict(CHOICE_Q)
    question.pop("answer_spec")
    _, gateway = _reply_and_capture(
        question, ["B"],
        [_open("我们来看这道题。"), _tutor("你说说你的选择。")])
    assert "完成判定" not in _last_user_prompt(gateway)


# ---------- 无 canonical answer ----------

def test_signal_fact_carries_no_canonical_answer():
    """信号事实恰两键,不含答案文本/值——「B」不出现在完成判定节内
    (参考答案段是 M3 PR2 教师侧既有面,注入零增量)。"""
    _, gateway = _reply_and_capture(
        dict(CHOICE_Q), ["B"],
        [_open("我们来看这道题。"), _tutor("你说说你的选择。")])
    fact = _last_user_prompt(gateway)["完成判定"]
    assert set(fact) == {"verified_complete", "evidence_turn_id"}
    assert "B" not in json.dumps(fact, ensure_ascii=False)


def test_first_question_and_summary_prompts_unchanged():
    """首问/总结装配零扰动:extra 无「学生本轮回答」键 → completion_signal_fact
    恒 None——C 段注入只发生在 reply 轮(§五的行为面)。"""
    gateway = FakeGateway([_open("我们来看这道题。"),
                           _tutor("我们把思路理清楚了。", ready=True),
                           {"summary": "你自己讲清了做法,完成。"}])
    session = start(dict(CHOICE_Q), {"grade": "五年级", "answer_status": "incorrect"},
                    gateway=gateway).session
    # 首问 user 消息 = 弧线提示前缀 + 装配 JSON(非纯 JSON,按子串断言)
    assert "完成判定" not in gateway.requests[0]["messages"][1]["content"]
    reply(session, "B", gateway=gateway)
    finish(session, gateway=gateway)          # evidence+ready → 模型总结路径
    summary_prompt = json.loads(gateway.requests[-1]["messages"][1]["content"])
    assert "完成判定" not in summary_prompt   # 总结装配不带轮级事实
    assert "完成判定" in json.loads(
        gateway.requests[1]["messages"][1]["content"])  # reply 轮带


# ---------- 终局指引在位性 ----------

def test_finality_guidance_in_system_prompt():
    """§二 verified 后同轮终局指引进 system 稳定段:承认+可选非交互式解释+收束;
    不再就答案槽确认性重问;信号缺席=继续引导。措辞不称结构性禁止(§五降格)。"""
    prompt = system_prompt("五年级")
    for marker in ("完成判定", "verified_complete", "evidence_turn_id",
                   "只读事实", "确认性重问", "不再开启新的提问", "只引导他讲思路与依据"):
        assert marker in prompt, marker
    assert "结构性禁止" not in prompt
    assert "系统会阻止" not in prompt       # 不描述 Kernel 门(§四:生成层不知门)


# ---------- 恒等性:prompt 侧重演 == session 真值 ----------

def test_prompt_fact_equals_session_signal_across_faces():
    """同一会话内,每轮装配出的完成判定事实与 session.verified_signal 逐轮相等
    (命中轮相等、未命中轮同缺)——重演不是第二套判据,单一实现单一真值源。"""
    gateway = FakeGateway([_open("我们来看这道题。"),
                           _tutor("你说说你的选择。", ready=True),
                           _tutor("我们再看看。", ready=True)])
    session = start(dict(CHOICE_Q), {"grade": "五年级"}, gateway=gateway).session
    reply(session, "B", gateway=gateway)                 # t1:evidence
    assert _last_user_prompt(gateway)["完成判定"] == session.verified_signal
    reply(session, "我做完啦", gateway=gateway)            # t2:无答案 → 覆写 None
    assert "完成判定" not in _last_user_prompt(gateway)
    assert session.verified_signal is None


def test_verified_signal_accessor_shape():
    """accessor(任务书裁定放 session.py,不进 kernel.py)白盒:None/在场两态。"""
    session = LearnerSession(question=dict(CHOICE_Q), learner={"grade": "五年级"})
    assert session.verified_signal is None               # 无证据(B 段缺省)
