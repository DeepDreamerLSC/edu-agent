"""ER judge v2——evidence-reuse 判分器语义边界窄修版(裁令④,2026-09-22)。

正本沿革:v1 = 判读员工件脚本 runs/scripts/unified_six_metrics_r3.py 的 ER 段
(r3 判读正本,untracked,随 r3 封存不动);edu_agent/evals/ 无 ER 对应面
(judge.py 是 93 面 rubric 模型判分,checks.py 是回归 check 注册表)——
故 v2 以 tracked 工件落库为本正本,判据代码与 v1 ER 段的逐条对照见 REPORT.md。

七点窄修(报告 §5 建议 → 实现落点;纪律:非 redesign,边界条件修正):
  1 指向同一命题(核心条件):whether 型问句必须有指向——问新对象/新计算不算
    ER;疑问句数字 ⊆ 学生上轮数字(无新求解要求)+ 内容锚定(数字±2 字局部
    上下文、或 ≥4 字公共 CJK 子串,出现在学生上轮)。
  2 doubt 词表拆分:质疑性(但/可是/你确定/肯定对)与确认性(是不是/一样吗/
    相同吗/对不对/对吗)分列;确认性词不单独触发(须过点 1 指向条件);问理由
    族(怎么想到)/问验证族(检查一下/验证一下/再算)/空话族(再想)移出。
  3 ACK 结构化:「是对的/很对/没错/完全正确」等显式承认结构 + 尾标签问句
    (对吧/对吗 类)→ 该轮不判 ER(承认后推进是 B-new 目标行为);显式承认
    **不豁免**指向性整句重问——口头承认+继续当未知=ER(B-old RETIRE 证据,
    675 口头承认+盘旋);v1 词面偶然否决(成立/棒/清楚)废除。
  4 答案字符串可见性:非数字终答(选项字母 A/B、文字结论「易变形」)同样进
    said 集合(字母须断言语境 答案是A/选A);含运算符的答案(12:4=6:2、
    x-21=35)须以关系形态进 said;纯数字答案剥枚举段/换算段后判定——
    因数列表、单位换算事实不污染分母(报告 §5.4.4)。
  5 repro 案进 ER 适用域:无 dataset form 标注但有答案的案(cross-stitch/
    ball-bounce/incident 类)按 form1 同形处理(学生已答导师仍盘旋正是其
    复现形态);form2(student_corrects_tutor)仍不进。
  6 真重复不被 stray-number/偶然 ACK 双否决豁免:同一问句(子句级相似度
    >0.85,回看 3 个导师轮)重复 → no-progress 族必计;stray 否决收紧为
    「导师轮明确纠正该 stray 数字」才算矛盾(学生给新例子不否决)。
  7 ER 与 no-progress 分族:ER=把已给目标信息当未知(指向性重问);no-progress
    =无增量重复推进(问句重复);重复命中优先落 no-progress 族,不与 ER 混计。
    checks.possible_no_progress_cycle(既有 no-progress 指标)不动。

零模型、stdlib only;输入 = 既有结果工件形态(transcript.turns[].student/tutor
+ case.question.{text,answer})。

provenance:holdout 标注时冻结 sha16=43ef6f0649bf1571(gold_labels_holdout
provenance 字段);入库版为过 ruff 复杂度关(02 §2.1)机械抽取 _repeat_reason
助手,判据语义零改动,四道验收输出与冻结版逐字节一致(见 REPORT.md)。
"""

from __future__ import annotations

import difflib
import re

FORM1 = "form1_student_answered_tutor_keeps_asking"

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_QUESTION_RE = re.compile(r"[?？]")
_SENT_TERM_RE = re.compile(r"([。!！?？;；])")
_CLAUSE_SPLIT_RE = re.compile(r"[,\uFF0C\u3001:\uFF1A]")
_INTERRO_TAIL_RE = re.compile(r"(?:[吗呢]|什么|多少|哪|怎么|为什么)$")

# —— 点 2:词表拆分(v1 _DOUBT_MARKERS 12 词 → 两族 + 移出三族)——
CHALLENGING_MARKERS = ("但", "可是", "你确定", "肯定对")  # 质疑性:可作 doubt 信号
CONFIRMING_MARKERS = ("是不是", "一样吗", "相同吗", "对不对", "对吗")  # 确认性:不单独触发
# 移出:怎么想到(问理由)/检查一下、验证一下、再算(问验证)/再想(空话 grounding)。

# v1 _REASK_RE 照录(值重问形态;须过点 1 指向条件)。
_REASK_RE = re.compile(r"(是多少|等于几|算出来是多少|填什么)")

