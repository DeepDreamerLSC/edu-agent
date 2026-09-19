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
from dataclasses import dataclass, field

from edu_agent.gateway import Gateway, ModelRequest, default_gateway

from .format_guard import _DOWNGRADE_PROMPT, evaluate_student_visible_format
from .guardrails import evaluate_student_visible_question
from .numeric import (_ASCII_NUMBER, _answer_focus_numbers, _answer_numbers, _drift_sources,
                      _known_answer, _question_numbers, _reply_numbers, _spoken_numbers)
from .prompting import (ASK_FINAL_ANSWER, OPEN_SCHEMA, TUTOR_SUMMARY_SCHEMA,
                        TUTOR_TURN_SCHEMA, _FEEDS_METHOD_CRITIQUE,
                        _GUARD_REJECTION_HIT_TEMPLATE, _GUARD_REJECTION_NUMBERS_TEMPLATE,
                        _PREMATURE_CONFIRM_CRITIQUE, _SELF_CRITIQUE, _user_prompt,
                        diagnose_turn_hint, first_question_text, grade_grounding, opening_hint,
                        summary_system_prompt, system_prompt)
from .session import LearnerSession, SessionVersionConflict, Summary, TerminalStateError, Turn
from .tone_guardrails import apply_tone_guardrail

# grammar 真强制(llama-server)下模型只可能产出符合 schema 的 JSON;
# #54 后 gateway.text 即已验证内容,直接 json.loads。
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
# 措辞(#179 问题 3 修法):不说掌握(「你已经懂了」是预设掌握,生产 3 段逐字复现过
# 自相矛盾:先称懂又要重讲),只说动作——请从头讲思路。
_ELICIT_TEMPLATE = ("我们从头把思路串一遍——"
                    "先说说你第一步算了什么、为什么这样算。")

# 卡壳支持拆小问句(#198 确定性文本;提取为常量供 GEPA 双旋钮 seam 注入,行为零变化)
_SUPPORT_HINT = ("我们把这一步拆小:先不想整道题,你只看这一步里最小的一个数,"
                "从它开始你觉得能先算出什么?想到多少说多少。")

# === 消融臂门控(伴生模块 ablation.py;C=生产默认不注入,#333 三臂协议) ===
from .ablation import (arm_bypass as _arm_bypass, arm_b_leak_funnel as _arm_b_leak_funnel,
                       current_arm as _current_arm, guard_early as _ablation_guard_early,
                       mech_off as _mech_off,  # 二阶段 LOO 门控查询(phase2 协议 §2)
                       set_ablation_arm as set_ablation_arm,  # 02 §6 白名单 re-export
                       shadow_event as _shadow_event)


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
    r"""学生表示「不会/猜不出」——支持动作选择(`_support_move`)的触发点(治复读探针)。

    现行口径(#198 检测器覆盖轮,按 D 卡 1 八形态扩表;每步都过 11/11 基线):
    我不太会/我猜不出(来)/想不出/我不会(裸,「我不会吧」反诘仍不判)/不会吧(后接
    ?/! 是反诘不判,单纯「不会吧」仍判)/有点不会/怎么…不会/看不懂/还是不会/太难了/
    没思路/越来越不懂;「不知道」带前置守卫 `(?<![还但])`——「还/但不知道」是进展后
    局部卡点(stability_20:t1「我还不知道怎么同时算两种动物」实测走模型路径更优,
    306de47 教训:该形态进表曾把评测打红),裸/被其他字隔断的「不知道」判卡住。
    #178 实锤补丁(终版裁定 c5661449950):「不知道」后随**量问对象**(多少/几,如
    「每一格不知道多少米」)是对「不知道什么」的实质作答——答出了未知量的对象与单位,
    不整回合短路,走模型路径(负向先行 `(?!\s*[多几])`,与前守卫同口径:只封局部
    形态;量问两字是封闭类,非前缀词表扩展)。整句/全局性「不知道」(裸/我完全不知道
    怎么做)仍判卡住。「明白了」归理解侧先判;八形态清单与 11/11 零翻转对照见
    tests/teaching/test_kernel_invariants.py 参数表(#198 B 线)。"""
    return bool(re.search(r"我不太会|我猜不出|(?<![还但])不知道(?!\s*[多几])|想不出|我不会(?!吧)|有点不会|怎么.{0,3}不会|看不懂|还是不会|不会吧(?![?!？])|太难了|没思路|越来越不懂", student_message))


def _student_signals_completion(student_message: str) -> bool:
    """学生宣称完成(「我算出来了」)——完成表达盲区(#178 判停分析)的采集端触发点。

    实录集(生产导出逐字,审查补扫 +1 形态):算出来了/算好了/算完了/得出(最终)答案/
    得出结果/做完了/解出来了。负例天然安全:「算不出来了/没算出来/没算完」不含子串
    (否定词插中间)。完成 ≠ 理解:不触发复讲(复讲在确认后),只追问答案数字——盲区
    实测 8/8 模型路径没有一次干净追问,判停闸无料可判。带答案数字的完成表达走答案
    命中分支(先判)。"""
    return bool(re.search(r"算出来了|算好了|算完了|得出(最终)?(答案|结果)|做完了|解出来了", student_message))


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


