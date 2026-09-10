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
        # 答案泄露防御(#146 M1,05 §5):回复前先承诺"本轮如何引导而不给答案"——
        # schema 经 json.dumps 进 prompt,字段声明顺序即生成顺序,排在 reply 之后等于没加。
        # 规划装置,不是验证装置:内容不进任何判定/守卫/报告/judge 输入,内核不读它
        # (cited_numbers 同为自报字段已实测虚报,reason 不重蹈自报歧途)。
        "reason": {"type": "string"},
        "reply": {"type": "string"},
        "ready_to_confirm": {"type": "boolean"},
        # 数字漂移守卫:模型自报本轮回复中引用的题目条件数字(服务端对题面校验)
        "cited_numbers": {"type": "array", "items": {"type": "number"}},
    },
    "required": ["reason", "reply", "ready_to_confirm", "cited_numbers"],
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
    "面积公式",  # #148 §5 实测从阶梯揭示句原样漏出(2026-09-10 按证据加词,只加词不改生成端)
)


def _mask_method_names(text: str) -> str:
    """复讲阶段方法名脱敏(确定性,零模型调用):方法名 → 「这种方法」。"""
    for token in _METHOD_TOKENS:
        text = text.replace(token, "这种方法")
    return text


def _mask_hit_tokens(text: str, tokens: list[str]) -> str:
    """只把**命中(学生尚未说出)**的方法词换成「这种方法」(确定性,零模型调用)。

    #165 WS4「守卫替换粒度」的末位确定性手段:重生成失败时也不整轮换模板——保留本轮
    引导/确认语义,只把不该点名的词隐去;学生已说出的词不动(弧线允许的点名保持原样)。
    词表内无互为子串的词(无「公分母/分母」这类),故一次替换即可清空命中。
    """
    for token in tokens:
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


def _feeds_method_hits(text: str, student_evidence: tuple[str, ...] = ()) -> list[str]:
    """tutor 输出里点名的方法词中,学生尚未自己说出的那部分(代喂命中,埋点用)。

    #157 裁定 1(#148 §6.3 误伤根因):弧线允许的「学生已说 → 教师复述定名」不算
    代喂——仅「学生尚未说出」的方法词才算;判定不放宽、词表不删,只是把已说词
    从命中里剔除(宽表窄记,埋点 rule_ids 精确到未说词)。student_evidence 含当轮
    学生消息(与泄露护栏的 student_evidence 同源,零新增模型调用)。
    """
    said = "".join(student_evidence)
    return [token for token in _METHOD_TOKENS if token in text and token not in said]


def _feeds_method(text: str, student_evidence: tuple[str, ...] = ()) -> bool:
    """tutor 输出里点名了方法(代喂):学生还没自己讲,tutor 不该报方法名。"""
    return bool(_feeds_method_hits(text, student_evidence))


def _student_signals_understanding(student_message: str) -> bool:
    """学生表示「懂了/明白了」——教学弧线里这是「请学生讲思路」的触发点。

    「会了」用负向断言 (?<!不),避免「我不会了」(卡住)被误判为「懂了」;「懂了」
    「明白了」同款负向断言,避免「越来越不懂了/我不明白了」(卡住)被误判为「懂了」。"""
    return bool(re.search(r"都懂了|(?<!不)懂了|(?<!不)明白了|没有不懂|(?<!不)会了|没问题|都明白|没疑问", student_message))


def _student_signals_stuck(student_message: str) -> bool:
    """学生表示「不会/猜不出」——这是「揭示下一级阶梯」的触发点(治 tutor 复读探针)。

    「不会吧」后接疑问/感叹标点(?!/?/!)是反诘惊讶(「不会吧?!这也能算对?」),不判卡住;
    单纯「不会吧」仍判卡住;「越来越不懂」补上「不懂了」类卡壳(不被「懂了」误吞)。
    #157 评审补第一人称卡壳缺口(实测漏检):「还不知道」(「还」隔断了「我不知道」)、
    裸「我不会」「不明白」「不会算」「还不会」——这类轮次误走模型路径 = 泄露+方差双来源;
    「我不会(?!吧)」保留「我不会吧?!」的反诘语义;「明白了」归理解侧,先于本判据。"""
    return bool(re.search(r"我不太会|我猜不出|我猜不出来|我不知道|我想不出|我想不出来|我不会做|我不会了|不会吧(?![?!？])|太难了|没思路|越来越不懂", student_message))


