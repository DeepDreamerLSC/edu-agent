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
from .prompting import _user_prompt, grade_grounding, opening_hint, summary_system_prompt, system_prompt
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
# 统一 open schema(任务包2步4):一次调用产出 转写 + 分步解 + 首问。
# 因 tutor 即 VL 模型,vision 判定(acceptable/transcription)与首问(reply)
# 合入同一次调用;steps 是阶梯底稿 + 数字校验基准。
OPEN_SCHEMA = {
    "type": "object",
    "properties": {
        "acceptable": {"type": "boolean"},
        "transcription": {"type": "string"},
        "steps": {"type": "array", "items": {
            "type": "object",
            "properties": {"step": {"type": "string"}, "value": {"type": "string"}},
            "required": ["step", "value"], "additionalProperties": False}},
        "reply": {"type": "string"},
    },
    "required": ["acceptable", "transcription", "steps", "reply"],
    "additionalProperties": False,
}

FAIL_CLOSED_TEXT = "这张题图我没法安全地开始讲解(可能包含多道题或不清晰)。请换一张只包含一道题的清晰照片,或者直接把题目打出来。"
# 统一 open 里 reply 留空(图文题 acceptable=false 且模型照"可留空"留空)时的确定性兜底首问
_OPENING_FALLBACK = "我们先看看这道题,你能说说题目给了哪些条件吗?"
# 方法名脱敏词表(任务包:代喂窄规则方案②):复讲阶段教师侧解析/知识点里的方法名
# 替换成「这种方法」,不点名——学生讲完、到总结阶段才由 finish 的教师侧上下文恢复点名。
_METHOD_TOKENS = (
    "方程法", "通分", "假设法", "抬腿法", "列表法", "移项", "合并同类项",
    "公分母", "最小公倍数", "底乘高", "图形转化", "等式性质", "异分母", "二元一次",
)


def _mask_method_names(text: str) -> str:
    """复讲阶段方法名脱敏(确定性,零模型调用):方法名 → 「这种方法」。"""
    for token in _METHOD_TOKENS:
        text = text.replace(token, "这种方法")
    return text


def _masked_question(question: dict) -> dict:
    """教师侧题面脱敏副本:解析与知识点里的方法名替换,不点名(题干/答案不动)。"""
    masked = dict(question)
    if question.get("analysis"):
        masked["analysis"] = _mask_method_names(str(question["analysis"]))
    if question.get("knowledge_points"):
        masked["knowledge_points"] = [_mask_method_names(str(kp))
                                      for kp in question["knowledge_points"]]
    return masked


# 复讲轮代喂的确定性兜底(代喂窄规则方案②+):tutor 在引导/确认轮直接点了方法名
# (学生还没讲) → 替换成固定"请学生讲"引导,且不关对话——继续收集学生的讲题内容。
_ELICIT_TEMPLATE = ("很好,你已经懂了。那请你从头讲讲你的思路——"
                    "先说说你第一步算了什么、为什么这样算。")


def _feeds_method(text: str) -> bool:
    """tutor 输出里点名了方法(代喂):学生还没自己讲,tutor 不该报方法名。"""
    return any(token in text for token in _METHOD_TOKENS)


def _student_signals_understanding(student_message: str) -> bool:
    """学生表示「懂了/明白了」——教学弧线里这是「请学生讲思路」的触发点。

    「会了」用负向断言 (?<!不),避免「我不会了」(卡住)被误判为「懂了」;「懂了」
    「明白了」同款负向断言,避免「越来越不懂了/我不明白了」(卡住)被误判为「懂了」。"""
    return bool(re.search(r"都懂了|(?<!不)懂了|(?<!不)明白了|没有不懂|(?<!不)会了|没问题|都明白|没疑问", student_message))


def _student_signals_stuck(student_message: str) -> bool:
    """学生表示「不会/猜不出」——这是「揭示下一级阶梯」的触发点(治 tutor 复读探针)。

    「不会吧」后接疑问/感叹标点(?!/?/!)是反诘惊讶(「不会吧?!这也能算对?」),不判卡住;
    单纯「不会吧」仍判卡住;「越来越不懂」补上「不懂了」类卡壳(不被「懂了」误吞)。"""
    return bool(re.search(r"我不太会|我猜不出|我猜不出来|我不知道|我想不出|我想不出来|我不会做|我不会了|不会吧(?![?!？])|太难了|没思路|越来越不懂", student_message))


def _next_step(session: "LearnerSession") -> dict | None:
    """阶梯逐级揭示:返回 steps 的下一级(推进 hint_level);揭示完毕返回 None。"""
    if session.hint_level < len(session.steps):
        step = session.steps[session.hint_level]
        session.hint_level += 1
        return step
    return None


