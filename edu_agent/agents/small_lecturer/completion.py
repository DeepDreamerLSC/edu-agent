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
算出是)内的数字为 claim,不全文扫数;命中前猜测词窗(我猜/估计)六窄面
通用,紧邻收尾之外另有声明模板交叠短距窗(#420:「我猜答案是X」的「是」
隔开猜测词与命中段,查模板之前剥标点末 2 字;正镜像「我先猜8。后来算出
是26只」的「猜」距模板 3 字,照常放行);候选连接窗(和/与/跟/及/同,
后须紧跟同面候选;跟/及/同 #420 并入同义连接词族)——#415 复审 P2-R1/R2
+#420 的有限枚举收窄,「和」不做消息级(「3和5相加,答案是8」类误伤
面),先猜后述照常命中;choice 多候选计数含合法集外字母(「B,E」枚举
一环,#420 P3)**;命中后紧跟自我否定(「…不对」「…错了」)不构成证据;
单位省略仅当题面 schema 显式 optional(审查修正③),同义单位仅维度安全
换算、无默认容差。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from .answer_normalizer import (
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

# 声明式模板(v3.1 §三可认证白名单,有限枚举的句法模式):numeric 的数字
# token 仅在裸答案(消息起头)或这些模板之后才算 claim——「答案是6」
# 「所以是0.5m」「应该是x-21=35」「算出是26只」;「我先猜8」的 8 不是
# claim(「猜」不在白名单,不全文扫数)。
_CLAIM_TEMPLATES = ("答案是", "所以是", "应该是", "算出是")

_TRUE_RE = re.compile(r"(?<![不没非])对(?![不起吗吧呢])|正确|没错|√|✓|对的|对了")
_FALSE_RE = re.compile(r"不对|不正确|错误|错了|错的|✗|✘|×|(?<![不没])错")
_LETTER_RE = re.compile(r"(?<![A-Za-z])([A-Za-z])(?![A-Za-z])")


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


def _negated(message: str, start: int) -> bool:
    """命中前否定窗(六窄面通用,short_text 原口径推广):命中起位之前
    剥空白标点的末 2 字含 不/没/非/未——「不是B」「我不选B」「不是x-21=35」
    「不是6。我觉得是5」整条不判(v3.1 §三否定句不可认证)。"""
    prefix = _prefix_key(message, start)
    return any(n in prefix[-2:] for n in "不没非未")


def _is_claim(message: str, start: int) -> bool:
    """数字 token 是否学生的答案声明(v3.1 §三白名单):token 之前剥空白
    标点为空=裸答案/裸答案+单位(消息以答案起头),或以声明式模板
    (答案是/所以是/应该是/算出是)收尾——此外的数字出现不算提交。"""
    prefix = _prefix_key(message, start)
    return (not prefix
            or any(prefix.endswith(t) for t in _CLAIM_TEMPLATES))


def _stripped_tail(message: str, end: int) -> str:
    """命中段止位之后剥掉紧邻空白标点的余文(撤回窗/连接窗共用)。"""
    return re.sub(r"^[\s,，。、;；:：!！?？]+", "", str(message)[end:])


def _retracted(message: str, end: int) -> bool:
    """命中段止位之后紧跟自我否定(剥标点空白后):「25.8度,不对」。"""
    tail = _stripped_tail(message, end)
    return bool(tail) and (tail[:2] in _RETRACT_AFTER or tail[0] in "吗吧呢")


def _guessed(message: str, start: int) -> bool:
    """命中前猜测词窗(P2-R1,六窄面):命中起位之前剥空白标点后以猜测词
    收尾(「我猜是B」),或收于声明式模板且模板之前末 2 字内有猜测词
    (#420 交叠缝:「我猜答案是B」——模板的「是」隔开猜测词与命中段);
    逐命中判定(与 _negated 同为窗口而非消息级),后继命中不受影响。"""
    prefix = _prefix_key(message, start)
    if prefix.endswith(_GUESS_MARKERS):
        return True
    for template in _CLAIM_TEMPLATES:
        if prefix.endswith(template):
            return bool(_GUESS_HEDGE.search(prefix[: len(prefix) - len(template)]))
    return False


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


def _unit_value_match(truth_unit: str, truth_value: Fraction, unit_optional: bool,
                      value: Fraction, unit: str) -> bool:
    """数值+单位判定:学生带单位 → token 相等或同族维度安全换算(零容差);
    单位省略 → 仅 schema 显式 optional 且数值与题面**原值同口径**相等
    (「2千米」的省略形态是 2,不是 2000——省略不换算,审查修正③)。"""
    if unit:
        return (units_compatible(truth_unit, unit)
                and value * unit_scale(unit) == truth_value * unit_scale(truth_unit))
    if truth_unit and not unit_optional:
        return False
    return value == truth_value


def _numeric_tags(span: str, truth_span: str, tags: list[str],
                  unit: str, truth_unit: str) -> tuple[str, ...]:
    """归一标签:原样命中=空;否则记学生侧数字归一 + 单位判定面。"""
    if span == truth_span:
        return ()
    applied = list(tags)
    if unit and unit != truth_unit:
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
    也是候选枚举一环,非终答。"""
    truth = _single_number(spec.ground_truth)
    if truth is None:
        return None
    truth_span, truth_value, truth_unit = truth
    for span, start, end, value, unit, tags in number_tokens(message):
        if value is None or not _is_claim(message, start):
            continue                      # 非 claim token(「猜8」):值对也不判
        if _guessed(message, start):
            continue                      # 「我猜答案是8」(#420):猜测非提交
        if _joined(message, start, end, _JOIN_AFTER_NUMERIC):
            continue                      # 候选连接(「答案是6。和7」):枚举非终答
        if not _unit_value_match(
                truth_unit, truth_value, spec.unit_optional, value, unit):
            continue
        if _negated(message, start) or _retracted(message, end):
            continue                      # 命中前否定/命中后自我否定:不构成证据
        return span, _numeric_tags(span, truth_span, tags, unit, truth_unit)
    return None


def _verify_choice_letter(spec: AnswerSpec, message: str) -> tuple[str, tuple[str, ...]] | None:
    """选项字母窄面:字母精确匹配(大小写敏感),合法集=题面选项字母表。

    letter_choices 必须非空(B 段组装方契约):空=合法集缺失,调度 None
    fail-closed,不静默跳过合法集校验。多候选(#415 复审 P2-R2+#420 P3):
    消息内 ≥2 个未被否定/未撤回的不同字母(「B和D」「B,D」「要么B要么D」;
    合法集外字母同属枚举一环,「B,E」也拒——两字母并列即未落终答,与
    E 是否在题面选项内无关)=未落终答,整面不判;「不选B,选A」「A不对,
    是B」的否定/撤回字母不计,修正后终选照常命中。命中前猜测词窗
    (P2-R1+#420):「我猜是B」「我猜答案是B」非提交。"""
    letters = [a for a in halfwidth(spec.ground_truth) if a.isascii() and a.isalpha()]
    if len(letters) != 1:
        return None                       # 非单字母答案:不属本窄面(fail-closed)
    truth_letter = letters[0]
    if not spec.letter_choices or truth_letter not in spec.letter_choices:
        return None                       # 合法集缺失/答案字母不在题面选项字母表内
    hits = [(m.group(1), m.start(), m.end(),
             not _negated(message, m.start()) and not _retracted(message, m.end()))
            for m in _LETTER_RE.finditer(halfwidth(message))]
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


def _verify_short_text_exact(spec: AnswerSpec, message: str) -> tuple[str, tuple[str, ...]] | None:
    """短文本窄面:normalized **whole-answer** exact / 题库显式 alias。

    仅无语义归一(全半角/空白/标点);命中必须是消息末段的完整答案断言
    (居中出现=裸 substring,不判);命中前否定窗(不/没/非/未,六窄面
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
        if not key_candidate or not key_message.endswith(key_candidate):
            continue
        start = len(key_message) - len(key_candidate)
        # 左边界:句首或断言系词(是/为)——「容易变形」不得经后缀包含命中
        # 「易变形」,变体只能走题库显式 alias(whole-answer,非裸 substring)。
        boundary = key_message[start - 1] if start else ""
        if boundary and boundary not in "是为":
            continue
        begin, last = spans[start][0], spans[-1][1]
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