# 中文数字单字映射(仅学生口述侧:「八分之七」这类说法没有 ASCII 数字)。
# 只映射单字、不解析复合(「十五」→ 10/5 而非 15)——宁漏勿误:漏 → 走模型路径(现状
# 行为);误 → 在不该请复讲时请复讲。参考答案侧不映射(题库答案均为 ASCII 写法,
# 「两直线平行」类文字答案无 ASCII 数字可对,保持不可判定 → 模型路径)。
_CJK_NUMERALS = {"零": 0.0, "〇": 0.0, "一": 1.0, "二": 2.0, "两": 2.0, "三": 3.0,
                 "四": 4.0, "五": 5.0, "六": 6.0, "七": 7.0, "八": 8.0, "九": 9.0,
                 "十": 10.0, "百": 100.0, "千": 1000.0, "万": 10000.0}


def _spoken_numbers(text: str) -> set[float]:
    """学生口述数字全集:ASCII 数字 ∪ 出现的中文数字单字。"""
    return _question_numbers(text) | {
        value for char, value in _CJK_NUMERALS.items() if char in (text or "")}


def _known_answer(session: "LearnerSession") -> str:
    """已知终答文本:question.answer 优先,空则阶梯末级 value(与 _reveal_stuck_hint/
    _drift_sources 同源,三处判定基线一致)。"""
    answer = str(session.question.get("answer") or "").strip()
    if not answer and session.steps:
        answer = str(session.steps[-1].get("value") or "").strip()
    return answer


def _student_hits_known_answer(session: "LearnerSession", student_message: str) -> bool:
    """incorrect 弧线:学生陈述命中已知答案(#112 触发判据,可复算、零文本相似度)。

    匹配 = 已知答案的**结论数字**(`_answer_focus_numbers`:答案数字 − 题面已给数字)
    都出现在学生本轮消息里(数字集包含;学生侧含中文数字单字)。不要求字面/顺序——
    「兔5只、鸡3只」同样命中「鸡3只,兔5只」。
    误触护栏(③ 为一组):① 仅 answer_status=incorrect(correct/unanswered/unknown
    路径零改动);② 非确认态;③ 此前未见过学生消息(incorrect 弧线首轮是学生当前
    (错误)答案的采集,数字撞集不算命中——鸡兔同笼典型错答恰是数字对调)、此前从未
    请过复讲(guard_events 有 elicit 埋点)、上一条 tutor 消息不是复讲引导(本轮消息
    即复讲内容,或代喂兜底刚换出的引导)——否则会对复讲内容再次请复讲,循环。"""
    if session.learner.get("answer_status") != "incorrect":
        return False
    if session.state == "ready_to_confirm":
        return False
    prev = session.history[-1]["content"] if session.history else session.first_question
    if (not any(message.get("role") == "user" for message in session.history)
            or any(event.get("branch") == "elicit" for event in session.guard_events)
            or prev == _ELICIT_TEMPLATE):
        return False
    return _hits_answer_numbers(session, student_message)


def _answer_numbers(session: "LearnerSession") -> set[float]:
    """已知答案里的 ASCII 数字集(#149 判据底座):空集 = 无法确定性判定 → fail-open。"""
    return _question_numbers(_known_answer(session))


def _answer_focus_numbers(session: "LearnerSession") -> set[float]:
    """答案数字里**剔除题面已给数字**后的结论数字(#165 WS4 守卫粒度)。

    实测(#152 / 夜评 run 34502985698):chicken_rabbit 的阶梯末级 value 是**算式**
    「8 - 5 = 3」→ 答案数字 {3,5,8},其中 8 是题面给定的总数;学生末轮
    「所以兔有10除以2等于5只,鸡有3只,检查…」**永远不会再复述题面数字** →
    「学生是否已陈述终答」恒 False → 判停闸在学生已说出终答的末轮误触发,确认句被
    换走 + 强制不确认 → needs_review(实测把 equation/chicken_rabbit 这类收束轮压分)。
    剔掉题面数字后,判据只要求说出**答案里真正新增的结论数字**;
    兜底:剔完为空(答案数字全在题面里)→ 退回原集,不放行任何判定(fail-closed)。

    注意与 `_answer_numbers` 的分工(两处口径不同,各有依据):
    - **漂移池**(`_drift_sources`)用全量 `_answer_numbers`——凡能泄露答案的数字都算;
    - **「是否已陈述」判据**(本函数)用结论数字——不逼学生复述题面给定的数。
    """
    numbers = _answer_numbers(session)
    given = _question_numbers(str(session.question.get("text") or ""))
    return (numbers - given) or numbers