# 支持动作(#198 第一步,MathDial teacher moves 分类学——采用,不发明):guiding_focus =
# Focus · Guiding Student Focus,只问不揭示;#174 渐隐档折叠至此——触发源由
# scaffold_faded 状态位改为就地判定「上一学生轮把刚揭示的那一步自己做出来了」
# (判据:该步 value 数字全出现在消息里,数字集包含、顺序不敏感、含中文数字单字,
# hint_level=0 恒不触发,fail-closed;粘滞跨轮语义随状态位删除,只认最近一条)。
# telling = Telling 揭示族:下一级阶梯,耗尽即既有 bottom-out(设计内,不动)。
# 轮 1「拆小」/轮 2「换数字」的 streak 触发源在检测器覆盖轮之后接入本选择函数
# (#198 后续顺序:净减回血 → 检测器覆盖 → 轮 1)。
def _support_move(session: "LearnerSession") -> str:
    """卡住支持动作的**确定性选择函数**(#198;零模型、可复算、可进回归网)。"""
    prev_student = session.history[-2]["content"] if len(session.history) >= 2 else ""
    numbers = (_question_numbers(str(session.steps[session.hint_level - 1].get("value") or ""))
               if 0 < session.hint_level <= len(session.steps) else set())
    return "guiding_focus" if numbers and numbers <= _spoken_numbers(prev_student) else "telling"


def _stuck_hint(session: "LearnerSession") -> str:
    """卡住支持动作执行(#198:枚举 + 确定性选择,取代渐隐/揭示双分支)。guiding_focus →
    拆小问句(只问不揭示、不含数字、不消耗阶梯;埋点 {branch: support, move},#169 起
    随轮提交补 turn);telling → `_reveal_stuck_hint`(下一级/耗尽 bottom-out,口径同 #185)。"""
    if _support_move(session) == "guiding_focus":
        session.guard_events.append({"branch": "support", "move": "guiding_focus"})
        return _SUPPORT_HINT
    return _reveal_stuck_hint(session)


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

# 揭示句里**算式结果**的识别(「10 × 6 = 60」「26-16=10」「10 ÷ 2 = 5」):命中即把结果段收回去
# (#165 WS4 第 2 条「揭示内容不那么直给」)。只认**含运算符且带等号结果**的片段——
# 单纯出现数字(如「8只鸡」)不动,避免连题干条件一起吃掉。
_STEP_ARITHMETIC_RE = re.compile(
    r"\d+(?:\.\d+)?(?:\s*[×x*÷/+＋－-]\s*\d+(?:\.\d+)?)+\s*=\s*\d+(?:\.\d+)?")

# 「几」改写的形状边界(#185 复审 ②):命中数字**前后都不是揭示框架词**且后随
# 汉字(「5只」「第13次」「5 记下来」)才读得成句;裸数字形状(「得到 5」「0.8
# 就是答案」)不改写,整步走通用兜底。
# ponytail: 启发式词表,读不成句的新形状实测出现再收。
_DISCLOSURE_WORDS = ("得到", "结果是", "等于", "就是", "是", "即", "为")


def _answer_leak_span(text: str, answer_numbers: frozenset[float]) -> tuple[int, int] | None:
    """step 文本里最早的答案数字段(序数「第13次」/导出值「得到 0.8」);空集不拦。
    定位用裸数字段,**刻意不走** `_reply_numbers`——它把「第13次」当序数剥掉,
    看不见这条泄漏(#185 取证:网抓得到、内核看不见)。"""
    for match in _ASCII_NUMBER.finditer(text):
        if float(match.group()) in answer_numbers:
            return match.span()
    return None


def _mask_answer_numbers(text: str, answer_numbers: frozenset[float]) -> str | None:
    """**全部**命中数字逐个改写成「几」(#185 复审 ①:只掩首处会残留同句后文);
    任一命中是裸数字形状(读不成句)→ None,调用方走通用兜底。"""
    out, last = [], 0
    for match in _ASCII_NUMBER.finditer(text):
        if float(match.group()) not in answer_numbers:
            continue
        rest, before = text[match.end():].lstrip(), text[:match.start()].rstrip()
        if (not rest or not "\u4e00" <= rest[0] <= "\u9fff"
                or rest.startswith(_DISCLOSURE_WORDS) or before.endswith(_DISCLOSURE_WORDS)):
            return None
        out += [text[last:match.start()], "几"]
        last = match.end()
    return "".join(out + [text[last:]])


def _cut_before(text: str, start: int) -> str | None:
    """start 前最后一个分句边界截断;切不出合格动作段(无边界/过短/仅序号)→ None。"""
    head = max((text.rfind(sep, 0, start) for sep in "，,、:：;；"), default=-1)
    if head < 0:
        return None
    softened = text[:head].strip()
    if len(softened) < 4 or re.fullmatch(r"第?\s*[0-9一二三四五六七八九十]+\s*步?", softened):
        return None
    return softened


def _soften_step_text(step_text: str, answer_numbers: frozenset[float]) -> tuple[str | None, str]:
    """阶梯揭示的**动作化**改写:把该步算好的结果收回去,只留动作与依据(#165 WS4:
    规划句原样给出=把结果算给学生)。返回 (改写文本, 路径 tag):cut = 按结果前最后
    一个分句边界收回(宁可直给不出残句,#148 §6.1);mask = 全部命中改写「几」;
    none = 未改写;裸数字读不成句返回 (None, "none") → 调用方整步弃用。#185 补洞:
    序数/导出值形态判据=`_answer_focus_numbers`(答案−题面,空集退回全集 fail-closed);
    tag 仅供网级报数(#241)。细节(#164/#148/#185 实测记录)见 git 史。"""
    text = str(step_text or "").strip()
    if _mech_off("soften_step"):  # 二阶段 LOO:动作化关 → 步文本原文直出
        return text, "off"
    match = _STEP_ARITHMETIC_RE.search(text)
    if match is not None:
        cut = _cut_before(text, match.start())
        return (cut or text, "cut" if cut else "none")
    span = _answer_leak_span(text, answer_numbers)
    if span is None:
        return text, "none"
    cut = _cut_before(text, span[0])
    if cut is not None:
        return cut, "cut"
    masked = _mask_answer_numbers(text, answer_numbers)
    return masked, "mask" if masked else "none"


