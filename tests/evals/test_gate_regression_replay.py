"""Trusted Completion Gate C 段:32 案回归重放对账(#414 §六.1,确定性,零模型)。

**冻结期望面是测量仪器,不得修改、不得硬凑绿**(任务书断言原则):实测与冻结
期望不符的案是**发现不是失败**——框架以「期望对账」模式逐案输出
pass/divergence+归因,已知 divergence 在下方 REGISTERED_DIVERGENCES 显式登记
(corpus 冻结张力旗标/#421 预登记 taxonomy 为标签来源,实测逐案确认);make check
绿 = 实测 divergence 集**恰等于**登记集(多一个=新回归,少一个=校准落地须重新
登记——两个方向都红,防静默重释),不靠改期望。

实测口径(2026-09-22,C 段跑面;2026-09-24 #416 claim 边界校准后重登记;
2026-09-24 2591 alias 入库后再重登记 5→4):
- **28 案 PASS**:21 正向案 completed(Gate 正确放行;四锚 2322/2960/3695/
  3138 全部实测放行——2322「结果是52」经 B-1 恢复;2591 终句「平行四边形的
  特性是它易变形。」经题库显式 alias 声明面恢复,gt_ref 仍为「易变形」)
  + 7 负向案 needs_review(completed 消失,硬断言);
- **4 案 DIVERGENCE**(校准前 13,#416 重登记 13→5,alias 入库后 5→4):与
  corpus 再生成后的 4 张力旗案**精确一致**——复合红线(5234)、复合+单位+stale
  (十字绣)、语义悬崖(3565,B-3 名词间不匹配是特性)、疑问形态(3666)——
  全部为设计内保守拒判或留审项,非 Gate 行为回归;8 案(2322/4814/val_58/
  4188/4813/1961/2196/val_142)经 #416 校准(B-1/B-5/C-3b/维度表)、2591 经
  alias 入库(2026-09-24 用户双重批准,语义裁决 gold-adjudication-c25c46c51-
  2591-20260924.md §B;仅 alias/等价形态不得推广,回指绑定本题)实测恢复
  completed;
- **675/val_13 分支案**:逐路径枚举——675 证据路径(correction/fallback
  「答案是A。」)completed=正向不劣化;纠错路径(claim_match,否定语境非
  claim)needs_review=结构拒判;val_13 两路径均 needs_review=假收束消失。
"""

from __future__ import annotations

import json

from edu_agent.evals import DATASETS_DIR

from gate_replay import ReplayOutcome, gate_question, replay_branch_paths, replay_linear, scripted_ready_flags

CORPUS = (DATASETS_DIR /
          "small_lecturer_completion_gate_regression_32_v1.json")

NEGATIVE_SEVEN = ("socraticmath_train_2791", "socraticmath_train_2857",
                  "socraticmath_train_372", "socraticmath_train_5181",
                  "socraticmath_train_5106", "socraticmath_train_3490",
                  "socraticmath_val_13")
ANCHOR_FOUR = ("socraticmath_train_2322", "socraticmath_train_2960",
               "socraticmath_train_3695", "socraticmath_train_3138")

