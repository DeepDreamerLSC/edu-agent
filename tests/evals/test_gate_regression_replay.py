"""Trusted Completion Gate C 段:32 案回归重放对账(#414 §六.1,确定性,零模型)。

**冻结期望面是测量仪器,不得修改、不得硬凑绿**(任务书断言原则):实测与冻结
期望不符的案是**发现不是失败**——框架以「期望对账」模式逐案输出
pass/divergence+归因,已知 divergence 在下方 REGISTERED_DIVERGENCES 显式登记
(corpus 冻结张力旗标/#421 预登记 taxonomy 为标签来源,实测逐案确认);make check
绿 = 实测 divergence 集**恰等于**登记集(多一个=新回归,少一个=校准落地须重新
登记——两个方向都红,防静默重释),不靠改期望。

实测口径(2026-09-22,C 段跑面):
- **19 案 PASS**:12 正向案 completed(Gate 正确放行;四锚中 2960/3695/3138
  实测放行)+ 7 负向案 needs_review(completed 消失,硬断言);
- **13 案 DIVERGENCE**:与 corpus 预登记的 13 张力案**精确一致**(probe_no_
  evidence_tension 旗)——§三 precision-first 保守拒判(claim 白名单外/单位
  形态/复合红线/左边界/疑问形态)与 §六.1 不劣化期望的结构张力,留人审
  (#421 留审项 2),非 Gate 行为回归;
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

# 已知 divergence 显式登记(标签来源:corpus 冻结张力旗 + #421 预登记 taxonomy
# 「claim 白名单外声明式(「结果是/就是/等于」8 案)、答案键无单位 vs 学生带单位
# (val_142)、复合红线(5234)、单位形态(十字绣)、short_text 左边界(2591)、
# 疑问形态(3666)」;以下逐案带实测确认的锚轮形态)。**期望面(completed)
# 不改**——恢复依赖 #416 claim 边界校准(人审)与复合 v2,按 corpus 冻结旗标
# 判读:结构性保守拒判(设计内),非行为回归。
REGISTERED_DIVERGENCES = {
    "socraticmath_train_2322":
        "claim 白名单外:锚轮「…结果是52」(「结果是」非声明式模板)",
    "socraticmath_train_4814":
        "claim 白名单外:锚轮「…就是28平方分米」(「就是」非模板)",
    "socraticmath_val_58":
        "claim 白名单外:终答携带形态非白名单声明式(#421 taxonomy 同组)",
    "socraticmath_train_4188":
        "claim 白名单外:锚轮「…就是826公顷」(「就是」非模板)",
    "socraticmath_train_4813":
        "claim 白名单外:锚轮「…就是3种方案」(「就是」非模板)",
    "socraticmath_train_1961":
        "claim 白名单外:锚轮「…结果是41」(「结果是」非模板)",
    "socraticmath_train_2196":
        "claim 白名单外:锚轮「…结果是26厘米」(「结果是」非模板)",
    "socraticmath_train_3565":
        "claim 白名单外:终答 100 由「等于100/分割成100」携带,白名单内 token"
        "(「应该是1」)是题面数非终答",
    "socraticmath_val_142":
        "单位形态:答案键无单位(7200)vs 学生带单位(「应该是7200页」——"
        "模板命中但单位缺省授权不存在)",
    "socraticmath_train_5234":
        "复合红线:「8或40.5」多候选答案,§三整体不判定(调度即 None)",
    "repro-close-loop-cross-stitch":
        "白名单外+单位形态+stale:「是6」无单位、「6dm」单位与键 6dm² 不同族、"
        "末轮「是的,我真棒」无当轮答案;完整 answer「B.6dm²」另属复合(corpus"
        " 短板注记:复合+stale)",
    "socraticmath_train_2591":
        "short_text 左边界:「它易变形」的左边界字「它」∉{是,为},whole-answer"
        " 左边界拒判(变体须走题库显式 alias)",
    "socraticmath_train_3666":
        "疑问形态:「应该是30:15=8:4也可以吧?」问句标记(吧/?)消息级"
        " fail-closed",
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
    """§六.2 四锚逐案结论:2960/3695/3138 实测放行(completed);2322 实测
    needs_review——登记张力案(claim 白名单外),锚语义「Gate 正确放行」受
    #416 校准前置约束,如实呈报不硬凑。2960 摇摆形态:t1/t2 confirm 被拒
    (「大概」不确定表达拒判,evidence 后置),t3 回正轮当轮证据+ready →
    同轮终局(§二)。"""
    outcomes = _replay_all()
    for cid in ("socraticmath_train_2960", "socraticmath_train_3695",
                "socraticmath_train_3138"):
        assert outcomes[cid][0].final_state == "completed", \
            f"四锚之一 {cid} 未放行(正向回归)"
    assert outcomes["socraticmath_train_2322"][0].final_state == "needs_review"
    assert "socraticmath_train_2322" in REGISTERED_DIVERGENCES


def test_constructible_twelve_all_pass_through_gate():
    """12/32 可构造案(探针 evidence 登记非空)全部实测 completed——Gate
    正向放行面(§六.1 completed 不劣化):evidence 轮+ready 剧本 → 同轮终局
    (§二;摇摆案 2960 先行拒绝埋点后于回正轮授权,同属放行)。"""
    by_id = {c["id"]: c for c in _load()["cases"]}
    constructible = {c["id"] for c in by_id.values()
                     if c["gate_a_probe"].get("evidence_turns")
                     or c["gate_a_probe"].get("any_evidence")}
    assert len(constructible) == 12, f"可构造案登记面变化:{sorted(constructible)}"
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