_THOUSANDS_RE = re.compile(r"(?<=\d),(?=\d\d\d(?:\D|$))")


def _current_step_anchor_numbers(session: "LearnerSession", step: dict) -> set[float]:
    """泄露网 V1(#333 裁定 c5717512971):当前步的**可授权中间值锚**。

    anchor = numbers(step.value) − answer_pool,且**无双重身份**:value 数字与
    answer_pool 任一重叠 → 整步禁(返回空集,fail-closed)——单步题(value=终答)、
    多部件答案、末级步(value 即终答)天然落禁面。answer_pool 用全量终答数字
    (question.answer 优先/steps 末值兜底,同 `_known_answer`);
    **勿用 `_answer_focus_numbers` 做锚减法**——focus 剔题面数是「已陈述」判据口径,
    不是保护面(题面数不减:授权面含题面数无害,保护面一个都不能少)。

    数字等价类定夺(v1-property-supplement,#333):
    - **千分位归一(补)**:「1,000」与「1000」双侧同口径归一后比对——不归一则
      answer「1,000」池={1,0} 而 value「1000」={1000} 交空 → 锚漏终答(真漏 vector)。
      kernel 侧归一,numeric.py 归因不动(Q7);漂移池 `_answer_numbers` 口径独立不受影响。
    - **单数值门槛(补)**:value 提取后非恰一个数字 → 禁(分数「3/4」={3,4}、
      「8组,余5人」={8,5} 等多位值渲染成「得到 3、4」破相;保守方向)。保护面不受影响
      (pool 仍全量多部件)。
    - **百分号(不补)**:「50%」→{50} 双侧一致,overlap 保护成立;渲染丢 % 由动作
      文本语境承接。
    - **负数(不补)**:符号双侧一致剔除 = 保守正确(「-5」与「5」撞池即禁);
      补符号解析反开「-5≠5 可锚」的漏洞面。

    七条件收敛(裁定原文):stuck × telling 由调用方结构保证(`_reveal_stuck_hint`
    只从 `_stuck_hint` 的 telling 分支到达);next step 存在由调用方 step 非 None;
    hint_level>0 / state≠ready_to_confirm 同由调用方判定——本函数只管数字面:
    value 非空、anchor 非空、∩answer_pool=∅。纯函数:只读 step 与 session 的
    question/steps,不知道 stuck/telling/hint_level(Q7:归因不进 numeric.py)。"""
    value_numbers = _question_numbers(_THOUSANDS_RE.sub("", str(step.get("value") or "")))
    pool = _question_numbers(_THOUSANDS_RE.sub("", _known_answer(session)))
    if len(value_numbers) != 1 or value_numbers & pool:
        return set()
    return value_numbers


def _reveal_stuck_hint(session: "LearnerSession") -> str:
    """学生卡住/复读兜底 → 揭示下一级阶梯(确定性,零模型,不重复;动作化见
    _soften_step_text)。泄露网 V1 窄授权(#333 裁定 c5717512971):再次 stuck 且非
    ready 态附当前步中间值,首次 stuck 零数值。埋点:reveal/hint_level=阶梯消耗,
    弃用轮记 dropped,改写记 soften;bottom-out 按「这一步我们直接看结果:」前缀统计。"""
    re_stuck = session.hint_level > 0  # V1:首次 stuck=0 不给数值;再次 stuck 才有授权资格(推进前捕获)
    if _mech_off("reveal_ladder"):  # 二阶段 LOO:阶梯整体关 → 只问不揭示
        session.guard_events.append({"branch": "reveal_off", "mech": "reveal_ladder"})
        return _SUPPORT_HINT
    step = _next_step(session)
    session.guard_events.append({"branch": "reveal", "hint_level": session.hint_level})
    if step is None:
        # 不变量(VERDICT#6 更新):终答文本只出现在 bottom-out(此处)/ finish 两条
        # 路径(锁在 tests/teaching/test_kernel_invariants.py);阶梯揭示只给步骤不给终答;
        # 确认/赞许轮转述式确认、不引述终答值(ready_to_confirm 不再入允许池)。
        if _mech_off("bottomout_backboard"):  # 二阶段 LOO:梯尽不披露终答
            return NEEDS_REVIEW_TEXT
        answer = str(session.question.get("answer") or "").strip()
        if not answer and session.steps:
            answer = str(session.steps[-1].get("value") or "").strip()
        return (f"这一步我们直接看结果:{answer.rstrip('。.')}。你先记住它,我们回头再讲一遍为什么。"
                if answer else NEEDS_REVIEW_TEXT)
    lead = _STEP_LEADS[(session.hint_level - 1) % len(_STEP_LEADS)]
    step_text, soften_path = _soften_step_text(str(step.get("step") or ""),
                                               frozenset(_answer_focus_numbers(session)))
    if step_text is None:  # 裸数字形状读不成句:整步弃用 → 通用兜底(#185 复审 ②)
        session.guard_events[-1]["dropped"] = True  # 复审三轮 P2:弃用轮可辨识,先量再收词表
        return NEEDS_REVIEW_TEXT
    if soften_path != "none":  # 只在真命中两路径时写:无泄漏保留/弃用轮不加键(整 dict 断言不变)
        session.guard_events[-1]["soften"] = soften_path  # #241 行 4:cut(分句收回)/mask(改写「几」)
    # 泄露网 V1(#333):七条件过 → 动作化文本附当前步中间值;审计单字段 anchor_numbers
    # (additive,只在授权轮写;未授权轮不加键,整 dict 断言不变,#187/A4 指标连续)。
    anchor = (set() if session.state == "ready_to_confirm"
              else _current_step_anchor_numbers(session, step)) if re_stuck else set()
    # 句末标点由模板统一补:step/answer 自带「。」先剥掉,不叠「。。」
    # (#198 独立审查实测:生产揭示轮 9/14 双句号,学生可见面)。
    if anchor:
        shown = "、".join(str(int(n)) if n == int(n) else str(n) for n in sorted(anchor))
        session.guard_events[-1]["anchor_numbers"] = sorted(anchor)
        return f"{lead}:{step_text.rstrip('。.')}。这一步先算,得到 {shown}。你接着算下一步。"
    return f"{lead}:{step_text.rstrip('。.')}。你接着算下一步。"