# 已知 divergence 显式登记(2026-09-24 #416 claim 边界校准人裁「按建议」后
# **重登记 13→5**;标签来源:corpus 再生成后的张力旗案,与提案 E-2 表一致)。
# 校准前 13 案中的 8 案(2322/4814/val_58/4188/4813/1961/2196/val_142)经
# B-1/B-5/C-3b/维度表补实测恢复 completed,登记移除;**期望面(completed)
# 全程未动**——重登记是「实测消失→显式确认」的防静默重释动作,非改期望。
# 2026-09-24 再重登记 **5→4**:2591 出列——题库显式 alias「它易变形」入库
# (用户双重批准,语义裁决 gold-adjudication-c25c46c51-2591-20260924.md §B;
# 仅 alias/等价形态,不得推广为通用规则,回指绑定本题)后 evidence 面恢复,
# 实测 completed 与期望一致;verifier 零改动,期望面未动。
REGISTERED_DIVERGENCES = {
    "socraticmath_train_3565":
        "语义悬崖:终答 100 由「等于100/分割成100」携带,B-3 算式直给形"
        "运算词间不允许夹汉字名词(「平方分米」)——名词间不匹配是特性不是"
        "缺陷;白名单内 token(「应该是1」)是题面数非终答",
    "socraticmath_train_5234":
        "复合红线:「8或40.5」多候选答案,§三整体不判定(调度即 None)",
    "repro-close-loop-cross-stitch":
        "白名单外+单位形态+stale:「是6」无单位、「6dm」单位与键 6dm² 不同族、"
        "末轮「是的,我真棒」无当轮答案;完整 answer「B.6dm²」另属复合(corpus"
        " 短板注记:复合+stale;B-6 名词+是 不收,恢复等复合 v2)",
    "socraticmath_train_3666":
        "疑问形态:「应该是30:15=8:4也可以吧?」问句标记(吧/?)消息级"
        " fail-closed(「吧」语气是否算断言属问句口径重裁,留人审)",
}


def _load() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def _replay_all() -> dict[str, list[ReplayOutcome]]:
    """32 案全量重放(线性照录;分支案全路径枚举)。确定性、零模型。"""
    outcomes: dict[str, list[ReplayOutcome]] = {}
    for case in _load()["cases"]:
        scenario = case["replay_input"]
        spec = case["gate_a_probe"].get("spec")
        if scenario.get("student_turns") is not None:
            outcomes[case["id"]] = [replay_linear(
                case["id"], gate_question(scenario, spec),
                scenario["student_turns"], scripted_ready_flags(case))]
        else:
            outcomes[case["id"]] = replay_branch_paths(
                case["id"], gate_question(scenario, spec), scenario["steps"])
    return outcomes


def _case_outcome(case: dict, outcomes: list[ReplayOutcome]) -> ReplayOutcome:
    """分支案取证据路径(探针 any_evidence 登记)为代表;线性案唯一。"""
    if len(outcomes) == 1:
        return outcomes[0]
    return next((o for o in outcomes if o.evidence_turns), outcomes[-1])


def test_replay_reconciliation_matches_registration():
    """期望对账主断言:实测 divergence 案集 == 登记集(双向精确相等)。
    多出的 divergence=未登记回归(CI 红,须呈报);消失的 divergence=校准落地
    (CI 红,须重新登记)——冻结期望面全程未动。"""
    by_id = {c["id"]: c for c in _load()["cases"]}
    measured = {cid for cid, outs in _replay_all().items()
                if _case_outcome(by_id[cid], outs).final_state
                != by_id[cid]["expected"]["final_state"]}
    unregistered = measured - set(REGISTERED_DIVERGENCES)
    vanished = set(REGISTERED_DIVERGENCES) - measured
    assert not unregistered, f"未登记的实测 divergence(新发现,呈报):{sorted(unregistered)}"
    assert not vanished, f"已登记 divergence 实测消失(校准落地?须重新登记):{sorted(vanished)}"


def test_negative_seven_completed_must_disappear():
    """§六.1 硬断言:负向七案(confirmation 负 6 + val_13 假收束防线)completed
    必须真消失——无当轮 evidence 的完成企图被门逐次拦截(埋点在案)。val_13
    逐路径枚举,两路径均须消失。"""
    for cid, outs in _replay_all().items():
        if cid in NEGATIVE_SEVEN:
            for outcome in outs:
                assert outcome.final_state == "needs_review", \
                    f"{cid}{('(' + outcome.path + ')') if outcome.path else ''} " \
                    f"completed 未消失(负向保护回归,实测 {outcome.final_state})"
                assert outcome.gate_rejections >= 1, \
                    f"{cid} 无 completion_gate_rejected 埋点(拦截证据缺席)"


