"""小讲师内核三函数(00 §5.1:与传输无关的纯模块;03 §4 状态机)。

对外只有 start/reply/finish(经包 __init__ 导出);模型调用只经 gateway
(tutor 角色走 llama-server grammar 级 json_strict;#54 后口径:校验成功的响应
text 即已验证 JSON,直接解析,不自行剥壳/二次校验)。GatewayError 按失败类型
冒泡,内核不吞——调用方(评测线/api 层)决定重试与降级。含图题目经 gateway
vision 角色做图意理解与「题图不可信/多题混入」检测(M3 PR7 schema 三字段:
acceptable/reason/transcription;纯图题——question.text 为空——的可信转写回填
question.text 进教师侧 prompt),不可信即 fail closed
(不调 tutor,Turn.state=failed);纯文本题跳过 vision。

PR2:system 消息按 prompting.py 装配(SKILL 剪裁版 + 风格档案 + 攻守图教学
指令);tutor 输出经三护栏(答案泄露/语气/格式)——护栏不过的文本不进入
Turn.text,替换为确定性安全问句(M2 清单阶段 2,断言即规格)。M3 PR7:题目
段带参考答案/解析进教师侧 prompt(question.answer/analysis/knowledge_points
由题源适配器填入),泄露护栏对照文本同步扩到 answer/analysis——教师侧看得见
答案,学生侧永远看不到。
"""

from __future__ import annotations

import json
import re

from edu_agent.gateway import Gateway, ModelRequest, default_gateway

from .format_guard import evaluate_student_visible_format
from .guardrails import evaluate_student_visible_question
from .prompting import _user_prompt, opening_hint, summary_system_prompt, system_prompt
from .session import LearnerSession, SessionVersionConflict, Summary, TerminalStateError, Turn
from .tone_guardrails import apply_tone_guardrail

# grammar 真强制(llama-server)下模型只可能产出符合 schema 的 JSON;
# #54 后 gateway.text 即已验证内容,直接 json.loads。
TUTOR_TURN_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "ready_to_confirm": {"type": "boolean"},
        # 数字漂移守卫:模型自报本轮回复中引用的题目条件数字(服务端对题面校验)
        "cited_numbers": {"type": "array", "items": {"type": "number"}},
    },
    "required": ["reply", "ready_to_confirm", "cited_numbers"],
    "additionalProperties": False,
}
TUTOR_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
    "additionalProperties": False,
}
VISION_CHECK_SCHEMA = {  # M3 PR7(#34):三字段;transcription=可信时的整题转写
    "type": "object",
    "properties": {
        "acceptable": {"type": "boolean"},
        "reason": {"type": "string"},
        "transcription": {"type": "string"},
    },
    "required": ["acceptable", "reason", "transcription"],
    "additionalProperties": False,
}

FAIL_CLOSED_TEXT = "这张题图我没法安全地开始讲解(可能包含多道题或不清晰)。请换一张只包含一道题的清晰照片,或者直接把题目打出来。"
NEEDS_REVIEW_TEXT = "这一题的学习证据还不够,我们继续——你能说说目前想到的第一步吗?"
# 护栏命中时的确定性安全问句(老仓库 hard_safety_fallback 同款语义;M2 清单
# 阶段 2:护栏不过的输出不得到达学生可见面)
SAFE_FALLBACK_TEXT = "先回到当前小问,你能说出题目明确给出的一个条件吗?"


def _question_numbers(text: str) -> set[float]:
    """题面条件数字全集(整数/小数;分数按两个数字处理,与口算习惯一致)。"""
    return {float(m) for m in re.findall(r"\d+(?:\.\d+)?", text or "")}


