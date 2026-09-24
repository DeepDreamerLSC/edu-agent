"""#423 正向完成面恢复验证:444a/2c85 等 5 景带声明面实测(Trusted Completion
Gate C 段并入件,零模型)。

#422 审查 P2① 的 5 景(#423 issue 列明)= shortboard 中被 Gate B 段翻转期望的
五景。恢复链三环:题库 answer_spec 声明面(#424 已合,partner 142 条)→
normalize() 透传(#427 已合)→ #416 claim 边界校准(2026-09-24 人裁「按建议」
已落地)。本件 = 验证动作:每景注入**测试本地构造的声明面**(ADVISORY 建议
规格同款)重放,实测恢复或逐景归因——#423 exit=逐景有结论。

实测结论(2026-09-22 C 段跑面 0/4 → 2026-09-24 #416 校准后 **1/4 正向景恢复**):
- echo-confirm(0.4kg)**恢复**:终答轮「那就是0.4千克。」经 B-5「就是」
  (末 token+3 字否定窗)+kg/千克同族换算命中 evidence → completed;
  中间轮「得到了400」仍不命中(truth 带单位而裸值无授权,C-3b 不适用)。
- 其余三正向景维持 needs_review(设计内):444a「…的高度是0.5m」名词+是
  (B-6 不收,留审走题库声明面或复合 v2)、25km 多槽复合红线(等 v2)、
  2c85 复合+单位不同族+stale(等 v2);1 景负向保护(no-premature)如设计成立。
"""

from __future__ import annotations

import json

from edu_agent.evals import DATASETS_DIR

from gate_replay import gate_question, replay_linear

SHORTBOARD = (DATASETS_DIR / "small_lecturer_regression_shortboard_v1.json")

FIVE = ("no-premature-confirm-before-student-answer",
        "repro-guard-student-echo-confirm",
        "repro-guard-given-scale-reference",
        "repro-close-loop-ball-bounce",
        "repro-close-loop-cross-stitch")

# 测试本地声明面(每景按题库 answer 形态构造;25km 多槽复合=六窄面外,
# 声明 composite 如实登记——组装即 None,§三红线;2c85 用 corpus 32 案同款
# numeric 建议规格=最强合理声明,实测仍不恢复,归因更完整)。
DECLARED_SPECS = {
    "no-premature-confirm-before-student-answer":
        {"answer_type": "numeric_with_unit", "ground_truth": "127本"},
    "repro-guard-student-echo-confirm":
        {"answer_type": "numeric_with_unit", "ground_truth": "0.4kg"},
    "repro-guard-given-scale-reference":
        {"answer_type": "composite",
         "ground_truth": "A(2,2),B(11,2);平均75千米/时;1小时后到(11,5)。"},
    "repro-close-loop-ball-bounce":
        {"answer_type": "numeric_with_unit", "ground_truth": "0.5m"},
    "repro-close-loop-cross-stitch":
        {"answer_type": "numeric_with_unit", "ground_truth": "6dm²"},
}

# tutor ready 剧本(0 起轮号,终答轮起 sticky——轨迹事实:学生何时给出/复述
# 终答;no-premature 全程无终答,ready@唯一轮=原失败形态的判停镜像)。
READY_ANCHORS = {
    "no-premature-confirm-before-student-answer": 0,
    "repro-guard-student-echo-confirm": 2,
    "repro-guard-given-scale-reference": 3,
    "repro-close-loop-ball-bounce": 3,
    "repro-close-loop-cross-stitch": 2,
}

# 逐景结论(归因清单,#423 exit 面板;2026-09-24 #416 校准后更新)
CONCLUSIONS = {
    "no-premature-confirm-before-student-answer":
        "负向保护(不适用恢复):学生全程未落终答,声明面在场仍无 evidence → "
        "needs_review 如设计(2791/5106/3490 同型;短路板冻结期望保持)",
    "repro-guard-student-echo-confirm":
        "已恢复(#416 B-5):终答轮「那就是0.4千克。」——「就是」收为声明模板"
        "(末 token+3 字否定窗双捆绑)+kg/千克同族换算 → evidence,completed;"
        "中间轮「得到了400」仍不命中(truth 带单位而学生裸值无授权)。",
    "repro-guard-given-scale-reference":
        "复合红线:answer 多槽(A/B 位置+平均速度+1小时后坐标),§三整体不"
        "判定——声明面在场(如实登记 composite)组装即 None,须复合 v2。",
    "repro-close-loop-ball-bounce":
        "白名单外(444a,B-6 不收):终答句「…的高度是0.5m」——「的高度是」"
        "名词+是,B-6 泛化不收(名词集开放,收=白名单坍缩);前轮「哦对是0.5」"
        "同。恢复走题库声明面或复合 v2,留人审。",
    "repro-close-loop-cross-stitch":
        "白名单外+单位形态+stale(2c85):「是6」无单位且键 6dm² 单位非可选、"
        "「绣了6dm」单位 dm 与 dm² 不同族、末轮「是的,我真棒」无当轮答案"
        "(stale);完整 answer「B.6dm²」另属复合(corpus 注记:复合+stale)。",
}


def _scenario(scenario_id: str) -> dict:
    board = json.loads(SHORTBOARD.read_text(encoding="utf-8"))
    return next(s for s in board["scenarios"] if s["id"] == scenario_id)


def _replay(scenario_id: str):
    scenario = _scenario(scenario_id)
    turns = scenario["student_turns"]
    question = gate_question(scenario, DECLARED_SPECS[scenario_id])
    ready = set(range(READY_ANCHORS[scenario_id], len(turns)))
    learner = {"grade": scenario.get("grade", "六年级"),
               "answer_status": scenario.get("answer_status", "incorrect")}
    return replay_linear(scenario_id, question, turns, ready, learner=learner)


def test_five_scenarios_each_has_conclusion():
    """#423 exit=逐景有结论:五景全部实测重放(带声明面),终态/证据面/归因
    逐景断言——#416 校准后 1/4 正向景恢复(echo-confirm,B-5「就是」),
    其余三正向景归因落在「白名单外(B-6 不收)/复合/stale」(留审),如实
    呈报;1 景负向保护如设计成立。"""
    for scenario_id in FIVE:
        outcome = _replay(scenario_id)
        if scenario_id == "repro-guard-student-echo-confirm":
            assert outcome.final_state == "completed", \
                f"{scenario_id} 校准后应恢复(B-5),实测 {outcome.final_state}"
            assert outcome.evidence_turns == [3], \
                f"{scenario_id} evidence 轮异常:{outcome.evidence_turns}"
        else:
            assert outcome.final_state == "needs_review", \
                f"{scenario_id} 带声明面实测 {outcome.final_state}" \
                "(若 completed=恢复超预期,更新 #423 结论与归因清单)"
            assert not outcome.evidence_turns, \
                f"{scenario_id} 出现 evidence 轮 {outcome.evidence_turns}(同上)"
            assert outcome.gate_rejections >= 1, \
                f"{scenario_id} 无拦截埋点(短路板冻结期望的保持证据)"
        assert scenario_id in CONCLUSIONS      # 归因清单逐景在案


def test_negative_scenario_keeps_shortboard_frozen_expectation():
    """负向景(no-premature)短路板冻结期望在声明面下保持:finish=needs_review
    + 末态 ready_to_confirm(门拒后 session 保持,教师可继续引导,§四)。"""
    outcome = _replay("no-premature-confirm-before-student-answer")
    assert outcome.final_state == "needs_review"
    assert "继续" in outcome.summary_text   # 确定性引导文案,非总结
