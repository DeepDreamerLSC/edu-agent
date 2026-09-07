"""小讲师内核三函数(00 §5.1:与传输无关的纯模块;03 §4 状态机)。

对外只有 start/reply/finish(经包 __init__ 导出);模型调用只经 gateway
(tutor 角色走 llama-server grammar 级 json_strict;#54 后口径:校验成功的响应
text 即已验证 JSON,直接解析,不自行剥壳/二次校验)。GatewayError 按失败类型
冒泡,内核不吞——调用方(评测线/api 层)决定重试与降级。含图题目经 gateway
vision 角色做图意理解与「题图不可信/多题混入」检测,不可信即 fail closed
(不调 tutor,Turn.state=failed);纯文本题跳过 vision。

PR2:system 消息按 prompting.py 装配(SKILL 剪裁版 + 风格档案 + 攻守图教学
指令);tutor 输出经三护栏(答案泄露/语气/格式)——护栏不过的文本不进入
Turn.text,替换为确定性安全问句(M2 清单阶段 2,断言即规格)。
"""

from __future__ import annotations

import json

from edu_agent.gateway import Gateway, ModelRequest, default_gateway

from .format_guard import evaluate_student_visible_format
from .guardrails import evaluate_student_visible_question
from .prompting import summary_system_prompt, system_prompt
from .session import LearnerSession, SessionVersionConflict, Summary, TerminalStateError, Turn
from .tone_guardrails import apply_tone_guardrail