def _hits_numbers(numbers: set[float], text: str) -> bool:
    """判据核心(唯一实现):「数字集非空且全部出现在 text 里」(顺序不敏感)。

    fail-open:数字集为空(答案取不到数字,如文字/字母类答案)→ False(不命中、不触发),
    沿用 #112 既有 `if not answer_numbers: return False` 语义。text 计数含中文数字单字。
    """
    if not numbers:
        return False
    return numbers <= _spoken_numbers(text)


def _hits_answer_numbers(session: "LearnerSession", text: str) -> bool:
    """确定性判据核心(#149 抽核,#112 触发与判停闸**共用同一套**,禁止出现第二套判据):
    「已知答案的结论数字全部出现在 text 里」(数字集包含,顺序不敏感;学生侧计入中文数字
    单字)。不要求字面/顺序——「兔5只、鸡3只」同样命中「鸡3只,兔5只」;题面已给的数字
    不算答案(见 `_answer_focus_numbers`)。"""
    return _hits_numbers(_answer_focus_numbers(session), text)



def _student_stated_answer(session: "LearnerSession", student_message: str) -> bool:
    """学生侧是否陈述过命中已知答案的结论数字集(判停闸判据;跨 answer_status 共用核心)。

    **逐条学生消息独立判定**(不取整段历史的数字并集):跨轮各说一半数字不算「陈述过
    答案」——与 #112「单条消息数字集包含」同源,避免把分散数字误当结论而放行判停。
    用 `_answer_focus_numbers`(结论数字):学生在收束轮复述结论即可,不要求复述题面
    给定的数字(#152 实测:算式型阶梯末级「8 - 5 = 3」曾让已说出终答的末轮恒判未陈述)。
    不预设例外(如「学生说懂了也放行」):证据驱动,实测出现再加(#149 PM 口径)。"""
    messages = [str(message.get("content") or "") for message in session.history
                if message.get("role") == "user"]
    messages.append(student_message)
    return any(_hits_answer_numbers(session, text) for text in messages)


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
    """学生卡住/复读兜底 → 揭示下一级阶梯(确定性,零模型调用,不重复)。

    内容 = session.steps 下一级;开场用 _STEP_LEADS 轮换,避免固定前缀生硬。
    模型措辞版实测会重复(3/7)且过度揭示,故仍用确定性。

    埋点(#112 评审建议):三条调用方(卡壳揭示 / 复读降级 / 输出面背板)统一在此记
    `{branch: reveal, hint_level}`,hint_level 为消耗后的级数——记的是**阶梯消耗**
    (阶梯有限,影子数据要能看「推进次数」与「是否过早烧到 bottom-out」);该轮最终
    学生可见文本若又被下游护栏替换,以 transcript 为准。bottom-out 与普通推进同记
    reveal(事件形状不变);bottom-out 率按确定性文本匹配统计(「这一步我们直接看结果:」
    / NEEDS_REVIEW_TEXT),与复讲引导按 _ELICIT_TEMPLATE 文本统计同口径。"""
    step = _next_step(session)
    session.guard_events.append({"branch": "reveal", "hint_level": session.hint_level})
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
    """数字来源标签池(M2 闭环 #113/#34 + #157 评审末值边界):允许集 =
    题面 ∪ (steps 值 − 终答数字) ∪ 学生历史数字 ∪ [终答数字:仅 ready_to_confirm 态并入]。

    终答数字按**值**从 steps 无条件允许集剥离(#157 评审:模型自报阶梯含末值=答案,
    整段照抄演算会 violations=[] 洗白——"自报进白名单"与 cited_numbers 同病);
    按值而非按位置(steps[:-1]):阶梯末级未必是答案(题库 16/10 阶梯答案 3/5),
    按位置会把诚实的末级中间值误伤,按值只锁真正要保护的答案数字。

    返回 (允许集, 终答数字池)。终答数字在非确认态单独成池、不入允许集,供违规
    来源标签判定:违规数字若在终答池 → 标签 "answer"(对话态提前说终答),否则
    "hallucinated"(无任何合法来源)。学生历史数字无条件放行(学生自己说过的不算喂)。"""
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
    answer = _answer_numbers(session)  # #156 统一判据底座:answer 优先,阶梯末级兜底
    allowed = face | (steps - answer) | student | (answer if ready_to_confirm else set())
    return allowed, answer


