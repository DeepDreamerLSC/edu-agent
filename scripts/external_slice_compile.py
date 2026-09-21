#!/usr/bin/env python3
"""slice 候选 → 可执行 scenario 编译器(#382 步骤 7 ·经理 v2 编译协议 PR #396)。

输入:edu_agent/evals/datasets/external_slices/socraticmath_v1.json(36 候选,#394)
  + edu_agent/evals/datasets/external_normalized/socraticmath.jsonl(reference_dialogue 回连)。
输出:edu_agent/evals/datasets/external_slices/socraticmath_executable_v1.json。

编译规则 R1-R4(协议操作化;协议正本 fetch 超时未取到,以任务内联版为准,见输出头部):
  R1 全弱依赖→线性 v1(学生轮原文照录;仅允许截断——turn 级丢弃或句内剥强依赖
     开场白,逐处记录);
  R2 强依赖在中后段→截断稳定前缀(记录截断位;本批无适用——F1 全 all_weak,F2
     强依赖轮即形态本体归 R3,唯一需中段切除的 5221 按宁少勿滥弃);
  R3 强依赖需保留→v2 分支:纠错步 claim 分支 when.assistant_contains_any=被回应
     tutor 轮的特征子串(脚本机械提取候选,人工通读定稿,宁 specific 勿泛化、宁漏
     勿误),student_response=该真实学生轮原文;同步恰一条 fallback,文本取同案例
     另一弱依赖真实轮(本批全部如此,无新写文本);
  R4 弃案从严,逐条记录原因。

硬不变量(边编译边断言,违者非零退出——不造数据):
  I1 v1 student_turns / v2 student_response 每条都是源记录某 student 轮的原文
     子串(允许剥前缀,记录截断文本);
  I2 v2 非兜底分支的每个特征子串都 ⊆ 被回应 tutor 轮原文;
  I3 每步恰一条 fallback,非兜底分支必有 contains 触发条件;
  I4 场景 question 与源 problem.text 逐字一致。

人工确认环节(初稿人工=编译执行代理,2026-09-21):36 条 reference_dialogue
逐条通读;R3 特征逐分支回读原对话校准;每形态抽 3 条全通读编译结果(见输出
头部 compile_review)。纯规则零模型;不建 simulator;真人 tutor 轮不进剧本。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SLICES = REPO / "edu_agent/evals/datasets/external_slices/socraticmath_v1.json"
NORMALIZED = REPO / "edu_agent/evals/datasets/external_normalized/socraticmath.jsonl"
OUT = REPO / "edu_agent/evals/datasets/external_slices/socraticmath_executable_v1.json"

V1 = "small_lecturer_dialogue_scenario/v1"
V2 = "small_lecturer_dialogue_scenario/v2"
FORM1 = "form1_student_answered_tutor_keeps_asking"
FORM2 = "form2_student_corrects_tutor"

# 机械特征提取的领域名词表(只影响候选生成,不影响定稿;定稿须过 I2 断言)。
_DOMAIN_NOUNS = (
    "整除|因数|倍数|十分位|百分位|比例|方程|等式|选项|题目|近似数|四舍五入|单位|"
    "直径|半径|面积|体积|容积|热水瓶|平方|千米|厘米|分米|口算|日记|体重|腰围|"
    "思路|操作|表述|写为|写成|代表实际|减少|下降|成立|判断")
_LEADING = re.compile(r"^(那么|那|所以|是的|对的|其实|也就是说|然后|我们|你注意|请注意)[^，。]{0,6}")


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_inputs() -> tuple[dict, dict[str, dict]]:
    slices = json.loads(SLICES.read_text(encoding="utf-8"))
    want = {e["id"] for entries in slices["slices"].values() for e in entries}
    records: dict[str, dict] = {}
    with NORMALIZED.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record.get("id") in want:
                records[record["id"]] = record
    missing = want - set(records)
    assert not missing, f"候选回连失败:{sorted(missing)}"
    return slices, records


def student_text(record: dict, index: int, cut: str = "") -> str:
    """I1:取源 student 轮原文;cut 为被剥掉的强依赖开场白(必须是原文前缀)。"""
    turn = record["reference_dialogue"][index]
    assert turn["role"] == "student", f"{record['id']} 轮 {index} 不是 student"
    text = turn["text"]
    if cut:
        assert text.startswith(cut), f"{record['id']} 轮 {index} 截断段非原文前缀:{cut!r}"
        text = text[len(cut):]
    return text


def extract_feature_candidates(text: str) -> list[str]:
    """机械提取 R3 特征候选(数字表达式/含领域名词的子句/问句核心),5-8 个。

    只做候选,不定稿;定稿由人工回读原对话校准(宁 specific 勿泛化)。
    """
    candidates: list[str] = []

    def _add(value: str) -> None:
        value = value.strip("，,。；;： " + "\"'")
        if 3 <= len(value) <= 48 and value not in candidates:
            candidates.append(value)

    for token in re.findall(r"[0-9][0-9.%．×÷+\-*/=…]*|\.[0-9][0-9]*", text):
        if len(token) >= 2:
            _add(token)
        for match in re.finditer(re.escape(token), text):
            _add(text[max(0, match.start() - 6):match.end() + 6])  # 数字±语境
    parts = re.split(r"([。？！；;])", text)
    for clause, sep in zip(parts[0::2], parts[1::2] + [""], strict=False):
        clause = _LEADING.sub("", clause.strip("，, ")).strip("，, ")
        if not clause:
            continue
        if sep in ("？", "?", "!"):  # 问/叹句:整句+尾部核心(去铺垫)
            _add(clause)
            _add(clause[-12:])
        elif re.search(_DOMAIN_NOUNS, clause):
            _add(clause)
    candidates.sort(key=len, reverse=True)
    return candidates[:8]


def build_v1(sid: str, form: str, rule: str, record: dict,
             plan: list[tuple[int, str]], note: str) -> dict:
    turns = []
    truncations = []
    for index, cut in plan:
        if cut:
            truncations.append({"dialogue_index": index, "cut_prefix": cut})
        turns.append(student_text(record, index, cut))
    assert turns, f"{sid} 空剧本"
    return {
        "schema_version": V1, "id": sid,
        "title": plan_title(record),
        "subject": "math",
        "question": record["problem"]["text"],  # I4
        "student_turns": turns,
        "expect": {"ready_to_record": True},
        "trajectory_tags": [form],
        "compile": {
            "rule": rule, "form": form, "record_id": record["id"],
            "student_turn_dialogue_indexes": [i for i, _ in plan],
            "truncations": truncations, "note": note,
        },
    }


def plan_title(record: dict) -> str:
    stem = re.sub(r"[\s　].*$", "", record["problem"]["text"])[:24]
    return f"外部slice·{stem}"


def _branch(bid: str, kind: str, response: str, *, keys=(), fallback=False) -> dict:
    when: dict = {"assistant_contains_any": list(keys), "assistant_contains_all": [],
                  "interaction_states": [], "fallback": fallback}
    return {"id": bid, "response_kind": kind, "when": when,
            "student_response": response, "trajectory_tags": []}


def build_v2(sid: str, form: str, record: dict, plan: dict) -> dict:
    """R3:prefix 弱轮步(单兜底)+ 纠错步(claim/fallback)+ suffix 弱轮步。

    plan 键:prefix[(idx,cut)]、claim{turn,keys,resp(idx,cut)}、fallback(idx,cut)、
    suffix[(idx,cut)]、dropped[{index,reason}]、note。
    """
    steps, audit, step_cuts = [], [], {}
    for n, (index, cut) in enumerate(plan["prefix"], 1):
        if cut:
            step_cuts[f"prefix_{n}"] = {"dialogue_index": index, "cut_prefix": cut}
        steps.append({"id": f"prefix_{n}", "branches": [
            _branch("fallback", "correct", student_text(record, index, cut),
                    fallback=True)]})
    claim = plan["claim"]
    claim_text = record["reference_dialogue"][claim["turn"]]["text"]
    assert record["reference_dialogue"][claim["turn"]]["role"] == "tutor"
    for key in claim["keys"]:  # I2
        assert key in claim_text, f"{sid} 特征非 claim 轮原文子串:{key!r}"
    audit.append({
        "dialogue_index": claim["turn"], "claim_turn_text": claim_text,
        "mechanical_candidates": extract_feature_candidates(claim_text),
        "chosen_features": claim["keys"],
    })
    resp_idx, resp_cut = claim["resp"]
    correction = student_text(record, resp_idx, resp_cut)
    fb_idx, fb_cut = plan["fallback"]
    steps.append({"id": "correction", "branches": [
        _branch("claim_match", "corrects_tutor", correction, keys=claim["keys"]),
        _branch("fallback", "correct", student_text(record, fb_idx, fb_cut),
                fallback=True),
    ]})
    # 协议 R3 判读标注:claim 命中=真实回应,fallback=降级回应(A/B 路由分布差=公平性证据)
    steps[-1]["branches"][0]["trajectory_tags"] = ["真实回应"]
    steps[-1]["branches"][1]["trajectory_tags"] = ["降级回应"]
    for n, (index, cut) in enumerate(plan["suffix"], 1):
        if cut:
            step_cuts[f"suffix_{n}"] = {"dialogue_index": index, "cut_prefix": cut}
        steps.append({"id": f"suffix_{n}", "branches": [
            _branch("fallback", "correct", student_text(record, index, cut),
                    fallback=True)]})
    for step in steps:  # I3
        fallbacks = [b for b in step["branches"] if b["when"]["fallback"]]
        assert len(fallbacks) == 1, f"{sid} 步 {step['id']} 兜底数 {len(fallbacks)} != 1"
        for branch in step["branches"]:
            if not branch["when"]["fallback"]:
                assert branch["when"]["assistant_contains_any"], f"{sid} 不可达分支"
    return {
        "schema_version": V2, "id": sid,
        "title": plan_title(record),
        "subject": "math",
        "question": record["problem"]["text"],  # I4
        "max_turns": len(steps),
        "expect": {"ready_to_record": True},
        "trajectory_tags": [form],
        "steps": steps,
        "compile": {
            "rule": "R3", "form": form, "record_id": record["id"],
            "claim_turn_index": claim["turn"],
            "correction_dialogue_index": resp_idx,
            "correction_cut_prefix": resp_cut,
            "fallback_dialogue_index": fb_idx, "fallback_cut_prefix": fb_cut,
            "dropped_turns": plan["dropped"], "feature_audit": audit,
            "step_cuts": step_cuts, "note": plan["note"],
        },
    }


# ── 人工确认环节定稿(初稿人工=编译执行代理,逐条回读原对话后落子)──────────
# v1 计划:plan=[(dialogue_index, cut_prefix)];cut_prefix 非空=剥掉该强依赖
# 开场白(I1 断言其为原文前缀)。
V1_PLAN: dict[str, tuple[str, list[tuple[int, str]]]] = {
    # R1 全弱、零截断(7 条)
    "socraticmath_train_1204": (FORM1, [(2, ""), (4, ""), (6, ""), (8, "")]),
    "socraticmath_train_866": (FORM1, [(2, ""), (4, ""), (6, ""), (8, ""),
                                       (10, ""), (12, "")]),
    "socraticmath_train_4510": (FORM1, [(2, ""), (4, ""), (6, "")]),
    "socraticmath_train_4776": (FORM1, [(2, ""), (4, ""), (6, ""), (8, "")]),
    "socraticmath_val_412": (FORM1, [(2, ""), (4, ""), (6, "")]),
    "socraticmath_train_559": (FORM1, [(2, ""), (4, ""), (6, ""), (8, ""),
                                       (10, "")]),
    "socraticmath_train_1559": (FORM1, [(2, ""), (4, ""), (6, "")]),
    # R1 含截断记录(7 条):剥的是词法标记检不出的隐性强依赖开场白(认错/回执)
    "socraticmath_train_4402": (FORM1, [
        (2, ""), (4, ""), (6, ""),
        (8, "哦哦，对不起老师是我不小心，"), (10, "")]),
    "socraticmath_train_3666": (FORM1, [
        (2, ""), (4, ""), (6, "如果交换一下的话，")]),
    "socraticmath_train_223": (FORM1, [
        (2, ""), (4, ""), (6, "哎呀，我理解错了，")]),
    "socraticmath_train_5191": (FORM1, [
        (2, ""), (4, ""), (6, "哦，我明白了，是我混淆了。")]),
    "socraticmath_train_2591": (FORM1, [
        (2, ""), (4, "哦，原来是这样，"), (6, ""), (8, "啊，对不起，我犯了个错，")]),
    "socraticmath_train_5228": (FORM1, [
        (2, ""), (4, ""), (6, ""), (8, "哦，我知道了，")]),
    "socraticmath_train_3565": (FORM1, [
        (2, ""), (4, ""), (6, "哦哦，犯了个错误，")]),
}

# v2 计划(R3,9 条):prefix/claim/fallback/suffix/dropped/note。
V2_PLAN: dict[str, dict] = {
    "socraticmath_train_1827": {
        "prefix": [(2, ""), (4, "")],
        "claim": {"turn": 5,
                  "keys": ["被48整除", "又能被48", "同时又能被48整除"],
                  "resp": (6, "")},
        "fallback": (8, ""),
        "suffix": [(10, "")],
        "dropped": [],
        "note": "强形态:因数方向说反(『又能被48整除』),学生纠正为『48能被它整除』;"
                "三特征均为错误签名变体,正确教学(『48的因数』『能整除48』)不含之。",
    },
    "socraticmath_val_61": {
        "prefix": [(2, "")],
        "claim": {"turn": 3,
                  "keys": ["12-10=2", "2只小船和10只大船", "这样解对吗"],
                  "resp": (4, "")},
        "fallback": (8, ""),
        "suffix": [(10, "")],
        "dropped": [{"index": 6, "reason": "裸答『应该坐在小船上。』强上下文(答特定问句),不可独立成步"}],
        "note": "强形态:10大船+2小船过渡解被学生以『超过46人』驳回;数字式特征 12-10=2 锐利。",
    },
    "socraticmath_train_1001": {
        "prefix": [(2, "")],
        "claim": {"turn": 3,
                  "keys": ["四舍五入为.7", "十分位如果是大于等于5"],
                  "resp": (4, "")},
        "fallback": (6, ""),
        "suffix": [(8, ""), (10, "")],
        "dropped": [],
        "note": "强形态但仅 2 特征定稿:第 3 候选『其实它应该被四舍五入为』会把"
                "『四舍五入为6.8』的正确教学误路由至纠错(学生将驳正确句),按宁漏勿误弃用;"
                "两特征均为原句错误签名,漏配走 fallback 保对话不断。",
    },
    "socraticmath_train_675": {
        "prefix": [(2, ""), (4, "")],
        "claim": {"turn": 5,
                  "keys": ["代表实际的100厘米", "题目的表述你认为对吗",
                           "1厘米代表实际的100厘米"],
                  "resp": (6, "")},
        "fallback": (8, "现在我知道了，"),
        "suffix": [],
        "dropped": [],
        "note": "强形态:比例尺 1:100 单位口径(100 厘米 vs 题面 100 米),学生指出题面"
                "与导师口径不一致;fallback 取轮 8 截断(剥导师问句回执)。",
    },
    "socraticmath_train_4275": {
        "prefix": [(2, ""), (4, ""), (6, ""), (8, ""), (10, ""), (12, "")],
        "claim": {"turn": 13,
                  "keys": ["549千米", "全年跑了549", "写的全年跑了549千米"],
                  "resp": (14, "")},
        "fallback": (16, ""),
        "suffix": [(18, ""), (20, ""), (22, "")],
        "dropped": [],
        "note": "中段路径最长案:日记多错误串行排查,纠错对象为导师转述的 549 千米;"
                "特征锚定数字 549,题面复述亦命中(转述即路由语境,合形态语义)。",
    },
    "socraticmath_train_3998": {
        "prefix": [(2, ""), (4, "")],
        "claim": {"turn": 5,
                  "keys": ["题目中的说法正确吗", "根据这个定义", "端点都在圆周上并且通过圆心"],
                  "resp": (6, "根据你的解释，")},
        "fallback": (8, "是的，"),
        "suffix": [],
        "dropped": [],
        "note": "命中轮自带强依赖标记『根据你的解释』(输入 manual_review 预警),剥除后"
                "理由句自足(引题面原文);纠错对象为题面主张,导师给定义后问询即路由语境。",
    },
    "socraticmath_train_2899": {
        "prefix": [],
        "claim": {"turn": 1,
                  "keys": ["热水瓶", "容积为60毫升", "60毫升"],
                  "resp": (2, "")},
        "fallback": (4, ""),
        "suffix": [(6, ""), (8, "哦，我懂了，就是说")],
        "dropped": [],
        "note": "纠错步为首步(候选无前缀):学生否掉选项 A 的 60 毫升;特征锚定"
                "热水瓶/60毫升,导师复述选项即命中。",
    },
    "socraticmath_val_495": {
        "prefix": [(2, ""), (4, "")],
        "claim": {"turn": 5,
                  "keys": ["注意看这个操作", "这个操作是不是"],
                  "resp": (6, "")},
        "fallback": (8, ""),
        "suffix": [(10, "")],
        "dropped": [],
        "note": "口算分解纠错(40+3 应先 75-30=45 再减 8);claim 轮本身措辞泛"
                "(『这个操作』),特征取其最长具体短语(弃『存在什么问题』通用问尾),"
                "误路由面限于本题语境,漏配走 fallback 由学生直接算出 37。",
    },
    "socraticmath_val_13": {
        "prefix": [(4, "")],
        "claim": {"turn": 5,
                  "keys": ["选项C", "对◇先进行除法"],
                  "resp": (6, "")},
        "fallback": (8, "能的，"),
        "suffix": [],
        "dropped": [{"index": 2, "reason": "裸肯定回执『是的，可以的。』强上下文,不可独立成步"}],
        "note": "等式性质纠错:选项 C 未同时对两边操作;特征锚定选项C与操作序"
                "(弃通用问尾『这样做对吗』——问选项B正确性亦含之,会把纠错误导至B,"
                "宁漏勿误);fallback 取轮 8 截断(剥『能的』回执)。",
    },
}

# R4 弃案(13 条,从严;reason 逐条入处置表)。
REJECTED: dict[str, str] = {
    "socraticmath_train_5221":
        "R4(应归 R2 位):中段导师连环纠错与学生回错轮深度耦合,需 5 处句内截断+1 轮"
        "中段丢弃,截后学生轮序列呈无因连环修订,失真——宁少勿滥弃。",
    "socraticmath_train_2013":
        "R4:形态信号过薄——命中后导师仅一句收尾确认问(『理解了吗』),学生次轮为纯"
        "回执(『我明白了,谢谢老师』),无实质追问链。",
    "socraticmath_train_1313":
        "R4:两轮剧本(命中+纯回执),导师追问仅一次理解性确认,形态1 信号最薄(与 2013 同型)。",
    "socraticmath_train_191":
        "R4:两轮剧本(命中+『我明白了』复述),形态1 信号薄,规模取舍弃(同型保 559)。",
    "socraticmath_train_4531":
        "R4:命中轮后仅一轮且需截断(『这种式子』指示词回指),编译面薄,规模取舍弃。",
    "socraticmath_train_5032":
        "R4:题面残缺(『叫平行四边形．』命名题主语在归一化中丢失),作被测 question 不可解,"
        "照录即注入坏题面。",
    "socraticmath_train_4786":
        "R4:源对话位值混乱——12.351 十分位/百分位数字多轮误标,纠错轮自身断言"
        "『百分位5是小于百分位3』为伪,前缀轮亦含伪断言,照录注入事实错误,截断不可修复。",
    "socraticmath_train_3749":
        "R4(应归 R3 位):纠错为首步无前缀,后继弱轮均为裸答(『应该是14乘以2』『等于28』)"
        "强上下文不可作 fallback,前步语义保持变体无前步可依——协议明文两者皆无降级 R4。",
    "socraticmath_train_515":
        "R4:命中轮为作答应用(『题目判断错了,应该选A』)非纠错,次轮与命中轮内容近重复,"
        "无差异化 fallback 可用;形态弱。",
    "socraticmath_val_97":
        "R4:命中轮为应答导师设问(评判选项 A 是否恒成立)而非纠正导师错误,形态2 语义弱"
        "(输入 manual_review 亦判弱),宁少勿滥弃。",
    "socraticmath_test_42":
        "R4:可编译但结构最薄(1 前缀步+纠错步,fallback 为纯回执『对的,我明白了』),"
        "规模上限取舍弃,同档保留结构更丰富者。",
    "socraticmath_train_1688":
        "R4:可编译但结构薄(1 前缀步+纠错步),路由特征依赖题面复述(『50是4的倍数』),"
        "规模上限取舍弃。",
    "socraticmath_train_29":
        "R4:可编译但结构薄(1 前缀步+纠错步),与 1688/test_42 同型,规模上限取舍弃。",
}

COMPILE_REVIEW = {
    "obligation": "协议人工确认环节:R3 分支逐条回读原对话校准特征路由;"
                  "每形态至少 3 条全通读编译结果。",
    "feature_candidate_note": "机械候选以 5-8 个为目标;claim 轮本身为单短句时"
                              "(val_495 全句 18 字/3998 长陈述句)实际可提取数少于此,"
                              "以 feature_audit 实录为准,不以泛化 n-gram 凑数。"
                              "定稿特征均为机械候选同跨度的更specific子串或错误签名"
                              "变体(逐条过 I2 断言=claim 轮原文子串)。",
    "form1_readback": ["socraticmath_train_4402", "socraticmath_train_2591",
                       "socraticmath_train_5228"],
    "form2_readback": ["socraticmath_train_1827", "socraticmath_val_61",
                       "socraticmath_train_4275"],
    "verdict": "形态1 抽读 3 条(4402/2591/5228):截断后学生轮自足、命中轮保真、"
               "追问链完整。形态2 抽读 3 条(1827/val_61/4275):claim 特征均为原句"
               "错误签名、命中即路由、漏配走 fallback 不断对话;4275 十一步全链回读通过。",
}


def _has_truncation(scenario: dict) -> bool:
    compile_info = scenario["compile"]
    return bool(compile_info.get("truncations")
                or compile_info.get("correction_cut_prefix")
                or compile_info.get("fallback_cut_prefix")
                or compile_info.get("step_cuts"))


def build_dispositions(slices: dict) -> dict[str, dict]:
    """36 条逐条去向表(编译规则 R1-R4 + 去向/原因),键=候选 id。"""
    compiled_ids = set(V1_PLAN) | set(V2_PLAN)
    dispositions: dict[str, dict] = {}
    for form, entries in slices["slices"].items():
        for entry in entries:
            sid = entry["id"]
            if sid in V1_PLAN:
                rule = "R1"
                detail = f"线性 v1,{len(V1_PLAN[sid][1])} 学生轮(含截断记录见 compile)"
            elif sid in V2_PLAN:
                rule = "R3"
                detail = "分支 v2,纠错步 claim/fallback + 前后缀弱轮步"
            else:
                assert sid in REJECTED, f"{sid} 无处置(处置表必须全覆盖)"
                rule = "R4"
                detail = REJECTED[sid]
            dispositions[sid] = {
                "form": form, "rule": rule,
                "compiled": sid in compiled_ids,
                "scenario_id": sid if sid in compiled_ids else None,
                "detail": detail,
            }
    assert len(dispositions) == 36, f"处置表 {len(dispositions)} != 36"
    return dispositions


def main() -> int:
    slices, records = load_inputs()
    assert sha256_of(NORMALIZED) == slices["source"]["file_sha256"], \
        "normalized 层 sha256 与 slice 声明不符(证据链断)"
    scenarios = []
    for sid, (form, plan) in V1_PLAN.items():
        scenarios.append(build_v1(sid, form, "R1", records[sid], plan,
                                  note="全弱依赖线性照录" if all(not c for _, c in plan)
                                  else "全弱依赖线性照录;截断=剥隐性强依赖开场白"))
    for sid, plan in V2_PLAN.items():
        scenarios.append(build_v2(sid, FORM2, records[sid], plan))
    order = {sid: n for n, sid in enumerate(V1_PLAN)}
    order.update({sid: n for n, sid in enumerate(V2_PLAN, len(V1_PLAN))})
    scenarios.sort(key=lambda s: order[s["id"]])
    dispositions = build_dispositions(slices)
    counts = {form: {"R1": 0, "R2": 0, "R3": 0, "R4": 0}
              for form in (FORM1, FORM2)}
    for item in dispositions.values():
        counts[item["form"]][item["rule"]] += 1
    compiled = [s for s in scenarios]
    payload = {
        "schema": "edu_agent_external_slice_executable/v1",
        "compiled_from": {
            "slice_version": slices["slice_version"],
            "slice_file": "edu_agent/evals/datasets/external_slices/socraticmath_v1.json",
            "slice_sha256": sha256_of(SLICES),
            "normalized_file": "edu_agent/evals/datasets/external_normalized/socraticmath.jsonl",
            "normalized_sha256": slices["source"]["file_sha256"],
        },
        "compile_protocol": {
            "version": "v1 正本 docs/evals/external-slice-compilation-protocol-v1.md"
                       "(PR #396,main 7b386c8 已合;执行以仓内正本为准)",
            "rules": {
                "R1": "全弱依赖→线性 v1;学生轮原文照录,只许截断(轮级丢弃/句内剥"
                      "强依赖开场白)不许改写,逐处记录",
                "R2": "强依赖在中后段→截断稳定前缀并记录截断位(本批无适用:F1 全"
                      " all_weak;F2 强依赖轮=形态本体归 R3;唯一需中段切除的 5221 弃)",
                "R3": "强依赖需保留→v2 分支:claim 分支特征=被回应 tutor 轮机械候选"
                      "人工定稿 3-5 个(宁 specific 勿泛化、宁漏勿误),student_response"
                      "=真实学生轮原文;恰一条 fallback,文本=同案例另一弱依赖真实轮"
                      "(本批 9/9 如此,零新写文本)",
                "R4": "弃案从严,逐条记录原因(见 dispositions)",
            },
            "invariants": ["I1 学生文本⊆源 student 轮原文(截断记录)",
                           "I2 特征子串⊆被回应 tutor 轮原文",
                           "I3 每步恰一 fallback 且非兜底分支可达",
                           "I4 question 与源 problem.text 逐字一致"],
        },
        "fallback_semantics": "v2 每步恰一条 fallback:select_branch 按声明序取首个"
                              " assistant_contains_any 命中,全不命中走该步 fallback。"
                              "纠错步 fallback 语义=导师未抛出可纠命题时学生以弱依赖"
                              "真实轮续走解题主线(保对话不断、不空转);prefix/suffix"
                              "步为单兜底分支=该形态下的线性照录。全部 fallback 文本"
                              "均为源案例真实学生轮(部分剥回执开场白,见 compile 记录)。",
        "compile_review": COMPILE_REVIEW,
        "dispositions": dispositions,
        "reconciliation": {
            "total": 36,
            "compiled": len(compiled),
            "of_which_with_truncation": sum(
                1 for s in compiled if _has_truncation(s)),
            "rejected": len(REJECTED),
            "note": "协议 §三.3 对账口径 36=编译+截断+弃:截断不独立占位"
                    "(R1 句内截断 7 条、R3 回应/兜底/尾步截断 4 条,均记入 compile),"
                    "R4 弃 13 条(含协议本义『强依赖不可靠路由』与 §四『宁少勿滥』"
                    "两类,逐条见 dispositions)。",
        },
        "form_stats": {
            "candidates": {"form1": 20, "form2": 16, "total": 36},
            "compiled": {
                "form1_linear_v1": sum(1 for s in compiled if s["compile"]["form"] == FORM1),
                "form2_branch_v2": sum(1 for s in compiled if s["compile"]["form"] == FORM2),
                "total": len(compiled),
            },
            "by_rule": {
                "R1": counts[FORM1]["R1"] + counts[FORM2]["R1"],
                "R2": counts[FORM1]["R2"] + counts[FORM2]["R2"],
                "R3": counts[FORM1]["R3"] + counts[FORM2]["R3"],
                "R4": counts[FORM1]["R4"] + counts[FORM2]["R4"],
            },
            "by_form_rule": counts,
        },
        "scenarios": compiled,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(f"compiled={len(compiled)} "
          f"(form1={payload['form_stats']['compiled']['form1_linear_v1']}, "
          f"form2={payload['form_stats']['compiled']['form2_branch_v2']}); "
          f"by_rule={payload['form_stats']['by_rule']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
