"""领域侧答案归一资产(Trusted Completion Gate A 段,#414 设计件 §二/§三)。

等价类资产沿革(设计 §三审查修正⑥):全半角映射/空白剥离/数字抽取这一族
归一层,自 ER judge v2 的 answer_keys(edu_agent/evals/artifacts/er-judge-v2)
独立抽取重写为本模块,并补产品判定需要的等价类(千分位/分数/小数/百分号/
单位维度表)——**产品侧零 import eval/judge**;评测侧也不用本模块验产品
(防 common-mode false green),两侧独立维护、形态各自测试钉死。

本模块只放**确定性归一资产**(纯函数+纯常量),不含判定;判定在 completion.py。
零行为变化:纯新增,不接线,现有模块零 import 本模块。
"""

from __future__ import annotations

import re
from fractions import Fraction

# —— 全半角与符号映射(1:1 字符映射,保位:归一侧下标 = 原文下标)——
# U+FF01-FF5E 整段偏移到 ASCII;区间外高频符号单列(×·÷− 与全角空格)。
# ×/·→`*` 是独立乘法 token,绝不映射到字母 x(设计 §三:ASCII x 在本题域
# 是变量,合并=灾难性等价)。
_SYMBOL_MAP = {"×": "*", "·": "*", "÷": "/", "−": "-", "　": " "}

# short_text 无语义剥离集:标点与空白(数字/字母/运算符/汉字都是内容,不剥)。
_TEXT_STRIP = set("，。、；：！？,.;:!?\"'“”‘’()（）【】《》…—~～\t\n\r ")


def _halfwidth_char(char: str) -> str:
    """单字符全半角/符号归一(全角 ASCII 段偏移 + 少数区间外符号)。"""
    code = ord(char)
    if 0xFF01 <= code <= 0xFF5E:
        return chr(code - 0xFEE0)
    return _SYMBOL_MAP.get(char, char)


def halfwidth(text: str) -> str:
    """逐字符归一(1:1,不丢字符):归一文本与原文等长同位。

    verifier 用「同位」性质把归一侧命中直接映射回**原文 span**
    (CompletionEvidence.provenance.matched_span 是审计凭证,必须原文)。"""
    return "".join(_halfwidth_char(c) for c in str(text or ""))


def text_key(text: str) -> tuple[str, list[tuple[int, int]]]:
    """short_text 无语义归一:全半角 + 剥空白标点,仅此而已(设计 §三)。

    返回(键串, 键位→原文区间表):键串第 i 字对应原文区间表的第 i 项
    [start, end)。不做编辑距离、不做裸 substring、不做任何语义归一
    (NFKC 会把 ㎡ 折成 m2,属语义面,不用;全半角走显式字符表)。"""
    mapped = halfwidth(text)
    chars: list[str] = []
    spans: list[tuple[int, int]] = []
    for i, char in enumerate(mapped):
        if char in _TEXT_STRIP:
            continue
        chars.append(char)
        spans.append((i, i + 1))
    return "".join(chars), spans


# —— 数字等价类(千分位/分数/小数/百分号;exact Fraction,零默认容差)——
# 候选 token:可选负号(前邻非字母数字,二元减号不算负号)+ 整数段(可含
# 千分位逗号)+ 可选小数 + 可选分数分母 + 尾随单位(%/℃/ASCII/汉字,最长
# 6 字:平方厘米 4 字;超长/未知单位按不匹配处理,fail-closed)。
_NUMBER_TOKEN = re.compile(
    r"(?<![A-Za-z\d.])([-]?)(\d[\d,]*)(?:\.(\d+))?(?:/(\d+))?\s*"
    r"([%℃]|[A-Za-z\u4e00-\u9fa5]{1,6})?")
_THOUSANDS = re.compile(r"^\d{1,3}(,\d{3})+$")


def number_tokens(text: str) -> list[tuple[str, int, int, Fraction | None, str, list[str]]]:
    """扫文本里的数字 token:(原文 span, 起位, 止位, 等价类值, 单位, 归一标签)。

    起止位是**原文坐标**(归一 1:1 保位),verifier 用止位判「命中后紧跟
    自我否定」。归一标签 ∈ {全半角, 千分位, 小数去零, 分数形态, 百分号}
    ——空 = 原样。值解析失败(非法千分位分组/带小数的分数/除零)时值为
    None,该 token 不参与匹配(fail-closed)。用途:复合题结构识别
    (≥2 token = 多槽,设计 §三红线)+ numeric_with_unit 判定。
    %折入数值(单位记空):「50%」与「0.5」同值等价。"""
    mapped = halfwidth(text)
    tokens: list[tuple[str, int, int, Fraction | None, str, list[str]]] = []
    for match in _NUMBER_TOKEN.finditer(mapped):
        value, tags = _parse_number(match)
        unit = "" if match.group(5) == "%" else (match.group(5) or "")
        span = str(text or "")[match.start():match.end()]
        if any(0xFF01 <= ord(c) <= 0xFF5E for c in span):
            tags = ["全半角", *tags]
        tokens.append((span, match.start(), match.end(), value, unit, tags))
    return tokens