# 复读自批评(业界 self-refine:把 tutor 自己上一条当反面证据喂回;任务包2步3)
_SELF_CRITIQUE = (
    "你上一轮已经这样问过,学生仍说不会/没答上来。别重复这个问点:"
    "要么把这一步拆小,并直接给出这一步的具体数值结果(照题面给,如「这一步先算…得到…」),"
    "让他接着算下一步;要么换一个更小的问点。"
)

# 判停闸重写指令(#149,走既有 _regenerate = judge→refiner 的 refiner 路径):
# 这是**给模型的指令**,不是学生可见模板(不新增模板);不删词、不做解析脱敏。
_PREMATURE_CONFIRM_CRITIQUE = (
    "学生还没有自己说出这道题的答案。此轮不能确认收尾:不要置 ready_to_confirm、"
    "不要说结论性数值(终答与等价改写都不行),也不要替学生把答案讲完。"
    "改成按教学弧线继续推进:顺着学生刚说的这一步,问一个更小的问题,让他自己往下算。"
)

# 代喂命中重写指令(#152 follow-up / #165 WS4「守卫替换粒度」):一次方法词命中
# **不再整轮换成复讲模板**——那会连本轮的引导/确认语义一起丢掉,并强制不确认,
# 把「学生已说出答案、本该收束」的末轮推向 needs_review(实测 12 分场景压到 3 分)。
# 这是**给模型的指令**(沿用既有 _regenerate 路径,不新增学生可见模板)。
_FEEDS_METHOD_CRITIQUE = (
    "这一轮不要说出方法名/术语(如「等式性质」「通分」「假设法」这类词的名称),"
    "也不要说出答案数字。保留这一轮原有的作用(该引导就继续引导、该确认就确认),"
    "只是不要替学生把方法的名字点出来——用学生已经说过的话来推进,重写这一轮回复。"
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
    # 泄露护栏的答案对照基线(#149):由 `_known_answer(session)` 填入(question.answer
    # 优先、steps 末值兜底)。此前直接读 question["answer"],评测侧 question 只传
    # {"text": ...} → 永远"无答案模式",护栏拿不到基准;统一基线后评测帧护栏也能生效。
    answer_reference: str = ""
    images: list[str] | None = None
    student_message: str | None = None
    student_evidence: tuple[str, ...] = ()  # 学生历史 user 消息(泄露护栏对照:已说答案可复述)


def _guard_check(ctx: "_GuardContext", text: str) -> tuple[str | None, list[str], str | None]:
    """三护栏(泄露/语气/格式)逐个过;返回 (guard_or_None, rule_ids, normalized_or_downgrade)。"""
    leak = evaluate_student_visible_question(
        text,
        # #149:答案基线统一走 _known_answer(answer 优先、steps 末值兜底);
        # ctx 未带基线(旧调用方)时退回 question["answer"],行为与改动前一致。
        answer_reference=ctx.answer_reference or str(ctx.question.get("answer") or ""),
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
                  original: str, regenerated: bool, mode: str | None = None) -> None:
    """护栏埋点。`mode`(可选,additive)记处置路径:regenerated / masked / template
    ——度量侧要区分「重生成修好」与「确定性脱敏」两类处置(#165 WS4 替换粒度)。"""
    if session is not None:
        event = {"guard": guard, "rule_ids": rule_ids,
                 "original": original, "regenerated": regenerated}
        if mode is not None:
            event["mode"] = mode
        session.guard_events.append(event)
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
        and not ctx.answer_reference.strip()  # #149:与护栏答案基线同源(此前读 question["answer"])
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


def _ask_restatement(session: LearnerSession, student_message: str) -> Turn:
    """确定性请学生从头复讲(理解信号/答案命中共用):零模型调用,不 confirm、不报答案,
    埋点 {branch: elicit, hint_level}——一次会话至多一次(供答案命中触发防循环判定)。"""
    session.guard_events.append({"branch": "elicit", "hint_level": session.hint_level})
    return _commit_turn(session, student_message, _ELICIT_TEMPLATE, "dialogue")


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
                        schema=OPEN_SCHEMA, answer_reference=_known_answer(session))
    safe_text = _guard_output(str(payload.get("reply") or ""), session, ctx)
    if not safe_text.strip():
        safe_text = _OPENING_FALLBACK  # 图文题 acceptable=false 且 reply 留空 → 确定性兜底首问
    session.state = "first_question_ready"
    session.first_question = safe_text
    return Turn(text=safe_text, session_version=session.session_version,
                state=session.state, ready_to_confirm=False,  # 首问恒非确认
                session=session)