def _guard_output(question: dict, reply_text: str, grade: str,
                  session: "LearnerSession | None" = None) -> str:
    """三护栏(泄露/语气/格式)逐个过;任一命中即替换为安全文案(M2 阶段 2)。

    M3 PR7:泄露护栏对照文本从题面扩到参考答案/解析——教师侧 prompt 里的
    answer/analysis 若出现在回复中即拦截(答案不许从教师侧漏到学生侧)。
    任务包1步1 埋点:命中时把 {guard, rule_ids, original, regenerated} 记入
    session.guard_events(随 FileSessionStore 落盘,评测侧汇总兜底率);
    regenerated 恒 None——第二步修复重生成实现后回填。"""
    def _hit(guard: str, rule_ids: list[str], replacement: str) -> str:
        if session is not None:
            session.guard_events.append({"guard": guard, "rule_ids": rule_ids,
                                         "original": reply_text, "regenerated": None})
        return replacement

    leak = evaluate_student_visible_question(
        reply_text,
        answer_reference=str(question.get("answer") or ""),
        active_subquestion_text=str(question.get("text") or ""),
        analysis_reference=str(question.get("analysis") or ""),
    )
    if leak.fallback_required:
        return _hit("answer_leak", [f.finding for f in leak.findings], SAFE_FALLBACK_TEXT)
    tone = apply_tone_guardrail(
        reply=reply_text, grade_band=_tone_band(grade), interaction_signal="neutral",
        teaching_move="connect_relation", ready_to_record=False)
    if tone.applied:
        return _hit("tone", list(tone.reason_codes), SAFE_FALLBACK_TEXT)
    fmt = evaluate_student_visible_format(reply_text)
    if not fmt.ok:
        return _hit("format", list(fmt.findings),
                    fmt.downgrade_prompt or SAFE_FALLBACK_TEXT)
    return reply_text


def _tone_band(grade: str) -> str:
    for token, band in (("一", "primary_lower"), ("二", "primary_lower"), ("三", "primary_lower"),
                        ("四", "primary_upper"), ("五", "primary_upper"), ("六", "primary_upper")):
        if token in str(grade):
            return band
    return "neutral"


def _opening_user_message(learner: dict, question: dict) -> dict:
    """首问 user 消息:answer_status 的策略提示拼在开头(unknown/缺省不加,#34 R6)。"""
    hint = opening_hint(learner.get("answer_status"))
    context = _user_prompt(question, {"学生": learner, "任务": "生成首问"})
    if hint:
        return {"role": "user", "content": f"{hint}\n{context}"}
    return {"role": "user", "content": context}


def _invoke(gateway: Gateway, role: str, messages: list[dict], schema: dict,
            session: LearnerSession, images: list[str] | None = None):
    return gateway.invoke(ModelRequest(
        role=role, messages=messages, response_schema=schema,
        session_id=session.session_id, max_tokens=800, temperature=0,
        images=images,
    ))


def start(question: dict, learner: dict, *, gateway: Gateway | None = None) -> Turn:
    """生成首问(03 §4 Preparing → FirstQuestionReady / Failed)。

    纯文本题跳过 vision(00 §5.1);含图题 vision 判不可信 → Turn.state=failed
    (fail closed,不调 tutor),后续 reply/finish 对该 session 抛 TerminalStateError。
    纯图题(question.text 为空)判可信时,transcription 回填题面(M3 PR7)——
    转写即教师侧 prompt 的题面,学生侧仍只见 tutor 输出经护栏后的文本。
    两条失败路径正交(审查留审 1 落档):vision 服务不可达/超时 = GatewayError
    冒泡(环境失败,调用方决定重试降级);vision 可达但判不可信 = fail closed
    (内容安全,不重试不降级)。
    """
    gateway = gateway or default_gateway()
    session = LearnerSession(question=question, learner=learner)
    if question.get("image") is not None:
        # 图片经 ModelRequest.images 走多模态内容块(不进文本,见 gateway request);
        # image 值由 api 层解析为 data URL(file_id 在那里翻译,内核不感知存储)。
        verdict = json.loads(_invoke(
            gateway, "vision",
            [{"role": "user", "content": json.dumps(
                {"task": "题图理解与安全检查"}, ensure_ascii=False)}],
            VISION_CHECK_SCHEMA, session, images=[str(question["image"])],
        ).text)
        if not verdict["acceptable"]:  # 题图不可信/多题混入
            session.state = "failed"
            return Turn(text=FAIL_CLOSED_TEXT, session_version=session.session_version,
                        state="failed", session=session)
        if not question.get("text") and verdict.get("transcription"):
            # 纯图题:转写回填题面(新 dict,不改调用方入参)
            session.question = {**session.question, "text": str(verdict["transcription"])}
    first = json.loads(_invoke(
        gateway, "tutor",
        [{"role": "system", "content": system_prompt(learner.get("grade", ""))},
         _opening_user_message(learner, session.question)],
        TUTOR_TURN_SCHEMA, session,
    ).text)
    session.state = "first_question_ready"
    session.first_question = first["reply"]
    safe_text = _guard_output(session.question, first["reply"], learner.get("grade", ""), session)
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
         {"role": "user", "content": _user_prompt(session.question, {
             "学生": session.learner, "对话记录": session.history,
             "学生本轮回答": student_message,
             "输出提醒": "若学生本轮已给出正确最终答案(或明确表示理解并完成检验),"
                         "ready_to_confirm 置 true;否则 false。"})}],
        TUTOR_TURN_SCHEMA, session,
    ).text)
    safe_text = _guard_output(session.question, output["reply"],
                              session.learner.get("grade", ""), session)
    if safe_text != output["reply"]:
        session.stuck = True  # 卡点标记(R6):护栏替换 = 本轮存在未解决的质量问题
    # 数字漂移守卫(M3):模型自报引用的数字 ⊆ 题面数字全集,超出 = 把口误数字
    # 当题目条件复读 → stuck 标记(不拒答,下一轮提醒纠偏);题面无数字跳过
    cited = [float(n) for n in (output.get("cited_numbers") or [])]
    face_numbers = _question_numbers(str(session.question.get("text") or ""))
    if face_numbers and any(n not in face_numbers for n in cited):
        session.stuck = True
    session.history.append({"role": "user", "content": student_message})
    session.history.append({"role": "assistant", "content": safe_text})
    session.session_version += 1
    session.state = "ready_to_confirm" if output["ready_to_confirm"] else "dialogue"
    return Turn(text=safe_text, session_version=session.session_version,
                state=session.state, ready_to_confirm=bool(output["ready_to_confirm"]),
                session=session)