# 阶梯揭示的多样开场(确定性,轮换)——避免「这一步我们先看」句句重复、显生硬。
_STEP_LEADS = ("我们从这里入手", "下一步是这样", "再往下看", "你看这一步", "接着这样算", "关键在这一步")


def _reveal_stuck_hint(session: "LearnerSession") -> str:
    """学生卡住 → 揭示下一级阶梯(确定性,零模型调用,不重复)。

    内容 = session.steps 下一级;开场用 _STEP_LEADS 轮换,避免固定前缀生硬。
    模型措辞版实测会重复(3/7)且过度揭示,故仍用确定性。"""
    step = _next_step(session)
    if step is None:
        # 不变量:终答文本只出现在 bottom-out(此处)/ finish / ready_to_confirm 三条
        # 路径(锁在 tests/teaching/test_kernel_invariants.py);阶梯揭示只给步骤不给终答。
        answer = str(session.question.get("answer") or "").strip()
        if not answer and session.steps:
            answer = str(session.steps[-1].get("value") or "").strip()
        return (f"这一步我们直接看结果:{answer}。你先记住它,我们回头再讲一遍为什么。"
                if answer else NEEDS_REVIEW_TEXT)
    lead = _STEP_LEADS[(session.hint_level - 1) % len(_STEP_LEADS)]
    return f"{lead}:{step['step']}。你接着算下一步。"
NEEDS_REVIEW_TEXT = "这一题的学习证据还不够,我们继续——你能说说目前想到的第一步吗?"
# 护栏命中时的确定性安全问句(老仓库 hard_safety_fallback 同款语义;M2 清单
# 阶段 2:护栏不过的输出不得到达学生可见面)
SAFE_FALLBACK_TEXT = "先回到当前小问,你能说出题目明确给出的一个条件吗?"


def _question_numbers(text: str) -> set[float]:
    """题面条件数字全集(整数/小数;分数按两个数字处理,与口算习惯一致)。"""
    return {float(m) for m in re.findall(r"\d+(?:\.\d+)?", text or "")}


def _reply_numbers(text: str) -> set[float]:
    """抽取制数字(替代自报制):回复文本里除「第N」序数语境外的全部数字。

    与 _question_numbers 同口径(整数/小数;分数按两个数字);先剔除「第N」序数
    (第1/第2步…),避免把序数当数字引用误标漂移。"""
    stripped = re.sub(r"第\s*\d+(?:\.\d+)?", "", text or "")
    return _question_numbers(stripped)


def _drift_sources(session: LearnerSession, student_message: str | None,
                   ready_to_confirm: bool) -> tuple[set[float], set[float]]:
    """数字来源标签池(M2 闭环 #113/#34):允许集 = 题面 ∪ steps 值 ∪ 学生历史数字 ∪
    [终答数字:仅 ready_to_confirm 态并入]。

    返回 (允许集, 终答数字池)。终答数字在非确认态单独成池、不入允许集,供违规
    来源标签判定:违规数字若在终答池 → 标签 "answer"(对话态提前说终答),否则
    "hallucinated"(无任何合法来源)。"""
    face = _question_numbers(str(session.question.get("text") or ""))
    steps = set()
    for step in session.steps:
        steps |= _question_numbers(str(step.get("value") or ""))
    student = set()
    for message in session.history:
        if message.get("role") == "user":
            student |= _question_numbers(str(message.get("content") or ""))
    if student_message:
        student |= _question_numbers(str(student_message))
    answer = _question_numbers(str(session.question.get("answer") or ""))
    if not answer and session.steps:
        answer = _question_numbers(str(session.steps[-1].get("value") or ""))
    allowed = face | steps | student | (answer if ready_to_confirm else set())
    return allowed, answer


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
    student_evidence: tuple[str, ...] = ()  # 学生历史 user 消息(泄露护栏对照:已说答案可复述)


