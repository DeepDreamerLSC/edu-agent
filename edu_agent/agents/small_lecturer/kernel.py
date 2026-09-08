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

import difflib
import json
import re
from dataclasses import dataclass

from edu_agent.gateway import Gateway, ModelRequest, default_gateway

from .format_guard import _DOWNGRADE_PROMPT, evaluate_student_visible_format
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


# 复读自批评(业界 self-refine:把 tutor 自己上一条当反面证据喂回;任务包2步3)
_SELF_CRITIQUE = (
    "你上一轮已经这样问过,学生仍说不会/没答上来。别重复这个问点:"
    "要么把这一步拆小,并直接给出这一步的具体数值结果(照题面给,如「这一步先算…得到…」),"
    "让他接着算下一步;要么换一个更小的问点。"
)


def _is_repeat(prev: str, new: str) -> bool:
    """语义复读检测:新回复与上一轮 tutor 输出高度相似(阈值 0.85,stdlib difflib)。

    0.85 较 0.9 更严:能多抓「同一个问点换措辞」的语义复读;正常对话里 tutor
    相近但实质推进的回复通常低于 0.85,仍不触发。"""
    if not prev or not new:
        return False
    return difflib.SequenceMatcher(None, prev.strip(), new.strip()).ratio() > 0.85


# 兜底句情境化(任务包2步2,消灭万能句):接学生原话/按护栏类型的提问式引导。
_CONTEXT_FALLBACKS = (
    "先回到当前小问,你能说出题目明确给出的一个条件吗?",
    "我们先把题目里的信息理清楚,你能先复述一个已知条件吗?",
    "先别急,一起看题目给了哪些条件,你能先说其中一个吗?",
    "回到题目本身,你从题干读到的最直接的一个信息是什么?",
)


def _contextual_fallback(session: "LearnerSession | None", guard: str,
                         rule_ids: list[str], student_message: str | None = None) -> str:
    """按情境选一个兜底句;对话轮优先接学生原话(提问式引导,不重复万能句)。"""
    if student_message:
        snippet = str(student_message).strip()[:24]
        return f"先回到你刚说的「{snippet}」——你能从题目里再确认一个已知条件吗?"
    # 纯图/无权威答案(十字绣/剪绳子/连线题):不逼学生答条件,软性回到看图
    if guard == "answer_leak" and "unverified_source_value_disclosure" in rule_ids:
        return "先回到这道题,我们一起看看题目或图片里说了什么——你能先读出一个已知信息吗?"
    if guard == "format":
        return _DOWNGRADE_PROMPT
    return _CONTEXT_FALLBACKS[0]


@dataclass(frozen=True)
class _GuardContext:
    """护栏重生成上下文:检测输入(question/grade)+ 修复重调所需装配(门控参数)。"""
    question: dict
    grade: str
    gateway: Gateway | None = None
    role: str = "tutor"
    messages: list[dict] | None = None
    schema: dict | None = None
    images: list[str] | None = None
    student_message: str | None = None


def _guard_check(ctx: "_GuardContext", text: str) -> tuple[str | None, list[str], str | None]:
    """三护栏(泄露/语气/格式)逐个过;返回 (guard_or_None, rule_ids, normalized_or_downgrade)。"""
    leak = evaluate_student_visible_question(
        text,
        answer_reference=str(ctx.question.get("answer") or ""),
        active_subquestion_text=str(ctx.question.get("text") or ""),
        analysis_reference=str(ctx.question.get("analysis") or ""),
    )
    if leak.fallback_required:
        return ("answer_leak", [f.finding for f in leak.findings], None)
    tone = apply_tone_guardrail(
        reply=text, grade_band=_tone_band(ctx.grade), interaction_signal="neutral",
        teaching_move="connect_relation", ready_to_record=False)
    if tone.applied:
        return ("tone", list(tone.reason_codes), None)
    fmt = evaluate_student_visible_format(text)
    if not fmt.ok:
        return ("format", list(fmt.findings), fmt.downgrade_prompt)
    return (None, [], fmt.reply)  # ok → 归一化文本(LaTeX 已转 a/b)


