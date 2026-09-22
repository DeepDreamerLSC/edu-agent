#!/usr/bin/env python3
"""confirmation 三 slice 编译器(#412 prereg §三·confirmation-bnew-prereg-v1)。

输入:edu_agent/evals/datasets/external_normalized/socraticmath.jsonl(6846 条,#392)
减去 r3 已用 23 案(socraticmath_executable_v1.json scenarios,#398 制度沿用)。
输出:edu_agent/evals/datasets/external_slices/socraticmath_confirmation_v1.json。

选择纪律(防 p-hack 红线,prereg §三):**只看源题面与学生话语,不看任何臂输出**。
逐案判定依据(哪一轮、什么特征)以 selection_evidence 写入产物头部——审计凭证。

三 slice(prereg §三规模:正 12-16 / 负 8-12 / 866 型 3-5;源池不足如实报数不凑):
  positive 学生已显式给出题目所求最终结论(终答形态陈述,非过程/方法);
    判定 = r3 form1/v2 严格断言语义(数值连续子序列/文本整串+护栏/字母断言)
    + judge 对齐闸(ER judge v2 的 said 必须恰在该终答轮置位——防 judge 剥换算段/
    枚举段/关系骨架导致 said 错位或永不置位的测量盲区);
  negative 学生止步于方法/原则/部分关系,终其对话未落到 problem.answer;
    判定 = judge 语义全对话零断言 + 原值闸(答案数值/文本任何形态不出现在任何
    学生轮——防 judge 盲区里学生已答的源真值错位)+ 剩余步骤实质闸(学生话语
    本身不构成结论——数值/定位/定性形态皆不算,防冤枉合理收束的假 FAIL 面);
  type866 题目实质已满足(学生已给出一组合法答案)但存在「全面性/另一种表示」
    延伸空间;judge 对齐闸同 positive。

编译规则(#398 协议沿用):本批 24 案全 R1 线性 v1(学生轮原文照录,仅允许
截断——剥回执/强依赖开场白,逐处记录;轮级丢弃记录)。无 R2/R3/R4 适用。
硬不变量(边编译边断言,违者非零退出):
  I1 v1 student_turns 每条都是源记录某 student 轮的原文子串(允许剥前缀,记录);
  I4 场景 question 与源 problem.text 逐字一致;
  I5 positive/type866:ER judge v2 语义下 said 恰在判定依据记录的终答轮置位;
  I6 negative:ER judge v2 语义下 said 在全部剧本轮永不置位,且答案原值
     (数值 token/规范化文本)不出现在任何剧本学生轮;
  I7 与 r3 已用 23 案零重叠(prereg §三排除条款)。

人工确认环节(初稿人工=本编译执行代理,2026-09-22):~100 条候选逐条通读
reference_dialogue;负向 slice 池穷尽(判定类案学生均以文字下结论,比较链/多空
案学生均逐组完成——三类形态系统性不产止步案),6/8-12 与 866 型 2/3-5 为
如实报数,排除理由分类入产物头部 selection_funnel。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NORMALIZED = REPO / "edu_agent/evals/datasets/external_normalized/socraticmath.jsonl"
OUT = (REPO / "edu_agent/evals/datasets/external_slices/"
       "socraticmath_confirmation_v1.json")
SELECT_HELPER = REPO / "scripts/external_slice_select.py"
JUDGE_PATH = REPO / "edu_agent/evals/artifacts/er-judge-v2/er_judge_v2.py"
R3_EXECUTABLE = (REPO / "edu_agent/evals/datasets/external_slices/"
                 "socraticmath_executable_v1.json")

V1 = "small_lecturer_dialogue_scenario/v1"
SLICE_POS = "confirmation_positive_student_final_answer"
SLICE_NEG = "confirmation_negative_student_stops_short"
SLICE_866 = "confirmation_type866_answer_complete_extensible"

# r3 已用 23 案(prereg §三:新案源必须排除;I7 断言零重叠)。
R3_USED = {
    "socraticmath_train_1204", "socraticmath_train_866", "socraticmath_train_4510",
    "socraticmath_train_4776", "socraticmath_val_412", "socraticmath_train_559",
    "socraticmath_train_1559", "socraticmath_train_4402", "socraticmath_train_3666",
    "socraticmath_train_223", "socraticmath_train_5191", "socraticmath_train_2591",
    "socraticmath_train_5228", "socraticmath_train_3565", "socraticmath_train_1827",
    "socraticmath_val_61", "socraticmath_train_1001", "socraticmath_train_675",
    "socraticmath_train_4275", "socraticmath_train_3998", "socraticmath_train_2899",
    "socraticmath_val_495", "socraticmath_val_13",
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


er = _load_module("er_judge_v2", JUDGE_PATH)
sel = _load_module("external_slice_select", SELECT_HELPER)


# ── 选定案与编译计划(人工判定定稿;plan=[(dialogue_index, cut_prefix)])─────
# evidence.basis 只引源对话内容(只看源面审计凭证);hit = 终答轮(正/866)
# 或「止步于」定位(负)。dropped = 轮级丢弃(含原因)。
SELECTION: dict[str, dict] = {
    # —— positive 16(prereg 12-16 上沿;强形态=终答后源导师假挑战/重问,学生持答)——
    "socraticmath_train_2322": {
        "slice": SLICE_POS, "hit": 4,
        "plan": [(2, ""), (4, ""), (6, "啊，我算错了。")],
        "basis": "t4「应该是74减去6再减去16，结果是52」——终答句含完整推导与答案值;"
                 "t5 源导师假挑战(「计算结果有些问题」),t6 学生复算得同值(截回执开场白)。",
    },
    "socraticmath_train_4814": {
        "slice": SLICE_POS, "hit": 4,
        "plan": [(2, ""), (4, ""), (6, "")],
        "basis": "t4「14乘以2，就是28平方分米」——终答句;t5 源导师假挑战"
                 "(「你确认你的计算没有问题吗」),t6 学生复算持同值。",
    },
    "socraticmath_val_190": {
        "slice": SLICE_POS, "hit": 4,
        "plan": [(2, ""), (4, ""), (6, "对不起，我算错了，")],
        "basis": "t4「…所以答案是21」——终答句;t5 源导师假挑战(十位算法误指),"
                 "t6 学生复算持同值(截回执开场白)。",
    },
    "socraticmath_val_58": {
        "slice": SLICE_POS, "hit": 4,
        "plan": [(2, ""), (4, ""), (6, "抱歉，我算错了。")],
        "basis": "t4「…四舍五入后，就是20立方分米」——终答句(保留整数口径已给);"
                 "t5 源导师假挑战,t6 学生复算(20.096→20)持同值(截回执开场白)。",
    },
    "socraticmath_train_4188": {
        "slice": SLICE_POS, "hit": 6,
        "plan": [(2, ""), (4, ""), (6, ""), (8, "")],
        "basis": "t6「800公顷再加上26公顷就是826公顷」——终答句;t7 源导师假挑战"
                 "(「并没有计算出正确的结果」),t8 学生坚持,t9 导师致歉确认。",
    },
    "socraticmath_train_898": {
        "slice": SLICE_POS, "hit": 4,
        "plan": [(2, ""), (4, ""), (6, "哦，对不起，我搞错了，")],
        "basis": "t4「去年总共就用了x乘以4，所以应该是4x吨」——代数终答句;"
                 "t5 源导师假挑战(「是不是应该是x乘以3」),t6 学生持答(截回执开场白)。",
    },
    "socraticmath_train_515": {
        "slice": SLICE_POS, "hit": 4,
        "plan": [(2, ""), (4, ""), (6, "啊，我错了，")],
        "basis": "t4「所以题目判断错了，应该选A」——选项字母终答(r3 form2 弃案,"
                 "非 23 已用);t5 源导师挑战,t6 学生重复同答(截回执开场白)。",
    },
    "socraticmath_train_2960": {
        "slice": SLICE_POS, "hit": 4,
        "plan": [(2, ""), (4, ""), (6, ""), (8, "啊！对对对，我说错了，")],
        "basis": "t4「应该是对的，应该选B」——选项字母终答;t5 源导师追问,t6 学生"
                 "改口错答 A,t8 又回正 B——追问诱发摇摆(4402 同款,截 t8 回执开场白)。",
    },
    "socraticmath_train_4813": {
        "slice": SLICE_POS, "hit": 4,
        "plan": [(2, ""), (4, ""), (6, "噢！我想起来了，")],
        "basis": "t4「1*18、2*9、3*6就是3种方案」——计数终答(枚举即答案,3 可见);"
                 "t5 源导师假挑战(「漏掉了一种情况」),t6 学生改错为 4 种——"
                 "假挑战诱发错答(截回执开场白)。",
    },
    "socraticmath_train_1961": {
        "slice": SLICE_POS, "hit": 6,
        "plan": [(2, ""), (4, ""), (6, ""), (8, "")],
        "basis": "t6「让我计算一下...结果是41」——终答句;t7 源导师答后重问"
                 "(「2788是68的多少倍呢」),t8 学生复述「是41倍」。",
    },
    "socraticmath_train_2196": {
        "slice": SLICE_POS, "hit": 6,
        "plan": [(2, ""), (4, ""), (6, ""), (8, "")],
        "basis": "t6「那应该是104除以4，结果是26厘米」——终答句;t7 源导师答后"
                 "重问同量(三条棱之和是多少),t8 学生复述。",
    },
    "socraticmath_train_3695": {
        "slice": SLICE_POS, "hit": 4,
        "plan": [(2, ""), (4, ""), (6, "")],
        "basis": "t4「9乘以4，再加上5。结果应该是41」——终答句;t5 源导师确认,"
                 "t6 学生致谢——干净收束面(无源追问)。",
    },
    "socraticmath_train_930": {
        "slice": SLICE_POS, "hit": 4,
        "plan": [(2, ""), (4, ""), (6, "")],
        "basis": "t4「我算了一下，结果应该是49」——终答句;t5 源导师确认收束,"
                 "t6 学生致谢——干净收束面。",
    },
    "socraticmath_val_142": {
        "slice": SLICE_POS, "hit": 4,
        "plan": [(2, ""), (4, ""), (6, "")],
        "basis": "t4「应该是7200页」——估算终答句;t6 学生谈估算误差体会"
                 "(实质收尾轮,无追问链)。",
    },
    "socraticmath_test_592": {
        "slice": SLICE_POS, "hit": 4,
        "plan": [(2, ""), (4, ""), (6, "好的，老师，我明白了。")],
        "basis": "t4「因为1平方千米等于100公顷,所以…所以我选B」——选项字母终答;"
                 "t5 源导师答后叮嘱,t6 学生求确认(截回执开场白)。",
    },
    "socraticmath_train_3138": {
        "slice": SLICE_POS, "hit": 6,
        "plan": [(2, ""), (6, "之前我没注意过，但根据你的解释，"), (8, "")],
        "dropped": [{ "index": 4,
                      "reason": "源导师讲解特性后的纯回执(「噢,原来是这样,我明白了」),不可独立成步"}],
        "basis": "t6「我觉得应该是的，所以我选A」——选项字母终答(截强依赖开场白"
                 "「根据你的解释」,断言句自足);t7 源导师挑战,t8 学生持答「我还是选A」"
                 "(t4 纯回执轮丢弃)。",
    },
    # —— negative 6(prereg 8-12;源池穷尽,如实报数,见 selection_funnel)——
    "socraticmath_train_2791": {
        "slice": SLICE_NEG, "hit": None,
        "plan": [(2, ""), (4, ""), (6, ""), (8, ""), (10, "")],
        "dropped": [{ "index": 12,
                      "reason": "源导师 t11 报出结论后的纯回执(「明白了,谢谢老师的解析」),不可独立成步"}],
        "basis": "止步于分解乘法部分积:t6「等于56」t8「等于112」t10「等于1120」,"
                 "总和(1176)与「四位数」位数判断终未给出;源导师 t11 代算,t13 报选项 B。",
    },
    "socraticmath_train_2857": {
        "slice": SLICE_NEG, "hit": None,
        "plan": [(2, ""), (4, ""), (6, ""), (8, ""), (10, ""), (12, "")],
        "dropped": [],
        "basis": "止步于逐位猜数:t2 A=5、t4 B=1(错,t5 导师纠 0)、t6 C=6、t8 D=6、"
                 "t10 E=6/F=7、t12 G=1;完整号码(5066671)拼装终未给出;"
                 "源导师 t13 拼出 0731-5066671。",
    },
    "socraticmath_train_372": {
        "slice": SLICE_NEG, "hit": None,
        "plan": [(2, ""), (4, ""), (6, ""), (8, "是的，我明白了。"),
                 (10, "是的，"), (12, "")],
        "dropped": [],
        "basis": "止步于公式关系:t4/t6 表面积增量=2πr²,t8 h 口径答错(2 米,应为全长),"
                 "t10 只言「用r的值和h算出来就可以」,t12 单位换算;数值计算终未执行,"
                 "全对话无人报出 100。",
    },
    "socraticmath_train_5181": {
        "slice": SLICE_NEG, "hit": None,
        "plan": [(2, ""), (4, ""), (6, ""), (8, "")],
        "dropped": [],
        "basis": "止步于表达式:t4 总路程 3600 千米、t6 总时间 450 分钟(均正确),"
                 "t8 只述「3600千米除以…总时间450分钟」;最终除法(=8)终未执行,"
                 "源导师 t9 报 8。",
    },
    "socraticmath_train_5106": {
        "slice": SLICE_NEG, "hit": None,
        "plan": [(2, ""), (4, ""), (6, "对的，")],
        "dropped": [{ "index": 8,
                      "reason": "源导师 t7 代完成后的纯回执(「我明白了,只要注意…」),不可独立成步"}],
        "basis": "止步于逐位除法中段:t6 算到借位与「次位是0」(商 80…,截回执开场白);"
                 "商末位与「中间有几个0」的判断终未完成;源导师 t7 代完成并报「只有一个0」。",
    },
    "socraticmath_train_3490": {
        "slice": SLICE_NEG, "hit": None,
        "plan": [(2, ""), (4, ""), (6, "")],
        "dropped": [],
        "basis": "止步于数位分析:t4 判整数部分 6/首位 7 但第二位分析含混"
                 "(「可能是0或者更大的数,但是不能超过5」),t6 只选出第三位取 4;"
                 "原数 6.704 终未拼出,源导师 t7 报出。",
    },
    # —— type866 2(prereg 3-5;judge 关系/枚举/换算剥除使同类形态大面积失明,
    #    见 selection_funnel,如实报数)——
    "socraticmath_train_5234": {
        "slice": SLICE_866, "hit": 10,
        "plan": [(2, ""), (4, ""), (6, ""), (8, ""), (10, "")],
        "dropped": [],
        "basis": "t10 学生解出一支「4：9=x：18…x=8」——合法终答(题面歧义两解之一,"
                 "judge 数值可见);延伸空间=另一支(40.5,哪个圆是 18 未定),"
                 "源导师 t11 补全两支「8或40.5」——全面性延伸同款。",
    },
    "socraticmath_train_4827": {
        "slice": SLICE_866, "hit": 6,
        "plan": [(2, ""), (4, "好的，"), (6, "哦，我明白了，")],
        "dropped": [],
        "basis": "t6 学生给出合法方程「160÷x = 20」(judge 关系骨架可见,截回执开场白);"
                 "延伸空间=等价方程其他列法(160÷8=x、x÷8=20、8x=160),"
                 "题目明言「列出一个」即任一合法——另一种表示延伸同款。",
    },
}

# 产物头部:逐案判定依据的审计摘要由 SELECTION 生成;此处为池探与排除分类记录。
FUNNEL = {
    "positive": {
        "pool": "normalized 6846 − r3 已用 23;r3 form1/v2 严格断言语料"
                "(数值连续子序列/文本整串+四护栏/字母断言)+单空题约束",
        "raw_hits_rank2_after1": 38,
        "excluded_by": {
            "judge_said_never": "终答以「X等于Y」关系形态给出,ER judge v2 剥换算段"
                                "把终答值一并剥掉,said 永不置位(2194/3578/1514/"
                                "test_54/test_103/1267/1799)——正向门分母为 0",
            "judge_said_early": "方法轮(比例/定义复述/候选枚举/关系陈述)提前触发 "
                                "said,与真实终答轮错位(2710/3067/val_147/4955)",
            "guess_or_question_form": "终答以疑问试探形态出现(「是不是叫做周长」「是不是"
                                      "…0.1076平方千米?」),非显式陈述(4401/635)",
            "source_contamination": "源导师连环纠错与学生回错轮深度耦合(5221,r3 弃案"
                                    "理由沿用)",
        },
        "final": 16,
        "band": "12-16",
    },
    "negative": {
        "pool": "同上;judge 语义全对话零断言 + 答案原值不出现在任何学生轮"
                "(防 judge 盲区源真值错位)+ 学生轮含数值/方法",
        "raw_candidates": 292,
        "read_manual": "~100 条逐条通读(数值+导师报答案/判定+报答案/比较链/多空/"
                       "无结论形态五路扫描全覆盖)",
        "excluded_by": {
            "student_stated_conclusion": "学生以文字/数值说出结论内容(判定类案几乎全数:"
                                         "3556/3823/5358/923/2106/2279/1730/4782/1528/"
                                         "3693/4180/752/625/652/3003/3082/3719/4357/"
                                         "val_369/test_36/test_41/1253/1504/2624/2908/"
                                         "928/val_494/4767 等)——学生话语本身构成结论",
            "wrong_answer_form": "学生已给出(错误)终答(49/5/m=5/1331/2040 中间量系),"
                                 "错答形态非止步形态(val_276/val_497/test_228/val_313/"
                                 "1579)",
            "notation_assembly_only": "结论内容已由学生逐位/定性给出,剩余仅记号拼装"
                                      "(1256/1097/3278/4793)",
            "source_contamination": "对话与题面错位/源导师确认错答/题面残缺"
                                    "(4304/4886/1449/1293/test_46/test_662/900/test_310/"
                                    "520)",
        },
        "final": 6,
        "band": "8-12",
        "note": "低于 prereg 区间,如实报数:语料对话绝大多数以学生报出终答/结论收尾,"
                "真实止步案稀缺;判定类、比较链类、多空类三类形态系统性不产止步案"
                "(排除类逐条有据,宁少勿滥)。",
    },
    "type866": {
        "pool": "同上;positive 形态 + 答案不唯一标注/写一个式题面/等价表示空间",
        "raw_candidates": "答案不唯一 6 + 或备选 6 + 写一个式题面 12 + 导师延伸探针 1"
                          " + 学生自予备选 5(并集去重)",
        "excluded_by": {
            "judge_relation_enum_blind": "answer_keys 关系骨架/枚举剥除使 said 永不置位"
                                         "(5346「8:1,16:2」/3966/5123/val_549 多段关系;"
                                         "3668/2990/val_148 枚举段;4474/5001 换算段)——"
                                         "与 866 本案(12:4=6:2 恰为答案原串)不同形",
            "false_marker": "延伸标记误中(「其他题目/知识点」「另一个内项」等非答案延伸:"
                            "1285/2754/4340/4627/2341/966)",
        },
        "final": 2,
        "band": "3-5",
        "note": "低于 prereg 区间,如实报数:866 形态(学生答案恰与答案键主形态逐字一致"
                "+答案不唯一)在余量池中仅 5234/4827 两案通过 judge 对齐闸。",
    },
}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_records() -> dict[str, dict]:
    records: dict[str, dict] = {}
    with NORMALIZED.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            records[record["id"]] = record
    return records


def r3_used_ids() -> set[str]:
    payload = json.loads(R3_EXECUTABLE.read_text(encoding="utf-8"))
    return {s["id"] for s in payload["scenarios"]}


def judge_case_for(record: dict) -> dict:
    return {"question": {"text": record["problem"]["text"],
                         "answer": record["problem"].get("answer") or ""}}


def student_turn(record: dict, index: int, cut: str) -> str:
    """I1:取源 student 轮原文;cut 为被剥掉的回执/强依赖开场白(必须逐字前缀)。"""
    turn = record["reference_dialogue"][index]
    assert turn["role"] == "student", f"{record['id']} 轮 {index} 非 student"
    text = turn["text"]
    if cut:
        assert text.startswith(cut), \
            f"{record['id']} 轮 {index} 截断段非原文前缀:{cut!r}"
        text = text[len(cut):]
    return text


def said_index(record: dict, plan: list[tuple[int, str]]) -> int | None:
    """ER judge v2 语义:剧本轮(截断后)上 said 首次置位的对话轮索引。"""
    case = judge_case_for(record)
    keys = er.answer_keys(case)
    for index, cut in plan:
        text = student_turn(record, index, cut)
        if er.student_asserts_answer(case, text, keys):
            return index
    return None


def raw_answer_in_script(record: dict, plan: list[tuple[int, str]]) -> bool:
    """I6 原值闸:答案数值 token 或规范化文本键出现在任何剧本学生轮。"""
    answer = record["problem"].get("answer") or ""
    tokens = {float(m) for m in re.findall(r"\d+(?:\.\d+)?", answer)}
    normalized = sel.norm_keep(answer).rstrip(".")
    for index, cut in plan:
        text = student_turn(record, index, cut)
        if tokens & {float(m) for m in re.findall(r"\d+(?:\.\d+)?", text)}:
            return True
        if len(normalized) >= 2 and normalized in sel.norm_keep(text):
            return True
    return False


def build_scenario(sid: str, spec: dict, record: dict) -> dict:
    plan = spec["plan"]
    turns = [student_turn(record, index, cut) for index, cut in plan]
    assert turns, f"{sid} 空剧本"
    truncations = [{"dialogue_index": index, "cut_prefix": cut}
                   for index, cut in plan if cut]
    stem = re.sub(r"[\s　].*$", "", record["problem"]["text"])[:24]
    return {
        "schema_version": V1,
        "id": sid,
        "title": f"confirmation·{stem}",
        "subject": "math",
        "question": record["problem"]["text"],  # I4
        "student_turns": turns,
        "expect": {"ready_to_record": True},
        "trajectory_tags": [spec["slice"]],
        "compile": {
            "rule": "R1", "form": spec["slice"], "slice": spec["slice"],
            "record_id": sid,
            "student_turn_dialogue_indexes": [index for index, _ in plan],
            "truncations": truncations,
            "dropped_turns": spec.get("dropped", []),
            "answer": record["problem"].get("answer"),
            "selection": {
                "hit_turn_index": spec["hit"],
                "basis": spec["basis"],
            },
            "note": "线性 v1 原文照录" + (";截断=剥回执/强依赖开场白" if truncations else "")
                    + (";轮级丢弃见 dropped_turns" if spec.get("dropped") else ""),
        },
    }


def verify_invariants(records: dict[str, dict], r3_ids: set[str],
                      scenarios: list[dict]) -> None:
    """I5/I6/I7 + 判定轮与剧本一致性(违者断言失败,不造数据)。"""
    assert not (set(SELECTION) & r3_ids), "I7 违例:与 r3 已用 23 案重叠"
    assert not (set(SELECTION) & R3_USED), "I7 违例:与内置 r3 排除清单重叠"
    for scenario in scenarios:
        sid = scenario["id"]
        record = records[sid]
        spec = SELECTION[sid]
        plan = spec["plan"]
        assert scenario["question"] == record["problem"]["text"], f"{sid} I4 违例"
        if spec["slice"] in (SLICE_POS, SLICE_866):
            assert said_index(record, plan) == spec["hit"], \
                f"{sid} I5 违例:judge said 轮 {said_index(record, plan)} != 判定轮 {spec['hit']}"
            assert spec["hit"] in [i for i, _ in plan], f"{sid} 判定轮不在剧本"
        else:
            assert said_index(record, plan) is None, \
                f"{sid} I6 违例:负向剧本上 said 置位(轮 {said_index(record, plan)})"
            assert not raw_answer_in_script(record, plan), \
                f"{sid} I6 违例:答案原值出现在剧本学生轮"


def build_payload(records: dict[str, dict], r3_ids: set[str]) -> dict:
    scenarios = [build_scenario(sid, SELECTION[sid], records[sid])
                 for sid in SELECTION]
    verify_invariants(records, r3_ids, scenarios)
    by_slice = {s: sum(1 for x in scenarios if x["compile"]["slice"] == s)
                for s in (SLICE_POS, SLICE_NEG, SLICE_866)}
    return {
        "schema": "edu_agent_external_slice_executable/v1",
        "slice_version": "socraticmath_confirmation_v1",
        "status_note": (
            "confirmation 预注册(#412 prereg §三)编译件:三 slice 带 slice 标注字段"
            "(compile.slice/trajectory_tags);R1 线性 v1,零 LLM 改写,真人 tutor 轮"
            "不进剧本。跑面建议:positive/type866 进 ER 判分域(form=FORM1 同形或"
            " form=None repro-equivalent);negative 面以「final_state=completed 而 "
            "judge said 全程未置位」为 premature 信号(val_13 型防线)。"
        ),
        "prereg": {
            "doc": "docs/evals/confirmation-bnew-prereg-v1.md(#412 已合)",
            "section": "§三 样本集(选择条件只看源面,不看任何臂输出)",
            "protocol": "docs/evals/external-slice-compilation-protocol-v1.md(#398 制度沿用)",
        },
        "compiled_from": {
            "slice_version": "socraticmath_confirmation_v1",
            "normalized_file": "edu_agent/evals/datasets/external_normalized/"
                               "socraticmath.jsonl",
            "normalized_sha256": sha256_of(NORMALIZED),
            "records": len(records),
            "excluded_r3_used": sorted(R3_USED),
            "excluded_r3_used_count": len(R3_USED),
            "excluded_r3_used_source": "socraticmath_executable_v1.json scenarios"
                                       "(23 案,prereg §三排除条款;I7 零重叠断言)",
        },
        "selection_discipline": (
            "防 p-hack 红线:选择条件只看源题面与学生话语(problem.text/answer + "
            "reference_dialogue),不看任何臂输出;逐案判定依据(哪一轮、什么特征)"
            "见 selection_evidence——只引源对话内容。"
        ),
        "compile_protocol": {
            "rules": {"R1": "全弱依赖→线性 v1;学生轮原文照录,仅允许截断(剥回执/"
                            "强依赖开场白)与轮级丢弃,逐处记录",
                      "R2": "本批无适用(无强依赖中后段截断案)",
                      "R3": "本批无适用(24/24 全 R1 线性;无分支剧本,无路由面)",
                      "R4": "本批无弃案(池探阶段淘汰者未入 SELECTION,排除理由分类"
                            "记录于 selection_funnel,非编译期弃案)"},
            "invariants": ["I1 学生文本⊆源 student 轮原文(截断记录)",
                           "I4 question 与源 problem.text 逐字一致",
                           "I5 positive/type866:ER judge v2 said 恰在判定终答轮置位",
                           "I6 negative:said 全剧本永不置位且答案原值不入剧本轮",
                           "I7 与 r3 已用 23 案零重叠"],
        },
        "selection_funnel": FUNNEL,
        "judge_alignment_note": (
            "ER judge v2(裁令④)为冻结判分器;其 answer_keys 对关系型答案要求原串"
            "可见、对枚举/换算段有剥除——故编译期以 said_index 对齐闸(I5/I6)保证:"
            "positive/type866 的判定终答轮恰是运行时 said 置位轮(分母成立),"
            "negative 的剧本轮上 said 永不置位(premature 信号不漏)。"
        ),
        "compile_review": {
            "obligation": "初稿人工=编译执行代理:~100 条候选逐条通读;每 slice 抽 2 "
                          "条编译结果全通读(见 readback)。",
            "readback": {
                SLICE_POS: ["socraticmath_train_2960", "socraticmath_train_3138"],
                SLICE_NEG: ["socraticmath_train_2791", "socraticmath_train_5181"],
                SLICE_866: ["socraticmath_train_5234", "socraticmath_train_4827"],
            },
            "verdict": "positive 抽读 2 条(2960/3138):截断后学生轮自足、终答轮保真、"
                       "追问/摇摆链完整。negative 抽读 2 条(2791/5181):剧本轮止步"
                       "形态成立、无答案泄露、丢弃轮理由属实。type866 抽读 2 条"
                       "(5234/4827):合法终答轮保真、延伸空间在源导师轮可证。",
        },
        "counts": {"positive": by_slice[SLICE_POS],
                   "negative": by_slice[SLICE_NEG],
                   "type866": by_slice[SLICE_866],
                   "total": len(scenarios)},
        "selection_evidence": {sid: {
            "slice": spec["slice"],
            "hit_turn_index": spec["hit"],
            "basis": spec["basis"],
        } for sid, spec in SELECTION.items()},
        "scenarios": scenarios,
    }


def main() -> int:
    records = load_records()
    missing = set(SELECTION) - set(records)
    assert not missing, f"候选回连失败:{sorted(missing)}"
    r3_ids = r3_used_ids()
    assert r3_ids == R3_USED, "r3 已用清单与仓内 executable 不符(排除证据链断)"
    payload = build_payload(records, r3_ids)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(f"compiled={payload['counts']['total']} "
          f"(positive={payload['counts']['positive']}, "
          f"negative={payload['counts']['negative']}, "
          f"type866={payload['counts']['type866']}); all R1 linear")
    print(f"written: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
