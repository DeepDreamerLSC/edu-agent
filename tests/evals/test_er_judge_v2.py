"""ER judge v2(裁令④七点窄修)回归电池——仓内判分器的语义护栏。

用真实 r3 案文(dev/drill/holdout 已验证规格案)的逐轮最小复现,锁七点:
FP 三(问理由/验证≠当未知、无指向「是不是」不触发、ACK 结构化+尾标签豁免)、
FN 三(字母终答可见性、repro 进域、真重复不被偶然 ACK 豁免)、概念分离
(ER=把已给目标信息当未知;no-progress=无增量重复推进)。

加载方式:工件目录名含连字符(er-judge-v2)不可作包名,且 artifacts 非
公开入口(02 §6),故按文件路径加载——同 tests/teaching/test_anchor_reveal_v1.py
按路径读 artifacts 资产的先例;判分器本体在
edu_agent/evals/artifacts/er-judge-v2/er_judge_v2.py。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_JUDGE_PATH = (
    Path(__file__).resolve().parents[2]
    / "edu_agent" / "evals" / "artifacts" / "er-judge-v2" / "er_judge_v2.py"
)
_spec = importlib.util.spec_from_file_location("er_judge_v2", _JUDGE_PATH)
er_judge_v2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(er_judge_v2)

FORM1 = "form1_student_answered_tutor_keeps_asking"
FORM2 = "form2_student_corrects_tutor"

# —— 真实案文(r3 结果工件照录;dev/drill 规格案)——
# 3565:b-t1 换算事实(v1 分母污染源)+ b-t3 承认+复述指令(legal)。
CASE_3565 = {"question": {
    "text": "边长是1分米的正方形，能分割成____个边长是1厘米的小正方形．",
    "answer": "100"}}
T_3565 = [
    ("嗯，我知道1平方米等于100平方分米，1平方分米等于100平方厘米。",
     "你刚才说1平方分米等于100平方厘米，那如果把大正方形按面积分成小正方形，"
     "是不是每个小正方形的面积是1平方厘米？你能说说怎么从面积换算得到小正方形的个数吗？"),
    ("应该是1平方分米等于100平方厘米，所以能分割成100个边长是1厘米的小正方形。",
     "你刚才说1平方分米等于100平方厘米，而且能分割成100个小正方形，这个思路完全对！"
     "最后请你自己完整说一遍结论，看看能不能让别人听懂这道题怎么做。"),
]
# 3666:c-t2 问理由(怎么想到)+ ACK(是对的)——v1 双误咬轮。
CASE_3666 = {"question": {
    "text": "把等式4×30=8×15改写成比例：______．", "answer": "4：8=15：30（答案不唯一）"}}
T_3666 = [("是不是应该写成4：8=15：30？",
           "你写成4：8=15：30是对的，因为比例里外项积等于内项积，和原等式4×30=8×15是一样的，"
           "那你是怎么想到把30和15放在比例右边的呢？")]
# 4402:b-t4 问验证族(检查一下数字含义)——v1 误咬轮。
CASE_4402 = {"question": {
    "text": "用方程表示下面的数量关系．超市有西瓜x吨，售出21吨，还剩下35吨．方程：________________．",
    "answer": "x-21=35"}}
T_4402 = [("应该是x-21=35。",
           "你刚才说x-21=35，这确实是对的，因为西瓜总重量减去售出的21吨，就等于剩下的35吨。"
           "那我们来一起检查一下，这个方程里每个数字代表什么？")]
# 675:b-t3 字母终答可见性 + 口头承认不豁免指向性重问(最纯 ER 样本)。
CASE_675 = {"question": {
    "text": "比例尺1：100说明图上的1厘米表示实际的距离100米．（判断对错）  A.×  B.√",
    "answer": "A"}}
T_675 = [
    ("这个问题中的单位长度是厘米。",
     "你刚才说单位是厘米，那图上1厘米对应的实际距离是100厘米吗？"
     "如果100厘米等于1米，那题干说100米对不对呢？"),
    ("答案是A。比例尺1：100说明图上的1厘米表示实际的距离100厘米，而不是100米。",
     "你刚才说图上1厘米对应实际100厘米，这没错，但题干说100米，那100厘米和100米一样吗？"),
]
# 866:b-t5 首问 legal / t6 逐字重复 → np(概念分离+真重复不被 ACK 豁免)。
CASE_866 = {"question": {
    "text": "用12的因数写一个比值是3的比例．", "answer": "12：4=6：2，（答案不唯一）"}}
T_866 = [
    ("先是12除以4等于3，然后是6除以2也等于3，所以我觉得比例可以是12：4=6：2。",
     "你刚才说12：4=6：2，这一步很到位！因为两边比值都是3，所以比例成立，"
     "那我们再确认一下，你是不是已经把所有可能的因数组合都检查过了？"),
    ("对，也可以是3：1=12：4。",
     "你刚才说12：4=6：2和3：1=12：4，这说明你已经找到了比值是3的比例，而且思路很清晰！"
     "那我们再确认一下，你是不是已经把所有可能的因数组合都检查过了？"),
]


# ---- #436 盲区三案(r3 真实案文,REPORT holdout 节 ①②③) ----

CASE_700M = {"question": {
    "text": "某山区从山脚向上,每升高100米气温下降3/5℃。A处海拔700米,山脚气温27℃,A处的气温是多少?",
    "answer": "25.8"}}
# ①700m-b:t2 首次推导问(legal)/t4 带脚手架增量的第二次(再乘以=步骤词,守卫不触发)/
# t6 换措辞显式重问(再讲讲,第 3 次)→ np(显式重问探针)。
T_700M_B = [
    ("这道题我会:A在700米,降了6/5度,所以A处是25.8度。",
     "你刚才说A处是25.8℃,能说说你是怎么从海拔700米推算出下降6/5℃的吗?"),
    ("A在500米上面两格,一格100米,所以700米。",
     "你刚才说700米气温降了6/5℃,这个数字是怎么来的?是把700÷100=□,再乘以3/5算出来的吗?"),
    ("是的,700÷100=7,7乘以3/5等于21/5。",
     "你刚才说A处气温是25.8℃,是从700米推算的——这个结果数字很准!但你还没说清楚"
     "'每升高100米下降3/5℃'怎么用在700米上,能再讲讲你是怎么算出下降6/5℃的吗?"),
]
# ②700m-c:数数脚手架问第 3 次,措辞具体化(几个→□个)→ np(槽位归一)。
T_700M_C = [
    ("这道题我会:A处是700米,气温降了6/5℃,所以是25.8℃。",
     "你提到A处是700米,还说气温降了6/5℃,能说说你是怎么从海拔算出这个温度变化的吗?"),
    ("不知道,算不出来。",
     "你刚才说A处海拔是700米,那如果每升高100米气温降3/5℃,700米里有多少个100米呢?我们来数一数。"),
    ("还是不会。",
     "你刚才说A在700米、B在1000米,这很关键!那我们来算算A处气温:700米里有□个100米,"
     "每个100米降3/5℃,一共降多少度?"),
]
# ③223-c:对比问换单字宾语(正方形→长方形)= 新问(legal);逐字重问 = np(正控)。
CASE_223 = {"question": {
    "text": "把长方形的一个角拉动后,形状会变成什么?", "answer": "平行四边形"}}
T_223_C = [
    ("拉角之后会变成正方形。",
     "你刚才说拉角后会变成正方形,但正方形的角必须是直角,而拉角后角会变,对边还是相等,"
     "所以它不是正方形。你想想,这和正方形有什么不同?"),
    ("拉角后边长没变,角变了,是平行四边形。",
     "你刚才说角度变化后会变成平行四边形,这已经对了!你再想想,拉角时边长不变,角变,"
     "这和长方形有什么不同?"),
    ("长方形四个角都是直角。",
     "你再想想,拉角时边长不变,角变,这和正方形有什么不同?"),
]


def _run(case: dict, turns: list[tuple[str, str]], form: str | None) -> dict:
    transcript = {"turns": [{"student": s, "tutor": t} for s, t in turns]}
    return er_judge_v2.judge_case(case, transcript, form)


def _turn(result: dict, index: int) -> dict:
    return result["turns"][index]


def test_fp_conversion_fact_not_said_and_unaimed_confirm():
    """点 4 分母去污染 + 点 1 无指向:换算事实不立 said(t0 不进分母),
    「是不是」指向新对象(小正方形面积)即使进分母也不触发;t1 承认+复述 legal。"""
    result = _run(CASE_3565, T_3565, FORM1)
    assert result["in_domain"]
    assert not _turn(result, 0)["said"] and not _turn(result, 0)["in_denominator"]
    assert _turn(result, 1)["in_denominator"]
    assert result["denominator"] == 1
    assert result["er_family"] == 0 and result["no_progress_family"] == 0


def test_fp_reason_ask_with_structured_ack_is_legal():
    """点 1/2/3:『怎么想到』问理由族移出 doubt;『是对的』显式承认结构。"""
    result = _run(CASE_3666, T_3666, FORM1)
    assert result["denominator"] == 1
    assert result["er_family"] == 0 and result["no_progress_family"] == 0


def test_fp_verification_ask_is_legal():
    """点 2:『检查一下』问验证族移出 doubt;宾语是新侧面(数字含义)。"""
    result = _run(CASE_4402, T_4402, FORM1)
    assert result["denominator"] == 1
    assert result["er_family"] == 0 and result["no_progress_family"] == 0


def test_fp_tag_question_is_not_er():
    """点 3:尾标签问句(对吧?)不判 ER——承认后推进是目标行为。
    短标签本身过不了点 1 锚定门,故同时直接钉 is_tag 过滤路径(防词表演化)。"""
    case = {"question": {"text": "170000平方千米，读作______。", "answer": "十七万"}}
    turns = [("应该是读作十七万平方千米。",
              "你刚才说读作十七万，完全正确！这个读法没问题，对吧？")]
    result = _run(case, turns, FORM1)
    assert result["denominator"] == 1
    assert result["er_family"] == 0 and result["no_progress_family"] == 0
    clauses = er_judge_v2.interrogative_clauses(turns[0][1])
    assert "对吧" in clauses and er_judge_v2.is_tag("对吧")


def test_fn_letter_answer_er_ack_not_exempting():
    """点 4 字母终答可见性(答案是A 立 said,form2 亦进域)+ 点 3 后半:
    口头承认(这没错)不豁免指向性整句重问(100厘米和100米一样吗)= ER。"""
    result = _run(CASE_675, T_675, FORM2)
    assert result["in_domain"]                      # 非数字终答盲区(FN-1)
    assert result["denominator"] == 1
    hit = _turn(result, 1)
    assert hit["er_hit"] and hit["ack_present"]     # 承认在场仍判 ER
    assert result["er_family"] == 1 and result["no_progress_family"] == 0


def test_fn_true_repeat_np_concept_separation():
    """点 6/7:逐字重复问句 → no-progress 族必计(承认『思路很清晰』不豁免);
    重复轮不与 ER 混计;t5 首问 legal。"""
    result = _run(CASE_866, T_866, FORM1)
    assert result["denominator"] == 2
    assert not _turn(result, 0)["no_progress_hit"]
    repeat = _turn(result, 1)
    assert repeat["no_progress_hit"] and not repeat["er_hit"]
    assert result["er_family"] == 0 and result["no_progress_family"] == 1


def test_domain_repro_in_form2_numeric_out():
    """点 5:无 form 标注但有答案(repro 案)进适用域;数值答案的 form2 案
    维持排除;无答案案排除。"""
    repro = _run(CASE_3666, T_3666, None)
    assert repro["in_domain"] and repro["domain_note"] == "repro-equivalent"
    form2_numeric = {"question": {"text": "一个数既是3的倍数又是48的因数。",
                                  "answer": "3、6、12、24、48"}}
    excluded = _run(form2_numeric, [("应该是3、6、12、24、48。", "对吗？")], FORM2)
    assert not excluded["in_domain"]
    assert excluded["domain_note"] == f"excluded:{FORM2}"
    no_answer = _run({"question": {"text": "改错题。", "answer": ""}}, [], None)
    assert not no_answer["in_domain"] and no_answer["domain_note"] == "excluded:no-answer"


# ---------- #436 盲区三案回归(REPORT holdout ①②③ 闭合) ----------


def test_blindspot_reworded_derivation_reask():
    """①700m-b:t2 首问 legal / t4 脚手架增量第二次 legal(再乘以=步骤词不触发
    重问探针——700m-b-t4 gold=legal 的守卫)/ t6 换措辞显式重问(再讲讲)→ np。"""
    result = _run(CASE_700M, T_700M_B, None)
    assert result["in_domain"] and result["denominator"] == 3
    assert not _turn(result, 0)["no_progress_hit"]   # 首次推导问
    assert not _turn(result, 1)["no_progress_hit"]   # 再乘以(步骤词)≠再讲讲(重问)
    assert not _turn(result, 0)["er_hit"] and not _turn(result, 1)["er_hit"]
    hit = _turn(result, 2)
    assert hit["no_progress_hit"] and "显式重问" in hit["no_progress_reason"]
    assert result["no_progress_family"] == 1 and result["er_family"] == 0


def test_blindspot_slot_concretization_repeat():
    """②700m-c:数数脚手架问第 3 次,几个→□个 措辞具体化=同一问(槽位归一)→ np。"""
    result = _run(CASE_700M, T_700M_C, None)
    assert result["in_domain"] and result["denominator"] == 3
    assert not _turn(result, 0)["no_progress_hit"]
    assert not _turn(result, 1)["no_progress_hit"]   # 首次数数问(有多少个)
    hit = _turn(result, 2)
    assert hit["no_progress_hit"] and "问句重复" in hit["no_progress_reason"]
    assert result["no_progress_family"] == 1 and result["er_family"] == 0
    # 槽位归一单元直钉:几/□/多少 同槽
    assert (er_judge_v2._slot_norm("700米里有几个100米")
            == er_judge_v2._slot_norm("700米里有□个100米")
            == er_judge_v2._slot_norm("700米里有多少个100米")
            == "700米里有◇个100米")


def test_blindspot_object_swap_is_new_question():
    """③223-c:对比问换单字宾语(正方形↔长方形)= 新问不判 np;同句逐字重问= np(正控)。"""
    result = _run(CASE_223, T_223_C, None)
    assert result["in_domain"] and result["denominator"] >= 2
    assert not _turn(result, 1)["no_progress_hit"]   # 长方形 vs 正方形 = 换宾语新问
    hit = _turn(result, 2)
    assert hit["no_progress_hit"]                     # 逐字重问正方形对比 = 真重复
    assert result["no_progress_family"] == 1 and result["er_family"] == 0
    # 守卫单元直钉:同比较框架对象槽变化=换宾语新问;全同/非框架单字差不入守卫
    assert er_judge_v2._object_swap("这和正方形有什么不同", "这和长方形有什么不同")
    assert not er_judge_v2._object_swap("这和正方形有什么不同", "这和正方形有什么不同")
    assert not er_judge_v2._object_swap("你是怎么算出下降6/5℃的", "能讲讲你是怎么算出下降6/5℃的")


# ---------- #436 收窄版对抗守卫(review 5334289101) ----------


def test_guard_nonframe_one_char_diff_still_repeat():
    """守卫 A:非比较框架的等长单字差**不豁免**——「算出→想出」类微小改写
    仍按相似度判重复(收窄防「改一字即新问」漏判口子;旧版单字守卫会误豁免)。"""
    turns = [
        ("这道题我会:下降6/5度,所以是25.8度。",
         "你能说说你是怎么算出下降6/5℃的吗?"),
        ("700÷100=7,再乘以3/5。",
         "你能说说你是怎么想出下降6/5℃的吗?"),
    ]
    result = _run(CASE_700M, turns, None)
    hit = _turn(result, 1)
    assert hit["no_progress_hit"] and "问句重复" in hit["no_progress_reason"]
    assert not er_judge_v2._object_swap("你是怎么算出下降6/5℃的", "你是怎么想出下降6/5℃的")


def test_guard_reask_new_object_not_repeat():
    """守卫 B:显式重问标记 + **新对象** ≠ 重复——「再讲讲另一种方法怎么做」
    与先例推导问无共享对象锚(数字/CJK 串),不触发显式重问探针。"""
    turns = [
        ("这道题我会:A在700米,降了6/5度,所以A处是25.8度。",
         "你能说说你是怎么从海拔700米推算出下降6/5℃的吗?"),
        ("700÷100=7,再乘以3/5,得到21/5。",
         "很好!那你能再讲讲另一种方法怎么做吗?"),
    ]
    result = _run(CASE_700M, turns, None)
    assert not _turn(result, 1)["no_progress_hit"]   # 新对象重问 = 新问
    assert result["no_progress_family"] == 0
    # 同对象锚单元直钉:数字锚(6/5)与 CJK 锚(平行四边形)成立;纯框架词不成立
    assert er_judge_v2._same_object("能再讲讲你是怎么算出下降6/5℃的吗",
                                    "能说说你是怎么从海拔700米推算出下降6/5℃的吗")
    assert er_judge_v2._same_object("再讲讲你是怎么拼出平行四边形的",
                                    "你是怎么想到拼成平行四边形的")
    assert not er_judge_v2._same_object("再讲讲另一种方法怎么做",
                                        "你是怎么从海拔700米推算出下降6/5℃的吗")