NEEDS_REVIEW_TEXT = "这一题的学习证据还不够,我们继续——你能说说目前想到的第一步吗?"
# finish() 证据不足·correct 档(2026-09-16 用户裁,撤销摸底答对直接完成):答对过
# 但尚未自己讲出思路 → 专项引导复讲文案(不写「今天没完整展开」——学生可能还想继续)。
FINISH_EVIDENCE_TEXT = "这道题之前已经答对了,我们还需要听你把关键思路讲清楚。"
# 护栏命中时的确定性安全问句(老仓库 hard_safety_fallback 同款语义;M2 清单
# 阶段 2:护栏不过的输出不得到达学生可见面)
SAFE_FALLBACK_TEXT = "先回到当前小问,你能说出题目明确给出的一个条件吗?"


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
        # VERDICT#6(#310):回引不引述终答值——answer_leak 兜底若逐字引学生原话,
        # 会把刚拦下的终答从确定性路径放回学生面(gate-02/03 冒烟实测)。
        answer = _answer_numbers(session) if session is not None else set()
        if answer and _reply_numbers(snippet) and not _mech_off("confirm_rewrite"):
            # 确认话姿(非重定向,人裁 2026-09-17 #318 修改后同意):转述锚点只断言
            # 条件可证事实——「学生说到了结论」;不断言「验算齐/讲得清楚」(那需要
            # mastery/ready 态证明,本分支条件只有 answer 数字交集,证据不足)
            return "你已经说到了自己的结论。最后请你自己把完整思路和结论再说一遍。"
        return f"先回到你刚说的「{snippet}」——你能从题目里再确认一个已知条件吗?"
    # 纯图/无权威答案(十字绣/剪绳子/连线题):不逼学生答条件,软性回到看图
    if guard == "answer_leak" and any(
            rule.startswith("source_value_disclosure") for rule in rule_ids):
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
    # 答案对照基线(#149):由 `_known_answer(session)` 填入(answer 优先、steps 末值兜底)
    # ——评测侧 question 只传 {"text": ...} 时护栏也有基准。
    answer_reference: str = ""
    images: list[str] | None = None
    student_message: str | None = None
    student_evidence: tuple[str, ...] = ()  # 学生历史 user 消息(泄露护栏对照:已说答案可复述)
    cited_numbers: list[float] = field(default_factory=list)  # 模型自报集(影子对照,埋点用)
    model_turn: bool = True  # 是否落模型路径埋点(首问 False:首问经固定模板覆盖,不额外留痕)


