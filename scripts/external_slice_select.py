"""external_slices 选择器(#368 下游·架构师执行序列步骤 7 实验原料)。

在 SocraticMATH normalized(canonical v1)上**纯规则**筛两个行为面 slice,零模型调用;
产物 edu_agent/evals/datasets/external_slices/socraticmath_v1.json 是 normalized 的**索引**
(记录 id + 命中轮次 + 短证据摘录 + 上下文依赖度标注),消费时按 id 回连
reference_dialogue,不整段拷贝。

**候选案例层,须经理 v2 编译协议转为可执行 scenario 后方进 A/B(架构师裁定 2026-09-21)。**

形态1「学生已答对但导师继续追问」(700m 事故同款) rule form1/v2,数值路径:
  1. problem.answer 非空;answer 数值 token(阿拉伯/小数/分数归一为 Fraction、圈号①-⑳映射
     为 "circ:N")按首次出现去重后 ≥2 个;
  2. 单空题:题面空槽(____ 连续下划线或 　　 连续全角空格,均 ≥2 字符)按槽组计——
     相邻槽之间只隔连接符(:：、,，＞><=＝与空白)算同组;槽组数 ≤1 且（数字/中文数字）
     型枚举 ≤1(多空题的 answer 串是小问答案拼接,早段小问命中全部 token 时,后续导师
     问句往往是"问下一空"而非追问,会造成伪命中——实测 116/719/1934/2412/3165/4780/
     val_549 均属此类,全部由本条款排除);
  3. 命中轮 = 最早 i≥1 的 student 轮(turn0 是题面复述),使 answer 去重 token 序列是该轮
     数值 token 序列的**连续子序列**(数值成串按序给出,排除散落/排序背诵巧合,实测排除
     866 turn4 因数背诵、934 合数列举等);answer 含结构型括号(括号内含数字,如
     650-(132+37))时命中轮须同含结构型括号(排除 2100:纯数字连续但运算结构错,
     "实质内容与最终答案不一致";不含数字的标注括号如"(答案不唯一)"不算);
  4. 命中轮之后 ≥1 个 tutor 以？/?结尾的轮。
形态1 文本路径(数值 token <2 的答案):
  5. 规范化 answer(保留小数点与括号、全角归半角、去空白与句读;去尾点)长度 ≥2;
  6. 同款单空题约束;题面回声护栏:规范化 answer 不得出现在规范化题面(排除 1094 类
     "学生复读题面给定数");无知表达护栏:命中轮不含(不[是很太]?知道|清楚|记得|了解|
     明白|没学过|不太会)(排除 4556"我对垂足的概念不是很清楚"——答串出现在无知表达里);
  7. 数值主导型答案(数字+≤3字符单位,如 2.5厘米/48只)要求去单位后与命中轮某数值 token
     等价(防前缀/子串巧合:4440 "4.0"⊆"4.042"、4461 "20"⊆"120"、4005 "158"⊆"158.33…");
     含数字的术语型(如"24时计时法")与纯文本答案要求整串包含(排除 1606:数字成分 24
     单独误配);断言框架护栏:命中轮含(应该|结果|等于|得到|所以|就是|是),排除纯罗列式
     提及(实测排除 2543 平年天数罗列等;术语复现型如 223 因含断言句式保留,复核降档);
  8. 同款"之后 ≥1 个 tutor 问号轮"。
  收紧阶梯:基础超集匹配+追问 → 224 条(过松);+单空题+≥1 token≥10 → 17;连续子序列
  替代超集 → 14;+结构括号一致 → 8(数值路径);文本路径 59 → 回声/无知/数值 token 等价/
  断言框架四护栏 → 33。两路径合并按依赖度偏好排序,每形态上限 20(宁少勿滥,2026-09-21
  PM 追加指令)。

形态2「学生纠正导师」(700m 第 7 轮同款) rule form2/v2,起始路径:
  1. 命中轮 = student 轮以「不对」「错了」起始。「不是」系起始(不是/不是的)实测 5/5 抽检
     (846/1251/2422/3397/3487)均为回答导师的是非问句而非纠正导师,整系排除;
  2. i≥2(前置导师轮存在;本语料对话严格 student/tutor 交替,前一轮必为导师);
  3. 对话未中断:命中轮之后 ≥2 轮(导师必有回应);
  4. 无知表达护栏(命中轮不含 不知道/不是很清楚/不记得 族——排除 1389 类混纠兼示弱)。
形态2 中段路径(轮中含不对/错了,非起始):
  5. 恰一次非回声出现(前一字非"对/没";批量选项/多句扫描如 2546「A…不对;B…不对;
     C…不对」、4063 四句逐一判错,非单一纠正动作,排除);
  6. 轮内不含自纠族(我+≤12字+错族动词/错了、道歉语、插语+错、等等…不对、有点不对、
     过程不对、候选自我否定、被动叙事「被弄错/看成了」——本语料中段否定标记被自纠
     淹没:136 条粗筛绝大多数为「哎呀我错了」系自纠;5116 为导师提示后自纠上轮计算;
     3048/2617/3934/2229/5150/206/test_6 各类自纠或叙事复述,全部排除);
  7. 不含条件/程序性用法(如果不对|不对就|不对的话);轮含纠正性理由/替换
     (因为|应该|而是|题目|实际上|正确的是);同款 i≥2、未中断、无知护栏。
  收紧阶梯:含否定标记+未中断 → 1,366 条;起始档 → 36(混入"不是很确定"类不确定性表达);
  排除不确定性+标记缩到不对/错了 → 9(起始路径);中段粗筛 136 → 门控+逐条通读 → 8
  (2899/4275/val_495/3998/val_13/test_42/29/515,均为学生评判导师转述/抛出命题的弱形态)。
  曾尝试加「前导师轮含断言词句」约束(词表 就是说/应该是/等于/代表…),9 条砍到 2 条且
  词表任意性大,弃用;导师命题真伪与纠正强度由人工抽检兜底并在产物头部标注。

上下文依赖度标注(PM 追加指令 2026-09-21,架构师决策二):
  每条案例对全部 student 轮打强弱依赖标:强依赖 = 轮内命中参照标记(你[刚才/刚刚/前面/
  之前]?…说/讲/提到/问/教、你说的、你的方法/意思/解释、根据你/按照你、老师+说/教、
  上一步、第N种方法…);弱依赖 = 自足断言(我不知道怎么算/我觉得应该是3/4 类)。
  输出:weak_turn_ratio、strong_turn_indexes、layout(all_weak|front_truncatable|
  throughout)。规则是**下界**:指示词回指(「这个应该不对」)无词法标记,检不出,弱占比
  应视为乐观估计。形态2 的命中轮按形态定义天然响应导师前一命题(否定回指),保守计为
  强依赖并在条目标注 form_inherent。选例偏好:all_weak > front_truncatable > throughout,
  同档按 weak_ratio 降序;每形态上限 20,宁少勿滥。

用法(仓根):
  python scripts/external_slice_select.py \
    edu_agent/evals/datasets/external_normalized/socraticmath.jsonl \
    edu_agent/evals/datasets/external_slices/socraticmath_v1.json
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

SLICE_VERSION = "socraticmath_v1"
FORM1_RULE = "form1/v2"
FORM2_RULE = "form2/v2"
FORM_CAP = 20  # 每形态上限(PM 追加指令:宁少勿滥,10-20 条可编译案例)

# ── 数值抽取(两形态共用) ──────────────────────────────────────────────
_ARAB = re.compile(r"\d+(?:\.\d+)?(?:/\d+)?")
_CIRCLED = {
    "①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5", "⑥": "6", "⑦": "7",
    "⑧": "8", "⑨": "9", "⑩": "10", "⑪": "11", "⑫": "12", "⑬": "13",
    "⑭": "14", "⑮": "15", "⑯": "16", "⑰": "17", "⑱": "18", "⑲": "19",
    "⑳": "20",
}

# ── 结构护栏 ──────────────────────────────────────────────────────────
_BLANK = re.compile(r"_{2,}|\u3000{2,}")
_JOIN_ONLY = re.compile(r"^[\s:：、,，＞><=＝]*$")
_ENUM = re.compile(r"（[一二三四五六七八九十\d]+）")
# 结构型括号:括号内含数字(如 650-(132+37));不含数字的标注括号(如"(答案不唯一)")不算
_STRUCT_PAREN = re.compile(r"[（(][^（）()]*\d[^（）()]*[）)]")
_IGNORANCE = re.compile(
    r"不[是很太]{0,2}(知道|清楚|记得|明白)|不了解|没学过|不太会"
)
_ASSERT_FRAME = re.compile(r"应该|结果|等于|得到|所以|就是|是")

# ── 形态2 中段门控 ────────────────────────────────────────────────────
_F2_MARKERS = ("不对", "错了")
# 自纠族:我…错了/我又错了/我弄错了/道歉+错/插语+错/等等…不对/有点不对/过程自检/候选自我否定
_SELF_ERR = re.compile(
    r"我[^。？？！\n]{0,12}(错了|弄错|记错|看错|理解错|算错|搞错|做错|写错|想错|弄反|搞反)"
    r"|(对不起|抱歉|不好意思)"
    r"|^(哎[呀哟]|啊|哦|噢|咦|诶|嗯)[^。\n]{0,6}(不对|错)"
    r"|^刚[刚才]{0,1}[^。\n]{0,8}错"
    r"|等等[^。\n]{0,12}不对"
    r"|有点不对|过程不对|不对[，，,]?\s*这[不没]|不满足"
    r"|被[弄看写记算]错|看成了"  # 题目叙事复述(如"因数被弄错了"指题中人看错)
)
_PROC_USAGE = re.compile(r"对不对|如果不对|不对就|不对的话|若不对")
_JUSTIFY = re.compile(r"因为|应该|而是|题目|实际上|正确的是")

# ── 上下文依赖度标注 ──────────────────────────────────────────────────
_STRONG_DEP = re.compile(
    r"你[^。？？！\n]{0,6}(说|讲|提到|问|教)"  # 你说/你刚刚不是说/你刚才提到
    r"|你说的|你说得|如你所说|按你|根据你|按照你"  # 你说的方法/根据你的解释
    r"|你(的)?(方法|意思|说法|思路|结论|答案|提示|解释)"  # 你的第二种/你的意思
    r"|(明白|懂)了?你|明白你"  # 我明白你说的…
    r"|老师[^。？？！\n]{0,4}(说|讲|教|提到)"  # 老师说的公式
    r"|上(一|1)步"  # 我上一步写的是12
    r"|第[一二两三四五1-5]种(方法|解法|思路|做法|情况)"  # 第二种方法
)


def numeric_tokens(text: str) -> list[Fraction | str]:
    """数值抽取:阿拉伯数串(小数/分数归一 Fraction)、圈号映射 "circ:N";保持出现顺序。"""
    toks: list[Fraction | str] = []
    for m in _ARAB.findall(text):
        try:
            toks.append(Fraction(m))
        except (ValueError, ZeroDivisionError):
            continue
    toks.extend("circ:" + _CIRCLED[c] for c in text if c in _CIRCLED)
    return toks


def dedupe_first(seq: list[Fraction | str]) -> list[Fraction | str]:
    """按首次出现去重(保持顺序)。"""
    seen: set[Fraction | str] = set()
    out: list[Fraction | str] = []
    for t in seq:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def contiguous_subseq(needle: list, hay: list) -> bool:
    """needle 是否为 hay 的连续子序列(逐位置窗口比较)。"""
    n = len(needle)
    return any(hay[k : k + n] == needle for k in range(len(hay) - n + 1))


def blank_groups(problem_text: str) -> int:
    """题面空槽组数:相邻槽之间只隔连接符(:：、,＞><=＝与空白)算同组。"""
    spans = [m.span() for m in _BLANK.finditer(problem_text)]
    if not spans:
        return 0
    groups = 1
    for (_, end), (start, _) in zip(spans, spans[1:], strict=False):
        if not _JOIN_ONLY.match(problem_text[end:start]):
            groups += 1
    return groups


def single_blank(problem_text: str) -> bool:
    """单空题判定(多空题的答案串为小问拼接,早段命中会造成伪追问)。"""
    return blank_groups(problem_text) <= 1 and len(_ENUM.findall(problem_text)) <= 1


def norm_keep(text: str) -> str:
    """规范化:保留小数点与括号(全角归半角),去空白与句读/引号——防数字前缀与括号巧合。"""
    t = text.translate(str.maketrans("（）＞＜：％", "()><:%"))
    return re.sub(r"[\s,，、;；。．\"'“”‘’]", "", t)


def tutor_question_turns(dialogue: list[dict], after: int) -> list[int]:
    """after 之后以？/?结尾的 tutor 轮索引。"""
    return [
        j
        for j in range(after + 1, len(dialogue))
        if dialogue[j]["role"] == "tutor" and dialogue[j]["text"].rstrip().endswith(("？", "?"))
    ]


def dependency_annotation(rec: dict, hit_index: int, hit_inherent_strong: bool) -> dict:
    """上下文依赖度:全部 student 轮打标,输出弱占比/强位置/布局。

    hit_inherent_strong:形态2 命中轮按定义否定回指导师前一命题,保守计强依赖。
    """
    dialogue = rec["reference_dialogue"]
    student_idx = [i for i, t in enumerate(dialogue) if t["role"] == "student"]
    strong = [i for i in student_idx if _STRONG_DEP.search(dialogue[i]["text"])]
    if hit_inherent_strong and hit_index not in strong:
        strong.append(hit_index)
    weak_ratio = 1 - len(strong) / len(student_idx) if student_idx else 1.0
    if not strong:
        layout = "all_weak"
    elif all(i < len(dialogue) / 2 for i in strong):
        layout = "front_truncatable"
    else:
        layout = "throughout"
    return {
        "weak_turn_ratio": round(weak_ratio, 3),
        "student_turns_total": len(student_idx),
        "strong_turn_indexes": strong,
        "layout": layout,
        "rule_note": "词法标记下界:指示词回指(如「这个应该不对」)无标记检不出",
    }


def preference_key(entry: dict) -> tuple:
    """选例偏好排序键:命中路径(数值/起始为主线索)→ 布局(all_weak>front>throughout)
    → 弱占比降序 → 追问轮数降序 → 命中轮次升序(早段优先)→ id 稳定。"""
    order = {"all_weak": 0, "front_truncatable": 1, "throughout": 2}
    path_rank = 0 if entry["match_path"] in ("numeric_subsequence", "marker_start") else 1
    dep = entry["context_dependency"]
    q_count = len(entry.get("tutor_question_turns_after", []))
    return (path_rank, order[dep["layout"]], -dep["weak_turn_ratio"], -q_count, entry["hit_turn_index"], entry["id"])


# ── 形态1 ─────────────────────────────────────────────────────────────


def form1_numeric_hit(rec: dict) -> tuple[int, list[int]] | None:
    """数值路径:answer 去重 token ≥2 且为命中轮 token 序列的连续子序列。"""
    answer = rec["problem"].get("answer")
    if not answer:
        return None
    aseq = dedupe_first(numeric_tokens(answer))
    if len(aseq) < 2:
        return None
    if not single_blank(rec["problem"]["text"]):
        return None
    needs_paren = bool(_STRUCT_PAREN.search(answer))
    dialogue = rec["reference_dialogue"]
    for i, turn in enumerate(dialogue):
        if turn["role"] != "student" or i == 0:
            continue
        if needs_paren and not _STRUCT_PAREN.search(turn["text"]):
            continue
        if not contiguous_subseq(aseq, numeric_tokens(turn["text"])):
            continue
        qs = tutor_question_turns(dialogue, i)
        if qs:
            return i, qs
    return None


def text_turn_matches(turn_text: str, na: str, numeric_dominant: bool) -> bool:
    """文本路径单轮匹配:无知/断言护栏 + 数值主导 token 等价或整串包含。"""
    if _IGNORANCE.search(turn_text) or not _ASSERT_FRAME.search(turn_text):
        return False
    if not numeric_dominant:
        return na in norm_keep(turn_text)
    num_part = re.match(r"\d+(?:\.\d+)?(?:/\d+)?", na)
    toks = {norm_keep(t).rstrip(".") for t in _ARAB.findall(turn_text)}
    return bool(num_part) and num_part.group(0) in toks


def text_path_target(rec: dict) -> tuple[str, bool] | None:
    """文本路径资格:返回 (规范化答案, 数值主导) 或 None(不满足护栏/归数值路径负责)。"""
    answer = rec["problem"].get("answer")
    if not answer or len(dedupe_first(numeric_tokens(answer))) >= 2:
        return None  # 无答案或数值路径负责
    na = norm_keep(answer).rstrip(".")
    if len(na) < 2 or not single_blank(rec["problem"]["text"]):
        return None
    if na in norm_keep(rec["problem"]["text"]):
        return None  # 题面回声
    # 数值主导型答案(数字+≤3字符单位,如 2.5厘米/48只)走 token 等价;
    # 含数字的术语型(如"24时计时法")仍走整串包含,防数字成分单独误配(实测排除 1606)
    numeric_dominant = bool(
        re.fullmatch(r"\d+(?:\.\d+)?(?:/\d+)?[^\d]{0,3}", answer.strip().rstrip("."))
    )
    return na, numeric_dominant


def form1_text_hit(rec: dict) -> tuple[int, list[int]] | None:
    """文本路径:数值 token <2 的答案,规范化整串(token 等价/包含)+护栏。"""
    target = text_path_target(rec)
    if target is None:
        return None
    na, numeric_dominant = target
    dialogue = rec["reference_dialogue"]
    for i, turn in enumerate(dialogue):
        if turn["role"] == "student" and i > 0 and text_turn_matches(turn["text"], na, numeric_dominant):
            qs = tutor_question_turns(dialogue, i)
            if qs:
                return i, qs
    return None


def select_form1(rec: dict) -> dict | None:
    """形态1:两路径取命中,组装条目(命中轮自足断言,依赖度按普通轮打标)。"""
    hit = form1_numeric_hit(rec) or form1_text_hit(rec)
    if hit is None:
        return None
    i, qs = hit
    dialogue = rec["reference_dialogue"]
    return {
        "id": rec["id"],
        "rule_version": FORM1_RULE,
        "match_path": "numeric_subsequence" if form1_numeric_hit(rec) else "text_substring",
        "hit_turn_index": i,
        "hit_role": "student",
        "tutor_question_turns_after": qs,
        "evidence": {
            "problem_answer": rec["problem"]["answer"],
            "student_turn_excerpt": excerpt(dialogue[i]["text"]),
            "tutor_question_turn_excerpt": excerpt(dialogue[qs[0]]["text"]),
        },
        "context_dependency": dependency_annotation(rec, i, hit_inherent_strong=False),
    }


# ── 形态2 ─────────────────────────────────────────────────────────────


def form2_mid_turn_gated(turn_text: str) -> bool:
    """中段路径门控:恰一次非回声 不对/错了(批量选项/多句扫描非单一纠正动作,排除
    2546/4063),排自纠族与条件式用法,须含纠正性理由。"""
    if _SELF_ERR.search(turn_text):
        return False
    occ = [m.start() for m in re.finditer(r"不对|错了", turn_text)]
    qualifying = [s for s in occ if not (s > 0 and turn_text[s - 1] in "对没")]
    if len(qualifying) != 1:
        return False
    if _PROC_USAGE.search(turn_text[max(0, qualifying[0] - 4) : qualifying[0] + 6]):
        return False
    return _JUSTIFY.search(turn_text) is not None


def select_form2(rec: dict) -> dict | None:
    """形态2:起始路径(不对/错了 起始)+ 中段门控路径;命中轮按形态定义计强依赖。"""
    dialogue = rec["reference_dialogue"]
    for i, turn in enumerate(dialogue):
        if turn["role"] != "student" or i < 2:
            continue
        if len(dialogue) - 1 - i < 2:
            continue
        text = turn["text"].strip()
        if _IGNORANCE.search(text):
            continue  # 无知表达护栏(排除 1389 类"这段我就不清楚了"混纠兼示弱)
        if text.startswith(_F2_MARKERS):
            path = "marker_start"
        elif form2_mid_turn_gated(text):
            path = "mid_turn_gated"
        else:
            continue
        return {
            "id": rec["id"],
            "rule_version": FORM2_RULE,
            "match_path": path,
            "hit_turn_index": i,
            "hit_role": "student",
            "tutor_claim_turn_index": i - 1,
            "evidence": {
                "tutor_turn_excerpt": excerpt(dialogue[i - 1]["text"]),
                "student_turn_excerpt": excerpt(text),
            },
            "context_dependency": dependency_annotation(
                rec, i, hit_inherent_strong=True
            ),
        }
    return None


# ── 产物头部:人工复核结论(复核人=本选择代理,逐轮通读) ─────────────────
MANUAL_REVIEW = {
    "obligation": (
        "每形态抽 3 条人工通读 reference_dialogue 确认形态成立(防规则误伤);实际执行:"
        "两形态终版条目已全部逐条通读,抽检 3 条为正式记录。"
    ),
    "form1": {
        "samples": [
            {
                "id": "socraticmath_train_4402",
                "verdict": "成立(最强样本)",
                "note": (
                    "学生第4轮已说出 x-21=35(与 answer 逐字一致),导师第5轮仍要求『变成"
                    "方程的形式』继续追问,追问后学生反而在第6轮改错为 x-22=35——与 700m "
                    "事故(已答对仍被追问、追问诱发新错)同构。"
                ),
            },
            {
                "id": "socraticmath_train_866",
                "verdict": "成立",
                "note": "学生第10轮给出完整比例 12:4=6:2(即 answer 本体),导师第11轮仍以问号轮追问(答案不唯一性),对话继续。",
            },
            {
                "id": "socraticmath_train_1204",
                "verdict": "成立",
                "note": "学生第4轮已给出完整答案集 2、5、8,导师第5、7轮仍连续追问(5 的倍数特点),第9轮才收束确认答案。",
            },
        ],
        "overall": (
            "终版 20 条(数值路径 8 + 文本路径 12)全部逐条通读。强度分档:强=完整答案句/"
            "计算断言后仍有问号轮(4402 为最典型——答案后重问同一步且追问诱发学生新错;"
            "5221 为导师给出错误结果 27、学生答出正确答案 189 后导师仍连续质疑);中=术语"
            "答案句(2013 分数/5228 十七万/2591 易变形确认问句);弱=术语复现型(223/5032/"
            "5191/3565,答案词出现在知识复述中,导师问号轮为应用引导)——弱档仍满足『答案"
            "实质内容已给出+导师继续问号轮』操作定义,依赖度均为弱,编译风险低,供按需取用。"
            "复核中淘汰的误伤均固化为规则条款:多空题伪追问 7 例(116/719/1934/2412/3165/"
            "4780/val_549)、排序背诵巧合 2 例(866 第4轮/934)、运算结构不一致 1 例(2100)、"
            "题面回声(1094)、无知表达(4556,『不是很清楚』两修饰字致正则漏配后修正)、"
            "数字前缀巧合(4440/4461/4005)、数字成分误配(1606『24时计时法』)。"
        ),
    },
}

MANUAL_REVIEW["form2"] = {
    "samples": [
        {
            "id": "socraticmath_train_675",
            "verdict": "成立(强)",
            "note": "导师第5轮断言『图上的1厘米代表实际的100厘米』(错,题目为 100 米),学生第6轮『不对,题目说的是1厘米表示100米,不是100厘米』明确纠正,导师第7轮接受——教科书式学生纠正导师。",
        },
        {
            "id": "socraticmath_train_1827",
            "verdict": "成立(强)",
            "note": "导师第5轮把因数方向说反(『又能被48整除』),学生第6轮『不对,它应该是能被3整除,48能被它整除』纠正方向,导师第7轮认可。",
        },
        {
            "id": "socraticmath_train_3998",
            "verdict": "成立(弱形态,中段路径抽检代表)",
            "note": "导师第5轮给出直径定义后问『题目中的说法正确吗』,学生第6轮『根据你的解释,题目中的说法好像不对』——学生以导师解释为据否定题目主张;注意该轮『根据你的解释』为强依赖标记,编译时须保真该上下文或弃选。",
        },
    ],
    "overall": (
        "终版 16 条(起始路径 8 + 中段路径 8)全部逐条通读。起始路径强度:强 5 条(675/1001/"
        "1827/4786/val_61,学生驳回导师自己的断言/解法/结论);中 1 条(3749,学生否定导师"
        "抛出的朴素解法);弱 2 条(1688/val_97,学生评判导师转述的题目/选项主张)。中段"
        "路径 8 条(2899/4275/val_495/3998/val_13/test_42/29/515)均为弱-中形态:学生评判"
        "导师转述或抛出的命题(题目主张/日记数据/题目人物的口算方法/选项),其中 val_495 "
        "学生正确指出题目口算分解符号错误(40+3 应为 40-3),3998 含强依赖标记『根据你的"
        "解释』编译须保真。中段粗筛 136 条被自纠族(『哎呀我错了』系)淹没,门控+逐条通读"
        "淘汰:5116(导师提示后自纠上轮计算)、3048/2617/3934/2229/5150/206(自纠/过程"
        "自检/候选自我否定)、test_6(『因数被弄错了』为题目叙事复述)、5295(学生误纠"
        "题目,纠正内容本身错误)、1099(等等引导的选项评判,连带排除)、2546/4063(批量"
        "选项/多句扫描,非单一纠正动作)、1389(混纠兼示弱)。另:『不是』系起始在本语料 "
        "5/5 抽检均为回答导师是非问句而非纠正,已整系排除(见规则)。"
    ),
}


def excerpt(text: str, limit: int = 90) -> str:
    """证据摘录:压缩空白、截断到 limit 字符,不整段拷贝。"""
    flat = re.sub(r"\s+", " ", text).strip()
    return flat[:limit] + ("…" if len(flat) > limit else "")


def source_stats(path: Path, records: list[dict]) -> dict:
    """源指纹统计:文件 sha256、行数、记录指纹唯一数、schema/版本/许可证快照。"""
    fingerprints = [r.get("fingerprint") for r in records]
    return {
        "path": "edu_agent/evals/datasets/external_normalized/socraticmath.jsonl",
        "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "records": len(records),
        "unique_record_fingerprints": len({f for f in fingerprints if f}),
        "schema_versions": sorted({r["schema_version"] for r in records}),
        "source_dataset": "SocraticMATH",
        "source_version": "837da0b",
        "license": "CC BY-NC 4.0",
        "note": (
            "normalized 全量证据层在 task/importer-socraticmath-adapt 分支入库(#368);"
            "本 slice 为其索引,消费时按 id 回连 reference_dialogue。"
        ),
    }


def build_slice(records: list[dict], stats: dict) -> dict:
    """组装产物:schema 头(版本/规则/时间/源指纹/复核/编译协议注记)+ 两形态条目。"""
    raw1 = [e for e in (select_form1(r) for r in records) if e]
    raw2 = [e for e in (select_form2(r) for r in records) if e]
    form1 = sorted(raw1, key=preference_key)[:FORM_CAP]
    form2 = sorted(raw2, key=preference_key)[:FORM_CAP]
    answer_non_null = sum(1 for r in records if r["problem"].get("answer"))
    return {
        "schema": "edu_agent_external_slice/v1",
        "slice_version": SLICE_VERSION,
        "status_note": (
            "候选案例层,须经理 v2 编译协议转为可执行 scenario 后方进 A/B"
            "(架构师裁定 2026-09-21)。架构师否决『学生轮机械顺序 replay』用法。"
        ),
        "description": (
            "SocraticMATH 行为面实验 slice(#368 下游·架构师执行序列步骤 7 Prompt/Model "
            "quality 实验原料):形态1=学生已答对但导师继续追问(700m 事故同款);"
            "形态2=学生纠正导师(700m 第 7 轮同款)。纯规则筛选,零模型调用;条目含"
            "上下文依赖度标注(弱依赖=自足断言可保留,强依赖=回指导师具体措辞需编译处理)。"
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "scripts/external_slice_select.py",
        "entry_fields": [
            "id(normalized 记录 id,回连键)",
            "rule_version / match_path(筛选规则版本与命中路径)",
            "hit_turn_index / hit_role(命中轮次索引与角色,0 起)",
            "形态1 另有 tutor_question_turns_after(命中轮之后以？结尾的导师轮索引)",
            "形态2 另有 tutor_claim_turn_index(被否定/纠正的导师轮索引)",
            "evidence(命中证据短摘录,非整段)",
            "context_dependency(weak_turn_ratio/strong_turn_indexes/layout:"
            "all_weak|front_truncatable|throughout;词法下界,弱占比为乐观估计)",
        ],
        "source": stats,
        "rules": {
            "form1": {
                "version": FORM1_RULE,
                "name": "学生已答对但导师继续追问",
                "text": (
                    "数值路径:answer 数值 token(阿拉伯/小数/分数归一、圈号映射)去重后≥2;"
                    "单空题(空槽按槽组计,相邻槽仅隔连接符算同组;槽组≤1 且（N）枚举≤1);"
                    "最早 i≥1 的 student 轮使 answer 去重 token 序列为其数值 token 序列的"
                    "连续子序列(answer 含结构型括号即括号内含数字时,命中轮须同含);该轮"
                    "之后≥1 个 tutor 以？/?结尾的轮。文本路径(数值 token<2):规范化 answer"
                    "(保点保括号)≥2 字符,单空题,题面回声护栏(答案串不在题面),无知表达"
                    "护栏,数值型答案要求 token 等价(防前缀巧合),断言框架护栏(应该|结果|"
                    "等于|得到|所以|就是|是),后续问号轮同款。收紧阶梯:基础超集 224→单空"
                    "+token≥10→17→连续子序列→14→+结构括号→8(数值路径);文本 59→四护栏→33;"
                    "两路径合并按依赖度偏好排序取前 20。"
                ),
            },
            "form2": {
                "version": FORM2_RULE,
                "name": "学生纠正导师",
                "text": (
                    "起始路径:student 轮以「不对」「错了」起始(「不是」系整系排除:5/5 抽检"
                    "均为回答导师是非问句);i≥2(前置导师轮存在,对话严格交替);之后≥2 轮"
                    "(对话未中断);无知表达护栏。中段路径:恰一次非回声 不对/错了(前一字非"
                    "对/没;批量选项/多句扫描排除),轮内不含自纠族(我+≤12字+错族/道歉语/"
                    "插语+错/等等…不对/有点不对/候选自我否定/被动叙事)与条件式用法,含纠正"
                    "性理由(因为|应该|而是|题目|实际上|正确的是)。收紧阶梯:含否定标记+未"
                    "中断 1,366→起始 36(混『不是很确定』)→排不确定性+缩标记 9;中段粗筛"
                    " 136→门控+逐条通读 8。两路径合并按依赖度偏好排序取前 20。"
                ),
            },
        },
        "selection_funnel": {
            "normalized_records": len(records),
            "form1": {
                "answer_non_null": answer_non_null,
                "raw_hits": len(raw1),
                "final": len(form1),
                "cap": FORM_CAP,
            },
            "form2": {
                "raw_hits": len(raw2),
                "final": len(form2),
                "cap": FORM_CAP,
            },
        },
        "manual_review": MANUAL_REVIEW,
        "counts": {"form1": len(form1), "form2": len(form2)},
        "slices": {
            "form1_student_answered_tutor_keeps_asking": form1,
            "form2_student_corrects_tutor": form2,
        },
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    src, dst = Path(argv[1]), Path(argv[2])
    records = [json.loads(line) for line in src.read_text(encoding="utf-8").splitlines() if line]
    slice_doc = build_slice(records, source_stats(src, records))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(slice_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"records={len(records)} form1={slice_doc['counts']['form1']} "
        f"(raw {slice_doc['selection_funnel']['form1']['raw_hits']}) "
        f"form2={slice_doc['counts']['form2']} "
        f"(raw {slice_doc['selection_funnel']['form2']['raw_hits']})"
    )
    print(f"written: {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
