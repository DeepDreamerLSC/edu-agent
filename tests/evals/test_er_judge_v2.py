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