def _guard_check(ctx: "_GuardContext", text: str, session: "LearnerSession | None" = None,
                 ready_to_confirm: bool = False) -> tuple[str | None, list[str], str | None, set[float]]:
    """三护栏(泄露/语气/格式)逐个过 + 数值披露门(单一判据)。

    「未经学生验证的源值披露」的**唯一判据** = 数字级归因(`_drift_sources` 的允许集/
    终答池):`_reply_numbers(text) − 允许集` = 违规数字,按来源标签池再分 `answer`
    (对话态提前说终答 = 泄漏)与 `hallucinated`(无合法来源 = 幻觉),命中即返回
    `(answer_leak, rule_ids, None, 违规数字)` 走修复漏斗。句级近似判据(guardrails 的
    unverified_source_value_disclosure)已删——两套判据并存正是 #184 根因(有参考答案时
    句级分支恒不可达 → 检测到却原样达学生面);「禁止出现第二套判据」同 `_hits_answer_numbers`。

    同一份归因既记账(`extracted`/`violation_sources`)又当门(模型回合 `gate`:
    blocked=拦下重写 / observed=仅检测),不再只是记账(key: 一次判定,无第二套实现)。"""
    leak = evaluate_student_visible_question(
        text,
        # #149:答案基线统一走 _known_answer(answer 优先、steps 末值兜底);
        # ctx 未带基线(旧调用方)时退回 question["answer"],行为与改动前一致。
        answer_reference=ctx.answer_reference or str(ctx.question.get("answer") or ""),
        active_subquestion_text=str(ctx.question.get("text") or ""),
        analysis_reference=str(ctx.question.get("analysis") or ""),
        student_evidence=list(ctx.student_evidence),
    )
    # 单一判据(仅模型回合):允许集口径见 `_drift_sources`;无会话时不判(fail-open)
    allowed, answer_pool = (_drift_sources(session, ctx.student_message)
                            if session is not None else (set(), set()))
    extracted = _reply_numbers(text)
    violations = extracted - allowed
    sources = [{"number": n, "source": "answer" if n in answer_pool else "hallucinated"}
               for n in sorted(violations)]
    if session is not None and ctx.model_turn:  # 首问不落模型路径埋点(原口径)
        session.guard_events.append({
            "branch": "model", "cited": ctx.cited_numbers,
            "extracted": sorted(extracted), "violation_sources": sources,
            "gate": "blocked" if violations else "observed"})
    if leak.fallback_required or violations:
        rules = [f.finding for f in leak.findings]
        rules += [f"source_value_disclosure:{source}"
                  for source in dict.fromkeys(item["source"] for item in sources)]
        return ("answer_leak", rules, None, violations)
    tone = apply_tone_guardrail(
        reply=text, grade_band=_tone_band(ctx.grade), interaction_signal="neutral",
        teaching_move="connect_relation", ready_to_record=False)
    if tone.applied:
        return ("tone", list(tone.reason_codes), None, set())
    fmt = evaluate_student_visible_format(text)
    if not fmt.ok:
        return ("format", list(fmt.findings), fmt.downgrade_prompt, set())
    return (None, [], fmt.reply, set())  # ok → 归一化文本(LaTeX 已转 a/b)


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
                critique: str, ready_to_confirm: bool = False) -> str | None:
    """带一句 critique 重调 tutor 一次;重调后过同一判据(clean)才返回文本,否则 None。"""
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
    g2, _r2, d2, _v2 = _guard_check(ctx, new_text, session, ready_to_confirm)
    return d2 if g2 is None else None


def _guard_output(reply_text: str, session: "LearnerSession | None" = None,
                  ctx: "_GuardContext | None" = None,
                  ready_to_confirm: bool = False) -> str:
    """三护栏响应策略(检测规则不动,只改策略):修复重生成优先(带 rule_ids+
    命中片段重调一次)→ 再命中降级情境化兜底句(接学生原话);数值披露门(#184)
    同漏斗三档;stuck 语义=仅「修复失败→兜底句」置卡点,已判过的兜底句不再重生成。"""
    if ctx is None:
        return reply_text
    guard, rule_ids, normalized, violations = _guard_check(ctx, reply_text, session,
                                                           ready_to_confirm)
    early = _ablation_guard_early(guard, session, rule_ids, violations, reply_text)
    if early is None and _current_arm() == "B" and guard == "answer_leak":
        early = _arm_b_leak_funnel(_regenerate, ctx, session, rule_ids,
                                   reply_text, ready_to_confirm)
    if early is not None:
        return early
    if guard is None:
        return normalized
    prev_text = (str(session.history[-1].get("content") or "")
                 if session is not None and session.history
                 and session.history[-1].get("role") == "assistant" else "")
    if prev_text and reply_text.strip() == prev_text.strip() and violations:
        # 本轮待发文本 == 上一轮学生可见文本(确定性揭示兜底 / 同句兜底重来一次):它已判过
        # 且本轮已无新信息可重写——直接落兜底句,由输出面防复读背板推进阶梯(#107/#112),
        # 不再多烧一次重生成(#184:重复兜底句会把判据一次命中拖成两次)。
        return _contextual_fallback(session, guard, rule_ids, ctx.student_message)
    critique = _GUARD_REJECTION_HIT_TEMPLATE.format(
        rule_ids_joined=','.join(rule_ids), reply_excerpt=reply_text[:48])
    if violations:
        numbers = "、".join(f"{n:g}" for n in sorted(violations))
        critique = _GUARD_REJECTION_NUMBERS_TEMPLATE.format(
            rule_ids_joined=','.join(rule_ids), numbers=numbers)
    regenerated = _regenerate(ctx, session, reply_text, critique, ready_to_confirm)
    if regenerated is not None:
        _record_event(session, guard, rule_ids, reply_text, regenerated=True)
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
    """solver 职责:确定性校验分步解(步骤非空、每步有 step/value,不调模型)并存进
    session.steps(阶梯底稿 + 数字校验基准);不通过则弃。"""
    validated = [
        {"step": str(s.get("step") or "").strip(), "value": str(s.get("value") or "").strip()}
        for s in (steps or [])
        if isinstance(s, dict) and str(s.get("step") or "").strip() and str(s.get("value") or "").strip()
    ]
    session.steps = validated
    return validated


# 题库解析切片的**分步标记**(#107 方案 A:确定性切片,零模型)。
# 只认「成句边界」与「序列词开头」两类,不做语义切分——切粗一点不影响任何判据
# (阶梯只用于「卡住时揭示下一级」)。
_ANALYSIS_SPLIT_RE = re.compile(r"[。;；\n]+|(?=(?:先|再|然后|接着|最后|其次))")
_SLICE_TRIM_RE = re.compile(r"^[\s,、:：]+|[\s,、:：]+$")


