"""小讲师内核的**数字归因与来源池**(从 kernel.py 原样搬出,零行为变更)。

这一族是纯函数/纯常量:题面与学生口述的数字全集、单步算式结果、以及「允许集 =
题面 ∪ 阶梯值 ∪ 学生历史 ∪〔终答:仅确认态〕」的来源标签池。搬出来的理由只有一条:
`kernel.py` 已顶到 02 §2 的单文件上限(800 代码行),而这一族与状态机/模型调用无关,
是内核里**最独立**的一块(仅读 `LearnerSession` 的 question/steps/history)。

口径归属(别在两处各写一遍):
- 判据底座 = `_drift_sources`(允许集) + `answer_pool`(终答数字池),见 #149/#156/#157/#184;
- 「漂移池」用全量 `_answer_numbers`;「是否已陈述终答」判据用 `_answer_focus_numbers`
  (剔除题面已给数字)——两处口径不同、各有依据,见各自 docstring。

result-assertion proof(#441 B′ containment,B1 终裁 5824408984)也住在这里:
`result_evidence` 是纯函数(片段+值 → ResultEvidence|None),与数字归因同族、
不读会话——规则只描述 syntax/property classes(封闭语法类),不是语义解析器。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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


def student_stated_answer(session: LearnerSession,
                          student_message: str | None) -> bool:
    """值级「学生已述终答」判定(guard-provenance-fix ① 值级补全,PM 追加令 A/B
    跑面揭出):guardrails 答案串门是**字符串粒度**(学生说「0.4千克」≠ 权威串
    「0.4kg」→ 句级豁免漏放 → 学生刚说完答案还吃「不能直接给出」)。本判定把
    内核值级归因注入句级门:终答数字**全体**在学生陈述式消息里(问句不算,
    _declarative 同口径)→ 导师复述非首次披露。判据单源(#184):值级抽取只在
    本模块,guardrails 纯参数消费。"""
    answer = _answer_numbers(session)
    if not answer:
        return False
    stated: set[float] = set()
    for message in session.history:
        if message.get("role") == "user" and _declarative(str(message.get("content") or "")):
            stated |= _question_numbers(str(message.get("content") or ""))
    if _declarative(str(student_message or "")):
        stated |= _question_numbers(str(student_message or ""))
    return answer <= stated


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


# ── result-assertion proof(#441 B′ containment;B1 分析件 §4 规则,终裁
#    5824408984)─────────────────────────────────────────────────────────────
# 规则类型(#442 硬编码治理 §一):deterministic parser + positive authority——
# 非 None 即向学生断言「得到 X」,验收从严。设计定位:defect(_step_value_candidate
# 抽到输入 → anchor 把操作数当结果断言)→ invariant(无 result-assertion proof
# 即无「得到 X」权限)→ proof obligation(本函数),不是 case→rule。
#
# 红线(B1 终裁④):只描述 syntax/property classes,禁具体数学内容/中文业务词。
# 下列全部集合均为封闭语法类/数学记号(共 7 组,见 B1 §4.4),无一成员是
# 「结果谓词内容词」(得到/算出/结果是/求出/可知…一律不出现)——需要新增
# 内容词白名单的瞬间 = 停,呈架构裁决(oracle census 门会先红,见
# tests/teaching/test_anchor_proof_oracle.py)。

# 从句界符(标点封闭类;注意 ，/、 不是切片分隔符,可在片内出现)
_CLAUSE_DELIMS = "，、。；,;“”（）():：…—"
_EQ_GUARDS = (("=", "!<>"), ("等于", "不"))     # 等式记号+否定守卫(排 !=/<=/>=/不等于)
_VALUE_SUFFIX = ("", "%", "倍")                 # 值后缀(封闭数学后缀;物理单位不收)
_COPULAS = ("是", "为", "等于")                 # 系词(汉语封闭语法类)
_COPULA_GUARDS = {"是": "但于就还若或要总却便乃即只",  # 连词/构形成素守卫(排「但是/于是/就是…」)
                  "为": "因认成作行以难无",            # (排「因为/认为/成为/作为…」)
                  "等于": "不"}
# C2 比较差值谓语:比 + ≤8 个非数字非界符非「比」字 + 多|少 紧邻绑定位收尾
# (「比…多/少」是汉语封闭比较句式;跨度内禁数字杀「比100多5」,禁再出现
# 「比」锚定最近比较比,杀「比较」的「比」跨接)
_COMPARATIVE_RE = re.compile(r"比[^0-9比，、。；,;“”（）():：]{0,8}[多少]$")


@dataclass(frozen=True)
class ResultEvidence:
    """X 取得「得到 X」authority 的证明(Trusted Source ≠ Trusted Derived Fact
    的最小操作化:#442 §四,Source provenance + Transformation validity =
    Derived fact authority)。

    可反查「X 凭什么取得 authority」:kind=哪条封闭语法 schema 出证;span=
    绑定位(X 所在数字段)在片内的位置;value=X 本身。不是 bool——弃锚(None)
    与「以何种结构出证」是两个审计面,Cost(FP)≫Cost(FN) 的 authority grant
    task 需要留证,不需要一个 True。"""

    kind: str                  # "explicit_equation_rhs" | "explicit_result_clause"
    span: tuple[int, int]      # 绑定位数字段在片段内的 (start, end)
    value: float               # X = float(step.value)

    def __post_init__(self) -> None:
        if self.kind not in ("explicit_equation_rhs", "explicit_result_clause"):
            raise ValueError(f"ResultEvidence.kind 不在两形态封闭集内:{self.kind!r}")


def _last_equation_marker(fragment: str) -> tuple[int, int] | None:
    """最后一个等式记号(位置,长度);否定形(!=/<=/>=/不等于)不算等式。"""
    best: tuple[int, int] | None = None
    for marker, guard in _EQ_GUARDS:
        for match in re.finditer(re.escape(marker), fragment):
            i = match.start()
            if i > 0 and fragment[i - 1] in guard:
                continue
            if best is None or i > best[0]:
                best = (i, len(marker))
    return best


def _unguarded_copula(seg: str) -> bool:
    """C1:当前从句内存在独立系词(是/为/等于),过构形成素守卫(宁过杀:
    「即是/就是」类真断言也被弃——fail-closed 方向,B1 残留 R1)。"""
    for i in range(len(seg)):
        for copula in _COPULAS:
            if seg.startswith(copula, i) and (i == 0 or seg[i - 1] not in _COPULA_GUARDS[copula]):
                return True
    return False


def result_evidence(fragment: str, value: str) -> ResultEvidence | None:
    """(#441 B′ containment)片段是否对 value=X 携带**结果断言证明**。

    不是「发现一个数字就证明它是结果」,而是**先找到结果陈述,再绑定这个数字**:
    非 None 才许 anchor 向学生断言「得到 X」;None = fail-closed(弃锚=少一个
    数值提示,不构成假教学)。绑定位(两形态共用)= 片内与 X 相等的最后一个
    ASCII 数字段——由 `_step_value_candidate` 取尾数的构造,这正是抽取发生的位置;片内
    无等于 X 的数字段 → 直接 None。

    形态 E(explicit_equation_rhs):最后一个等式记号(= / 等于,过否定守卫)
    的 RHS **首数** == X。「26÷3=8(套)…2(米)」绑首数不绑尾数——LHS=RHS
    断言的值是 RHS 头部;取尾恰是 `_step_value_candidate` 的错归因形态,允许尾数作证
    等于给已定性的错归因族发通行证。已知语义边界:定义式等式(「1寸=3.33厘米」)
    形态过、RHS 是换算常数非该步结果(语法 proof 看不见「定义 vs 计算」,
    B1 残留 R3;现 bank anchor 面零等式形态)。

    形态 C(explicit_result_clause):X(+至多一个封闭值后缀 %/倍;物理单位
    不收——开放类,收了就是词表化)收尾全片(操作叙述的数字后几乎总接续
    操作内容,值断言的值头收尾从句——区分两形态最强的单一结构信号),且
    绑定位所在当前从句满足其一:C1 独立系词(是/为/等于,构形成素守卫);
    C2 比较差值谓语(比…多/少,`_COMPARATIVE_RE`)。机械判据不枚举操作动词,
    只识别封闭断言模式——白名单不中即 None。

    禁演化成开放式结果谓词短语表(phrase-list DSL 红线):反例 #9
    「再求少10%的结果」含「结果」二字仍 None——「结果」在那里是求的宾语
    (操作叙述),词表方案(见「结果」即放行)必挂、结构方案能过。"""
    fragment = str(fragment)
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None                     # 非单数值(「8组,余5人」/单位文本):fail-closed
    hits = [m for m in _ASCII_NUMBER.finditer(fragment) if float(m.group()) == x]
    if not hits:
        return None
    site = hits[-1]                     # 绑定位:value 在片内的最后一次出现(= 抽取位)
    eq = _last_equation_marker(fragment)
    if eq is not None:
        rhs_numbers = _ASCII_NUMBER.findall(fragment[eq[0] + eq[1]:])
        if rhs_numbers and float(rhs_numbers[0]) == x:
            return ResultEvidence("explicit_equation_rhs", site.span(), x)
    if fragment[site.end():] not in _VALUE_SUFFIX:
        return None                     # C-终位前置:X(可带 %/倍)收尾全片
    head = max(fragment.rfind(d, 0, site.start()) for d in _CLAUSE_DELIMS) + 1
    seg = fragment[head:site.start()]   # 绑定位所在当前从句
    if _unguarded_copula(seg) or _COMPARATIVE_RE.search(seg):
        return ResultEvidence("explicit_result_clause", site.span(), x)
    return None