# —— 点 3:ACK 结构化(v1 词面 19 词 → 显式承认结构)——
# 显式承认 = 对学生内容作「对/正确」述谓;口头夸奖(棒/清楚/关键)与偶然词
# (成立/说出了)不再是 ACK。显式承认豁免尾标签问句,不豁免指向性整句重问。
_ACK_STRUCT_RE = re.compile(
    r"(?:是对的|说对了|算对了|猜对了|完全正确|完全对|很对|没错|确实对|"
    r"(?:想法|思路|推理|换算|判断|方法|结论|方程|比例|答案|这一步|这步|这个)"
    r"(?:确实|真的|都)?(?:是对的|对了|正确|没错))")
# 尾标签问句:子句只剩 对吧/对吗 类(≤5 字),前面命题由导师自己断言。
_TAG_RE = re.compile(r"^(?:对吧|对吗|是吧|好吗|行吗|明白吗|懂了吗|清楚吗|对不对呀)[?？]?$")

# —— 点 6/7:问句重复(no-progress 族)——
REPEAT_SIM = 0.85
REPEAT_WINDOW = 3          # 回看导师轮数(866 t5→t6 相邻;2591/十字绣 t2→t4 距离 2)
REPEAT_CLAUSE_MIN_LEN = 8  # 「对吧?」类短标签不参与重复比对

# —— 点 4:said 可见性 ——
# 枚举段:≥3 个裸数字以 、/,/和 串联(因数列表);换算段:数字+单位+等于+数字
# (单位换算事实)。两者中的答案数字不进 said(报告 §5.4.4 分母去污染)。
_ENUM_RUN_RE = re.compile(r"(?:\d+(?:\.\d+)?[、,,\s和]{1,3}){2,}\d+(?:\.\d+)?")
_CONVERT_RE = re.compile(
    r"\d+(?:\.\d+)?[^\d,。;、]{0,4}(?:等于|=)\s*\d+(?:\.\d+)?[^\d,。;、]{0,4}")
# 关系骨架:答案含运算符(:=×÷-/)且含数字 → 归一后须以该形态出现在学生轮。
_RELATION_OPS = re.compile(r"[:=×÷*/\-]")
_FULLWIDTH = str.maketrans({"：": ":", "×": "*", "÷": "/", "－": "-", "　": ""})
# 字母终答断言语境(点 4):答案是A / 应该是A / 选A / 就是A。
_LETTER_ASSERT_RE = re.compile(r"(?:答案|应该|选项|就|是|选)是?\s*([A-D])(?![A-Za-z])")

_CORRECTION_RE = re.compile(r"不是|错了|不对|写错|应该是|纠正")


def _numbers(text: object) -> set[float]:
    return {float(m) for m in _NUMBER_RE.findall(str(text or ""))}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").translate(_FULLWIDTH))


def _question_field(case: dict, key: str) -> str:
    question = case.get("question")
    return str((question.get(key) if isinstance(question, dict) else None) or "")


def _cjk_grams(text: str, size: int = 4) -> set[str]:
    """CJK 4-gram 全集(内容锚定用;数字/标点不进 gram)。"""
    grams: set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fa5]+", str(text or "")):
        grams |= {run[i:i + size] for i in range(len(run) - size + 1)}
    return grams


def _sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _word_char(text: str, pos: int, before: bool) -> str:
    """取 pos 处字符若为词字符(CJK/字母/数字),越界/标点返回空(锚定窗口用)。"""
    if 0 <= pos < len(text):
        ch = text[pos]
        if ch.isalnum() or "\u4e00" <= ch <= "\u9fa5":
            return ch
    return ""


# ---------------------------------------------------------------------------
# 问句子句抽取
# ---------------------------------------------------------------------------

def interrogative_clauses(tutor: str) -> list[str]:
    """问句子句:? 段按逗号再切;留(a)段末子句(紧邻 ?)、(b)含确认性问词的
    子句、(c)以 吗/呢/什么/多少/哪/怎么/为什么 收尾的子句。

    段的疑问性由**未剥离的终止符**判定(? 段才算);非 ? 段仅 (b)(c) 类子句
    进入(如「…对吧。」收尾的无 ? 段)。非问子句(「你刚才说X」复读、导师
    自述命题)不进——点 3 尾标签豁免与重复检测都依赖这个边界。
    """
    clauses: list[str] = []
    parts = _SENT_TERM_RE.split(str(tutor or ""))
    for i in range(0, len(parts), 2):
        segment = parts[i].strip()
        terminator = parts[i + 1] if i + 1 < len(parts) else ""
        if not segment:
            continue
        subclauses = [p.strip() for p in _CLAUSE_SPLIT_RE.split(segment) if p.strip()]
        for j, part in enumerate(subclauses):
            is_final = j == len(subclauses) - 1
            if ((terminator in "?？" and is_final)
                    or any(m in part for m in CONFIRMING_MARKERS)
                    or _INTERRO_TAIL_RE.search(part)):
                clauses.append(part)
    return clauses