def _record_event(session: "LearnerSession | None", guard: str, rule_ids: list[str],
                  original: str, regenerated: bool) -> None:
    if session is not None:
        session.guard_events.append({"guard": guard, "rule_ids": rule_ids,
                                     "original": original, "regenerated": regenerated})
        if not regenerated:
            session.stuck = True  # 硬降级 = 未解决的质量问题(卡点标记,R6)


def _regenerate(ctx: "_GuardContext", session: "LearnerSession | None", reply_text: str,
                critique: str) -> str | None:
    """带一句 critique 重调 tutor 一次;重调后过护栏(clean)才返回文本,否则 None。"""
    if ctx.gateway is None or ctx.messages is None:
        return None
    repair_messages = [*ctx.messages, {"role": "user", "content": critique}]
    try:
        repaired = json.loads(_invoke(
            ctx.gateway, ctx.role, repair_messages, ctx.schema or TUTOR_TURN_SCHEMA,
            session, images=ctx.images,
        ).text)
    except Exception as error:  # noqa: BLE001 重生成异常(网络/解析):降级到兜底句
        return None
    new_text = str(repaired.get("reply") or "").strip()
    if not new_text:
        return None
    g2, _r2, d2 = _guard_check(ctx, new_text)
    return d2 if g2 is None else None


def _guard_output(reply_text: str, session: "LearnerSession | None" = None,
                  ctx: "_GuardContext | None" = None) -> str:
    """三护栏响应策略(任务包2步2;检测规则不动,只改策略与调用方式):
    - 修复重生成优先:命中 → 带规则 id+命中片段重调 tutor 一次,再命中才降级;
    - 兜底句情境化:万能句扩为情境变体(接学生原话);
    - 无答案模式放宽:answer 空时 unverified_source_value_disclosure 走 stuck+重生成;
    - LaTeX 双修:格式护栏归一化 \frac{a}{b} → a/b。
    命中埋点 {guard, rule_ids, original, regenerated} 落 session.guard_events。"""
    if ctx is None:
        return reply_text
    guard, rule_ids, normalized = _guard_check(ctx, reply_text)
    if guard is None:
        return normalized
    soft_no_answer = (
        guard == "answer_leak"
        and "unverified_source_value_disclosure" in rule_ids
        and not str(ctx.question.get("answer") or "").strip()
    )
    critique = (f"你上一条回复被教学护栏拦截(规则:{','.join(rule_ids)};命中内容:"
                f"「{reply_text[:48]}」)。请重写这条回复,直接回应用户当前的问题;"
                f"不要重复被拦截的内容,不要提前给出答案或方法名。")
    regenerated = _regenerate(ctx, session, reply_text, critique)
    if regenerated is not None:
        _record_event(session, guard, rule_ids, reply_text, regenerated=True)
        if session is not None and soft_no_answer:
            session.stuck = True  # 无答案放宽:stuck 标记 + 重生成(软信号)
        return regenerated
    fallback = _contextual_fallback(session, guard, rule_ids, ctx.student_message)
    _record_event(session, guard, rule_ids, reply_text, regenerated=False)
    return fallback


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


_VISION_TASK = {
    "task": "题图理解与安全检查",
    "判定标准": (
        "acceptable=true 当且仅当:一张图片承载一道题——一道题内含多个小问、"
        "多幅小图、图表或选项,都算一道;主体文字清晰可读即可。"
        "你解不出这道题、题干看似歧义、数据看似矛盾,都不影响 acceptable——"
        "照实转写,教学时再处理。"
        "acceptable=false 仅当:多道独立题目混在同一张图、图片模糊到无法辨认主体文字、"
        "或图片与题目无关。"
    ),
    "转写要求": (
        "transcription 用纯文本照实转写整题;分数一律写成 a/b 纯文本形式(如 2/3、3/4),"
        "不要用 LaTeX(不得出现 \\frac、反斜杠命令、$ 公式边界)。"
    ),
}