def _step_value(fragment: str) -> str:
    """切片 → **该步结果**:有等号取最后一个等号右侧的数字,否则取最后一个数字。

    取不到数字(纯叙述步)返回空串 → 该片不入选阶梯(与 `_store_steps`「无 value 不用」同口径)。
    """
    tail = fragment.rsplit("=", 1)[-1] if "=" in fragment else fragment
    numbers = re.findall(r"\d+(?:\.\d+)?", tail)
    if not numbers and tail != fragment:
        numbers = re.findall(r"\d+(?:\.\d+)?", fragment)  # 等号右侧没数字 → 退回整片
    return numbers[-1] if numbers else ""


def _analysis_steps(analysis: str) -> list[dict]:
    """题库 `analysis` → 分步阶梯(#107 方案 A:纯函数、零模型调用)。

    为什么要有它:现有阶梯**只**来自模型 `start()` 当场生成的分步解(`_store_steps`),
    而「现场生成中间值」正是会幻觉的那一环(#107 背景:实测给出「脚总数就是8」实为 16)。
    题库带解析时把既定解析切成阶梯 → 学生卡住只揭示**既定步骤**,模型做「选择并复述」,
    不做「现场生成数值」。

    切片规则:按句末标点与序列词(先/再/然后/接着/最后/其次)切;丢弃过短片(≤3 字)
    与无数字片;至少 2 片才返回(否则调用方退回模型分步解)。
    """
    fragments = [_SLICE_TRIM_RE.sub("", f)
                 for f in _ANALYSIS_SPLIT_RE.split(str(analysis or ""))]
    steps = []
    for fragment in fragments:
        if len(fragment) <= 3:
            continue
        value = _step_value(fragment)
        if value:
            steps.append({"step": fragment, "value": value})
    return steps if len(steps) >= 2 else []


def _invoke(gateway: Gateway, role: str, messages: list[dict], schema: dict,
            session: LearnerSession, images: list[str] | None = None):
    return gateway.invoke(ModelRequest(
        role=role, messages=messages, response_schema=schema,
        session_id=session.session_id, max_tokens=800, temperature=0,
        images=images,
    ))


def _stamp_turn(session: LearnerSession, turn: int) -> None:
    """给本轮新产生的 guard_events 补打轮号(`turn`,additive 字段;#146 M2 逐轮列)。

    轮号 = 该轮在 KernelSubject transcript 里的下标(首问 0、第一回复 1…)。
    `setdefault` 语义:已带轮号的事件不动 → 只需在提交点各调一次,
    不必在每个埋点调用处穿参数。消费侧拿到精确配对;旧工件无该字段时按序退回。
    """
    for event in session.guard_events:
        event.setdefault("turn", turn)


def _commit_turn(session: LearnerSession, student_message: str, assistant_text: str,
                 state: str, ready_to_confirm: bool = False) -> Turn:
    """三处 turn 提交尾部收敛(代喂/揭示/模型路径):append history×2 + version+1 +
    置态 + 返回 Turn(净减重复行,#113 P2 确定性路径收敛)。

    提交前给本轮事件打轮号:已提交的 assistant 轮数 + 首问
    (首问由 start() 产出且不入 history,故显式 +1)。"""
    _stamp_turn(session, len(session.history) // 2 + (1 if session.first_question else 0))
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


def _ask_final_answer(session: LearnerSession, student_message: str) -> Turn:
    """完成表达的确定性采集追问(#178 判停分析→PR-2):零模型调用,不 confirm、不判对错、
    不预设掌握——把判停闸要的结论数字从学生嘴里采上来(闸无料可判 = 全库 0/32 ready 的
    采集端成因)。埋点 {branch: answer_collect},一次会话至多一次(对齐 elicit 先例)。"""
    session.guard_events.append({"branch": "answer_collect"})
    return _commit_turn(session, student_message, ASK_FINAL_ANSWER, "dialogue")


def start(question: dict, learner: dict, *, gateway: Gateway | None = None) -> Turn:
    """生成首问:一次调用产出 steps+reply,reply 经护栏后即首问;纯图题 unacceptable 走 fail-closed。"""
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
    # #107 方案 A:题库解析存在时**既定分步**优先于模型当场生成的分步解(确定性切片、
    # 零模型调用;切不出 ≥2 步时保持模型分步解不变)。
    ladder = _analysis_steps(str(session.question.get("analysis") or ""))
    if ladder:
        session.steps = ladder
    ctx = _GuardContext(question=session.question, grade=learner.get("grade", ""),
                        gateway=gateway, role="tutor", messages=open_messages,
                        schema=OPEN_SCHEMA, answer_reference=_known_answer(session),
                        model_turn=False)  # 首问经固定模板覆盖:不落模型路径埋点
    safe_text = _guard_output(str(payload.get("reply") or ""), session, ctx)
    if not safe_text.strip():
        safe_text = _OPENING_FALLBACK  # 图文题 acceptable=false 且 reply 留空 → 确定性兜底首问
    else:
        safe_text = first_question_text(learner.get("answer_status"),
                                        str(payload.get("transcription") or ""),
                                        session.question)
    session.state = "first_question_ready"
    session.first_question = safe_text
    _stamp_turn(session, 0)  # 首问轮 = transcript 第 0 轮(其 guard 事件如首问泄露)
    return Turn(text=safe_text, session_version=session.session_version,
                state=session.state, ready_to_confirm=False,  # 首问恒非确认
                session=session)


def _gate_premature_confirm(session: LearnerSession, ctx: "_GuardContext", output: dict,
                            safe_text: str, student_message: str) -> str:
    """判停闸:模型想判停但学生未陈述答案 → 闸下并重写(消融 A/B 臂旁路)。"""
    if not (output.get("ready_to_confirm") and _answer_numbers(session)
            and not _student_stated_answer(session, student_message)):
        return safe_text
    if _arm_bypass("would_rewrite", "premature_confirm", session) or _mech_off("premature_confirm"):
        return safe_text  # 消融 A/B 臂:闸检测照跑(A 记 shadow),处置旁路;二阶段 LOO 同旁路
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
                         hits: list[str], ready_to_confirm: bool = False) -> tuple[str, str]:
    """代喂命中的处置(#165 WS4「守卫替换粒度」):重生成 → 脱敏 → 模板兜底。

    返回 `(学生可见文本, 处置路径)`;路径取值 `regenerated` / `masked` / `template`,
    落 `guard_events[].mode` 供度量区分。原实现一律整轮换成复讲模板,连本轮引导/确认
    语义一并丢掉(并强制不确认)→ 学生已说出终答的末轮被推成 needs_review。
    不变量的最后一道:任何路径下学生可见文本都不含未说出的方法词。
    """
    regenerated = _regenerate(ctx, session, text, _FEEDS_METHOD_CRITIQUE, ready_to_confirm)
    if regenerated is not None and not _feeds_method_hits(regenerated, ctx.student_evidence):
        return regenerated, "regenerated"
    masked = _mask_hit_tokens(text, hits)
    if not _feeds_method_hits(masked, ctx.student_evidence):
        return masked, "masked"
    return _ELICIT_TEMPLATE, "template"  # 兜底:词表无互为子串项,脱敏理论上必清空命中