def _guard_check(ctx: "_GuardContext", text: str) -> tuple[str | None, list[str], str | None]:
    """三护栏(泄露/语气/格式)逐个过;返回 (guard_or_None, rule_ids, normalized_or_downgrade)。"""
    leak = evaluate_student_visible_question(
        text,
        answer_reference=str(ctx.question.get("answer") or ""),
        active_subquestion_text=str(ctx.question.get("text") or ""),
        analysis_reference=str(ctx.question.get("analysis") or ""),
        student_evidence=list(ctx.student_evidence),
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


def _open_user_message(learner: dict, question: dict) -> dict:
    """统一 open user 消息:先解分步解(steps),再按 answer_status 策略给首问(reply)。

    命中该年级知识树时向任务注入年级知识点依据;不命中为空,不扰动现有弧线。"""
    hint = opening_hint(learner.get("answer_status"))
    task = {
        "学生": learner,
        "任务": ("先给出这道题的完整分步解 steps(每步一句 step + 该步数值/结果 value),"
                 "再按学生 answer_status 给首问 reply"),
        "输出要求": (
            "steps 每步只推进一个最小步骤,value 是该步算出的具体值;"
            "reply 是首问:correct 只问「还有没有不懂的地方」此轮不提讲一遍,"
            "incorrect 只采集学生现在认为的答案不评判,unanswered 引导从第一步开始。"
            "若题目带图:acceptable=true 当且仅当一张图片承载一道题(一道题内含多个小问、"
            "多幅小图、图表或选项都算一道;主体文字清晰可读即可)。"
            "你解不出、题干歧义、数据矛盾都不影响 acceptable;"
            "acceptable=false 仅当多道独立题目混在同一张图、图片模糊到无法辨认主体文字、或与题目无关;"
            "此时 transcription/reply/steps 可留空。纯文本题 acceptable=true、transcription 空。"),
    }
    grounding = grade_grounding(learner.get("grade", ""), question.get("knowledge_points"))
    if grounding:
        task["年级知识点依据"] = f"本年级({learner.get('grade', '')})可依据的知识点:{grounding}"
    context = _user_prompt(question, task)
    if hint:
        return {"role": "user", "content": f"{hint}\n{context}"}
    return {"role": "user", "content": context}


def _store_steps(session: LearnerSession, steps: list[dict]) -> list[dict]:
    """solver 职责(独立函数):校验分步解并存进 session.steps(阶梯底稿 + 数字校验基准)。

    只做确定性校验(步骤非空、每步有 step/value),不调模型;不校验通过则弃。
    """
    validated = [
        {"step": str(s.get("step") or "").strip(), "value": str(s.get("value") or "").strip()}
        for s in (steps or [])
        if isinstance(s, dict) and str(s.get("step") or "").strip() and str(s.get("value") or "").strip()
    ]
    session.steps = validated
    return validated


def _invoke(gateway: Gateway, role: str, messages: list[dict], schema: dict,
            session: LearnerSession, images: list[str] | None = None):
    return gateway.invoke(ModelRequest(
        role=role, messages=messages, response_schema=schema,
        session_id=session.session_id, max_tokens=800, temperature=0,
        images=images,
    ))


def _commit_turn(session: LearnerSession, student_message: str, assistant_text: str,
                 state: str, ready_to_confirm: bool = False) -> Turn:
    """三处 turn 提交尾部收敛(代喂/揭示/模型路径):append history×2 + version+1 +
    置态 + 返回 Turn(净减重复行,#113 P2 确定性路径收敛)。"""
    session.history.append({"role": "user", "content": student_message})
    session.history.append({"role": "assistant", "content": assistant_text})
    session.session_version += 1
    session.state = state
    return Turn(text=assistant_text, session_version=session.session_version,
                state=state, ready_to_confirm=ready_to_confirm, session=session)


def start(question: dict, learner: dict, *, gateway: Gateway | None = None) -> Turn:
    """生成首问(03 §4 Preparing → FirstQuestionReady / Failed)。

    任务包2步4 统一 open:一次调用产出 {acceptable, transcription, steps, reply}。
    - 因 tutor 即 VL 模型,vision 判定与首问合入同一次调用(图文题不再两次调用);
    - steps 由 _store_steps(独立 solver 职责)校验并存 session.steps;
    - reply 经护栏后即首问。
    fail-closed 语义保留:纯图题(question.text 为空)判 unacceptable → 不采信 reply/steps,
    Turn.state=failed。图文题(题库命中)判 unacceptable 仍降级纯文教学(题面文答是权威)。
    """
    gateway = gateway or default_gateway()
    session = LearnerSession(question=question, learner=learner)
    images = [str(question["image"])] if question.get("image") is not None else None
    open_messages = [
        {"role": "system", "content": system_prompt(learner.get("grade", ""))},
        _open_user_message(learner, question),
    ]
    payload = json.loads(_invoke(
        gateway, "tutor", open_messages, OPEN_SCHEMA, session, images=images,
    ).text)
    if not payload.get("acceptable", True) and not question.get("text"):
        # 纯图题无文字兜底:fail closed(与旧 vision 语义一致,不采信 reply/steps)
        session.state = "failed"
        return Turn(text=FAIL_CLOSED_TEXT, session_version=session.session_version,
                    state="failed", session=session)
    if not question.get("text") and payload.get("transcription"):
        # 纯图题:转写回填题面(新 dict,不改调用方入参)
        session.question = {**session.question, "text": str(payload["transcription"])}
    _store_steps(session, payload.get("steps") or [])  # solver 职责:阶梯底稿 + 校验基准
    ctx = _GuardContext(question=session.question, grade=learner.get("grade", ""),
                        gateway=gateway, role="tutor", messages=open_messages,
                        schema=OPEN_SCHEMA)
    safe_text = _guard_output(str(payload.get("reply") or ""), session, ctx)
    if not safe_text.strip():
        safe_text = _OPENING_FALLBACK  # 图文题 acceptable=false 且 reply 留空 → 确定性兜底首问
    session.state = "first_question_ready"
    session.first_question = safe_text
    return Turn(text=safe_text, session_version=session.session_version,
                state=session.state, ready_to_confirm=False,  # 首问恒非确认
                session=session)


def reply(session: LearnerSession, student_message: str, *,
          gateway: Gateway | None = None, expected_session_version: int | None = None) -> Turn:
    """多轮苏格拉底交流(03 §4 Dialogue 自旋;Conflict 为可选校验,#34 映射表决策)。"""
    if session.finished:
        raise TerminalStateError(f"会话已终态({session.state})")
    if expected_session_version is not None and expected_session_version != session.session_version:
        raise SessionVersionConflict(  # 不推进:旧版本不静默覆盖新一轮诊断(00 §5.2 约定 3)
            f"expected_session_version={expected_session_version} != 当前 {session.session_version}")
    if _student_signals_understanding(student_message):
        # 学生说「懂了」→ 直接请学生讲思路(确定性,不调模型),不 confirm、不报答案。
        # 这是教学弧线的固定策略(00 §8.5/人定):学生表示懂,就该由学生自己讲,而非 tutor 复述。
        session.guard_events.append({"branch": "elicit", "hint_level": session.hint_level})
        return _commit_turn(session, student_message, _ELICIT_TEMPLATE, "dialogue")
    if _student_signals_stuck(student_message):
        # 学生说「不会/猜不出」→ 揭示下一级阶梯(内容确定性,措辞交模型,代喂/无步骤兜底)。
        gateway = gateway or default_gateway()
        hint = _reveal_stuck_hint(session)
        session.stuck = True
        session.guard_events.append({"branch": "reveal", "hint_level": session.hint_level})
        return _commit_turn(session, student_message, hint, "dialogue")
    gateway = gateway or default_gateway()
    _reply_messages = [
        {"role": "system", "content": system_prompt(session.learner.get("grade", ""))},
        {"role": "user", "content": _user_prompt(_masked_question(session.question), {
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
                        schema=TUTOR_TURN_SCHEMA, student_message=student_message,
                        student_evidence=(tuple(
                            str(message["content"]) for message in session.history
                            if message.get("role") == "user"
                        ) + (student_message,)))
    # 复读自批评(self-refine):与上一轮 tutor 输出高度相似 → 打回重生成一次,仍复读才降级。
    prev = session.history[-1]["content"] if session.history else session.first_question
    if prev and _is_repeat(prev, output["reply"]):
        refined = _regenerate(ctx, session, output["reply"], _SELF_CRITIQUE)
        if refined is None or _is_repeat(prev, refined):
            refined = _contextual_fallback(session, "repeat", [], student_message)
            session.stuck = True  # 复读打断 = 卡点标记(R6 同款)
        output["reply"] = refined
    safe_text = _guard_output(output["reply"], session, ctx)
    if _feeds_method(safe_text):
        # 复讲轮代喂:换成固定"请学生讲"引导,并强制 ready_to_confirm=False——
        # 不关对话,继续收集学生的讲题内容(总结轮才由 finish 点名方法)。
        safe_text = _ELICIT_TEMPLATE
        output["ready_to_confirm"] = False
        session.stuck = True  # 代喂 = 未解决的教学质量问题(卡点标记,R6 同款)
    # 数字漂移守卫(抽取制 + 来源标签池,M2 闭环 #113/#34):抽取模型 reply 文本
    # 里的数字(排除"第N"序数),允许集 = 题面 ∪ steps 值 ∪ 学生历史数字 ∪
    # [终答:仅 ready_to_confirm 态];cited_numbers 自报集保留(影子对照)。
    cited = sorted({float(n) for n in (output.get("cited_numbers") or [])})
    extracted = _reply_numbers(str(output.get("reply") or ""))
    allowed, answer_pool = _drift_sources(
        session, student_message, bool(output.get("ready_to_confirm")))
    drift_violations = sorted(extracted - allowed)
    session.guard_events.append({
        "branch": "model",
        "cited": cited,
        "extracted": sorted(extracted),
        "violation_sources": [
            {"number": n, "source": ("answer" if n in answer_pool else "hallucinated")}
            for n in drift_violations
        ],
    })
    if drift_violations:
        session.stuck = True
    state = "ready_to_confirm" if output["ready_to_confirm"] else "dialogue"
    return _commit_turn(session, student_message, safe_text, state,
                        ready_to_confirm=bool(output["ready_to_confirm"]))


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
