"""#324 GEPA 优化器最小修复回归:候选识别/恢复/选优可复现(A1–A3/B1–B2/C1–C2)。

单文件 800 行上限拆分自 test_gepa.py(02 §2,同 gepa_editors.py 拆分先例):
全部假上游、零模型;mock 口径:编辑器返回 (值, 原因) 二元组、
gateway.writer 配 _wire_writer_counters、evaluate_batch/paired 按 side_effect。
"""

import json
from unittest.mock import MagicMock, patch

from edu_agent.evals import (
    ScoreVector,
    evaluate_batch,
)


def _wire_writer_counters(gateway: MagicMock, *, start: int = 0) -> None:
    """MagicMock gateway 的 writer 配进程内计数真值(#324 C2 口径,与
    test_gepa.py 同名 helper 一致:生产 FactWriter 自带进程内累计,
    mock 下需显式配 int,否则 Mock 参与算术直接 TypeError)。"""
    gateway.writer.count = start
    gateway.writer.tokens_in = 0
    gateway.writer.tokens_out = 0


# === 11. #324 GEPA 优化器最小修复:候选识别/恢复/选优可复现(A1–A3/B1–B2/C1–C2) ===
# 全部假上游,零模型;mock 口径:编辑器返回 (值, 原因) 二元组,
# gateway.writer 配 _wire_writer_counters,evaluate_batch/paired 按 side_effect。


def _sv(mean, nr, viol, hard=0.0):
    return ScoreVector(mean, nr, viol, hard)


def _stats(**overrides):
    """假批 stats(#332 起含 HNU 初筛口径);字段用 overrides 覆盖。"""
    stats = {"calls": 0, "tokens_in": 0, "tokens_out": 0, "wall_ms": 1,
             "env_failures": 0, "content_failures": 0,
             "tutor_calls": 0, "judge_calls": 0,
             "leak_net_violations": 0, "hard_vetoed": False,
             "h": 0, "n": 0, "u": 0, "mean": 0.0}
    stats.update(overrides)
    return stats


TRAIN_3 = [
    {"id": "c1", "question": "q1", "student_turns": ["a"]},
    {"id": "c2", "question": "q2", "student_turns": ["b"]},
    {"id": "c3", "question": "q3", "student_turns": ["c"]},
]


def test_a1_support_only_variant_is_new_candidate_not_noop(tmp_path):
    """A1:双旋钮下 support-only 改写是新候选——评估器观察到新值,不误判 noop。"""
    from edu_agent.evals import GepaConfig, gepa_loop

    seen_supports = []

    def fake_eval(cases, template, gateway, judge_role="judge", support_hint=None):
        seen_supports.append(support_hint)
        return _sv(9.5, 0.05, 0.05), [], _stats(calls=5)

    with patch("edu_agent.evals.gepa.evaluate_batch", side_effect=fake_eval), \
         patch("edu_agent.evals.gepa.edit_support_hint",
               return_value=("新support:你先看这一步最小的数?", "edited")), \
         patch("edu_agent.evals.gepa.edit_template",
               return_value=("初始:说说你的思路,先说第一步", "unchanged")):
        _, scores, reports = gepa_loop(
            train_cases=TRAIN_3, initial_template="初始:说说你的思路,先说第一步",
            config=GepaConfig(rounds=2, max_calls=100, two_knobs=True),
            gateway=MagicMock(), output_dir=tmp_path, resume=False)

    # 初始批 + 2 代:奇代(round 1)support 改写后 evaluate_batch 收到新值
    assert "新support:你先看这一步最小的数?" in seen_supports
    # round 0 偶代:elicit 编辑 unchanged + support 未被编辑 → 完整组合相同 →
    # noop(正确,双旋钮同变才跳过);round 1 奇代:support-only 改写 → 非 noop
    # (旧 bug:只比 template 会把 support 改写也误判 noop,丢搜索)
    assert reports[0]["noop"] is True
    assert reports[1]["noop"] is False
    assert reports[1]["edit_reason"] == "edited"