def _gate_premature_confirm(session: LearnerSession, ctx: "_GuardContext", output: dict,
                            safe_text: str, student_message: str) -> str:
    """判停闸(#149):模型想判停,但学生尚未陈述已知答案 → 闸下并重写。

    `ready_to_confirm` 只是**模型建议**,判停权威在确定性验证层(#112 同源判据,
    见 `_hits_answer_numbers`)。缺口实测:incorrect 弧线第 3 轮学生尚未说出答案,
    模型已置 ready_to_confirm 并把答案讲完,而判停语义(kernel_subject.py 的
    ready_to_confirm break)随即结束对话 → 复讲步/后续步骤永远到不了。
    处置走既有 `_regenerate`(judge→refiner 的 refiner):不新增学生可见模板、不删词、
    不做解析脱敏;重写失败落既有阶梯兜底 + stuck。fail-open:答案无数字时不闸。

    返回学生可见文本(闸未触发时原样返回)。"""
    if not (output.get("ready_to_confirm") and _answer_numbers(session)
            and not _student_stated_answer(session, student_message)):
        return safe_text
    _record_event(session, "premature_confirm", [], str(output.get("reply") or ""),
                  regenerated=False)
    refined = _regenerate(ctx, session, safe_text, _PREMATURE_CONFIRM_CRITIQUE)
    if refined is None:
        refined = _reveal_stuck_hint(session)
        session.stuck = True
    output["reply"] = refined
    output["ready_to_confirm"] = False
    return refined