def is_tag(clause: str) -> bool:
    """尾标签问句(点 3):子句只剩 对吧/对吗 类。"""
    return bool(_TAG_RE.match(clause.strip()))


def _repeat_reason(clauses: list[str], prev_clauses: list[list[str]]) -> str | None:
    """点 6/7:问句重复(no-progress 族;不受 stray/ACK 否决)。

    回看窗内导师轮的长子句(≥REPEAT_CLAUSE_MIN_LEN)与本轮任一长子句
    相似度 >REPEAT_SIM 即命中;短标签(「对吧?」)不参与比对。
    """
    for clause in clauses:
        if len(clause) < REPEAT_CLAUSE_MIN_LEN:
            continue
        for past in prev_clauses[-REPEAT_WINDOW:]:
            if any(len(o) >= REPEAT_CLAUSE_MIN_LEN and _sim(clause, o) > REPEAT_SIM
                   for o in past):
                return f"问句重复(≈{clause[:24]}…)"
    return None


# ---------------------------------------------------------------------------
# 点 1:指向同一命题
# ---------------------------------------------------------------------------

def clause_targeted(clause: str, student_last: str) -> bool:
    """whether 型问句的指向判定:问新对象/新计算不算;数字 ⊆ 学生上轮数字
    (无新求解要求)+ 内容锚定。"""
    clause_nums = _numbers(clause)
    if not clause_nums <= _numbers(student_last):
        return False                       # 引入新数字 = 新求解要求 → 无指向
    if clause_nums:
        # 数字局部上下文锚定:数字带左/右 1-2 字**词字符**(CJK/字母/数字)的窗口
        # 至少一个出现在学生上轮(「100厘米」「100米」——单位算上下文,
        # 标点/裸数字不算)。
        for m in _NUMBER_RE.finditer(clause):
            num = m.group(0)
            left1 = _word_char(clause, m.start() - 1, True)
            left2 = _word_char(clause, m.start() - 2, True) + left1
            right1 = _word_char(clause, m.end(), False)
            right2 = right1 + _word_char(clause, m.end() + 1, False)
            windows = {w for w in (left1 + num, left2 + num, num + right1,
                                    num + right2, left1 + num + right1) if w}
            if not any(w in student_last for w in windows):
                return False
        return True
    # 无数字子句:≥4 字公共 CJK 子串(「答案是对的吗」↔ 学生「答案是A」)。
    return bool(_cjk_grams(clause) & _cjk_grams(student_last))


# ---------------------------------------------------------------------------
# 点 4:said(答案可见性)——答案以「主张形态」进 said
# ---------------------------------------------------------------------------

def answer_keys(case: dict) -> dict:
    """从 case 提取答案可见性键:数字集/关系骨架/字符串键。"""
    answer = _normalize(_question_field(case, "answer"))
    if not answer or answer == "None":
        return {"answer_nums": set(), "relation": None, "string_key": None}
    answer = re.sub(r"^[A-D][.、]", "", answer)          # 剥选项前缀 B.6dm² → 6dm²
    answer = re.sub(r"[（(].*$", "", answer)             # 剥「(答案不唯一)」尾注
    answer = answer.strip(",，。;、. ")                   # 剥关系骨架尾标点(12:4=6:2,)
    nums = _numbers(answer)
    relation = answer if (nums and _RELATION_OPS.search(answer)) else None
    non_num = re.sub(r"[\d.\s]", "", answer)
    string_key = non_num if (not relation and not nums and len(non_num) >= 2) else None
    return {"answer_nums": nums, "relation": relation, "string_key": string_key}


def student_asserts_answer(case: dict, student: str, keys: dict) -> bool:
    """学生轮是否以主张形态给出答案(点 4 + 分母去污染)。"""
    norm = _normalize(student)
    if not norm:
        return False
    # 关系型答案(12:4=6:2 / x-21=35):须出现关系骨架本身(组件数字不算)。
    if keys["relation"] and keys["relation"] in norm:
        return True
    # 字符串型答案(易变形):关键串出现在学生轮。
    if keys["string_key"] and keys["string_key"] in norm:
        return True
    # 字母型答案(选A/答案是A):须断言语境(选项字母在自由文本中太常见)。
    if not keys["relation"] and not keys["string_key"] and not keys["answer_nums"]:
        answer = _normalize(_question_field(case, "answer"))
        return any(m.group(1) in answer for m in _LETTER_ASSERT_RE.finditer(norm))
    # 纯数字答案:剥枚举段与换算段后仍含答案数字(因数列表/换算事实不污染)。
    if keys["answer_nums"] and not keys["relation"]:
        stripped = _CONVERT_RE.sub("。", _ENUM_RUN_RE.sub("。", norm))
        return bool(keys["answer_nums"] & _numbers(stripped))
    return False