def start(question: dict, learner: dict, *, gateway: Gateway | None = None) -> Turn:
    """生成首问(03 §4 Preparing → FirstQuestionReady / Failed)。

    纯文本题跳过 vision(00 §5.1);纯图题(question.text 为空)vision 判不可信 →
    Turn.state=failed(fail closed,不调 tutor),后续 reply/finish 对该 session 抛
    TerminalStateError。图文题(题库命中,权威文答在题面)vision 拒图 → 降级纯文
    教学不终态——判定标准不写明时模型会把「解不出/题干歧义」当不可接受,实测
    题库误杀 6/12;fail-closed 只留给无文字兜底的纯图题。
    纯图题判可信时,transcription 回填题面(M3 PR7)——转写即教师侧 prompt 的
    题面,学生侧仍只见 tutor 输出经护栏后的文本。
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
            [{"role": "user", "content": json.dumps(_VISION_TASK, ensure_ascii=False)}],
            VISION_CHECK_SCHEMA, session, images=[str(question["image"])],
        ).text)
        if not verdict["acceptable"] and not question.get("text"):
            # 纯图题无文字兜底:fail closed;图文题降级纯文教学(题面文答是权威)
            session.state = "failed"
            return Turn(text=FAIL_CLOSED_TEXT, session_version=session.session_version,
                        state="failed", session=session)
        if not question.get("text") and verdict.get("transcription"):
            # 纯图题:转写回填题面(新 dict,不改调用方入参)
            session.question = {**session.question, "text": str(verdict["transcription"])}
    tutor_messages = [
        {"role": "system", "content": system_prompt(learner.get("grade", ""))},
        _opening_user_message(learner, session.question),
    ]
    first = json.loads(_invoke(
        gateway, "tutor", tutor_messages, TUTOR_TURN_SCHEMA, session,
    ).text)
    ctx = _GuardContext(question=session.question, grade=learner.get("grade", ""),
                        gateway=gateway, role="tutor", messages=tutor_messages,
                        schema=TUTOR_TURN_SCHEMA)
    safe_text = _guard_output(first["reply"], session, ctx)
    session.state = "first_question_ready"
    session.first_question = safe_text  # 存学生实际所见(可能经护栏重生成),不存泄露原文
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
    _reply_messages = [
        {"role": "system", "content": system_prompt(session.learner.get("grade", ""))},
        {"role": "user", "content": _user_prompt(session.question, {
            "学生": session.learner, "对话记录": session.history,
            "学生本轮回答": student_message,
            "输出提醒": "若学生本轮已给出正确最终答案(或明确表示理解并完成检验),"
                        "ready_to_confirm 置 true;否则 false。"})},
    ]
    output = json.loads(_invoke(
        gateway, "tutor", _reply_messages, TUTOR_TURN_SCHEMA, session,
    ).text)
    ctx = _GuardContext(question=session.question, grade=session.learner.get("grade", ""),
                        gateway=gateway, role="tutor", messages=_reply_messages,
                        schema=TUTOR_TURN_SCHEMA, student_message=student_message)
    # 复读自批评(self-refine):与上一轮 tutor 输出高度相似 → 打回重生成一次,仍复读才降级。
    prev = session.history[-1]["content"] if session.history else session.first_question
    if prev and _is_repeat(prev, output["reply"]):
        refined = _regenerate(ctx, session, output["reply"], _SELF_CRITIQUE)
        if refined is None or _is_repeat(prev, refined):
            refined = _contextual_fallback(session, "repeat", [], student_message)
            session.stuck = True  # 复读打断 = 卡点标记(R6 同款)
        output["reply"] = refined
    safe_text = _guard_output(output["reply"], session, ctx)
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
