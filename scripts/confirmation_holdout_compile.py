#!/usr/bin/env python3
"""fresh confirmation holdout 编译器(终裁执行链⑦燃料,C 段预备件)。

输入:edu_agent/evals/datasets/external_normalized/socraticmath.jsonl(6846 条,#392)
减去全部先前曝光/调优用案(反污染铁律,I7' 零重叠断言):
  - r2/r3 双臂 26 案的 socraticmath 23 案(socraticmath_executable_v1.json,
    #398;含 ablation 五臂 8 案、ER judge v2 DEV10 人审 10 案之 socraticmath 部分、
    ER judge v2 holdout 16 未曝光案——均为 r3 26 案子集);
  - confirm 双臂批次 24 案(socraticmath_confirmation_v1.json,#413;
    含负向三案 2791/5106/3490);
  - boundary gold(A 段单测合成案,零语料案 ID,与本池无交集——核验记录)。
输出:edu_agent/evals/datasets/external_slices/socraticmath_confirmation_holdout_v1.json

用途:baseline 系统 vs baseline+Gate 的 fresh confirmation(#414 设计 v3.1 §六.3:
32 案 regression 重放全绿后才点火)。形态对齐 #413 先例(16/6/2 目标配比),
不足如实报数不硬凑:负向 6(自然止步 2 + 确定性截断变换 4,逐处记录)、
866 型 0(余量池该形态枯竭,理由分类入 selection_funnel)。

选择纪律(防 p-hack 红线,#412 prereg §三沿用):只看源题面与学生话语,
不看任何臂输出;逐案判定依据见 selection_evidence。
确定性变换(同 #253 counterfactual 精神,非 LLM 改写):负向不足部分取
未曝光正向形态源案,在终答轮前按记录的轮位机械截断(cut_before),
I6 闸(零断言+原值不入轮)机械复验;变换案逐案带 origin=transform 与
cut_before 记录,判读时可分层(方法差异见 selection_funnel.note,留人审)。

硬不变量(边编译边断言,违者非零退出):
  I1 学生文本⊆源 student 轮原文(截断记录);
  I4 question 与源 problem.text 逐字一致;
  I5 positive:ER judge v2 语义下 said 恰在判定终答轮置位(截断后剧本轮);
  I6 negative:said 全剧本永不置位,且答案原值(数值 token/规范化文本)
     不出现在任何剧本学生轮;
  I7' 与全部曝光名单零重叠(r3 23 + confirm 24 + repro 3 + DEV10/holdout16
     子集核验);变换案另验 cut_before 轮确为源终答轮。
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
       "socraticmath_confirmation_holdout_v1.json")
SELECT_HELPER = REPO / "scripts/external_slice_select.py"
JUDGE_PATH = REPO / "edu_agent/evals/artifacts/er-judge-v2/er_judge_v2.py"
R3_EXECUTABLE = (REPO / "edu_agent/evals/datasets/external_slices/"
                 "socraticmath_executable_v1.json")
CONFIRMATION = (REPO / "edu_agent/evals/datasets/external_slices/"
                "socraticmath_confirmation_v1.json")

V1 = "small_lecturer_dialogue_scenario/v1"
SLICE_POS = "confirmation_positive_student_final_answer"
SLICE_NEG = "confirmation_negative_student_stops_short"
SLICE_866 = "confirmation_type866_answer_complete_extensible"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


er = _load_module("er_judge_v2", JUDGE_PATH)
sel = _load_module("external_slice_select", SELECT_HELPER)

# ── 选定案与编译计划(人工判定定稿 2026-09-23;编译执行代理逐案通读)────────
# plan=[(dialogue_index, cut_prefix)];hit=终答轮(正);dropped=轮级丢弃;
# origin=fresh_scan(自然扫描)|transform(确定性截断,须带 cut_before);
# read_by=#398 v1 候选索引读档记录(读档≠曝光,先例 #413 I7 仅排已用案)。
SELECTION: dict[str, dict] = {
    # —— positive 16(目标配比 16;数值/文本/代数 8 + 字母断言 8)——
    "socraticmath_train_191": {
        "slice": SLICE_POS, "hit": 2,
        "plan": [(2, ""), (4, "")],
        "basis": "t2「860除以5是172。」——终答句(除法直给);t3 源导师确认,"
                 "t4 学生方法回执——干净收束面。",
        "read_by": "#398 v1 索引读档(form1 池探,未编译未跑)",
    },
    "socraticmath_train_2013": {
        "slice": SLICE_POS, "hit": 2,
        "plan": [(2, ""), (4, "")],
        "basis": "t2「这应该用分数来表示。」——术语终答句;t3 源导师确认,"
                 "t4 致谢——干净收束面。",
        "read_by": "#398 v1 索引读档(form1 池探,未编译未跑)",
    },
    "socraticmath_train_2301": {
        "slice": SLICE_POS, "hit": 8,
        "plan": [(2, ""), (4, ""), (6, ""), (8, ""), (10, "")],
        "basis": "t2 拆分(500×4 与 1+2+3)、t4 部分和 2000、t6 部分和 6,"
                 "t8「结果应该是2006。」——终答句;t9 确认,t10 回执。",
    },
    "socraticmath_train_2804": {
        "slice": SLICE_POS, "hit": 8,
        "plan": [(2, ""), (4, ""), (6, ""), (8, ""), (10, "")],
        "basis": "t6 中间和 218 元,t8「那么，总共是353元。」——终答句;"
                 "t10 方法总结轮(实质收尾)。",
    },
    "socraticmath_train_4248": {
        "slice": SLICE_POS, "hit": 10,
        "plan": [(2, ""), (4, ""), (6, ""), (8, ""),
                 (10, "对不起老师，我算错了，"), (12, "")],
        "basis": "t4 错式 x+36=24→t6 正式 x+24=36→t8 错答 11→t10(截回执)"
                 "「36减24应该是12。」——终答句(纠错链);t12 致谢。",
    },
    "socraticmath_train_4531": {
        "slice": SLICE_POS, "hit": 2,
        "plan": [(2, ""), (4, "")],
        "basis": "t2「所以总的水费就是6a+2b。」——代数终答句(分段计费完整"
                 "推导);t4 代数表达理解延伸轮。",
        "read_by": "#398 v1 索引读档(form1 池探,未编译未跑)",
    },
    "socraticmath_train_5362": {
        "slice": SLICE_POS, "hit": 6,
        "plan": [(2, ""), (4, ""), (6, ""), (8, "")],
        "basis": "t4 代入「20乘13加4减6」,t6「我算一下…得到258。」——终答句"
                 "(含中间量 260);t8 回执。",
    },
    "socraticmath_train_4616": {
        "slice": SLICE_POS, "hit": 8,
        "plan": [(2, ""), (4, ""), (6, ""), (8, "")],
        "basis": "t2 面积公式、t6 分量(4r²/πr²)、t8「比是4：π。」——终答句"
                 "(判定轮=judge said 轮 t8;扫描初命中 t6 为分量误中,已弃)。",
    },
    "socraticmath_train_271": {
        "slice": SLICE_POS, "hit": 6,
        "plan": [(2, ""), (4, ""), (6, "哦，我明白了，我判断错了，")],
        "basis": "t4 推理正确(1208≠20)但选错字母 A,t5 源导师指出判断口径,"
                 "t6(截回执)「应该选B，意思是题目判断错了。」——字母终答"
                 "(摇摆/纠错形态,2960 同款)。",
    },
    "socraticmath_train_1548": {
        "slice": SLICE_POS, "hit": 8,
        "plan": [(2, ""), (4, ""), (6, ""), (8, "")],
        "basis": "t2/t4 方程与不等式概念、t6 判定 3x+1＞2 非等式,t8「答案是A，"
                 "这是一个不等式，不是方程。」——字母终答(概念 buildup)。",
    },
    "socraticmath_train_1960": {
        "slice": SLICE_POS, "hit": 8,
        "plan": [(2, ""), (4, ""), (6, ""), (8, "")],
        "basis": "t6 前后项不可互换(含 3比4 例),t8「不正确，所以答案是B。」"
                 "——字母终答。",
    },
    "socraticmath_train_4609": {
        "slice": SLICE_POS, "hit": 8,
        "plan": [(2, ""), (4, ""), (6, ""), (8, "哦，对不起，老师，我犯错了。")],
        "basis": "t6 错选 A(偶数+1 不一定奇数),t7 源导师质疑,t8(截回执)"
                 "「所以答案应该是选B，题目的说法是正确的。」——字母终答"
                 "(摇摆形态)。",
    },
    "socraticmath_train_5063": {
        "slice": SLICE_POS, "hit": 6,
        "plan": [(2, ""), (4, ""), (6, "")],
        "basis": "t4 轴对称对折推理,t6「应该是A，等腰梯形是轴对称图形。」"
                 "——字母终答;干净收束面。",
    },
    "socraticmath_test_88": {
        "slice": SLICE_POS, "hit": 6,
        "plan": [(2, ""), (4, ""), (6, "噢！我明白了，")],
        "basis": "t4 错答(1000 平方米),t5 源导师纠单位乘法,t6(截回执)"
                 "「那这个题的答案应该是A，不对。」——字母终答(纠错形态)。",
    },
    "socraticmath_train_862": {
        "slice": SLICE_POS, "hit": 6,
        "plan": [(2, ""), (4, ""), (6, "")],
        "basis": "t2/t4 试商推理(余数=除数→商+1 恰尽),t6「我觉得答案应该是B，"
                 "题目说法正确。」——字母终答。",
    },
    "socraticmath_train_3114": {
        "slice": SLICE_POS, "hit": 6,
        "plan": [(2, ""), (4, ""), (6, "")],
        "basis": "t4 公顷↔平方米进率 10000(反例),t6「…所以它应该是错的，就选B。」"
                 "——字母终答(概念修正链)。",
    },
    # —— negative 6(目标配比 6;自然止步 2 + 确定性截断变换 4)——
    "socraticmath_train_838": {
        "slice": SLICE_NEG, "hit": None,
        "plan": [(2, ""), (4, "")],
        "dropped": [{"index": 6, "reason": "源导师 t5 报出 2.84 后的纯回执"
                                           "(「我明白了,谢谢老师」),不可独立成步"}],
        "origin": "fresh_scan",
        "basis": "止步于区间分析:t2 四舍五入规则,t4 区间判断(「2.75到2.79…都是2.8,"
                 "2.85以后…2.9」——且漏 2.80-2.84 段,分析有误),最大两位小数终未给出;"
                 "源导师 t5 报 2.84。",
    },
    "socraticmath_train_3096": {
        "slice": SLICE_NEG, "hit": None,
        "plan": [(2, ""), (4, "")],
        "dropped": [{"index": 6, "reason": "源导师 t5 代算后的纯回执"
                                           "(「哦,我明白了…谢谢老师」),不可独立成步"}],
        "origin": "fresh_scan",
        "basis": "止步于方法探问:t2 比的定义,t4 方法假设(「然后相乘就可以得到…"
                 "吗?」),连比换算(统一乙数 6:10=10:5)终未执行;源导师 t5 代算。",
    },
    "socraticmath_train_2869": {
        "slice": SLICE_NEG, "hit": None,
        "plan": [(2, ""), (4, ""), (6, "")],
        "origin": "transform",
        "transform": {"kind": "cut_before_assertion", "cut_before": 8,
                      "source_hit_turn": 8,
                      "note": "源 t8 为终答轮(「后项从8变为了32，那就应该加上24」);"
                              "截断后止步于方法(后项应乘以4),换算(8×4=32)与"
                              "加量(24)未执行——5181 同款形态"},
        "basis": "止步于方法:t2 比的定义,t4 不知比例性,t6「比的后项应该也乘以4」"
                 "(方法已立),换算与加法未执行。",
    },
    "socraticmath_train_5220": {
        "slice": SLICE_NEG, "hit": None,
        "plan": [(2, ""), (4, "")],
        "origin": "transform",
        "transform": {"kind": "cut_before_assertion", "cut_before": 6,
                      "source_hit_turn": 6,
                      "note": "源 t6 为终答轮(「我算的结果是17。」);截断后止步于"
                              "算式((420-12)÷24 已列),除法未执行——5181 同款形态"},
        "basis": "止步于算式:t2 除法规则,t4「需要执行（420-12）÷24」(算式已列),"
                 "除法未执行。",
    },
    "socraticmath_train_3797": {
        "slice": SLICE_NEG, "hit": None,
        "plan": [(2, ""), (4, ""), (6, "")],
        "origin": "transform",
        "transform": {"kind": "cut_before_assertion", "cut_before": 8,
                      "source_hit_turn": 8,
                      "note": "源 t8 为终答轮(「…所以答案应该是B，正确。」);"
                              "截断后止步于天数核算,判断未下"},
        "basis": "止步于天数核算:t2 大小月口诀,t4 上/下半年天数初算(182/183,有误),"
                 "t6 修正(181或182/184),「天数都比…少」的判断终未下。",
    },
    "socraticmath_test_241": {
        "slice": SLICE_NEG, "hit": None,
        "plan": [(2, "是的，"), (4, "")],
        "origin": "transform",
        "transform": {"kind": "cut_before_assertion", "cut_before": 6,
                      "source_hit_turn": 6,
                      "note": "源 t6 为终答轮(「所以选项应该是B.」);截断后止步于"
                              "验证计算,判断与选项未下"},
        "basis": "止步于验证计算:t2(截回执)分配律理解,t4「43乘以20就是860，"
                 "860再减去43，就得到817」(验证已算),等式真伪判断与选项终未下。",
    },
    # —— type866 0 案(如实报数,见 selection_funnel)——
}

FUNNEL = {
    "positive": {
        "pool": "normalized 6846 − 曝光排除 47(r3 已用 23 + confirm 24)= 6799",
        "scan": "form1 数值/文本路径(external_slice_select 规则)+ 字母断言路径"
                "(单字母答案+题面选项+said):第一轮 27 raw(其中 12 为 #413 已结构"
                "排除:said_never 7/said_early 3/guess_form 1/源污染 1),字母宽松"
                "补扫 58 raw(其中 5 为 #413 池探读档:1285/2754/4340/4627/4955)",
        "read_manual": "新鲜候选 30 条逐条通读(第一轮 15 + 字母 15);"
                       "排除:1313(终答疑问形态「28+300÷5?」)、1648(said 双置位"
                       "错位,144 为中间量)、1910(said 轮 t8 与首断言 t4 错位)、"
                       "5025(源导师连环翻案污染)、5032(题面残缺)、811/637/4229/"
                       "2834(错答形态/记号拼装/等价形态已给,负向筛余)、18/"
                       "2875/val_305(薄形态,留作负向变换源评估后未用)",
        "final": 16,
        "band": "16(对齐 #413 配比)",
        "form_mix": "数值/文本/代数 8(191/2013/2301/2804/4248/4531/5362/4616)"
                    "+ 字母断言 8(271/1548/1960/4609/5063/test_88/862/3114)"
                    "——字母占比高于 #413(4/16):余量池强形态(终答后源导师假挑战"
                    "再持答)已被 #413 优先收割,数值/文本面以干净收束+纠错摇摆为主,"
                    "如实记录",
    },
    "negative": {
        "pool": "同上;单空题 + judge 全对话零断言 + 答案原值不入任何学生轮"
                "(t0 题面复述轮豁免)+ 学生轮含数值/方法",
        "scan": "确定性预筛 619 raw;导师报答案路径 20(未读 6 逐条通读)、"
                "全对话无答案路径(未读聚焦数值 6 条通读+文本 17 条通读)、"
                "t0 豁免补扫 2 条通读——共 31 条新鲜候选逐条通读",
        "read_manual": "排除分类:多空/比较链逐组完成(54/78/136/392/436/1571/1883/"
                       "3432/3977旧/4130/5317/5400/test_368/test_435 等)、语义等价"
                       "结论已给(1881「剩下的需要修建的路的长度」/2210「垂直线段"
                       "应该更短」/3214「题目的答案是正确的」/4055「有一个0」等)、"
                       "错答形态(637「22个」/811 t12「等于4.62平方厘米」——全文"
                       "通读纠正了截断误读/3378 t6 认同题干)、记号拼装(4229 两位"
                       "逐位已定/5207 符号未填/2834 等价比 8:10 已给)、源污染"
                       "(1213 导师确认错答 81,题库 17/2069 确认错答 5,题库 8/"
                       "2586 导师报 70 亿,题库 7 亿/4334 确认错答 4602,题库 4603/"
                       "test_202 对话 999 与题库 9999 冲突)、薄形态(379 学生仅"
                       "概念复述+附和,3096 前身评估后录用)",
        "final": 6,
        "band": "6(对齐 #413 配比 6)",
        "origin_mix": "自然止步 2(838/3096)+ 确定性截断变换 4(2869/5220/3797/"
                      "test_241,取自本批正向筛余的未曝光源案,终答轮前按记录轮位"
                      "机械截断,I6 闸机械复验)",
        "note": "低于 prereg 区间 8-12 的自然止步供给(2 案)——#413「池穷尽」结论"
                "在新鲜池同样成立:判定类学生均以文字下结论、比较链/多空案逐组"
                "完成、数值路径聚焦池全数源污染(导师确认错答/题库答案冲突 6 案"
                "为新鲜发现);不足部分以确定性变换补足并逐案标记,判读时可分层"
                "(自然 vs 变换),方法差异留人审。",
    },
    "type866": {
        "pool": "同上;答案不唯一/或备选/写一个式/等价表示形态标记扫描",
        "read_manual": "全数排除:或-枚举答案(Gate 多候选红线+judge 枚举段盲区,"
                       "2990/5001/val_148)、多空拼装(17/573/579/1549/5260 等)、"
                       "「其中一个」类伪标记(16/2341/5284 等)",
        "final": 0,
        "band": "2(对齐 #413 实得 2/3-5)",
        "note": "如实报数 0:余量池中 866 形态(学生答案恰与答案键主形态逐字一致+"
                "答案不唯一)已被 #413 收割殆尽,余量为 judge 盲区类与或-形态,"
                "无可编译案。",
    },
}

# 反污染排除宇宙(编译期与仓内文件互证)
R3_USED_COUNT = 23
CONFIRM_COUNT = 24
REPRO_CASES = ("repro-close-loop-cross-stitch", "repro-close-loop-ball-bounce",
               "incident-700m-replay")
DEV10 = ("repro-close-loop-cross-stitch", "socraticmath_train_2591",
         "socraticmath_train_675", "socraticmath_val_13", "socraticmath_train_3565",
         "socraticmath_train_4402", "socraticmath_train_3666",
         "socraticmath_train_866", "repro-close-loop-ball-bounce",
         "socraticmath_train_4275")


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_records() -> dict[str, dict]:
    records: dict[str, dict] = {}
    with NORMALIZED.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            records[record["id"]] = record
    return records


def student_turn(record: dict, index: int, cut: str) -> str:
    turn = record["reference_dialogue"][index]
    assert turn["role"] == "student", f"{record['id']} 轮 {index} 非 student"
    text = turn["text"]
    if cut:
        assert text.startswith(cut), \
            f"{record['id']} 轮 {index} 截断段非原文前缀:{cut!r}"
        text = text[len(cut):]
    return text


def said_index(record: dict, plan: list[tuple[int, str]]) -> int | None:
    case = {"question": {"text": record["problem"]["text"],
                         "answer": record["problem"].get("answer") or ""}}
    keys = er.answer_keys(case)
    for index, cut in plan:
        if er.student_asserts_answer(case, student_turn(record, index, cut), keys):
            return index
    return None


def raw_answer_in_script(record: dict, plan: list[tuple[int, str]]) -> bool:
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
    compile_info = {
        "rule": "R1+T" if spec.get("origin") == "transform" else "R1",
        "form": spec["slice"], "slice": spec["slice"],
        "record_id": sid,
        "student_turn_dialogue_indexes": [index for index, _ in plan],
        "truncations": truncations,
        "dropped_turns": spec.get("dropped", []),
        "answer": record["problem"].get("answer"),
        "origin": spec.get("origin", "fresh_scan"),
        "selection": {"hit_turn_index": spec["hit"], "basis": spec["basis"]},
        "note": "线性原文照录" + (";截断=剥回执/强依赖开场白" if truncations else "")
                + (";轮级丢弃见 dropped_turns" if spec.get("dropped") else "")
                + (";确定性截断变换见 transform" if spec.get("transform") else ""),
    }
    if spec.get("transform"):
        compile_info["transform"] = spec["transform"]
    if spec.get("read_by"):
        compile_info["prior_read_record"] = spec["read_by"]
    return {
        "schema_version": V1,
        "id": sid,
        "title": f"holdout·{stem}",
        "subject": "math",
        "question": record["problem"]["text"],  # I4
        "student_turns": turns,
        "expect": {"ready_to_record": True},
        "trajectory_tags": [spec["slice"]],
        "compile": compile_info,
    }


def verify_invariants(records: dict[str, dict], scenarios: list[dict]) -> None:
    r3_ids = {s["id"] for s in json.loads(
        R3_EXECUTABLE.read_text(encoding="utf-8"))["scenarios"]}
    confirm_ids = {s["id"] for s in json.loads(
        CONFIRMATION.read_text(encoding="utf-8"))["scenarios"]}
    assert len(r3_ids) == R3_USED_COUNT and len(confirm_ids) == CONFIRM_COUNT
    excluded = r3_ids | confirm_ids
    ours = {s["id"] for s in scenarios}
    assert not (ours & excluded), f"I7' 违例:与曝光名单重叠:{sorted(ours & excluded)}"
    # repro/DEV10/ER-judge holdout 均为 r3 26 案子集或非语料案,核验记录入头部
    for scenario in scenarios:
        sid = scenario["id"]
        record = records[sid]
        spec = SELECTION[sid]
        plan = spec["plan"]
        assert scenario["question"] == record["problem"]["text"], f"{sid} I4 违例"
        if spec["slice"] in (SLICE_POS, SLICE_866):
            assert said_index(record, plan) == spec["hit"], \
                f"{sid} I5 违例:said 轮 {said_index(record, plan)} != 判定轮 {spec['hit']}"
            assert spec["hit"] in [i for i, _ in plan], f"{sid} 判定轮不在剧本"
        else:
            assert said_index(record, plan) is None, \
                f"{sid} I6 违例:负向剧本上 said 置位(轮 {said_index(record, plan)})"
            assert not raw_answer_in_script(record, plan), \
                f"{sid} I6 违例:答案原值出现在剧本学生轮"
            if spec.get("origin") == "transform":
                full_plan = plan + [(spec["transform"]["cut_before"], "")]
                assert said_index(record, full_plan) == spec["transform"]["cut_before"], \
                    f"{sid} 变换校验违例:cut_before 轮非源终答轮"


def build_payload(records: dict[str, dict]) -> dict:
    scenarios = [build_scenario(sid, SELECTION[sid], records[sid])
                 for sid in SELECTION]
    verify_invariants(records, scenarios)
    by_slice = {s: sum(1 for x in scenarios if x["compile"]["slice"] == s)
                for s in (SLICE_POS, SLICE_NEG, SLICE_866)}
    r3_ids = {s["id"] for s in json.loads(
        R3_EXECUTABLE.read_text(encoding="utf-8"))["scenarios"]}
    confirm_ids = {s["id"] for s in json.loads(
        CONFIRMATION.read_text(encoding="utf-8"))["scenarios"]}
    return {
        "schema": "edu_agent_external_slice_executable/v1",
        "slice_version": "socraticmath_confirmation_holdout_v1",
        "status_note": (
            "fresh confirmation holdout(终裁执行链⑦燃料,#414 设计 v3.1 §六.3:"
            "32 案 regression 重放全绿后才点火):baseline 系统 vs baseline+Gate "
            "的 fresh confirmation 新案。反污染铁律:与任何先前曝光/调优用案零重叠"
            "(I7' 断言);判分器=ER judge v2 冻结语义;正向门=unnecessary re-ask/"
            "closure,反向硬门=premature completion 不增加且负向 completed 目标 0。"
            "负向含确定性截断变换案(origin=transform,可分层判读);866 型 0 案"
            "如实报数。"
        ),
        "design": {
            "doc": "docs/evals/trusted-completion-gate-design-v3.md",
            "section": "§六.3 fresh holdout(终裁执行链⑦)",
            "prereg_form": "docs/evals/confirmation-bnew-prereg-v1.md(形态沿用,"
                           "#412);编译协议 #398 沿用",
        },
        "compiled_from": {
            "slice_version": "socraticmath_confirmation_holdout_v1",
            "normalized_file": "edu_agent/evals/datasets/external_normalized/"
                               "socraticmath.jsonl",
            "normalized_sha256": sha256_of(NORMALIZED),
            "records": len(records),
            "excluded_r3_used": sorted(r3_ids),
            "excluded_r3_used_count": len(r3_ids),
            "excluded_confirm_24": sorted(confirm_ids),
            "excluded_confirm_24_count": len(confirm_ids),
            "excluded_repro_cases": list(REPRO_CASES),
            "exclusion_note": "排除宇宙=r2/r3 双臂 26 案(23 语料案+repro 3,含 "
                              "ablation 五臂 8/DEV10 人审 10/ER-judge holdout 16 "
                              "子集)+confirm 双臂批次 24 案(含负向三案);boundary "
                              "gold=A 段单测合成案,零语料案 ID,无交集(核验);"
                              "#398 v1 候选索引与 #413 池探的读档案(未编译未跑)"
                              "按先例(#413 I7 仅排已用案)不视为曝光,逐案 "
                              "prior_read_record 字段透明登记。",
        },
        "selection_discipline": (
            "防 p-hack 红线:选择条件只看源题面与学生话语(problem.text/answer + "
            "reference_dialogue),不看任何臂输出;逐案判定依据见 selection_evidence;"
            "确定性变换(负向不足部分)=未曝光正向形态源案在终答轮前的机械截断,"
            "逐处记录 cut_before,I6 闸机械复验——非 LLM 改写。"
        ),
        "compile_protocol": {
            "rules": {
                "R1": "全弱依赖→线性照录;学生轮原文照录,仅允许截断(剥回执/"
                      "强依赖开场白)与轮级丢弃,逐处记录",
                "R1+T": "R1 + 确定性截断变换:在源终答轮(cut_before,经 judge said "
                        "校验)前截断,变换记录入 compile.transform",
                "R2/R3": "本批无适用(全线性,无分支剧本)",
                "R4": "本批编译期无弃案(池探淘汰者未入 SELECTION,排除理由分类"
                      "记录于 selection_funnel)",
            },
            "invariants": ["I1 学生文本⊆源 student 轮原文(截断记录)",
                           "I4 question 与源 problem.text 逐字一致",
                           "I5 positive:ER judge v2 said 恰在判定终答轮置位",
                           "I6 negative:said 全剧本永不置位且答案原值不入剧本轮"
                           "(变换案另验 cut_before 轮确为源终答轮)",
                           "I7' 与全部曝光名单零重叠(r3 23+confirm 24+repro 3;"
                           "DEV10/ER-judge holdout 16 为子集核验)"],
        },
        "selection_funnel": FUNNEL,
        "exposure_check": {
            "r3_26(r2/r3 双臂)": "pass(23 语料案 I7' 断言;repro 3 案非语料池)",
            "ablation 五臂 8 案": "pass(⊂ r3 26)",
            "人审 10 案(DEV10)": "pass(⊂ r3 26)",
            "confirm 24 案(#413)": "pass(I7' 断言)",
            "负向三案(2791/5106/3490)": "pass(⊂ confirm 24)",
            "boundary gold(A 段)": "pass(单测合成案,零语料案 ID,与本池无交集)",
            "ER judge v2 holdout 16": "pass(⊂ r3 26)",
            "prior_reads": "3 案(191/2013/4531)曾入 #398 v1 候选索引(读档未编译"
                           "未跑)——逐案 prior_read_record 登记;读档≠曝光,"
                           "先例 #413 I7 仅排已用案",
        },
        "compile_review": {
            "obligation": "初稿人工=编译执行代理:负向五路 31 条新鲜候选逐条通读,"
                          "正向 30 条新鲜候选逐条通读(811 全文通读纠正截断误读,"
                          "曾误判为止步实为错答形态);每 slice 抽 2 条编译结果"
                          "全通读(见 readback)。",
            "readback": {
                SLICE_POS: ["socraticmath_train_4248", "socraticmath_train_271"],
                SLICE_NEG: ["socraticmath_train_838", "socraticmath_test_241"],
            },
            "verdict": "positive 抽读 2 条(4248/271):截断后学生轮自足、终答轮保真、"
                       "纠错/摇摆链完整。negative 抽读 2 条(838/test_241):838 "
                       "止步形态成立、区间分析之误如实保留;test_241 变换截点"
                       "确在源终答轮前、I6 复验通过、无答案泄露。",
        },
        "counts": {"positive": by_slice[SLICE_POS],
                   "negative": by_slice[SLICE_NEG],
                   "type866": by_slice[SLICE_866],
                   "total": len(scenarios),
                   "negative_natural": sum(
                       1 for s in scenarios
                       if s["compile"]["slice"] == SLICE_NEG
                       and s["compile"]["origin"] == "fresh_scan"),
                   "negative_transform": sum(
                       1 for s in scenarios
                       if s["compile"]["slice"] == SLICE_NEG
                       and s["compile"]["origin"] == "transform")},
        "selection_evidence": {sid: {
            "slice": spec["slice"],
            "hit_turn_index": spec["hit"],
            "basis": spec["basis"],
            "origin": spec.get("origin", "fresh_scan"),
        } for sid, spec in SELECTION.items()},
        "scenarios": scenarios,
    }


def main() -> int:
    records = load_records()
    missing = set(SELECTION) - set(records)
    assert not missing, f"候选回连失败:{sorted(missing)}"
    payload = build_payload(records)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    c = payload["counts"]
    print(f"compiled={c['total']} (positive={c['positive']}, "
          f"negative={c['negative']} [natural={c['negative_natural']}, "
          f"transform={c['negative_transform']}], type866={c['type866']})")
    print(f"written: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