def _structured_summary(session: LearnerSession) -> str:
    """确定性模板(人批②,00 §8.4 R6):①重述学生做到的事(引原话)②关键思路(题面+学生正确回答)③固定收尾。

    纯文本短句(过语气/格式护栏);引用来自会话历史的学生原话与题面,不从模型生成。
    """
    user_turns = [m["content"] for m in session.history if m["role"] == "user"]
    first = user_turns[0] if user_turns else "你从题目本身开始"
    last = user_turns[-1] if user_turns else "给出了你的结论"
    question = str(session.question.get("text") or "")
    return (
        f"这一题(「{question}」)是你自己讲下来的:从「{first}」开始,一步步说到「{last}」,"
        f"每一步都是你自己的思路,结论和题目的要求也对上了。"
        f"这道题你已经完整讲清楚了,可以再做一道,或者今天先到这里。"
    )


def finish(session: LearnerSession, *, gateway: Gateway | None = None) -> Summary:
    """学习总结(03 §4 ReadyToConfirm → Completed,summary 不可变;证据不足 needs_review)。

    R6 结构化通路(人批②):learner.answer_status == "correct" 且会话无卡点标记
    → 掌握已由数据侧证实,直接走确定性模板 completed(零模型调用);
    条件不满足的会话零经过此分支。"""
    if session.finished:
        if session.state == "completed" and session.summary is not None:
            return session.summary  # completed 终态:finish 幂等返回同一 Summary
        raise TerminalStateError(f"会话已终态({session.state})")
    if session.learner.get("answer_status") == "correct" and not session.stuck:
        summary = Summary(text=_structured_summary(session), status="completed",
                          session_version=session.session_version)
        session.state = "completed"
        session.summary = summary
        return summary
    if session.state != "ready_to_confirm":
        # 证据不足(00 §5.1):不调模型、不写 summary,确定性引导文案
        return Summary(text=NEEDS_REVIEW_TEXT, status="needs_review",
                       session_version=session.session_version)
    gateway = gateway or default_gateway()
    output = json.loads(_invoke(
        gateway, "tutor",
        [{"role": "system", "content": summary_system_prompt(session.learner.get("grade", ""))},
         {"role": "user", "content": _user_prompt(session.question, {
             "学生": session.learner, "对话记录": session.history,
             "任务": "生成学习总结"})}],
        TUTOR_SUMMARY_SCHEMA, session,
    ).text)
    session.state = "completed"
    session.summary = Summary(text=output["summary"], status="completed",
                              session_version=session.session_version)
    return session.summary