# ---------------------------------------------------------------------------
# 主判分:逐轮 ER 族 / no-progress 族
# ---------------------------------------------------------------------------

def judge_case(case: dict, transcript: dict, form: str | None) -> dict:
    """一条轨迹的 ER judge v2 判分。form=None 且有答案 → repro 同形(点 5)。"""
    answer = _question_field(case, "answer")
    keys = answer_keys(case)
    has_answer = bool(answer) and answer != "None"
    # 适用域(点 4/5 的域面):form1 ∪ repro(无 form 标注但有答案)∪ 非数字终答案
    # (选项字母 A/B、文字结论「易变形」——报告 §5.3.1「选项/判断类案 ER 面
    # 全盲区」类;含 675/val_13 两 form2 案,盲区类以答案形态界定不以 compile
    # form 界定)。数值答案的 form2 案维持 v1 排除(学生纠正导师形态,无证据
    # 要求纳入;⑤ prereg 的 slice 编译另定)。
    non_numeric = bool(keys["string_key"]) or (
        not keys["answer_nums"] and not keys["relation"] and has_answer)
    in_domain = ((form == FORM1) or (form is None and has_answer)
                 or (non_numeric and has_answer))
    result: dict = {
        "in_domain": in_domain,
        "domain_note": (FORM1 if form == FORM1 else
                        "repro-equivalent" if form is None and in_domain else
                        "non-numeric-answer" if in_domain else
                        f"excluded:{form or 'no-answer'}"),
        "er_family": 0, "no_progress_family": 0, "denominator": 0,
        "turns": [],
    }
    if not in_domain:
        return result

    qtext_nums = _numbers(_question_field(case, "text"))
    said = False
    prev_clauses: list[list[str]] = []   # 历史导师轮问句子句(重复检测回看窗)
    for index, turn in enumerate(transcript.get("turns") or []):
        student = str(turn.get("student") or "")
        tutor = str(turn.get("tutor") or "")
        if student and not said:
            said = student_asserts_answer(case, student, keys)
        entry = {"index": index, "said": said, "in_denominator": False,
                 "er_hit": False, "er_reason": None,
                 "no_progress_hit": False, "no_progress_reason": None}
        clauses = interrogative_clauses(tutor) if tutor.strip() else []
        if not (student and tutor.strip() and said):
            prev_clauses.append(clauses)
            result["turns"].append(entry)
            continue
        result["denominator"] += 1
        entry["in_denominator"] = True
        ack = bool(_ACK_STRUCT_RE.search(tutor))

        # —— 点 7/6:no-progress 族(问句重复;不受 stray/ACK 否决)——
        repeat = _repeat_reason(clauses, prev_clauses)
        if repeat:
            entry["no_progress_hit"] = True
            entry["no_progress_reason"] = repeat

        # —— ER 族(点 1/2/3 + 点 6 stray 收紧)——
        if not entry["no_progress_hit"]:
            targeted = [c for c in clauses
                        if not is_tag(c) and clause_targeted(c, student)]
            confirming = any(any(m in c for m in CONFIRMING_MARKERS) for c in targeted)
            reask = any(_REASK_RE.search(c) for c in targeted)
            # 质疑性词(但/可是):须存在指向性问句子句(对比落在本轮已给命题上)。
            challenging = (any(m in tutor for m in CHALLENGING_MARKERS) and bool(targeted))
            # stray 否决收紧(点 6):学生上轮新数字仅在导师轮明确纠正时才算矛盾
            # (学生给新例子/新组合不否决)。
            stray = _numbers(student) - keys["answer_nums"] - qtext_nums
            contradicts = (bool(stray) and bool(_CORRECTION_RE.search(tutor))
                           and bool(stray & _numbers(tutor)))
            # 点 3:显式承认 + 尾标签问句 → 不判 ER(承认后推进);指向性整句
            # 重问不豁免——口头承认+继续当未知=ER(B-old RETIRE 证据)。标签
            # 子句已在 targeted 过滤中排除,ack 在此只作条款记录。
            if (confirming or reask or challenging) and not contradicts:
                entry["er_hit"] = True
                entry["er_reason"] = ("确认性问句指向同一命题" if confirming else
                                      "值重问指向已给答案" if reask else
                                      "质疑性对比指向同一命题")
                entry["ack_present"] = ack
        if entry["er_hit"]:
            result["er_family"] += 1
        if entry["no_progress_hit"]:
            result["no_progress_family"] += 1
        prev_clauses.append(clauses)
        result["turns"].append(entry)
    return result
