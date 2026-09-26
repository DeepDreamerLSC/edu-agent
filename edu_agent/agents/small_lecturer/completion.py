"""Trusted Completion Gate A 段(#414 设计件 v3.1 §一/§二/§三,零行为变化)。

CompletionEvidence = 类型化完成事实:**任何成功的 completed 迁移都必须由
一条 trusted CompletionEvidence 授权,无 evidence 时 fail-closed;Evidence
不自行触发状态迁移——它是必要授权条件,不是「出现即完成」的充分条件**
(v3.1 §一核心不变量,iff 口径已删)。它只能来源于学生本轮消息经确定性
verifier 判定——LLM 输出/summary/guard 事件/教师转述的学生话都无构造权
(设计 §二不可构造面)。A 段只交付数据结构与六窄面判定函数,**不接
Kernel、不接 generation、不改任何现有模块行为**(§九:B/C 段另开 PR)。

复合题红线(§三审查修正②):多空/复合题**整体不判定**——answer_type 不在
六窄面(如 composite/open)调度即 None;numeric/short_text 的 ground_truth
含 ≥2 个数字 token 也按多槽拒判(「鸡3只兔5只」任何局部槽命中不构造
evidence,未来部分进度另建 ProgressEvidence,不偷「半完成态」)。

fail-closed 姿态贯穿:问句猜答(疑问标记/语气词)不构成证据(与 numeric
._declarative 同口径:问句里的数字不算已述,混合消息整条按问句处理);
**precision-first claim matching(v3.1 §三):value_match(答案值出现)≠
claim(学生提交该答案)——不确定表达(可能/还不确定/大概/也许)与候选间
「或/还是/要么」多候选消息级整条不判;命中前否定窗(不/没/非/未)六窄面
通用;numeric 仅认裸答案/裸答案+单位/声明式模板(答案是/所以是/应该是/
算出是 + #416 校准:结果是/总共是/就是/得到/得到了 与算式直给形
「860除以5是172」,新模板须为消息末数字 token)内的数字为 claim,不全文
扫数;命中前猜测词窗(我猜/估计)六窄面
通用,紧邻收尾之外另有声明模板交叠短距窗(#420:「我猜答案是X」的「是」
隔开猜测词与命中段,查模板之前剥标点末 2 字;正镜像「我先猜8。后来算出
是26只」的「猜」距模板 3 字,照常放行);候选连接窗(和/与/跟/及/同,
后须紧跟同面候选;跟/及/同 #420 并入同义连接词族)——#415 复审 P2-R1/R2
+#420 的有限枚举收窄,「和」不做消息级(「3和5相加,答案是8」类误伤
面),先猜后述照常命中;choice 多候选计数含合法集外字母(「B,E」枚举
一环,#420 P3)**;命中后紧跟自我否定(「…不对」「…错了」)不构成证据;
单位省略仅当题面 schema 显式 optional(审查修正③),同义单位仅维度安全
换算、无默认容差。

C′ stalled-completion mitigation(#423 终裁 2026-09-27,评论 5846062131):
verify_completion 的返回类型与判定行为**零变化**(仍 Evidence|None,零 Gate
精度变化);文末新增 CompletionRejectionReason/diagnose_rejection——证据
缺席时「值匹配但 claim 形态未认证」的**纯 diagnostic 拒因**(#453 实证两类
FN 形态:numeric「每份重0.4kg」答案嵌陈述无模板 / short_text「结论是无法
确定」答案先行理由后置),八条件全成立才产生、缺一不产生,共用本文件同一
解析/归一化/红线逻辑(不在 generation 里另建语义 classifier);它不是
authority——不触发任何状态迁移,唯一消费效果是 generation 的回复路由
(否定重置文案 → 一次轻量 restatement bridge,四铁律:不宣告正确/不补
canonical answer/不重新教学/不重置已有进展)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from .answer_normalizer import (
    UNIT_FAMILIES,
    equation_candidates,
    halfwidth,
    number_tokens,
    symbol_key,
    text_key,
    unit_scale,
    units_compatible,
)

# 设计 §二三:判定所用窄面。复合/开放式不在其内(整体 needs_review,
# 宁可 needs_review 不让 8B 猜完成态);~67% answer-key 形态可判是
# eligibility upper bound,非运行时完成覆盖率。
ANSWER_TYPES = (
    "numeric_with_unit",
    "choice_letter",
    "true_false",
    "equation_form",
    "ratio_or_expression",
    "short_text_exact",
)

# 问句/犹疑标记(消息级 fail-closed):「是不是25.8度?」「25.8度对吗」「对吧」
# 都不构成证据。口径对齐 numeric._declarative(问句猜答≠已述)+ ER judge
# 的疑问尾词族(吗/呢/什么/多少/哪/怎么/为什么),另收 吧/对不对/是不是。
# (「是多少」已删:子串被「多少」覆盖,ponytail delete。)
_QUESTION_MARKERS = ("?", "吗", "呢", "吧", "对不对", "是不是",
                     "多少", "什么", "怎么", "为什么", "哪")

# 不确定表达(v3.1 §三不可认证形态,消息级 fail-closed,六窄面前置):
# 「可能 是 6」「可能是B」「对,不过我不确定」——正确值出现但学生未落定,
# 整条不判(宁 needs_review)。有限枚举 marker,不是语义理解。
_UNCERTAIN_MARKERS = ("可能", "不确定", "大概", "也许")

# 多候选连接(候选间 或/还是/要么 形态,消息级 fail-closed):「B或D」「6 还是 7」
# 「要么B要么D」——未在候选间落终答,整条不判。要么与 或/还是 同族(专用
# 关联词,无「和」类误伤面,#415 复审 P2-R2 并入消息级 marker)。
_ALTERNATIVE_MARKERS = ("或", "还是", "要么")

# 猜测词(v3.1 §三不确定表达族的有限枚举扩展,#415 复审 P2-R1):六窄面的
# 命中前判定——「我猜是B」「估计是对」「我猜是x-21=35」「我猜是易变形」。
# 不进消息级(「我先猜8。后来算出是26只」的后继真声明必须放行)。numeric
# 的紧邻窗恒不触发(claim 前缀为空或收于模板,模板尾字 案/以/出 与猜测词
# 收尾互斥),经下方交叠窗(#420)生效;答案原文含「猜」不受影响:窗口只
# 看命中之前的前缀,裸答案/声明模板后接「猜灯谜」照常命中(过度拒绝≈零)。
_GUESS_MARKERS = ("猜", "猜是", "估计", "估计是")

# 猜测词×声明模板交叠短距窗(#420 六面缝):claim 模板的「是」把猜测词与
# 命中段隔开(「我猜答案是X」),紧邻窗扫不到——命中前缀收于声明式模板时,
# 改查模板之前(同剥空白标点)末 2 字内是否出现猜测词。距离上界 2 = 正镜像
# 边界:「我先猜8。后来算出是26只」的「猜」距模板 3 字(「8后来」=自带
# 宾语+时序词),必须放行——窗口再宽即误伤先猜后述。停顿标点(「我猜一下,
# 答案是X」)剥除后同窗覆盖;「的」插入(「我猜的答案是X」)距 1,亦收。
_GUESS_HEDGE = re.compile(r"(?:猜|估计).{0,2}$")

# 候选连接词 和/与/跟/及/同(#415 复审 P2-R2;跟/及/同 #420 并入——同义
# 候选连接词族,「对跟错」「x-21=35跟x+21=35」原在非 choice 面仍穿):
# 「B和D」「x-21=35和x+21=35」「对和错」。不可做消息级 marker(「和」
# 常用字,「3和5相加,答案是8」误伤面巨大),收窄为命中两侧紧邻窗:前剥
# 空白标点后以连接词收尾,或后剥空白标点后以 连接词+同面候选 起头
# (follower 防介词/分句误伤:「答案是6。跟同桌的一样」的「跟」后是
# 「同桌」非候选;「对及格」「我同意,答案是6」的 及/同 在词内不落窗尾,
# 照常命中)。choice 走存活字母计数(更宽,「B,D」「B,E」也拒,#420 P3
# 计数含合法集外字母);short_text 结构性免疫(左边界只认句首/是/为 +
# 整答收尾);numeric 前侧恒不触发(claim 前缀为空或收于模板「…是」),
# 仅后侧生效(邻接「6和7」另由单位吞噬意外挡住,本窗补标点分隔形态
# 「答案是6。和7」「26只,跟27只」)。
_JOIN_MARKERS = ("和", "与", "跟", "及", "同")
_JOIN_AFTER_NUMERIC = re.compile(r"[-\d]")            # 连接词后另一数字 token 起头
_JOIN_AFTER_SYMBOLIC = re.compile(r"[0-9A-Za-z(-]")   # 连接词后算式段起头
_JOIN_AFTER_TRUE_FALSE = re.compile(r"[对错没正√✓×✗✘]")  # 连接词后极性词起头

# 命中段之后的自我否定/犹疑(剥掉紧邻标点空白后起算):「x-21=35不对」。
_RETRACT_AFTER = ("不对", "不成立", "错了", "错的", "不是", "并不")

# 声明式模板(v3.1 §三可认证白名单 + #416 校准扩词,2026-09-24 人裁「按建议」):
# numeric 的数字 token 仅在裸答案(消息起头)或这些模板之后才算 claim——
# 「答案是6」「所以是0.5m」「应该是x-21=35」「算出是26只」;「我先猜8」的 8
# 不是 claim(「猜」不在白名单,不全文扫数)。#416 校准新增五模板(结果是/
# 总共是/就是/得到/得到了)统一受「命中 token 须为消息末数字 token」约束
# (3797 枚举形态对抗:「就是7，8，9…」的枚举员不得被收为 claim);动词类
# (就是/得到/得到了)否定窗加宽至 3 字;「得到的是」不收(5362 中间值形态,
# 收了会把第一个非终值变 claim);既有四模板语义与 2 字否定窗不动。
_CLAIM_TEMPLATES = ("答案是", "所以是", "应该是", "算出是",
                    "结果是", "总共是", "就是", "得到", "得到了")
# #416 校准新增模板(末 token 约束面)与动词类(3 字否定窗面)
_CALIBRATED_TEMPLATES = ("结果是", "总共是", "就是", "得到", "得到了")
_VERB_TEMPLATES = ("就是", "得到", "得到了")

# B-3 算式直给形「A〈运算〉B〈系词〉C」(#416 条件收:末 token 约束+交叠窗
# 接算式段起点前扫):运算词/系词均封闭集,运算词间不允许夹汉字名词
# (「1平方分米等于100」不匹配——3565 语义悬崖是特性不是缺陷);「等于」
# 单独(前缀无算式段)不匹配。仍是句法模板,无算术求值、无语义角色识别。
_ARITH_KIND = "<算式>"
_ARITH_DIRECT = re.compile(
    r"\d+(?:(?:加上|乘以|除以|减去|加|减|乘|除|[×÷+\-*/])\d+)+"
    r"(?:得出了|得到了|等于|就是|得出|得到|是)$")

_TRUE_RE = re.compile(r"(?<![不没非])对(?![不起吗吧呢])|正确|没错|√|✓|对的|对了")
_FALSE_RE = re.compile(r"不对|不正确|错误|错了|错的|✗|✘|×|(?<![不没])错")
_LETTER_RE = re.compile(r"(?<![A-Za-z])([A-Za-z])(?![A-Za-z])")

# 计数单位封闭集(#416 C-3a,2026-09-24 人裁):truth 单位 ∈ 此集 → spec 组装
# 侧置 unit_optional=True(计数语义下学生裸值可收,4248「36减24应该是12」
# 形态);「分」不入集(时间/人民币度量歧义,维持裸 token 精确匹配)。
# 集合归组装面消费(kernel._answer_spec),verifier 判定逻辑零依赖此授权。
COUNTING_UNITS = frozenset("名只本人个棵张条辆件次岁页种块支间道门步")

# #416 C-3b 单位剥除:truth 无单位而学生带已识别单位词(「应该是7200页」
# 「就是28平方分米」)→ 剥除比数值。必须限「已识别单位前缀 startswith+
# 单位串无 和/与/跟/及/同/或」:无条件剥除会打穿 neg-join-numeric×2(「6和7」
# 的「和」被单位捕获吞成未知单位,是既有意外防线);startswith 判据兼容贪婪
# 捕获的复合串(「种方案」「公顷啊」)。已识别单位 = 维度表全部成员 ∪ 计数
# 单位字(计数单位不入换算表,但作为单位词可剥)。
_UNIT_WORD_PREFIXES = tuple(sorted(
    ({unit for members in UNIT_FAMILIES.values() for unit in members}
     | set(COUNTING_UNITS)), key=len, reverse=True))


@dataclass(frozen=True)
class AnswerSpec:
    """题库 answer 的判定规格(ground_truth 的结构化形态,A 段由调用方组装)。

    answer_type 必须是 ANSWER_TYPES 之一;复合/开放题不造本规格(调度即
    None)。aliases 是**题库显式**声明的同义答案(short_text_exact 专用,
    不扩病例短语表,终裁红线)。unit_optional 是题面 schema 对单位省略的
    显式授权(默认 False:单位不可省)。letter_choices 是题面选项字母表
    (choice_letter 的合法集,必须非空——空=组装方违约,调度 None
    fail-closed;B 段组装方契约)。"""

    answer_type: str
    ground_truth: str
    aliases: tuple[str, ...] = ()
    unit_optional: bool = False
    letter_choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceProvenance:
    """证据溯源:指向题库 answer/answer schema(非病例短语)+ 命中原文。"""

    ground_truth_ref: str                  # 题库 answer 原文(判定基准,可追溯)
    matched_span: str                      # 学生消息中命中的原文片段(审计凭证)
    normalization: tuple[str, ...] = ()    # 施加的归一(如千分位/分数形态);空=原样


@dataclass(frozen=True)
class CompletionEvidence:
    """学生本轮消息经确定性 verifier 命中的完成事实(类型化,设计 §二)。

    **生命周期:turn-scoped / ephemeral**——evidence 只对当前 student turn
    生成、当轮消费、跨轮不复用:上一轮已验证的答案在下一轮确认时**不构成**
    证据,该轮需重新命中(§二 v1 显式设计选择,保守口径)。

    不可构造面(运行时红线):source 恒为 "student"、verdict 恒为
    "matched"、answer_type 必须在六窄面内——LLM 输出/summary/guard 事件/
    教师转述均不得构造本类型(A 段以构造期校验钉死,B 段接线时消费侧只认
    verify_completion 产物)。"""

    source: str
    turn_id: int
    answer_type: str
    verdict: str
    verifier: str
    provenance: EvidenceProvenance

    def __post_init__(self) -> None:
        if self.source != "student":
            raise ValueError("CompletionEvidence.source 恒为 student(设计 §二不可构造面)")
        if self.verdict != "matched":
            raise ValueError("CompletionEvidence.verdict 恒为 matched(未匹配即无证据)")
        if self.answer_type not in ANSWER_TYPES:
            raise ValueError(f"CompletionEvidence.answer_type 必须是六窄面之一:{ANSWER_TYPES}")


@dataclass(frozen=True)
class CompletionRejectionReason:
    """completion gate 拒绝路径的拒因诊断(#423 C′ 终裁,2026-09-27)。

    **纯 diagnostic,零 authority(权限分级铁律)**:CompletionEvidence 是
    state authority(completed 迁移的必要授权);本类型只回答「为什么这一轮
    没有证据」——reason 在场**不触发任何状态迁移、不进任何判定口径**,也
    绝不被当作 trusted signal 消费(#448 §五 verified_complete 处理「已认证
    完成事实」,本类型处理「未认证但存在窄定义 completion candidate 的拒绝
    原因」,两者权限等级不同,命名不得复用)。唯一消费效果:generation 的
    回复路由把 reset-to-first-step 换成一次轻量 restatement bridge(四铁律:
    不宣告正确/不补 canonical answer/不重新教学/不重置已有进展)。

    matched_value 是学生消息中值命中的**原文片段**(审计凭证,学生自己的
    话——不是 canonical answer;信号不含题库答案,塞答案=新 answer-leak 面)。
    reason_type 恒为单值:当前唯一形态是「值匹配但 claim 形态未认证」。"""

    reason_type: str
    answer_type: str
    matched_value: str
    turn_id: int

    def __post_init__(self) -> None:
        if self.reason_type != "value_matched_but_claim_uncertified":
            raise ValueError("CompletionRejectionReason.reason_type 恒为 "
                             "value_matched_but_claim_uncertified(C′ 单一形态)")
        if self.answer_type not in ANSWER_TYPES:
            raise ValueError(f"CompletionRejectionReason.answer_type 必须是六窄面之一:{ANSWER_TYPES}")


def _is_question(message: str) -> bool:
    """问句/犹疑消息判定(消息级 fail-closed):末尾问号或含疑问标记。"""
    mapped = halfwidth(message).rstrip()
    return mapped.endswith("?") or any(m in mapped for m in _QUESTION_MARKERS)


def _is_uncertain(message: str) -> bool:
    """不确定表达判定(消息级 fail-closed,六窄面前置):「可能是6」
    「6 还不确定」——正确值出现但学生未落定,整条不判(v3.1 §三)。"""
    return any(m in message for m in _UNCERTAIN_MARKERS)


def _is_alternatives(message: str) -> bool:
    """多候选判定(消息级 fail-closed,候选间 或/还是/要么 形态):「B或D」
    「6 还是 7」「要么B要么D」——未在候选间落终答,整条不判(v3.1 §三)。"""
    return any(m in message for m in _ALTERNATIVE_MARKERS)


def _prefix_key(message: str, start: int) -> str:
    """命中起位之前(剥空白标点)的键串:否定窗/claim 判定的共用前缀。"""
    key, _ = text_key(str(message)[:start])
    return key


def _negated(message: str, start: int, width: int = 2) -> bool:
    """命中前否定窗(六窄面通用,short_text 原口径推广):命中起位之前
    剥空白标点的末 2 字含 不/没/非/未——「不是B」「我不选B」「不是x-21=35」
    「不是6。我觉得是5」整条不判(v3.1 §三否定句不可认证)。#416 校准:
    动词类新模板/算式直给形加宽至 3 字(「就没得到400」「答案不就是6」的
    否定字紧贴模板前,2 字窗只见模板尾即穿透);既有模板维持 2 字
    (gold pos/negation 系列不回归)。"""
    prefix = _prefix_key(message, start)
    return any(n in prefix[-width:] for n in "不没非未")


def _claim_match(message: str, start: int) -> tuple[str, int] | None:
    """数字 token 的 claim 形态与交叠窗扫描止点(v3.1 §三白名单 + #416 校准):
    (形态, head_end)。形态 ""=裸答案(消息以答案起头);声明式模板串=前缀
    剥空白标点后以该模板收尾;_ARITH_KIND=算式直给形(B-3)。head_end =
    模板/算式段起位(猜测词交叠窗改查此前的前缀,#420 口径延伸到新模板
    与算式段:「我猜结果是52」「我猜860除以5是172」照拦)。None=非 claim。"""
    prefix = _prefix_key(message, start)
    if not prefix:
        return "", 0
    for template in _CLAIM_TEMPLATES:
        if prefix.endswith(template):
            return template, len(prefix) - len(template)
    arith = _ARITH_DIRECT.search(prefix)
    if arith is not None:
        return _ARITH_KIND, arith.start()
    return None


def _stripped_tail(message: str, end: int) -> str:
    """命中段止位之后剥掉紧邻空白标点的余文(撤回窗/连接窗共用)。"""
    return re.sub(r"^[\s,，。、;；:：!！?？]+", "", str(message)[end:])


def _retracted(message: str, end: int) -> bool:
    """命中段止位之后紧跟自我否定(剥标点空白后):「25.8度,不对」。"""
    tail = _stripped_tail(message, end)
    return bool(tail) and (tail[:2] in _RETRACT_AFTER or tail[0] in "吗吧呢")


def _guessed(message: str, start: int) -> bool:
    """命中前猜测词窗(P2-R1,六窄面):命中起位之前剥空白标点后以猜测词
    收尾(「我猜是B」),或收于声明式模板/算式直给形且其之前末 2 字内有
    猜测词(#420 交叠缝:「我猜答案是B」——模板的「是」隔开猜测词与命中
    段;#416 延伸:「我猜结果是52」「我猜860除以5是172」照拦——B-3 交叠窗
    接算式段起点前扫);逐命中判定(与 _negated 同为窗口而非消息级),
    后继命中不受影响。"""
    prefix = _prefix_key(message, start)
    if prefix.endswith(_GUESS_MARKERS):
        return True
    match = _claim_match(message, start)
    if match is None or not match[0]:
        return False
    _kind, head_end = match
    return bool(_GUESS_HEDGE.search(prefix[:head_end]))


def _joined(message: str, start: int, end: int,
            follower: re.Pattern[str]) -> bool:
    """命中是候选枚举一环(P2-R2,和/与 紧邻连接):前剥空白标点后以
    和/与 收尾,或余文剥空白标点后以 和/与+同面候选(follower)起头
    ——「x-21=35和x+21=35」「答案是6。和7」,而介词/分句「和」不误伤。"""
    if _prefix_key(message, start).endswith(_JOIN_MARKERS):
        return True
    tail = _stripped_tail(message, end)
    return any(tail.startswith(m) and follower.match(tail[len(m):].lstrip())
               for m in _JOIN_MARKERS)


def _single_number(ground_truth: str) -> tuple[str, Fraction, str] | None:
    """ground_truth 恰含一个数字 token 时返回(原文形态, 等价类值, 单位);
    0 个=非本窄面,≥2 个=多槽复合(红线:整体不判定),都返回 None。"""
    tokens = [t for t in number_tokens(ground_truth) if t[3] is not None]
    if len(tokens) != 1:
        return None
    span, _start, _end, value, unit, _tags = tokens[0]
    return span, value, unit


def counting_unit_optional(ground_truth: str) -> bool:
    """#416 C-3a(spec 组装侧,verifier 零改动):truth 单位 ∈ 计数单位封闭集
    → 题面授权单位省略(「12名」的学生裸值「36减24应该是12」可收)。供
    kernel._answer_spec 组装时消费;「分」不入集(度量歧义)。"""
    truth = _single_number(ground_truth)
    return truth is not None and truth[2] in COUNTING_UNITS


def _strippable_unit(unit: str) -> bool:
    """truth 无单位时学生侧尾单位词可剥(C-3b 限定):已识别单位前缀
    startswith(贪婪捕获吞「种方案」「公顷啊」等复合串亦认)+ 单位串不含
    候选连接字(「6和7」的「和」被吞成单位是 neg-join 两钉的意外防线)。"""
    return (not any(marker in unit for marker in _JOIN_MARKERS)
            and unit.startswith(_UNIT_WORD_PREFIXES))


def _unit_value_match(truth_unit: str, truth_value: Fraction, unit_optional: bool,
                      value: Fraction, unit: str) -> bool:
    """数值+单位判定:学生带单位 → token 相等或同族维度安全换算(零容差);
    truth 无单位而学生带已识别单位词 → 剥除比数值(C-3b:答案键裸值 +
    「7200页」「28平方分米」形态,前缀/连接字限定见 _strippable_unit);
    单位省略 → 仅 schema 显式 optional 且数值与题面**原值同口径**相等
    (「2千米」的省略形态是 2,不是 2000——省略不换算,审查修正③)。"""
    if unit:
        if not truth_unit:
            return _strippable_unit(unit) and value == truth_value
        return (units_compatible(truth_unit, unit)
                and value * unit_scale(unit) == truth_value * unit_scale(truth_unit))
    if truth_unit and not unit_optional:
        return False
    return value == truth_value


def _numeric_tags(span: str, truth_span: str, tags: list[str],
                  unit: str, truth_unit: str,
                  stripped: bool = False) -> tuple[str, ...]:
    """归一标签:原样命中=空;否则记学生侧数字归一 + 单位判定面。"""
    if span == truth_span:
        return ()
    applied = list(tags)
    if stripped:
        applied.append("单位剥除")
    elif unit and unit != truth_unit:
        applied.append("单位同义换算")
    if not unit and truth_unit:
        applied.append("单位省略(schema授权)")
    return tuple(applied)


def _verify_numeric_with_unit(spec: AnswerSpec, message: str) -> tuple[str, tuple[str, ...]] | None:
    """数值+单位窄面:数字等价类归一(千分位/分数/小数/百分号,零容差)+
    单位判定(相等,或同族维度安全换算;省略仅 schema 显式 optional)。

    precision-first(v3.1 §三):仅 claim token 参与判定——消息起头的裸
    答案/裸答案+单位,或声明式模板之后的数字;不全文扫数(「我先猜8。
    后来算出是26只」里「猜」的 8 不算提交)。claim token 的声明模板之前
    短距内有猜测词(「我猜答案是26只」,#420 交叠缝)也是猜测陈述,非
    提交;被 和/与/跟/及/同 连接到另一数字(「答案是6。和7」,P2-R2)
    也是候选枚举一环,非终答。#416 校准:新增模板与算式直给形
    (结果是/总共是/就是/得到/得到了/「860除以5是172」)的命中还须是
    **消息末数字 token**(枚举员/中间值非终答:「就是7，8，9…」「3乘4是12,
    再用12除以6是2」拒),动词类与算式系词否定窗 3 字(见 _negated)。"""
    truth = _single_number(spec.ground_truth)
    if truth is None:
        return None
    truth_span, truth_value, truth_unit = truth
    tokens = number_tokens(message)
    last_end = max((token[2] for token in tokens), default=-1)
    for span, start, end, value, unit, tags in tokens:
        claim = _claim_match(message, start)
        if value is None or claim is None:
            continue                      # 非 claim token(「猜8」):值对也不判
        kind = claim[0]
        if (kind in _CALIBRATED_TEMPLATES or kind == _ARITH_KIND) and end != last_end:
            continue                      # 校准新模板/算式直给形:非消息末数字
                                         # token(枚举员/中间值)不算终答
        if _guessed(message, start):
            continue                      # 「我猜答案是8」(#420):猜测非提交
        if _joined(message, start, end, _JOIN_AFTER_NUMERIC):
            continue                      # 候选连接(「答案是6。和7」):枚举非终答
        stripped = not truth_unit and bool(unit)
        if not _unit_value_match(
                truth_unit, truth_value, spec.unit_optional, value, unit):
            continue
        width = 3 if kind in _VERB_TEMPLATES or kind == _ARITH_KIND else 2
        if _negated(message, start, width) or _retracted(message, end):
            continue                      # 命中前否定/命中后自我否定:不构成证据
        return span, _numeric_tags(span, truth_span, tags, unit, truth_unit, stripped)
    return None


def _verify_choice_letter(spec: AnswerSpec, message: str) -> tuple[str, tuple[str, ...]] | None:
    """选项字母窄面:字母精确匹配(大小写敏感),合法集=题面选项字母表。

    letter_choices 必须非空(B 段组装方契约):空=合法集缺失,调度 None
    fail-closed,不静默跳过合法集校验。多候选(#415 复审 P2-R2+#420 P3):
    消息内 ≥2 个未被否定/未撤回的不同字母(「B和D」「B,D」「要么B要么D」;
    合法集外字母同属枚举一环,「B,E」也拒——两字母并列即未落终答,与
    E 是否在题面选项内无关)=未落终答,整面不判;「不选B,选A」「A不对,
    是B」的否定/撤回字母不计,修正后终选照常命中。命中前猜测词窗
    (P2-R1+#420):「我猜是B」「我猜答案是B」非提交。#416 C-4 算式变量
    豁免:字母落在含数字的 equation 候选段内(2n、2n+1 的 n)视为变量,
    不计存活、不作命中——「偶数表示为2n…所以答案应该是选B」的 n 不与 B
    并列;顺带关闭「2B+1是奇数,题目说的对」的 B 被当选项命中的误放面
    (变量是算式记号,非答案)。"""
    letters = [a for a in halfwidth(spec.ground_truth) if a.isascii() and a.isalpha()]
    if len(letters) != 1:
        return None                       # 非单字母答案:不属本窄面(fail-closed)
    truth_letter = letters[0]
    if not spec.letter_choices or truth_letter not in spec.letter_choices:
        return None                       # 合法集缺失/答案字母不在题面选项字母表内
    variable_zones = [(seg_start, seg_end)
                      for _seg, seg_start, seg_end in equation_candidates(message)]
    hits = [(m.group(1), m.start(), m.end(),
             not _negated(message, m.start()) and not _retracted(message, m.end()))
            for m in _LETTER_RE.finditer(halfwidth(message))
            if not any(seg_start <= m.start() < seg_end
                       for seg_start, seg_end in variable_zones)]
    surviving = {letter for letter, _s, _e, alive in hits if alive}
    if len(surviving) >= 2:
        return None                       # 多候选:≥2 个存活字母(不限合法集,
                                         # 「B,E」枚举一环同拒,#420 P3)未落终答
    for letter, start, end, alive in hits:
        if letter != truth_letter or not alive or _guessed(message, start):
            continue                      # 非答案字母/已否定撤回/猜测(大小写敏感)
        span = message[start:end]
        tags = ("全半角",) if any(0xFF01 <= ord(c) <= 0xFF5E for c in span) else ()
        return span, tags
    return None


def _true_false_value(text: str) -> bool | None:
    """对/错/√/× 映射:先认否定形(不对/不正确含「对」「正确」字面)。"""
    if _FALSE_RE.search(text):
        return False
    if _TRUE_RE.search(text):
        return True
    return None


def _verify_true_false(spec: AnswerSpec, message: str) -> tuple[str, tuple[str, ...]] | None:
    """判断窄面(类型来自 answer schema/spec 声明,非题面文字猜——v3.1
    二审 P1-②口径):对/错/√/× 映射,否定形先判。"""
    truth = _true_false_value(spec.ground_truth)
    if truth is None:
        return None
    matched = _FALSE_RE.search(message) if not truth else _TRUE_RE.search(message)
    if matched is None:
        return None
    if (_negated(message, matched.start()) or _retracted(message, matched.end())
            or _guessed(message, matched.start())
            or _joined(message, matched.start(), matched.end(), _JOIN_AFTER_TRUE_FALSE)):
        return None                       # 「不是对」「我猜是对」「对和错」:不构成证据
    return matched.group(0), ()


def _verify_symbolic(spec: AnswerSpec, message: str) -> tuple[str, tuple[str, ...]] | None:
    """equation_form / ratio_or_expression 共用:符号归一后整段字符串等价。

    ×/·→`*`(独立乘法 token,绝不与变量 x 合并);=/＝→==;÷→/;剥空白。
    「3×4=12」与「3x4=12」**不相等**——x 是变量不是乘号(审查修正①)。
    命中 span 剥尾随空白(matched_span 是审计凭证,不得带 'x-21=35 ' 尾巴)。"""
    truth_key = symbol_key(spec.ground_truth)
    if not truth_key:
        return None
    for span, start, end in equation_candidates(message):
        if symbol_key(span) != truth_key:
            continue
        if _negated(message, start) or _retracted(message, end):
            continue                      # 命中前否定/「x-21=35不对」已撤回
        if _guessed(message, start) or _joined(message, start, end, _JOIN_AFTER_SYMBOLIC):
            continue                      # 「我猜是x-21=35」/和连接候选枚举(P2-R1/R2)
        span = span.rstrip()              # 剥尾随空白(候选段含空白字符)
        tags = () if symbol_key(span) == span else ("符号归一",)
        return span, tags
    return None


def _shorttext_bounds(key_message: str,
                      key_candidate: str) -> tuple[int, int] | None:
    """whole-answer 命中键位区间 [start, stop) 与左边界核验:直收尾=整答
    收尾,左边界句首或断言系词(是/为)——「容易变形」不得经后缀包含命中
    「易变形」,变体只能走题库显式 alias;#416 C-2 配对尾框「用X来表示/
    用X表示」(「这应该用分数来表示。」)仅在左边界恰为「用」时接受,
    通用左边界(是/为)不放宽。"""
    if key_message.endswith(key_candidate):
        start = len(key_message) - len(key_candidate)
        boundary = key_message[start - 1] if start else ""
        if not boundary or boundary in "是为":
            return start, len(key_message)
        return None
    for frame in ("来表示", "表示"):
        if not key_message.endswith(frame):
            continue
        stop = len(key_message) - len(frame)
        if not key_message[:stop].endswith(key_candidate):
            continue
        start = stop - len(key_candidate)
        boundary = key_message[start - 1] if start else ""
        if boundary == "用":
            return start, stop
    return None


def _verify_short_text_exact(spec: AnswerSpec, message: str) -> tuple[str, tuple[str, ...]] | None:
    """短文本窄面:normalized **whole-answer** exact / 题库显式 alias。

    仅无语义归一(全半角/空白/标点);命中必须是消息末段的完整答案断言
    (居中出现=裸 substring,不判;#416 C-2 尾框「用X来表示/用X表示」是
    唯一例外形态,配对左边界「用」);命中前否定窗(不/没/非/未,六窄面
    通用 _negated——「不是易变形」不得因包含「易变形」命中,审查修正④)
    与猜测词窗(「我猜是易变形」,P2-R1);和/与 连接候选结构性免疫——
    左边界只认句首/断言系词(是/为)、右端必须整答收尾,「…和易变形」
    进不了命中位。ground_truth 含 ≥2 数字 token = 多槽复合,整体不判定
    (红线)。"""
    if len([t for t in number_tokens(spec.ground_truth) if t[3] is not None]) >= 2:
        return None
    key_message, spans = text_key(message)
    for candidate in (spec.ground_truth, *spec.aliases):
        key_candidate, _ = text_key(candidate)
        if not key_candidate:
            continue
        bounds = _shorttext_bounds(key_message, key_candidate)
        if bounds is None:
            continue
        start, stop = bounds
        begin, last = spans[start][0], spans[stop - 1][1]
        # 否定窗口:命中前 2 字(剥空白标点)含 不/没/非/未(「不是易变形」)。
        if _negated(message, begin):
            continue
        if _guessed(message, begin):
            continue                      # 「我猜是易变形」:猜测陈述非提交(P2-R1)
        span = str(message)[begin:last]
        tags: list[str] = []
        if any(0xFF01 <= ord(c) <= 0xFF5E for c in span):
            tags.append("全半角")
        if len(span) != len(key_candidate):
            tags.append("剥空白标点")     # 命中段内剥过空白/标点
        return span, tuple(tags)
    return None


_VERIFIERS = {
    "numeric_with_unit": _verify_numeric_with_unit,
    "choice_letter": _verify_choice_letter,
    "true_false": _verify_true_false,
    "equation_form": _verify_symbolic,
    "ratio_or_expression": _verify_symbolic,
    "short_text_exact": _verify_short_text_exact,
}


def verify_completion(spec: AnswerSpec, student_message: str | None,
                      turn_id: int) -> CompletionEvidence | None:
    """六窄面调度:命中返回 CompletionEvidence,否则 None(整体不判定)。

    turn-scoped:只判 student_message(本轮学生原文)——上一轮的证据不进
    本轮,跨轮不复用(§二);turn_id 标记证据归属轮。复合/开放/未知
    answer_type、空消息、问句猜答、不确定表达(可能/还不确定/大概/也许)、
    多候选(候选间 或/还是/要么)一律 None(fail-closed,B 段 Kernel 据此
    拒 completed 迁移)。B 段接线前本函数无调用方;#416 缺口闭环**有意
    收窄**判定行为:非 numeric 五面的猜测词(我猜/估计)与 和/与 连接
    多候选改判 None(P2-R1/R2);#420 再收窄:猜测词×声明模板交叠
    (「我猜答案是X」)六面改判 None(猜测词窗经交叠短距窗扩至 numeric),
    候选连接词并入 跟/及/同,choice 多候选计数含合法集外字母(「B,E」),
    正例边界见 tests/teaching/test_completion_boundary_gold.py。"""
    if spec.answer_type not in _VERIFIERS:
        return None                       # 复合/开放/未知窄面:整体 needs_review
    message = str(student_message or "")
    if (not message.strip() or not spec.ground_truth.strip()
            or _is_question(message) or _is_uncertain(message)
            or _is_alternatives(message)):
        return None
    hit = _VERIFIERS[spec.answer_type](spec, message)
    if hit is None:
        return None
    span, tags = hit
    return CompletionEvidence(
        source="student",
        turn_id=turn_id,
        answer_type=spec.answer_type,
        verdict="matched",
        verifier=spec.answer_type,
        provenance=EvidenceProvenance(
            ground_truth_ref=spec.ground_truth, matched_span=span, normalization=tags),
    )


# ---------------------------------------------------------------------------
# C′ stalled-completion mitigation(#423 终裁 2026-09-27,评论 5846062131)
#
# #453 实证:学生完整作答但句式未命中 claim 白名单(答案嵌陈述无模板词 /
# 答案先行理由后置)→ 无 CompletionEvidence → gate 拒 → Tutor 输出否定重置
# 文案(C24 形态)。C′ 不动 Gate(零精度变化),只在证据缺席时暴露一个
# current-turn、read-only、non-authoritative 拒因。**与现有 verifier 共用
# 同一解析/归一化/红线逻辑**(同一 number_tokens/text_key/_unit_value_match/
# _shorttext_bounds 与同款窗口守卫),不在 generation 里另建语义 classifier。
# ---------------------------------------------------------------------------


def _diagnose_numeric_with_unit(spec: AnswerSpec, message: str) -> str | None:
    """numeric 面拒因扫描:存在数字 token 经同一 _unit_value_match 命中 truth
    (条件③),该 token 的猜测/连接/否定/撤回窗全过(条件⑤⑥⑦,逐命中),
    且 _claim_match 为 None(条件⑧:非裸答案/声明模板/算式直给位——**值出现
    了但 claim 形态未认证**,#453「每份重0.4kg」形态)。claim 位在场仍无证据
    的消息(校准模板非末 token 的枚举/中间值形态)失败在别的面,不属「唯一
    缺口」,不产生拒因。多槽复合(truth ≥2 数字 token)与 verifier 同口径
    整体不判定。否定窗取最宽 3 字(动词类模板口径;无 claim kind 可依,
    保守方向)。"""
    truth = _single_number(spec.ground_truth)
    if truth is None:
        return None
    _truth_span, truth_value, truth_unit = truth
    for span, start, end, value, unit, _tags in number_tokens(message):
        if value is None or not _unit_value_match(
                truth_unit, truth_value, spec.unit_optional, value, unit):
            continue                      # 条件③:值/单位确实匹配(同一判定面)
        if (_guessed(message, start)      # 条件⑤:逐命中猜测窗(「我猜0.4kg」)
                or _joined(message, start, end, _JOIN_AFTER_NUMERIC)   # 条件⑦紧邻连接
                or _negated(message, start, 3)        # 条件⑥:命中前否定窗(最宽)
                or _retracted(message, end)):         # 条件⑥:命中后自我撤回
            continue
        if _claim_match(message, start) is not None:
            continue                      # 条件⑧:claim 位在场——非「claim 未认证」
        return span
    return None


# 文本面「同面候选」无字符类判据:连接词后任何非空后继都按候选枚举一环拦
# (deny-only 方向,宁可漏发 bridge 不误发;verifier 的 short_text 面靠
# 「末段整答收尾」结构性免疫连接窗,本诊断看任意出现位,免疫不成立须显式补)。
_JOIN_AFTER_TEXT = re.compile(r".")


def _diagnose_short_text_exact(spec: AnswerSpec, message: str) -> str | None:
    """short_text 面拒因扫描:题库 truth/显式 alias 经同一 text_key 归一后在
    消息中出现(条件③),该出现位的否定/猜测/连接窗全过(条件⑤⑥⑦),且不在
    认证命中位(条件⑧:_shorttext_bounds——末段整答收尾+左边界句首/断言系词/
    「用X表示」尾框;#453「结论是无法确定」答案先行形态)。候选在认证位时,
    证据缺席的失败在否定/猜测等其他守卫,非「唯一缺口」,不产生拒因。多槽
    复合(truth ≥2 数字 token)同口径整体不判定。"""
    if len([t for t in number_tokens(spec.ground_truth) if t[3] is not None]) >= 2:
        return None
    key_message, spans = text_key(message)
    for candidate in (spec.ground_truth, *spec.aliases):
        key_candidate, _ = text_key(candidate)
        if not key_candidate:
            continue
        idx = key_message.find(key_candidate)
        if idx == -1:
            continue                      # 条件③:候选值未在消息中出现
        if _shorttext_bounds(key_message, key_candidate) is not None:
            continue                      # 条件⑧:认证位在场(失败在别的守卫)
        begin = spans[idx][0]
        last = spans[idx + len(key_candidate) - 1][1]
        if (_negated(message, begin) or _guessed(message, begin)
                or _joined(message, begin, last, _JOIN_AFTER_TEXT)):
            continue                      # 条件⑥⑤⑦:该出现位被红线拦
        return str(message)[begin:last]
    return None


# 仅 numeric/short_text 两面的 verifier 有 claim 位形态门(裸答案/声明模板位;
# 末段整答收尾+系词左界)。choice/true_false/equation/ratio 四面无此门——
# 值匹配且守卫全过即命中,「唯一失败=claim 形态未认证」结构性不可能,不进
# 诊断表(条件②在 dispatch 层收口:六窄面 ∩ 有 claim 门的面)。
_REJECTION_DIAGNOSES = {
    "numeric_with_unit": _diagnose_numeric_with_unit,
    "short_text_exact": _diagnose_short_text_exact,
}


def diagnose_rejection(spec: AnswerSpec | None, student_message: str | None,
                       turn_id: int) -> CompletionRejectionReason | None:
    """C′ 拒因诊断:**八条件全成立才产生,缺一不产生**(#423 终裁钉死):

    ① 有合法 answer_spec(spec None → None,fail-closed,不私造);
    ② answer_type 在可验证窄面且该面有 claim 形态门(复合/开放/未知 → None;
      choice/true_false/equation/ratio 结构性无「唯一失败=claim 形态」形态);
    ③ ground-truth/candidate 值确实匹配(value_match:同一归一/换算/等价判定,
      值不出现或不匹配 → None);
    ④ 非问句(同一 _is_question,消息级 fail-closed);
    ⑤ 非猜测/不确定(同一 _is_uncertain 消息级 + 逐命中猜测窗 _guessed);
    ⑥ 非否定/撤回(同一 _negated/_retracted 窗口);
    ⑦ 非多候选(同一 _is_alternatives 消息级 + 逐命中连接窗 _joined);
    ⑧ 唯一失败原因=claim 形态未认证(其他守卫全过;claim 位在场的证据缺席
      属别的失败面——枚举/中间值/否定/猜测——不产生拒因)。

    禁止清单(终裁原文):「我猜0.4kg」「不是0.4kg」「0.4kg还是0.5kg」
    「可能是0.4kg」及一切问句形态均不得产生拒因。与 verify_completion 的
    关系:共用同一解析/归一化/红线逻辑(单一实现),但 **verify_completion
    返回类型与行为零变化**——本函数由调用方在 Evidence 为 None 时选择性调用
    (kernel finish 拒绝路径 / prompting 装配侧重演),产物是 diagnostic/
    routing signal,不是 trusted signal,更不是 state authority。"""
    if spec is None or spec.answer_type not in _REJECTION_DIAGNOSES:
        return None                       # 条件①②:无声明面/复合红线/无 claim 门面
    message = str(student_message or "")
    if (not message.strip() or not spec.ground_truth.strip()
            or _is_question(message)      # 条件④:问句猜答不可认证
            or _is_uncertain(message)     # 条件⑤:不确定表达(消息级)
            or _is_alternatives(message)):
        return None                       # 条件⑦:候选间 或/还是/要么(消息级)
    span = _REJECTION_DIAGNOSES[spec.answer_type](spec, message)
    if span is None:
        return None
    return CompletionRejectionReason(
        reason_type="value_matched_but_claim_uncertified",
        answer_type=spec.answer_type,
        matched_value=span,
        turn_id=turn_id)
