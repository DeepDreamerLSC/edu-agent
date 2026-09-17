"""#332 GEPA 第二轮设计规格回归:分层采样 / U 合并接受函数 / 单一最优 lineage。

全假上游零模型;T1-T6 验收锚点 + #332 规格块伪代码逐条钉死。
"""

import json
from unittest.mock import MagicMock, patch

from edu_agent.evals import (
    ACCEPT_DELTA,
    GepaConfig,
    HnuOutcome,
    ScoreVector,
    accept_variant,
    gepa_loop,
    sample_stratified_batch,
)


def _sv(mean, nr, viol, hard=0.0):
    return ScoreVector(mean, nr, viol, hard)


def _stats(calls=0, tutor=0, judge=0, **overrides):
    stats = {"calls": calls, "tokens_in": 0, "tokens_out": 0, "wall_ms": 1,
             "env_failures": 0, "content_failures": 0,
             "tutor_calls": tutor, "judge_calls": judge,
             "leak_net_violations": 0, "hard_vetoed": False,
             "h": 0, "n": 0, "u": 0, "mean": 0.0}
    stats.update(overrides)
    return stats


# 信号词形(kernel 一手判据,分层分类用)
UNDE = "老师,我懂了,这一步没问题"
STUCK = "老师我没思路,不知道怎么算"
COMP = "我算出来了,答案是十二"
PLAIN = "嗯,让我想一想"

TRAIN_3 = [
    {"id": "c1", "question": "q", "student_turns": ["a"]},
    {"id": "c2", "question": "q", "student_turns": ["b"]},
    {"id": "c3", "question": "q", "student_turns": ["c"]},
]


def _classify(case):
    """测试内联分类(与 sample_stratified_batch 同词形口径)。"""
    turn = case["student_turns"][0]
    if "懂了" in turn or "没问题" in turn:
        return "understanding"
    if "没思路" in turn or "不知道" in turn:
        return "stuck"
    if "算出来了" in turn:
        return "completion"
    return "background"


# === T1 采样 ===


def test_t1_stratified_batch_composition():
    """T1:16 案构成 3 understanding + 3 stuck + 3 completion + 7 背景;
    同 seed 确定,小池降级不报错。"""
    pool = (
        [{"id": f"u{i}", "question": "q", "student_turns": [UNDE]} for i in range(5)]
        + [{"id": f"s{i}", "question": "q", "student_turns": [STUCK]} for i in range(5)]
        + [{"id": f"c{i}", "question": "q", "student_turns": [COMP]} for i in range(5)]
        + [{"id": f"p{i}", "question": "q", "student_turns": [PLAIN]} for i in range(20)]
    )
    batch = sample_stratified_batch(pool, seed=7)
    assert len(batch) == 16
    kinds = [_classify(c) for c in batch]
    assert kinds.count("understanding") == 3
    assert kinds.count("stuck") == 3
    assert kinds.count("completion") == 3
    assert kinds.count("background") == 7
    # 同 seed 确定性
    again = sample_stratified_batch(pool, seed=7)
    assert [c["id"] for c in batch] == [c["id"] for c in again]
    # 换 seed 刷新(防过拟合单批)
    other = sample_stratified_batch(pool, seed=8)
    assert [c["id"] for c in batch] != [c["id"] for c in other]
    # 小池降级:3 案全背景 → 3 案全量(rng 序),不报错
    tiny = sample_stratified_batch(TRAIN_3, seed=0)
    assert {c["id"] for c in tiny} == {"c1", "c2", "c3"}


def test_t1_five_candidates_share_batch_and_refresh_on_switch(tmp_path):
    """T1:每 5 个评估候选同批;第 6 候选换批且换批触发当前最优重评。"""
    calls = []  # (batch_ids, template)

    def fake_eval(cases, template, gateway, judge_role="judge", support_hint=None):
        calls.append((tuple(c["id"] for c in cases), template))
        # 探索读数与参考同分 → 初筛拒(不进配对,批管理隔离观察)
        return _sv(8.0, 0.1, 0.1), [], _stats(calls=5, mean=8.0)

    variants = [(f"变体{i}:讲讲思路的第一步", "edited") for i in range(6)]
    with patch("edu_agent.evals.gepa.evaluate_batch", side_effect=fake_eval), \
         patch("edu_agent.evals.gepa.edit_template", side_effect=variants):
        gepa_loop(train_cases=TRAIN_3, initial_template="初始:说说思路",
                  config=GepaConfig(rounds=6, max_calls=1000),
                  gateway=MagicMock(), output_dir=tmp_path, resume=False)

    # 序列:初始批 → [ref(c0), v1..v5(同批 c0)] → [ref(c1), v6(批 c1)]
    templates = [t for _, t in calls]
    assert templates[0] == "初始:说说思路"  # 初始批
    assert templates[1] == "初始:说说思路"  # cohort 0 换批参考重评(当前最优)
    assert calls.count((calls[1][0], "初始:说说思路")) >= 2  # c0 参考 + c1 参考
    # 候选 1-5(v1..v5 = calls[2..6])与 c0 参考同批
    for i in range(2, 7):
        assert calls[i][0] == calls[1][0], f"评估 {i} 脱批"
    # 第 6 候选(calls[8])换新批 ≠ 批 c0
    assert calls[7][0] != calls[1][0]  # calls[7] = ref(c1)
    assert calls[8][0] == calls[7][0] and calls[8][1].startswith("变体5")