def test_5106_summary_does_not_speak_answer():
    """§六.1 硬断言:5106 summary 代说必须消失——门拒后 summary 为确定性
    NEEDS_REVIEW_TEXT,答案值(1)与任何模型生成面都不得出现。"""
    outcome = _replay_all()["socraticmath_train_5106"][0]
    assert outcome.final_state == "needs_review"
    assert outcome.gate_rejections >= 1
    assert "1" not in outcome.summary_text and "继续" in outcome.summary_text


def test_anchor_four_gate_behavior():
    """§六.2 四锚逐案结论(#416 校准后):四锚全部实测放行(completed)——
    2322 锚轮「结果是52」经 B-1(结果是)恢复,t0「吧」问句形态照旧正确
    保守,evidence 后置 t2(0 起);2960 摇摆形态:t1/t2 confirm 被拒
    (「大概」不确定表达拒判,evidence 后置),t3 回正轮当轮证据+ready →
    同轮终局(§二)。"""
    outcomes = _replay_all()
    for cid in ANCHOR_FOUR:
        assert outcomes[cid][0].final_state == "completed", \
            f"四锚之一 {cid} 未放行(正向回归)"
    assert outcomes["socraticmath_train_2322"][0].evidence_turns == [3]


def test_constructible_cases_all_pass_through_gate():
    """21/32 可构造案(探针 evidence 登记非空)全部实测 completed——Gate
    正向放行面(§六.1 completed 不劣化):evidence 轮+ready 剧本 → 同轮终局
    (§二;摇摆案 2960 先行拒绝埋点后于回正轮授权,同属放行)。#416 校准
    前为 12 案;8 案张力解锁(2322/4814/val_58/4188/4813/1961/2196/
    val_142)后为 20;2591 经题库显式 alias「它易变形」入库(2026-09-24
    用户双重批准,verifier 零改动)后为 21,登记面变化即红,防静默重释。"""
    by_id = {c["id"]: c for c in _load()["cases"]}
    constructible = {c["id"] for c in by_id.values()
                     if c["gate_a_probe"].get("evidence_turns")
                     or c["gate_a_probe"].get("any_evidence")}
    assert len(constructible) == 21, f"可构造案登记面变化:{sorted(constructible)}"
    for cid, outs in _replay_all().items():
        if cid in constructible:
            outcome = _case_outcome(by_id[cid], outs)
            assert outcome.final_state == "completed", \
                f"可构造案 {cid} 未放行(实测 {outcome.final_state})"


def test_probe_evidence_registration_confirmed():
    """探针一致性(全量):实测逐轮 evidence(1 起轮号)== gate_a_probe 登记
    (0 起轮号+1);提前终局案取其前缀;负向七案全程零 evidence。分支案逐
    路径逐段对账 evidence_branches(#421 ADVISORY 探针由重放全量复算确认)。"""
    by_id = {c["id"]: c for c in _load()["cases"]}
    for cid, outs in _replay_all().items():
        probe = by_id[cid]["gate_a_probe"]
        if "evidence_branches" in probe:
            for outcome in outs:
                segments = outcome.path.split("/")
                pairs = list(zip(segments[0::2], segments[1::2], strict=True))
                expected = {i + 1 for i, (step_id, branch_id) in enumerate(pairs)
                            if probe["evidence_branches"].get(f"{step_id}/{branch_id}")}
                assert set(outcome.evidence_turns) == expected, \
                    f"{cid} 路径 {outcome.path} 实测 evidence 轮 " \
                    f"{outcome.evidence_turns} != 探针登记 {sorted(expected)}"
            continue
        registered = {t + 1 for t in (probe.get("evidence_turns") or [])}
        for outcome in outs:
            for turn in outcome.evidence_turns:
                assert turn in registered, \
                    f"{cid} 实测 evidence 轮 {turn} 不在探针登记 {sorted(registered)}"
            if outcome.final_state == "completed":
                assert outcome.evidence_turns, f"{cid} completed 但零 evidence 轮"
            if cid in NEGATIVE_SEVEN:
                assert not outcome.evidence_turns, \
                    f"{cid} 负向案出现 evidence 轮 {outcome.evidence_turns}"