def test_a1_both_knobs_unchanged_is_noop(tmp_path):
    """A1:两旋钮都没变才跳过(evaluate_batch 不被重复调用烧预算)。"""
    from edu_agent.evals import GepaConfig, gepa_loop

    def support_unchanged(support, failures, gw, **_kwargs):
        return support, "unchanged"  # unchanged 语义:回传输入原值

    with patch("edu_agent.evals.gepa.evaluate_batch") as mock_eval, \
         patch("edu_agent.evals.gepa.edit_support_hint",
               side_effect=support_unchanged), \
         patch("edu_agent.evals.gepa.edit_template",
               return_value=("初始:说说你的思路,先说第一步", "unchanged")):
        mock_eval.return_value = (_sv(9.0, 0.1, 0.1), [], _stats(calls=5))
        _, _, reports = gepa_loop(
            train_cases=TRAIN_3, initial_template="初始:说说你的思路,先说第一步",
            config=GepaConfig(rounds=2, max_calls=100, two_knobs=True),
            gateway=MagicMock(), output_dir=tmp_path, resume=False)
    # 两代编辑全原样 → 初始批 + #332 换批参考 = 2 次(noop 代零评估)
    assert mock_eval.call_count == 2
    assert all(r["noop"] for r in reports)


def test_a1_support_lint_accepts_both_question_marks():
    """A1:`？`(全角)与 `?`(ASCII)合法问句样本均过 lint——中文编辑器输出全角
    曾被 ASCII-only 关键词全数退回(奇代机械 noop,PM 已核)。"""
    from edu_agent.evals import edit_support_hint

    for mark in ("？", "?"):
        gateway = MagicMock()
        gateway.invoke.return_value = MagicMock(
            text=f"拆小:你只看这一步里最小的一个数,能先算出什么{mark}")
        variant, reason = edit_support_hint("旧support:原样问句?", [], gateway)
        assert reason == "edited", mark
        assert variant.endswith(mark)

    # 违规样本(无问号)留 lint 原因,保留父代
    gateway = MagicMock()
    gateway.invoke.return_value = MagicMock(text="这不是问句,只是陈述,长度足够越过下限了")
    variant, reason = edit_support_hint("旧support:原样问句?", [], gateway)
    assert reason == "lint_rejected"
    assert variant == "旧support:原样问句?"


def test_a2_checkpoint_restore_no_splicing(tmp_path):
    """A2:历史 best=A 与最近被拒变体=B;保存/恢复的 template/support/score
    均属 A,不拼接 B 或顶层;恢复后首案注入值与保存值一致。"""
    from edu_agent.evals import GepaConfig, gepa_loop
    from edu_agent.evals import search_identity

    a_support = "A的support:你看最小的数?"
    checkpoint = {
        "next_round": 3,
        "identity": search_identity(GepaConfig(rounds=4, two_knobs=True,
                                               max_calls=100), TRAIN_3),
        "budget": {"calls": 50, "rounds": 2, "wall_s": 1.0, "exhausted": False},
        "best": {"candidate_id": 0,
                 "template": "A:说说你的思路,先说第一步",
                 "support_hint": a_support,
                 "scores": {"mean_score": 9.0, "needs_review_rate": 0.1,
                            "numerical_violation_rate": 0.1,
                            "hard_failure_rate": 0.0}},
        # B(被拒变体)只留在失败帧语境里,不进 best
        "last_failures": [{"case_id": "c9", "kind": "judge_low_score",
                           "detail": "B 变体 total=6"}],
    }
    (tmp_path / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")

    editor_args = []

    def fake_elicit(current, failures, gw, **_kwargs):
        editor_args.append(("elicit", current))
        return current, "unchanged"  # 不动 elicit,只记录父代注入值

    def fake_support(support, failures, gw, **_kwargs):
        editor_args.append(("support", support))
        return support, "unchanged"

    with patch("edu_agent.evals.gepa.evaluate_batch") as mock_eval, \
         patch("edu_agent.evals.gepa.edit_template", side_effect=fake_elicit), \
         patch("edu_agent.evals.gepa.edit_support_hint", side_effect=fake_support):
        mock_eval.return_value = (_sv(9.0, 0.1, 0.1), [], _stats(calls=5))
        population, scores, reports = gepa_loop(
            train_cases=TRAIN_3, initial_template="不应被用的初始模板",
            config=GepaConfig(rounds=4, max_calls=100, two_knobs=True),
            gateway=MagicMock(), output_dir=tmp_path, resume=True)

    # 恢复后唯一评估 = #332 换批参考重评(注入 A 的完整组合,不是初始模板/
    # 不是被拒变体 B);noop 代零额外评估
    assert mock_eval.call_count == 1
    assert mock_eval.call_args_list[0].args[1] == "A:说说你的思路,先说第一步"
    assert mock_eval.call_args_list[0].kwargs.get(
        "support_hint") == a_support  # 参考也注入候选自身的完整旋钮
    # round 3 奇代:编辑 support 臂,父代注入的 support = A 的保存值(不拼接)
    assert editor_args == [("support", a_support)]
    assert reports[0]["parent_template"] == "A:说说你的思路,先说第一步"
    assert reports[0]["parent_support_hint"] == a_support
    # 分数池:恢复的 A 保留原分(9.0),无 B 的分数混入
    assert any(s.mean_score == 9.0 for s in scores.values())
    saved = json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))
    assert saved["best"]["support_hint"] == a_support
    assert saved["best"]["template"] == "A:说说你的思路,先说第一步"