def _repair_feeds_method(ctx: "_GuardContext", session: LearnerSession, text: str,
                         hits: list[str]) -> tuple[str, str]:
    """代喂命中的处置(#165 WS4「守卫替换粒度」):重生成 → 脱敏 → 模板兜底。

    返回 `(学生可见文本, 处置路径)`;路径取值 `regenerated` / `masked` / `template`,
    落 `guard_events[].mode` 供度量区分。原实现一律整轮换成复讲模板,连本轮引导/确认
    语义一并丢掉(并强制不确认)→ 学生已说出终答的末轮被推成 needs_review。
    不变量的最后一道:任何路径下学生可见文本都不含未说出的方法词。
    """
    regenerated = _regenerate(ctx, session, text, _FEEDS_METHOD_CRITIQUE)
    if regenerated is not None and not _feeds_method_hits(regenerated, ctx.student_evidence):
        return regenerated, "regenerated"
    masked = _mask_hit_tokens(text, hits)
    if not _feeds_method_hits(masked, ctx.student_evidence):
        return masked, "masked"
    return _ELICIT_TEMPLATE, "template"  # 兜底:词表无互为子串项,脱敏理论上必清空命中


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
        return _ask_restatement(session, student_message)
    if _student_signals_stuck(student_message):
        # 学生说「不会/猜不出」→ 揭示下一级阶梯(内容确定性,措辞交模型,代喂/无步骤兜底)。
        gateway = gateway or default_gateway()
        hint = _reveal_stuck_hint(session)  # 埋点在 _reveal_stuck_hint 内统一记(#112 评审)
        session.stuck = True
        return _commit_turn(session, student_message, hint, "dialogue")
    if _student_hits_known_answer(session, student_message):
        # incorrect 弧线:学生被纠错后说出已知答案 → 同样确定性请他从头复讲(#112:
        # 交给模型会直接置 ready_to_confirm 从模型侧确认,复讲步落空——issue 实测
        # 复讲未达成 3/4 的根因)。人定弧线「答对后学生复讲,讲完讲师才点名方法」。
        return _ask_restatement(session, student_message)
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
                        answer_reference=_known_answer(session),
                        student_evidence=(tuple(
                            str(message["content"]) for message in session.history
                            if message.get("role") == "user"
                        ) + (student_message,)))
    # 复读自批评(self-refine):与上一轮 tutor 输出高度相似 → 打回重生成一次,仍复读才降级。
    prev = session.history[-1]["content"] if session.history else session.first_question
    if prev and _is_repeat(prev, output["reply"]):
        refined = _regenerate(ctx, session, output["reply"], _SELF_CRITIQUE)
        if refined is None or _is_repeat(prev, refined):
            # 复读仍未破 → 阶梯推进替代同款问句兜底(#112 复读循环:旧兜底「先回到你
            # 刚说的…」以同句反复,自身成为复读源头;实测 chicken_rabbit/triangle_area
            # 9 轮不推进)。揭示下一级阶梯 = 每轮内容不同且推进教学,阶梯耗尽走
            # bottom-out(终答仅该路径披露,不变量保持)。
            refined = _reveal_stuck_hint(session)
            session.stuck = True  # 复读打断 = 卡点标记(R6 同款)
        output["reply"] = refined
    safe_text = _guard_output(output["reply"], session, ctx)
    method_hits = _feeds_method_hits(safe_text, ctx.student_evidence)
    if method_hits:
        # 复讲轮代喂(仅「学生尚未说出」的方法词,#157 裁定 1)。**替换粒度**(#152
        # follow-up / #165 WS4):命中 ≠ 整轮作废——先带指令重生成(保留本轮引导/确认
        # 语义),失败再确定性脱敏(只隐去命中词),模板仅末位兜底。埋点补齐(#112):
        # 记被换下的原文 + 命中词 + 处置路径 mode(护栏重生成 vs 解析脱敏对照口径)。
        repaired, mode = _repair_feeds_method(ctx, session, safe_text, method_hits)
        _record_event(session, "feeds_method", method_hits, safe_text,
                      regenerated=(mode != "template"), mode=mode)
        safe_text = repaired
        if not _student_stated_answer(session, student_message):
            # 学生尚未说出终答 → 不关对话,继续收集学生的讲题内容(原语义)。
            # 学生**已陈述终答**的末轮不再强制不确认:一次方法词命中不该把本该收束的
            # 轮次推向 needs_review(#152 实测把 12 分场景压到 3 分)。
            output["ready_to_confirm"] = False
    if prev and safe_text == prev:
        # 输出面防复读(#112 终极不变量,精确等值——不吞正当的相近推进):任何兜底
        # (护栏兜底/复读自批评降级/代喂替换)的产出若与上一轮学生可见文本完全相同,
        # 即同句复读 → 阶梯推进给新内容。复读探针实测(修复前):同句兜底可连发
        # 8 轮——泄露兜底「先回到你刚说的…」×8、代喂替换复讲引导 ×8,9 轮零推进。
        safe_text = _reveal_stuck_hint(session)
        output["reply"] = safe_text
        output["ready_to_confirm"] = False
        session.stuck = True
    # 判停闸(#149):模型建议的 ready_to_confirm 需过确定性校验,见 _gate_premature_confirm
    safe_text = _gate_premature_confirm(session, ctx, output, safe_text, student_message)
    # 数字漂移守卫(抽取制 + 来源标签池,M2 闭环 #113/#34):抽取模型 reply 文本
    # 里的数字(排除"第N"序数),允许集 = 题面 ∪ (steps 值 − 终答数字) ∪ 学生历史
    # 数字 ∪ [终答:仅 ready_to_confirm 态](#157 评审末值边界);cited_numbers
    # 自报集保留(影子对照)。
    # 判停闸在前:被闸下的轮次按非确认态取池,提前说出的终答数字即标 "answer" 违规。
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