def _parse_number(match: re.Match) -> tuple[Fraction | None, list[str]]:
    """单个数字 token → 等价类归一值(exact Fraction,无默认容差)。"""
    negative, whole, decimal, denominator, _percent = match.groups()
    tags: list[str] = []
    digits = whole
    if "," in digits:
        if not _THOUSANDS.fullmatch(digits):
            return None, tags          # 1,00 / 12,34 非法分组:不是数字
        digits = digits.replace(",", "")
        tags.append("千分位")
    if decimal and denominator:
        return None, tags              # 1.5/2 带小数的分数:非规范形态
    try:
        if decimal:
            value = Fraction(int(digits + decimal), 10 ** len(decimal))
            if decimal.endswith("0"):
                tags.append("小数去零")
        elif denominator:
            value = Fraction(int(digits), int(denominator))
            tags.append("分数形态")
        else:
            value = Fraction(int(digits))
        if match.group(5) == "%":
            value /= 100
            tags.append("百分号")
    except (ValueError, ZeroDivisionError):
        return None, tags
    return (-value if negative else value), tags


# —— 单位维度表(同义/换算仅限同族;无默认容差,跨族不换算)——
# 设计 §三审查修正③:同义单位须**维度安全**的确定性转换。族内 scale 是换算
# 到族基准单位的精确倍率(Fraction);计数单位(只/本/人/组/岁…)不入表——
# 只认精确 token 相等,「3只」永不当「3本」。歧义单字(分=时间/人民币、
# 度=温度/角度)不换算或只收无歧义面:度按温度族 1:1(题库实测「25.8度」),
# 角度的「度」第二版再看;「分」两侧都不收(裸 token 精确匹配)。
UNIT_FAMILIES: dict[str, dict[str, Fraction]] = {
    "长度": {"米": Fraction(1), "m": Fraction(1), "分米": Fraction(1, 10),
             "dm": Fraction(1, 10), "厘米": Fraction(1, 100), "cm": Fraction(1, 100),
             "毫米": Fraction(1, 1000), "mm": Fraction(1, 1000),
             "千米": Fraction(1000), "km": Fraction(1000), "公里": Fraction(1000)},
    "面积": {"平方米": Fraction(1), "平方厘米": Fraction(1, 10000),
             "平方千米": Fraction(1000000), "公顷": Fraction(10000)},
    "质量": {"千克": Fraction(1), "kg": Fraction(1), "公斤": Fraction(1),
             "克": Fraction(1, 1000), "g": Fraction(1, 1000), "吨": Fraction(1000)},
    "时间": {"小时": Fraction(1), "时": Fraction(1), "h": Fraction(1),
             "分钟": Fraction(1, 60), "秒": Fraction(1, 3600), "s": Fraction(1, 3600)},
    "温度": {"度": Fraction(1), "摄氏度": Fraction(1), "℃": Fraction(1)},
    "人民币": {"元": Fraction(1), "角": Fraction(1, 10)},
}


def unit_family(unit: str) -> str | None:
    """单位所属维度族;不在任何族(计数单位/未知单位)返回 None。"""
    for family, members in UNIT_FAMILIES.items():
        if unit in members:
            return family
    return None


def units_compatible(truth_unit: str, student_unit: str) -> bool:
    """两单位是否可在同维度下换算:token 相等,或同族(跨族=维度不安全)。"""
    if truth_unit == student_unit:
        return True
    truth_family = unit_family(truth_unit)
    return bool(truth_family) and truth_family == unit_family(student_unit)


def unit_scale(unit: str) -> Fraction:
    """单位换算到族基准的倍率(不在族内的单位 scale 恒 1,只做 token 相等)。"""
    for members in UNIT_FAMILIES.values():
        if unit in members:
            return members[unit]
    return Fraction(1)


# —— 方程/比例符号归一(设计 §三 equation_form / ratio_or_expression)——
# ×/·→独立乘法 token `*`(绝不与变量 x 合并);=/＝→`==`(等号两侧同规范,
# 学生半角/全角等价);÷→/;全角括号/小数点→半角;剥空白。字符串等价,
# sympy 符号等价是第二版(§八 YAGNI)。冒号保留(比例 12:4=6:2 的结构符)。
_EQUATION_CHARS = re.compile(r"[0-9A-Za-z+\-*/=():.\s]+")


def symbol_key(text: str) -> str:
    """符号归一后的规范形:×·→*, ÷→/, =/＝(等号段)→==, 剥空白。"""
    mapped = halfwidth(text)
    return re.sub(r"\s+", "", re.sub(r"=+", "==", mapped))


def equation_candidates(text: str) -> list[tuple[str, int, int]]:
    """原文里的算式候选段:数字/字母/运算符/括号/冒号/空白的连续段(汉字断开)。

    返回(原文形态, 起位, 止位)——「我算出来是x-21=35」抽出 x-21=35。
    纯字母段(无数字)不是算式,跳过。"""
    mapped = halfwidth(text)
    out: list[tuple[str, int, int]] = []
    for match in _EQUATION_CHARS.finditer(mapped):
        if not re.search(r"\d", match.group(0)):
            continue
        out.append((str(text or "")[match.start():match.end()], match.start(), match.end()))
    return out
