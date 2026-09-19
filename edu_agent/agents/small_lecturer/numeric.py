"""小讲师内核的**数字归因与来源池**(从 kernel.py 原样搬出,零行为变更)。

这一族是纯函数/纯常量:题面与学生口述的数字全集、单步算式结果、以及「允许集 =
题面 ∪ 阶梯值 ∪ 学生历史 ∪〔终答:仅确认态〕」的来源标签池。搬出来的理由只有一条:
`kernel.py` 已顶到 02 §2 的单文件上限(800 代码行),而这一族与状态机/模型调用无关,
是内核里**最独立**的一块(仅读 `LearnerSession` 的 question/steps/history)。

口径归属(别在两处各写一遍):
- 判据底座 = `_drift_sources`(允许集) + `answer_pool`(终答数字池),见 #149/#156/#157/#184;
- 「漂移池」用全量 `_answer_numbers`;「是否已陈述终答」判据用 `_answer_focus_numbers`
  (剔除题面已给数字)——两处口径不同、各有依据,见各自 docstring。
"""

from __future__ import annotations

import re

from .session import LearnerSession

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


# 裸 ASCII 数字段(整数/小数;分数算两个)——numeric/kernel 共用(#185 复审 shrink)。
_ASCII_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _question_numbers(text: str) -> set[float]:
    """题面条件数字全集(整数/小数;分数按两个数字处理,与口算习惯一致)。"""
    return {float(m) for m in _ASCII_NUMBER.findall(text or "")}


# 单步算式识别(学生验算/讲师复述用):「5乘4」「8×2」「10 ÷ 2」「26-16」——两操作数一个算子。
_ARITHMETIC_STEP = re.compile(
    r"(?<![A-Za-z0-9.])(\d+(?:\.\d+)?)\s*"
    r"(?P<op>乘以|乘上|除以|乘|加|减|[×x*÷/+＋\-－−])\s*(\d+(?:\.\d+)?)")


_ARITHMETIC_OPS = {
    "乘": lambda a, b: a * b, "乘以": lambda a, b: a * b, "乘上": lambda a, b: a * b,
    "除以": lambda a, b: a / b, "加": lambda a, b: a + b, "减": lambda a, b: a - b,
    "×": lambda a, b: a * b, "x": lambda a, b: a * b, "*": lambda a, b: a * b,
    "÷": lambda a, b: a / b, "/": lambda a, b: a / b, "+": lambda a, b: a + b,
    "＋": lambda a, b: a + b, "-": lambda a, b: a - b, "－": lambda a, b: a - b,
    "−": lambda a, b: a - b}


def _reply_numbers(text: str) -> set[float]:
    """抽取制数字(替代自报制):回复文本里除「第N」序数语境外的全部数字。

    与 _question_numbers 同口径(整数/小数;分数按两个数字);先剔除「第N」序数
    (第1/第2步…),避免把序数当数字引用误标漂移。"""
    stripped = re.sub(r"第\s*\d+(?:\.\d+)?", "", text or "")
    return _question_numbers(stripped)


def _arithmetic_results(text: str) -> set[float]:
    """文本里**单步算式**的数值结果(学生验算「5乘4加3乘2等于26」→ 20/6)。

    只认单步(两操作数一个算子),不做表达式求值——用途仅是把「学生自己算过的中间
    结果」放进允许集(#184 不误伤:讲师复述学生验算步骤时不把该结果当幻觉数字)。"""
    found = set()
    for match in _ARITHMETIC_STEP.finditer(text or ""):
        try:
            found.add(float(_ARITHMETIC_OPS[match.group("op")](float(match.group(1)),
                                                              float(match.group(3)))))
        except (KeyError, ZeroDivisionError):
            continue  # 不认识的算子/除零:宁漏勿误(该数字照旧走原判据)
    return found


def _usable_numbers(text: str, answer: set[float]) -> set[float]:
    """来源池数字 ∪ 其**单步算式结果**(#184「不误伤」)——终答数字一律剔除。

    出处写着「5乘4」则结果 20 与出处数字同权(讲师复述学生验算/题面自带的算式不算
    幻觉);结果落在终答池的算式不并入(防「8-5=3」把终答洗白,#157 同款边界)。"""
    numbers = _question_numbers(text)
    return numbers | (_arithmetic_results(text) - numbers - answer)