# === T2 U 合并 ===


def test_t2_u_merge_fail_to_review_not_rejected():
    """T2:fail→review 不被 U 拒——U 合并口径下两态同计,靠 Δ/H 判定;
    旧口径(nr 率单独比较)会把 fail→review 误判退化,本修的靶点。"""
    # parent:1 案 verdict=fail(hard) → h=1, u=1;variant:同案 → review → h=0, u=1
    accepted, ev = accept_variant(
        HnuOutcome(1, 0, 1, 9.0), HnuOutcome(0, 0, 1, 9.5))
    assert accepted is True  # U 不增(fail/review 同计)+ H 减 + Δ=0.5 ≥ 0.125
    assert ev["decision"] in ("delta_ge_threshold", "hnu_reduced_mean_not_worse")
    # 纯 Δ 场景:U 同、H/N 同,靠 Δ 过闸
    accepted2, ev2 = accept_variant(
        HnuOutcome(0, 0, 1, 9.0), HnuOutcome(0, 0, 1, 9.5))
    assert accepted2 is True and ev2["decision"] == "delta_ge_threshold"


# === T3 新增 hard fail ===


def test_t3_new_hard_fail_rejected_despite_mean_surge():
    """T3:新增 hard fail 案即使均值大涨也拒绝,证据保留(reason 落判定)。"""
    accepted, ev = accept_variant(
        HnuOutcome(0, 0, 0, 9.0), HnuOutcome(1, 0, 1, 11.8))
    assert accepted is False
    assert ev["decision"] == "new_hard_fail"  # 留证:拒绝原因进 round report
    # HNU 其他维增加同样拒
    accepted_n, ev_n = accept_variant(
        HnuOutcome(0, 0, 0, 9.0), HnuOutcome(0, 1, 0, 11.0))
    assert accepted_n is False and ev_n["decision"] == "hnu_increase"


# === T4 阈值边界 ===


def test_t4_threshold_boundaries():
    """T4:Δ=0.125 恰过 / Δ=0.124 恰拒;路径②(H 降+均值平)接受。"""
    # 0.125 恰过(浮点边界:9.0 + 0.125 精确)
    ok, ev = accept_variant(
        HnuOutcome(0, 0, 0, 9.0), HnuOutcome(0, 0, 0, 9.0 + ACCEPT_DELTA))
    assert ok is True and ev["decision"] == "delta_ge_threshold"
    assert ev["delta_mean"] >= ACCEPT_DELTA
    # 0.124 恰拒
    no, ev_no = accept_variant(
        HnuOutcome(0, 0, 0, 9.0), HnuOutcome(0, 0, 0, 9.124))
    assert no is False and ev_no["decision"] == "keep_parent"
    # 路径②:H 减 + 均值不降 → 接受
    ok2, ev2 = accept_variant(
        HnuOutcome(1, 0, 1, 9.0), HnuOutcome(0, 0, 1, 9.0))
    assert ok2 is True and ev2["decision"] == "hnu_reduced_mean_not_worse"
    # 路径②的边界:均值下降 → 拒(「不下降」是硬条件)
    no2, _ = accept_variant(
        HnuOutcome(1, 0, 1, 9.0), HnuOutcome(0, 0, 1, 8.99))
    assert no2 is False


# === T5 lineage ===


def _arm(totals, hards=None):
    """配对臂构造:totals 逐案分;hards 标 hard 案(verdict=fail/mi=0)。"""
    hards = hards or [False] * len(totals)
    return [{"case_id": f"c{i}", "total": t, "verdict": "fail" if h else "pass",
             "leaked": False, "mi": 0 if h else 2, "hard_fail": h}
            for i, (t, h) in enumerate(zip(totals, hards, strict=True), 1)]