# grammar 真强制(llama-server)下模型只可能产出符合 schema 的 JSON;
# #54 后 gateway.text 即已验证内容,直接 json.loads。
TUTOR_TURN_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "ready_to_confirm": {"type": "boolean"},
    },
    "required": ["reply", "ready_to_confirm"],
    "additionalProperties": False,
}
TUTOR_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
    "additionalProperties": False,
}
VISION_CHECK_SCHEMA = {
    "type": "object",
    "properties": {
        "acceptable": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["acceptable", "reason"],
    "additionalProperties": False,
}

FAIL_CLOSED_TEXT = "这张题图我没法安全地开始讲解(可能包含多道题或不清晰)。请换一张只包含一道题的清晰照片,或者直接把题目打出来。"
NEEDS_REVIEW_TEXT = "这一题的学习证据还不够,我们继续——你能说说目前想到的第一步吗?"
# 护栏命中时的确定性安全问句(老仓库 hard_safety_fallback 同款语义;M2 清单
# 阶段 2:护栏不过的输出不得到达学生可见面)
SAFE_FALLBACK_TEXT = "先回到当前小问,你能说出题目明确给出的一个条件吗?"


def _guard_output(question_text: str, reply_text: str, grade: str) -> str:
    """三护栏(泄露/语气/格式)逐个过;任一命中即替换为安全文案(M2 阶段 2)。"""
    leak = evaluate_student_visible_question(
        reply_text, active_subquestion_text=question_text)
    if leak.fallback_required:
        return SAFE_FALLBACK_TEXT
    tone = apply_tone_guardrail(
        reply=reply_text, grade_band=_tone_band(grade), interaction_signal="neutral",
        teaching_move="connect_relation", ready_to_record=False)
    if tone.applied:
        return SAFE_FALLBACK_TEXT
    fmt = evaluate_student_visible_format(reply_text)
    if not fmt.ok:
        return fmt.downgrade_prompt or SAFE_FALLBACK_TEXT
    return reply_text


def _tone_band(grade: str) -> str:
    for token, band in (("一", "primary_lower"), ("二", "primary_lower"), ("三", "primary_lower"),
                        ("四", "primary_upper"), ("五", "primary_upper"), ("六", "primary_upper")):
        if token in str(grade):
            return band
    return "neutral"


def _invoke(gateway: Gateway, role: str, messages: list[dict], schema: dict,
            session: LearnerSession):
    return gateway.invoke(ModelRequest(
        role=role, messages=messages, response_schema=schema,
        session_id=session.session_id, max_tokens=800, temperature=0,
    ))


def start(question: dict, learner: dict, *, gateway: Gateway | None = None) -> Turn:
    """生成首问(03 §4 Preparing → FirstQuestionReady / Failed)。

    纯文本题跳过 vision(00 §5.1);含图题 vision 判不可信 → Turn.state=failed
    (fail closed,不调 tutor),后续 reply/finish 对该 session 抛 TerminalStateError。
    """
    gateway = gateway or default_gateway()
    session = LearnerSession(question=question, learner=learner)
    if question.get("image") is not None:
        verdict = json.loads(_invoke(
            gateway, "vision",
            [{"role": "user", "content": json.dumps(
                {"task": "题图理解与安全检查", "image": question["image"]}, ensure_ascii=False)}],
            VISION_CHECK_SCHEMA, session,
        ).text)
        if not verdict["acceptable"]:  # 题图不可信/多题混入
            session.state = "failed"
            return Turn(text=FAIL_CLOSED_TEXT, session_version=session.session_version,
                        state="failed", session=session)
    first = json.loads(_invoke(
        gateway, "tutor",
        [{"role": "system", "content": system_prompt(learner.get("grade", ""))},
         {"role": "user", "content": json.dumps(
             {"题目": question.get("text") or question.get("image"), "学生": learner,
              "任务": "生成首问"}, ensure_ascii=False)}],
        TUTOR_TURN_SCHEMA, session,
    ).text)
    session.state = "first_question_ready"
    session.first_question = first["reply"]
    safe_text = _guard_output(str(question.get("text") or ""), first["reply"], learner.get("grade", ""))
    return Turn(text=safe_text, session_version=session.session_version,
                state=session.state, ready_to_confirm=bool(first["ready_to_confirm"]),
                session=session)


def reply(session: LearnerSession, student_message: str, *,
          gateway: Gateway | None = None, expected_session_version: int | None = None) -> Turn:
    """多轮苏格拉底交流(03 §4 Dialogue 自旋;Conflict 为可选校验,#34 映射表决策)。"""
    if session.finished:
        raise TerminalStateError(f"会话已终态({session.state})")
    if expected_session_version is not None and expected_session_version != session.session_version:
        raise SessionVersionConflict(  # 不推进:旧版本不静默覆盖新一轮诊断(00 §5.2 约定 3)
            f"expected_session_version={expected_session_version} != 当前 {session.session_version}")
    gateway = gateway or default_gateway()
    output = json.loads(_invoke(
        gateway, "tutor",
        [{"role": "system", "content": system_prompt(session.learner.get("grade", ""))},
         {"role": "user", "content": json.dumps(
             {"题目": session.question, "学生": session.learner, "对话记录": session.history,
              "学生本轮回答": student_message}, ensure_ascii=False)}],
        TUTOR_TURN_SCHEMA, session,
    ).text)
    safe_text = _guard_output(str(session.question.get("text") or ""), output["reply"],
                              session.learner.get("grade", ""))
    session.history.append({"role": "user", "content": student_message})
    session.history.append({"role": "assistant", "content": safe_text})
    session.session_version += 1
    session.state = "ready_to_confirm" if output["ready_to_confirm"] else "dialogue"
    return Turn(text=safe_text, session_version=session.session_version,
                state=session.state, ready_to_confirm=bool(output["ready_to_confirm"]),
                session=session)


def finish(session: LearnerSession, *, gateway: Gateway | None = None) -> Summary:
    """学习总结(03 §4 ReadyToConfirm → Completed,summary 不可变;证据不足 needs_review)。"""
    if session.finished:
        if session.state == "completed" and session.summary is not None:
            return session.summary  # completed 终态:finish 幂等返回同一 Summary
        raise TerminalStateError(f"会话已终态({session.state})")
    if session.state != "ready_to_confirm":
        # 证据不足(00 §5.1):不调模型、不写 summary,确定性引导文案
        return Summary(text=NEEDS_REVIEW_TEXT, status="needs_review",
                       session_version=session.session_version)
    gateway = gateway or default_gateway()
    output = json.loads(_invoke(
        gateway, "tutor",
        [{"role": "system", "content": summary_system_prompt(session.learner.get("grade", ""))},
         {"role": "user", "content": json.dumps(
             {"题目": session.question, "学生": session.learner, "对话记录": session.history,
              "任务": "生成学习总结"}, ensure_ascii=False)}],
        TUTOR_SUMMARY_SCHEMA, session,
    ).text)
    session.state = "completed"
    session.summary = Summary(text=output["summary"], status="completed",
                              session_version=session.session_version)
    return session.summary