def _declarative(text: str) -> bool:
    """陈述式判定(guard-provenance-fix 追加边界,PM 追加令 2026-09-19):问句猜答
    (「是不是0.4?」)≠ 已述——问句里的数字不入学生池,导师直 confirm 仍走掩码门。
    判据=消息剥空白后不以 ?/? 结尾;混合消息(先陈述后问)整条按问句处理
    (fail-closed:宁过掩不放过)。已知残留:无疑问标记的口语问句漏判(同
    _CJK_NUMERALS「宁漏勿误」族,出现再收)。"""
    return not str(text or "").rstrip().endswith(("?", "?"))


def _drift_sources(session: LearnerSession,
                   student_message: str | None) -> tuple[set[float], set[float]]:
    """数字来源标签池(M2 闭环 #113/#34 + #157 评审末值边界;VERDICT#6 更新):允许集 =
    题面 ∪ 题库解析题给数 ∪ (steps 值 − 终答数字) ∪ 学生历史数字(含终答)。
    学生已述豁免(guard-provenance-fix ①,2026-09-19 用户键 fix-forward):学生
    已述数字——含终答值——导师可复述/确认(confirm 命根:0.4kg 案学生连答四次
    被 □ 掩成死锁);首次披露仍禁(学生未述且题面/解析未给 → 照旧掩码门)。
    取代 #310 VERDICT#6 的「确认轮终答零例外」口径(A 类语义变更,差异入档)。
    边界(PM 追加令):豁免只认**陈述式**已述——问句猜答(「是不是0.4?」)不算,
    导师直 confirm 照旧拦截(_declarative)。

    终答数字按**值**从 steps 无条件允许集剥离(#157 评审:模型自报阶梯含末值=答案,
    整段照抄演算会 violations=[] 洗白——"自报进白名单"与 cited_numbers 同病);
    按值而非按位置(steps[:-1]):阶梯末级未必是答案(题库 16/10 阶梯答案 3/5),
    按位置会把诚实的末级中间值误伤,按值只锁真正要保护的答案数字。

    返回 (允许集, 终答数字池)。终答数字单独成池、不入允许集,供违规
    来源标签判定:违规数字若在终答池 → 标签 "answer"(对话态提前说终答),否则
    "hallucinated"(无任何合法来源)。四个来源各自并上其算式结果(见 `_usable_numbers`,
    #184 不误伤),终答数字处处剔除。"""
    answer = _answer_numbers(session)  # #156 统一判据底座:answer 优先,阶梯末级兜底
    face = _usable_numbers(str(session.question.get("text") or ""), answer)
    # guard-provenance-fix ②:题库解析的题给数入池(按值剔终答;analysis 非学生可见面)
    face |= _question_numbers(str(session.question.get("analysis") or "")) - answer
    steps: set[float] = set()
    for step in session.steps:
        steps |= _usable_numbers(str(step.get("value") or ""), answer)
    student: set[float] = set()
    for message in session.history:
        if message.get("role") == "user" and _declarative(str(message.get("content") or "")):
            student |= _usable_numbers(str(message.get("content") or ""), answer)
    if _declarative(str(student_message or "")):
        student |= _usable_numbers(str(student_message or ""), answer)
    allowed = face | (steps - answer) | student  # 学生池含终答(guard-provenance-fix ①)
    return allowed, answer


def _number_forms(number: float) -> list[str]:
    """终答数值的可见文本形态:整数补千分位逗号形态,小数补去零形态(f"{n:g}")。"""
    if number == int(number):
        whole = str(int(number))
        return [whole] if abs(number) < 1000 else [whole, f"{int(number):,}"]
    return [str(number), f"{number:g}"]


def mask_numbers(text: str, numbers) -> str:
    """确定性数值掩码(#333 Thin Kernel·附录 A):把命中的终答数值替换为 □,其余
    逐字保留。词边界防误伤:千分位片段(「1,000」里的 1/000)与小数片段(「3.0」
    里的 3/0)不掩,裸逗号/顿号邻接照掩(property 实测边界)。零模型、零重生成。"""
    masked = str(text)
    for number in numbers or ():
        for form in _number_forms(float(number)):
            masked = re.sub(
                rf"(?<!\d)(?<!\d,)(?<!\.){re.escape(form)}(?![\d.])(?!,\d)",
                "□", masked)
    return masked