def test_t5_lineage_ignores_pool_max(tmp_path):
    """T5:选择器只认配对确认的当前最优——池内历史高分不参与选父代。

    世界:初始带 1 hard 案;A 靠 HNU 减路径确认(均值平);B 靠 Δ 确认。
    A 的探索分 9.9 是池内最高,但 lineage 前进到 B 后,父代只认 B。
    """
    world = {  # 探索/参考读数(evaluate_batch)
        "初始:说说思路": _stats(calls=5, mean=9.0, h=1, n=1, u=1),
        "变体A:讲讲思路的第一步": _stats(calls=5, mean=9.9),
        "变体B:说说你的思路,先说第一步": _stats(calls=5, mean=9.3),
        "变体C:从头讲思路第一步": _stats(calls=5, mean=11.5),
    }

    def fake_eval(cases, template, gateway, judge_role="judge", support_hint=None):
        st = world[template]
        return _sv(st["mean"], 0.1, 0.1), [], st

    def fake_paired(cases, template, gateway, judge_role="judge", support_hint=None):
        if template.startswith("变体A"):
            return _arm([9.1, 9.1, 9.1]), [], _stats(calls=6)
        if template == "初始:说说思路":  # A 闸父臂:1 hard 案
            return _arm([0, 9.0, 9.0], [True, False, False]), [], _stats(calls=6)
        # B/C 闸:变体臂 11 vs 父臂 10
        return (_arm([11, 11, 11]) if template.startswith("变体")
                else _arm([10, 10, 10])), [], _stats(calls=6)

    with patch("edu_agent.evals.gepa.evaluate_batch", side_effect=fake_eval), \
         patch("edu_agent.evals.gepa_paired.evaluate_batch_paired",
               side_effect=fake_paired), \
         patch("edu_agent.evals.gepa.edit_template",
               side_effect=[("变体A:讲讲思路的第一步", "edited"),
                            ("变体B:说说你的思路,先说第一步", "edited"),
                            ("变体C:从头讲思路第一步", "edited")]):
        _, scores, reports = gepa_loop(
            train_cases=TRAIN_3, initial_template="初始:说说思路",
            config=GepaConfig(rounds=3, max_calls=1000),
            gateway=MagicMock(), output_dir=tmp_path, resume=False)

    # round0:A 过初筛(H 减+Δ=0.9)→ 配对确认(父臂 hard 减)→ lineage=A
    assert reports[0]["accepted"] is True
    assert reports[1]["parent_template"] == "变体A:讲讲思路的第一步"
    # round1:B 过初筛(参考=A 配对臂 9.1 vs 探索 9.3)→ 确认 → lineage=B
    assert reports[1]["accepted"] is True
    # T5 靶点:池内 A 探索分 9.9 最高,但 round2 父代 = B(current_best)
    assert any(s.mean_score == 9.9 for s in scores.values())  # A 高分在池里
    assert reports[2]["parent_template"] == "变体B:说说你的思路,先说第一步"
    # round2:C 配对同分拒 → best 留在 B(配对确认者,非池 max)
    assert reports[2]["accepted"] is False
    saved = json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))
    assert saved["best"]["template"] == "变体B:说说你的思路,先说第一步"


# === T6 计量 ===


def test_t6_refresh_reference_counted_in_ledger(tmp_path):
    """T6:换批重评计入台账(budget.calls + 分项累计)。"""
    def fake_eval(cases, template, gateway, judge_role="judge", support_hint=None):
        return _sv(8.0, 0.1, 0.1), [], _stats(calls=5, tutor=3, judge=2, mean=8.0)

    variants = [(f"变体{i}:讲讲思路的第一步", "edited") for i in range(6)]
    with patch("edu_agent.evals.gepa.evaluate_batch", side_effect=fake_eval), \
         patch("edu_agent.evals.gepa.edit_template", side_effect=variants):
        gepa_loop(train_cases=TRAIN_3, initial_template="初始:说说思路",
                  config=GepaConfig(rounds=6, max_calls=1000),
                  gateway=MagicMock(), output_dir=tmp_path, resume=False)

    saved = json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))
    # 台账:初始 1 + 参考 2(c0/c1 换批)+ 变体 6 = 9 批 × 5 calls + 6 编辑器 = 51
    assert saved["budget"]["calls"] == 9 * 5 + 6
    # 分项:9 批 × (tutor 3 + judge 2) + editor 6
    assert saved["call_breakdown"] == {"tutor_calls": 27, "judge_calls": 18,
                                       "editor_calls": 6}
    # 分项之和 = 总量(不含 editor 的批内分项自洽)
    assert 27 + 18 == 9 * 5