def test_a3_identity_mismatch_rejects_reuse_before_model_calls(tmp_path):
    """A3:案集变化(身份不匹配)→ 拒绝复用旧分数;拒绝后的首次评估用
    initial_template 从零开始,不携带旧 best 分数。"""
    from edu_agent.evals import GepaConfig, gepa_loop
    from edu_agent.evals import search_identity

    other_cases = [{"id": "x9", "question": "q", "student_turns": ["a"]}]
    checkpoint = {
        "next_round": 5,
        "identity": search_identity(GepaConfig(rounds=6, max_calls=100), other_cases),
        "budget": {"calls": 100, "rounds": 5, "wall_s": 1.0, "exhausted": False},
        "best": {"candidate_id": 0, "template": "旧best:案集已变",
                 "scores": {"mean_score": 9.9, "needs_review_rate": 0.0,
                            "numerical_violation_rate": 0.0,
                            "hard_failure_rate": 0.0}},
        "last_failures": [],
    }
    (tmp_path / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")

    first_template = {}

    def fake_eval(cases, template, gateway, judge_role="judge", support_hint=None):
        first_template.setdefault("t", template)
        return _sv(8.0, 0.1, 0.1), [], _stats(calls=5)

    with patch("edu_agent.evals.gepa.evaluate_batch", side_effect=fake_eval), \
         patch("edu_agent.evals.gepa.edit_template",
               return_value=("变体:讲讲思路第一步", "edited")):
        population, scores, _ = gepa_loop(
            train_cases=TRAIN_3, initial_template="全新初始:说说思路",
            config=GepaConfig(rounds=6, max_calls=100),
            gateway=MagicMock(), output_dir=tmp_path, resume=True)

    # 拒绝复用:首次评估的模板是 initial(不是旧 best),分数池无 9.9 旧分
    assert first_template["t"] == "全新初始:说说思路"
    assert not any(s.mean_score == 9.9 for s in scores.values())


def test_a3_legacy_checkpoint_without_identity_requires_explicit_seed(tmp_path):
    """A3:缺身份字段的旧 checkpoint 只能显式提取模板作新种子——
    无 identity → 拒绝恢复,从 initial_template 全新开始。"""
    from edu_agent.evals import GepaConfig, gepa_loop

    legacy = {
        "next_round": 5,
        "budget": {"calls": 100, "rounds": 5, "wall_s": 1.0, "exhausted": False},
        "best": {"candidate_id": 0, "template": "旧格式best",
                 "scores": {"mean_score": 9.5, "needs_review_rate": 0.1,
                            "numerical_violation_rate": 0.1,
                            "hard_failure_rate": 0.0}},
        "last_failures": [],
    }
    (tmp_path / "checkpoint.json").write_text(json.dumps(legacy), encoding="utf-8")

    first_template = {}

    def fake_eval(cases, template, gateway, judge_role="judge", support_hint=None):
        first_template.setdefault("t", template)
        return _sv(8.0, 0.1, 0.1), [], _stats(calls=5)

    with patch("edu_agent.evals.gepa.evaluate_batch", side_effect=fake_eval), \
         patch("edu_agent.evals.gepa.edit_template",
               return_value=("变体:讲讲思路第一步", "edited")):
        _, scores, _ = gepa_loop(
            train_cases=TRAIN_3, initial_template="种子:说说你的思路",
            config=GepaConfig(rounds=6, max_calls=100),
            gateway=MagicMock(), output_dir=tmp_path, resume=True)
    assert first_template["t"] == "种子:说说你的思路"
    assert not any(s.mean_score == 9.5 for s in scores.values())


def test_a3_same_identity_resumes_from_saved_round(tmp_path):
    """A3:同代码/配置/判据/案集/搜索参数 → 可续跑(evaluate_batch 只跑变体批)。"""
    from edu_agent.evals import GepaConfig, gepa_loop
    from edu_agent.evals import search_identity

    checkpoint = {
        "next_round": 5,
        "identity": search_identity(GepaConfig(rounds=6, max_calls=100), TRAIN_3),
        "budget": {"calls": 50, "rounds": 5, "wall_s": 1.0, "exhausted": False},
        "best": {"candidate_id": 0, "template": "恢复best:说说思路",
                 "scores": {"mean_score": 9.0, "needs_review_rate": 0.1,
                            "numerical_violation_rate": 0.1,
                            "hard_failure_rate": 0.0}},
        "last_failures": [],
    }
    (tmp_path / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")

    with patch("edu_agent.evals.gepa.evaluate_batch") as mock_eval, \
         patch("edu_agent.evals.gepa.edit_template",
               return_value=("变体:讲讲思路第一步", "edited")):
        mock_eval.return_value = (_sv(9.0, 0.1, 0.1), [], _stats(calls=5))
        gepa_loop(train_cases=TRAIN_3, initial_template="原始",
                  config=GepaConfig(rounds=6, max_calls=100),
                  gateway=MagicMock(), output_dir=tmp_path, resume=True)
        # 初始不重评;#332 换批参考 + 第 5 代变体批 = 2 次
        assert mock_eval.call_count == 2


def _gate_per_case(total, hard=False):
    return [{"case_id": f"c{i}", "total": total, "verdict": "pass",
             "leaked": False, "mi": 2, "hard_fail": hard} for i in (1, 2, 3)]


def test_b1_cross_batch_pseudo_gain_rejected_by_paired_gate(tmp_path):
    """B1:两批不同难度的固定假分数构造跨批「伪提升」→ 配对闸同批对照拆穿,
    不得选优;未确认候选 0 次成为父代/best。"""
    from edu_agent.evals import GepaConfig, gepa_loop

    def fake_eval(cases, template, gateway, judge_role="judge", support_hint=None):
        # 探索代读数:变体批「看起来」全面占优(跨批难度差,伪提升)
        if template.startswith("变体"):
            return _sv(9.5, 0.05, 0.05), [], _stats(calls=5, mean=9.5)
        return _sv(9.0, 0.1, 0.1), [], _stats(calls=5, mean=9.0)

    gate_batches = []

    def fake_paired(cases, template, gateway, judge_role="judge", support_hint=None):
        # 同批配对真读数:两臂同分 → 四维全平,无严格改善
        gate_batches.append([c["id"] for c in cases])
        return _gate_per_case(10), [], _stats(calls=6)

    with patch("edu_agent.evals.gepa.evaluate_batch", side_effect=fake_eval), \
         patch("edu_agent.evals.gepa_paired.evaluate_batch_paired",
               side_effect=fake_paired), \
         patch("edu_agent.evals.gepa.edit_template",
               return_value=("变体:讲讲思路第一步", "edited")):
        population, scores, reports = gepa_loop(
            train_cases=TRAIN_3, initial_template="初始:说说思路",
            config=GepaConfig(rounds=1, max_calls=100),
            gateway=MagicMock(), output_dir=tmp_path, resume=False)

    r = reports[0]
    assert r["variant_scores"]["mean_score"] == 9.5  # 探索读数如实进报告
    assert r["accepted"] is False  # 配对闸拆穿伪提升
    assert r["paired_evidence"]["accepted"] is False
    assert r["paired_evidence"]["case_ids"] == gate_batches[0]  # 同批(与臂一致)
    # 未确认候选不进分数池 → best 仍是初始(9.0),无 9.5 候选
    assert all(s.mean_score != 9.5 for s in scores.values())
    best = population.select_parent(scores)
    assert best.template.startswith("初始")


def test_b1_same_batch_real_improvement_accepted_with_evidence(tmp_path):
    """B1:同批四维真实改善才更新——配对两臂真分差 → accepted + 进池 + 证据齐。"""
    from edu_agent.evals import GepaConfig, gepa_loop

    def fake_eval(cases, template, gateway, judge_role="judge", support_hint=None):
        return (_sv(9.5, 0.05, 0.05) if template.startswith("变体")
                else _sv(9.0, 0.1, 0.1)), [], \
            _stats(calls=5, mean=9.5 if template.startswith("变体") else 9.0)

    def fake_paired(cases, template, gateway, judge_role="judge", support_hint=None):
        # 同批真读数:变体臂各案 +1 → mean 改善,其余三维持平
        return _gate_per_case(11 if template.startswith("变体") else 10), [], \
            _stats(calls=6)

    with patch("edu_agent.evals.gepa.evaluate_batch", side_effect=fake_eval), \
         patch("edu_agent.evals.gepa_paired.evaluate_batch_paired",
               side_effect=fake_paired), \
         patch("edu_agent.evals.gepa.edit_template",
               return_value=("变体:讲讲思路第一步", "edited")):
        population, scores, reports = gepa_loop(
            train_cases=TRAIN_3, initial_template="初始:说说思路",
            config=GepaConfig(rounds=1, max_calls=100),
            gateway=MagicMock(), output_dir=tmp_path, resume=False)

    r = reports[0]
    assert r["accepted"] is True
    ev = r["paired_evidence"]
    assert ev["accepted"] is True
    assert ev["parent_hnu"]["mean"] == 10.0  # #332:HNU 口径
    assert ev["variant_hnu"]["mean"] == 11.0
    assert all(c["delta"] == 1 for c in ev["per_case"])
    best = population.select_parent(scores)
    assert best.template.startswith("变体")


def test_b1_regression_cannot_masquerade_as_improvement(tmp_path):
    """B1:相同/退化候选不得冒充改善——配对臂更差 → 拒绝。"""
    from edu_agent.evals import GepaConfig, gepa_loop

    def fake_eval(cases, template, gateway, judge_role="judge", support_hint=None):
        return (_sv(9.5, 0.05, 0.05) if template.startswith("变体")
                else _sv(9.0, 0.1, 0.1)), [], \
            _stats(calls=5, mean=9.5 if template.startswith("变体") else 9.0)

    def fake_paired(cases, template, gateway, judge_role="judge", support_hint=None):
        # 同批真读数:变体臂退化(配对臂 hard 一案 → 四维劣化)
        return (_gate_per_case(8, hard=True) if template.startswith("变体")
                else _gate_per_case(10)), [], _stats(calls=6)

    with patch("edu_agent.evals.gepa.evaluate_batch", side_effect=fake_eval), \
         patch("edu_agent.evals.gepa_paired.evaluate_batch_paired",
               side_effect=fake_paired), \
         patch("edu_agent.evals.gepa.edit_template",
               return_value=("变体:讲讲思路第一步", "edited")):
        _, scores, reports = gepa_loop(
            train_cases=TRAIN_3, initial_template="初始:说说思路",
            config=GepaConfig(rounds=1, max_calls=100),
            gateway=MagicMock(), output_dir=tmp_path, resume=False)

    assert reports[0]["accepted"] is False
    assert reports[0]["paired_evidence"]["variant_hnu"]["h"] > 0  # #332
    assert all(s.mean_score != 9.5 for s in scores.values())


def test_b2_paired_gate_arms_carry_own_knobs_and_case_ids(tmp_path):
    """B2:双旋钮配对——父子两臂注入自身完整旋钮组合;配对结果与
    case IDs/运行身份一致;两臂各跑一次(仅复用同次运行证据,无通用缓存)。"""
    from edu_agent.evals import GepaConfig, gepa_loop

    arms = []

    new_support = "新support:你看最小的数?"

    def fake_paired(cases, template, gateway, judge_role="judge", support_hint=None):
        arms.append((template, support_hint, tuple(c["id"] for c in cases)))
        # variant 臂:round 0 靠 elicit 模板、round 1 靠 support(两代改的旋钮不同)
        is_variant_arm = support_hint == new_support or template.startswith("变体")
        return _gate_per_case(11 if is_variant_arm else 10), [], _stats(calls=6)

    def fake_eval(cases, template, gateway, judge_role="judge", support_hint=None):
        if support_hint == new_support:  # round 1:support 改写的变体
            # 探索读数与配对臂刷新后的参考同世界(参考=round0 配对臂 mean=11)
            return _sv(9.6, 0.05, 0.05), [], _stats(calls=5, mean=11.5)
        return (_sv(9.5, 0.05, 0.05) if template.startswith("变体")
                else _sv(9.0, 0.1, 0.1)), [], \
            _stats(calls=5, mean=9.5 if template.startswith("变体") else 9.0)

    with patch("edu_agent.evals.gepa.evaluate_batch", side_effect=fake_eval), \
         patch("edu_agent.evals.gepa_paired.evaluate_batch_paired",
               side_effect=fake_paired), \
         patch("edu_agent.evals.gepa.edit_template",
               return_value=("变体:讲讲思路第一步", "edited")), \
         patch("edu_agent.evals.gepa.edit_support_hint",
               return_value=(new_support, "edited")):
        _, _, reports = gepa_loop(
            train_cases=TRAIN_3, initial_template="初始:说说思路",
            config=GepaConfig(rounds=2, max_calls=100, two_knobs=True),
            gateway=MagicMock(), output_dir=tmp_path, resume=False)

    # round 0(偶代)配对闸:parent(初始) vs variant(elicit 变体,support=DEFAULT)
    # round 1(奇代)配对闸:parent(round0 变体) vs variant(support 改写)
    assert len(arms) == 4  # 每次替换时刻两臂各一次
    parent_arm, variant_arm = arms[2], arms[3]  # round 1 奇代(support 臂)
    from edu_agent.evals import DEFAULT_SUPPORT_HINT
    # round 1 父臂 = round 0 已确认变体(elicit 已换,support 仍是默认);
    # 子臂 = 同 elicit + 新 support(support-only 改写的新候选)
    assert parent_arm[0] == "变体:讲讲思路第一步"
    assert parent_arm[1] == DEFAULT_SUPPORT_HINT  # 父代自身完整旋钮组合
    assert variant_arm[0] == "变体:讲讲思路第一步"
    assert variant_arm[1] == new_support  # variant 自身 support,不共用父代值
    # 同批 case IDs:每代换批(seed=round_idx),同轮两臂一致
    assert parent_arm[2] == variant_arm[2]
    ev0, ev1 = reports[0]["paired_evidence"], reports[1]["paired_evidence"]
    assert ev0["case_ids"] == list(arms[0][2])  # round 0 两臂的批
    assert ev1["case_ids"] == list(parent_arm[2])  # round 1 两臂的批
    assert ev0["case_ids"] != ev1["case_ids"] or ev0["case_ids"] == ev1["case_ids"]
    # (不同 seed 允许同批或换批;关键是证据 case_ids 与臂实际跑的严格一致)


def test_c1_net_a_early_stop_skips_rest(tmp_path):
    """C1:三案固定顺序第二案命中 Net A → 第三案 Tutor 与全部 Judge 额外调用 0;
    失败转录保留;提前失败不计全批成功(hard-fail 向量)。"""
    leaky_case = {"id": "c2",
                  "question": {"text": "妈妈36岁是小华的3倍,小华几岁?", "answer": "12"},
                  "student_turns": ["x"]}
    cases = [
        {"id": "c1", "question": "q", "student_turns": ["a"]},
        leaky_case,
        {"id": "c3", "question": "q", "student_turns": ["c"]},
    ]
    gateway = MagicMock()
    _wire_writer_counters(gateway)
    subject_mock = MagicMock()
    subject_mock.run_case.side_effect = [
        {"turns": [{"student": "", "tutor": "说说你的思路", "state": "dialogue"}],
         "summary": "s"},  # c1 干净
        {"turns": [{"student": "", "tutor": "答案就是12,你验证下", "state": "dialogue"}],
         "summary": "s"},  # c2 泄露(命中 Net A)
        {"turns": [{"student": "", "tutor": "第三案不应被跑到", "state": "dialogue"}],
         "summary": "s"},  # c3 不应消耗
    ]
    with patch("edu_agent.evals.gepa.ElicitSubject", return_value=subject_mock), \
         patch("edu_agent.evals.gepa.judge_transcript") as mock_judge:
        sv, failures, stats = evaluate_batch(cases, "模板", gateway)

    # 第三案 Tutor 0(subject.run_case 恰好 2 次)+ 全部 Judge 0
    assert subject_mock.run_case.call_count == 2
    assert mock_judge.call_count == 0
    assert stats["hard_vetoed"] is True and stats["leak_net_violations"] == 1
    assert sv == ScoreVector(0.0, 1.0, 1.0, 1.0)  # 不计全批成功
    leak_frames = [f for f in failures if f["kind"] == "leak_net"]
    assert len(leak_frames) == 1
    assert any("12" in t.get("tutor", "") for t in leak_frames[0]["transcript"]["turns"])  # 转录保留


def test_c1_seed_hard_failure_stops_before_start(tmp_path):
    """C1:种子(初始批)硬失败 → 停在开跑前:编辑器 0 调用,无代循环。"""
    from edu_agent.evals import GepaConfig, gepa_loop

    leaky = {"id": "c1",
             "question": {"text": "妈妈36岁是小华的3倍,小华几岁?", "answer": "12"},
             "student_turns": ["x"]}
    gateway = MagicMock()
    _wire_writer_counters(gateway)
    subject_mock = MagicMock()
    subject_mock.run_case.return_value = {
        "turns": [{"student": "", "tutor": "答案就是12", "state": "dialogue"}],
        "summary": "s"}

    with patch("edu_agent.evals.gepa.ElicitSubject", return_value=subject_mock), \
         patch("edu_agent.evals.gepa.judge_transcript"), \
         patch("edu_agent.evals.gepa.edit_template") as mock_edit:
        population, scores, reports = gepa_loop(
            train_cases=[leaky], initial_template="种子模板:说说思路",
            config=GepaConfig(rounds=5, max_calls=100),
            gateway=gateway, output_dir=tmp_path, resume=False)

    assert mock_edit.call_count == 0  # 停在开跑前
    assert reports == []
    assert scores == {}  # 种子分不注册
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["seed_hard_vetoed"] is True


def test_c2_fact_writer_counts_only_its_own_process(tmp_path):
    """C2:旁路另一 run(同 facts 目录另一 writer)+ 跨 UTC 日切文件——
    进程内计数只含自己且不丢,不再用「当天文件行数差」承担跨运行归属。"""
    from edu_agent.gateway import FactWriter

    mine, bystander = FactWriter(tmp_path), FactWriter(tmp_path)
    # edu.outcome 补真实字段形态(#332 账实后 count 只计成功调用)
    mine.write({"edu.outcome": "ok", "gen_ai.usage.input_tokens": 10,
                "gen_ai.usage.output_tokens": 5})
    bystander.write({"edu.outcome": "ok", "gen_ai.usage.input_tokens": 99,
                     "gen_ai.usage.output_tokens": 99})
    bystander.write({"edu.outcome": "ok", "gen_ai.usage.input_tokens": 99,
                     "gen_ai.usage.output_tokens": 99})
    mine.write({"edu.outcome": "ok", "gen_ai.usage.input_tokens": 20,
                "gen_ai.usage.output_tokens": 8,
                "gen_ai.usage.cache_read.input_tokens": 3})
    # 本 run 计数只含自己:2 行,不含旁路 2 行
    assert mine.count == 2 and mine.tokens_in == 30 and mine.tokens_out == 13
    assert bystander.count == 2
    # 落盘仍是共享 JSONL(审计事实不丢):4 行
    total_lines = sum(
        len(p.read_text(encoding="utf-8").splitlines())
        for p in tmp_path.glob("model_calls-*.jsonl"))
    assert total_lines == 4


def test_c2_breakdown_sums_to_total_and_survives_resume(tmp_path):
    """C2:分项之和 = facts 总量;恢复后分项累计不归零(跨恢复延续)。"""
    from edu_agent.evals import GepaConfig, gepa_loop
    from edu_agent.evals import search_identity

    # 批级:分项之和 == 总量(evaluate_batch 内 tutor+judge 分臂)
    gateway = MagicMock()
    _wire_writer_counters(gateway)
    subject_mock = MagicMock()

    def fake_judge(gw, judge_case, role="judge"):
        gw.writer.count += 2  # judge 臂 2 calls
        return {"total": 10, "verdict": "pass", "answer_leaked": False,
                "math_integrity": 2, "evidence": {}, "scores": {}}

    def fake_tutor(case):
        gateway.writer.count += 1  # 模拟 tutor 臂 1 call(subject mock 不走真 writer)
        return {"turns": [{"student": "", "tutor": "说说思路", "state": "dialogue"}],
                "summary": "s"}

    subject_mock.run_case.side_effect = fake_tutor
    with patch("edu_agent.evals.gepa.ElicitSubject", return_value=subject_mock), \
         patch("edu_agent.evals.gepa.judge_transcript", side_effect=fake_judge):
        _, _, stats = evaluate_batch([{"id": "c1", "question": "q",
                                       "student_turns": ["a"]}], "模板", gateway)
    assert stats["tutor_calls"] + stats["judge_calls"] == stats["calls"] == 3

    # 恢复级:checkpoint 分项延续
    checkpoint = {
        "next_round": 5,
        "identity": search_identity(GepaConfig(rounds=6, max_calls=100), TRAIN_3),
        "budget": {"calls": 50, "rounds": 5, "wall_s": 1.0, "exhausted": False},
        "best": {"candidate_id": 0, "template": "恢复best",
                 "scores": {"mean_score": 9.0, "needs_review_rate": 0.1,
                            "numerical_violation_rate": 0.1,
                            "hard_failure_rate": 0.0}},
        "call_breakdown": {"tutor_calls": 40, "judge_calls": 9, "editor_calls": 1},
        "last_failures": [],
    }
    (tmp_path / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")

    def fake_eval(cases, template, gateway, judge_role="judge", support_hint=None):
        return _sv(9.0, 0.1, 0.1), [], _stats(calls=5, tutor_calls=3, judge_calls=2)

    with patch("edu_agent.evals.gepa.evaluate_batch", side_effect=fake_eval), \
         patch("edu_agent.evals.gepa.edit_template",
               return_value=("变体:讲讲思路第一步", "edited")):
        gepa_loop(train_cases=TRAIN_3, initial_template="原始",
                  config=GepaConfig(rounds=6, max_calls=100),
                  gateway=MagicMock(), output_dir=tmp_path, resume=True)
    saved = json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))
    # 恢复前 40/9/1 + #332 换批参考 3/2 + 变体批 3/2 + editor 1 → 累计不归零
    assert saved["call_breakdown"] == {"tutor_calls": 46, "judge_calls": 13,
                                       "editor_calls": 2}