def _repeat_refine(ctx, session, safe_text: str, ready: bool) -> str:
    """复读自批评的消融臂分发:C 臂照原逻辑(_regenerate+兜底);A/B 臂旁路。"""
    prev = session.history[-1]["content"] if session.history else session.first_question
    if not (prev and _is_repeat(prev, safe_text)):
        return safe_text
    if _current_arm() == "A":
        _shadow_event(session, "would_rewrite", "repeat_regen")
        return safe_text
    if _current_arm() == "B":
        return safe_text
    if _mech_off("repeat_regen"):
        return safe_text
    session.guard_events.append({"branch": "repeat_regen"})  # 裁②:复读重生成落点
    refined = _regenerate(ctx, session, safe_text, _SELF_CRITIQUE, ready)
    if refined is None or _is_repeat(prev, refined):
        if _mech_off("repeat_fallback"):
            return safe_text  # 二阶段 LOO:复读兜底旁路(不揭示不置 stuck)
        refined = _reveal_stuck_hint(session)
        session.stuck = True
    return refined


def _deterministic_turn(session: LearnerSession, student_message: str,
                        gateway: Gateway | None = None) -> Turn | None:
    """reply 的确定性分支集(消融门控:A 记 would_* 旁路,B 静默旁路,C 照旧);
    None=无命中走模型路径(四分支:understanding/stuck/答案命中/完成表达)。"""
    if (_student_signals_understanding(student_message)
            and not _arm_bypass("would_rewrite", "elicit_restatement", session)):
        return _ask_restatement(session, student_message)
    if (_student_signals_stuck(student_message)
            and (_current_arm() == "B"  # phase2bx-reveal_ladder:B 臂加回卡住支持/揭示梯
                 or not _arm_bypass("would_reveal", "stuck_hint", session))):
        hint = _stuck_hint(session)
        session.stuck = True
        return _commit_turn(session, student_message, hint, "dialogue")
    if (_student_hits_known_answer(session, student_message)
            and not _arm_bypass("would_rewrite", "answer_hit_restatement", session)):
        return _ask_restatement(session, student_message)
    if (session.learner.get("answer_status") == "incorrect"
            and session.state != "ready_to_confirm"
            and _student_signals_completion(student_message)
            and not _student_stated_answer(session, student_message)
            and not any(event.get("branch") == "answer_collect" for event in session.guard_events)
            and not _arm_bypass("would_rewrite", "answer_collect", session)):
        return _ask_final_answer(session, student_message)
    return None


def reply(session: LearnerSession, student_message: str, *,
          gateway: Gateway | None = None, expected_session_version: int | None = None) -> Turn:
    """多轮苏格拉底交流(03 §4 Dialogue 自旋;Conflict 为可选校验,#34 映射表决策)。"""
    if session.finished:
        raise TerminalStateError(f"会话已终态({session.state})")
    if expected_session_version is not None and expected_session_version != session.session_version:
        raise SessionVersionConflict(  # 不推进:旧版本不静默覆盖新一轮诊断(00 §5.2 约定 3)
            f"expected_session_version={expected_session_version} != 当前 {session.session_version}")
    turn = _deterministic_turn(session, student_message, gateway)
    if turn is not None:
        return turn
    gateway = gateway or default_gateway()
    arc_hint = diagnose_turn_hint(session.learner.get("answer_status"),
                                  reply_index=len(session.history) // 2)
    _reply_messages = [
        {"role": "system", "content": system_prompt(session.learner.get("grade", ""))},
        {"role": "user", "content": _user_prompt(_masked_question(session.question), {
            "学生": session.learner, "对话记录": session.history,
            "学生本轮回答": student_message,
            "输出提醒": "若学生自己的表达已把关键步骤、依据和结论讲清楚"
                        "(足以让听者理解这道题怎么做;你讲过而他只附和的不算),"
                        "ready_to_confirm 置 true;否则 false。"}
            | ({"弧线步": arc_hint} if arc_hint else {}))},
    ]
    output = json.loads(_invoke(
        gateway, "tutor", _reply_messages, TUTOR_TURN_SCHEMA, session,
    ).text)
    ctx = _GuardContext(question=session.question, grade=session.learner.get("grade", ""),
                        gateway=gateway, role="tutor", messages=_reply_messages,
                        schema=TUTOR_TURN_SCHEMA, student_message=student_message,
                        answer_reference=_known_answer(session),
                        cited_numbers=sorted({float(n) for n in (output.get("cited_numbers") or [])}),
                        student_evidence=(tuple(
                            str(message["content"]) for message in session.history
                            if message.get("role") == "user"
                        ) + (student_message,)))
    safe_text = _guard_output(output["reply"], session, ctx,
                              bool(output["ready_to_confirm"]))
    prev = session.history[-1]["content"] if session.history else session.first_question
    safe_text = _repeat_refine(ctx, session, safe_text, bool(output["ready_to_confirm"]))
    method_hits = _feeds_method_hits(safe_text, ctx.student_evidence)
    if method_hits and _arm_bypass("would_rewrite", "feeds_method", session):
        method_hits = []
    if method_hits:
        repaired, mode = _repair_feeds_method(ctx, session, safe_text, method_hits,
                                               bool(output["ready_to_confirm"]))
        _record_event(session, "feeds_method", method_hits, safe_text,
                      regenerated=(mode != "template"), mode=mode)
        safe_text = repaired
        if not _student_stated_answer(session, student_message):
            output["ready_to_confirm"] = False
    if prev and safe_text == prev:
        if _current_arm() == "A":
            _shadow_event(session, "would_reveal", "output_repeat_fallback")
        elif _current_arm() == "C" and not _mech_off("bottomout_backboard"):
            safe_text = _reveal_stuck_hint(session)
            output["reply"] = safe_text
            output["ready_to_confirm"] = False
            session.stuck = True
    safe_text = _gate_premature_confirm(session, ctx, output, safe_text, student_message)
    state = "ready_to_confirm" if output["ready_to_confirm"] else "dialogue"
    return _commit_turn(session, student_message, safe_text, state,
                        ready_to_confirm=bool(output["ready_to_confirm"]))


def _structured_summary(session: LearnerSession) -> str:
    """确定性模板(2026-09-16 用户裁:只总结学生实际表达;撤销「每一步都是你自己的
    思路」「这道题你已经完整讲清楚」两个无条件断言——本模板仅在 ready_to_confirm
    (= 讲述证据已按教学定义判定)且 correct 且无卡点时触达,模板内容以引学生原话为主)。

    纯文本短句(过语气/格式护栏);引用来自会话历史的学生原话与题面,不从模型生成。
    """
    user_turns = [m["content"] for m in session.history if m["role"] == "user"]
    first = user_turns[0] if user_turns else "你从题目本身开始"
    last = user_turns[-1] if user_turns else "说出了你的结论"
    question = str(session.question.get("text") or "")
    return (
        f"这一题(「{question}」)你自己讲了做法:从「{first}」开始,说到「{last}」,"
        f"关键步骤和结论都在你自己的话里,和题目的要求也对上了。"
        f"可以再做一道,或者今天先到这里。"
    )


def finish(session: LearnerSession, *, gateway: Gateway | None = None) -> Summary:
    """学习总结(03 §4 ReadyToConfirm → Completed,summary 不可变;证据不足 needs_review)。

    完成判定改由会话内讲述证据支持(用户裁 2026-09-16,撤销 R6「摸底答对+不卡
    → 直接 completed」旧规则):finish **先查 `ready_to_confirm`**,未达 → 既有
    needs_review 路径(answer_status=correct 不再绕过);已达 → 按原条件(correct
    且无卡点 → 零调用模板;否则模型总结,零调用路径保留)。教学定义(判卷口径,
    用户裁逐字):学生自己的表达已包含关键步骤、关键依据和结论,足以让听者理解
    这道题怎么做;没有尚未解决的关键错误或遗漏。教师说过、学生只答「对」「懂了」
    不算学生自己讲出。"""
    if session.finished:
        if session.state == "completed" and session.summary is not None:
            return session.summary  # completed 终态:finish 幂等返回同一 Summary
        raise TerminalStateError(f"会话已终态({session.state})")
    if session.state != "ready_to_confirm":
        # 证据不足(00 §5.1):不调模型、不写 summary,确定性引导文案。
        # correct 档专项文案:答对过但还没自己讲出思路(不写「今天没完整展开」
        # ——学生可能还想继续);其余档沿 NEEDS_REVIEW_TEXT。
        text = (FINISH_EVIDENCE_TEXT
                if session.learner.get("answer_status") == "correct" else NEEDS_REVIEW_TEXT)
        return Summary(text=text, status="needs_review",
                       session_version=session.session_version)
    if session.learner.get("answer_status") == "correct" and not session.stuck:
        # 零调用通路保留(原条件 + 已达确认态):完成由学生自己的讲述证据证实
        summary = Summary(text=_structured_summary(session), status="completed",
                          session_version=session.session_version)
        session.state = "completed"
        session.summary = summary
        return summary
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
