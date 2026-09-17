"""#256 GEPA spike 单元测试:6 组件逐一验证,零 API。"""

from datetime import datetime

import json
from datetime import datetime, timezone

from unittest.mock import MagicMock, patch

from edu_agent.evals import (
    Budget,
    Candidate,
    ElicitSubject,
    Population,
    ScoreVector,
    edit_template,
    evaluate_batch,
    sample_batch,
)


def _wire_writer_counters(gateway: MagicMock, *, start: int = 0) -> None:
    """#324 C2:MagicMock gateway 的 writer 配进程内计数真值(int 差值可算)。

    生产路径 FactWriter 自带 count/tokens_in/tokens_out 进程内累计;
    mock 下需要显式配 int,否则 Mock 参与算术直接 TypeError。
    fake 上游模拟"真实调用落账"时自增 gateway.writer.count 即可。
    """
    gateway.writer.count = start
    gateway.writer.tokens_in = 0
    gateway.writer.tokens_out = 0


# === 0. 三键裁决契约:判分默认本地主选角色(2026-09-17)===

def test_judge_role_defaults_are_local_primary():
    """判分入口默认 judge_role='judge'(registry: mlx_27b 主选 + deepseek 备选)。

    三键裁决落地(PM sha256=d7256fcc631e69e7):evaluate_batch /
    evaluate_batch_paired / GepaConfig 判分默认由 judge_independent(纯远程
    DeepSeek,无 fallback)翻转为 'judge';judge_independent 保留编辑器与
    #32 平行评分用途。契约钉默认值,防回退。
    """
    import inspect

    from edu_agent.evals import GepaConfig, evaluate_batch_paired

    assert inspect.signature(evaluate_batch).parameters["judge_role"].default == "judge"
    assert inspect.signature(evaluate_batch_paired).parameters["judge_role"].default == "judge"
    assert GepaConfig().judge_role == "judge"


# === 1. Prompt seam ===

def test_elicit_subject_calls_kernel():
    """ElicitSubject 包装 KernelSubject,run_case 调用内核。"""
    gateway = MagicMock()
    subject = ElicitSubject("测试变体模板", gateway)
    
    # Mock kernel_subject.run_case to avoid actual model calls
    subject._kernel_subject.run_case = MagicMock(return_value={
        "turns": [],
        "summary": "",
        "session_id": "test",
    })
    
    # Run a case and verify it delegates to kernel_subject
    result = subject.run_case({"id": "test", "question": "1+1=?"})
    
    assert result == {"turns": [], "summary": "", "session_id": "test"}
    subject._kernel_subject.run_case.assert_called_once()


def test_elicit_subject_sensitivity_proof():
    """敏感性自证(P1-1):monkeypatch 实际影响 _ELICIT_TEMPLATE。
    
    同案、同 seed、不同 initial_template → 模板确实被替换。
    这是目标函数敏感性的一票证据:monkeypatch 不是 noop。
    
    注意:此测试验证模板替换机制,不验证 transcript 差异(那需要真实 API)。
    真实敏感性需 smoke test 验证(README §五问①)。
    """
    template1 = "模板 A:请说说你的思路"
    template2 = "模板 B:从头讲一遍"
    
    gateway = MagicMock()
    subject1 = ElicitSubject(template1, gateway)
    subject2 = ElicitSubject(template2, gateway)
    
    # Mock to capture the template used during run_case
    captured1 = []
    captured2 = []
    
    def make_mock(subject, captured):
        def mock_run_case(case):
            captured.append(subject.get_active_template())
            return {"turns": [], "summary": "", "session_id": "test"}
        return mock_run_case
    
    subject1._kernel_subject.run_case = make_mock(subject1, captured1)
    subject2._kernel_subject.run_case = make_mock(subject2, captured2)
    
    # Run both
    subject1.run_case({"id": "test", "question": "1+1=?"})
    subject2.run_case({"id": "test", "question": "1+1=?"})
    
    # Verify templates were different during execution
    assert captured1[0] == template1
    assert captured2[0] == template2
    assert captured1[0] != captured2[0]
    
    # Verify original is restored after each call
    # (We can't check kernel._ELICIT_TEMPLATE directly, but the finally block ensures restoration)


# === 2. Mini-batch sampling ===

def test_sample_batch_deterministic():
    """同种子 = 同批次;换种子 = 刷新。"""
    cases = [{"id": f"c{i}"} for i in range(20)]
    
    batch1 = sample_batch(cases, k=5, seed=42)
    batch2 = sample_batch(cases, k=5, seed=42)
    batch3 = sample_batch(cases, k=5, seed=99)
    
    assert batch1 == batch2  # 同种子确定性
    assert batch1 != batch3  # 换种子刷新
    assert len(batch1) == 5


def test_sample_batch_clamp():
    """k > len(cases) → 返回全部(不报错)。"""
    cases = [{"id": f"c{i}"} for i in range(3)]
    batch = sample_batch(cases, k=10, seed=0)
    assert len(batch) == 3


# === 3. Score vector ===

def test_score_vector_dominates():
    """Pareto 简化:不劣于 + 一维严格更好。"""
    better = ScoreVector(mean_score=8.0, needs_review_rate=0.2, numerical_violation_rate=0.1)
    worse = ScoreVector(mean_score=7.0, needs_review_rate=0.3, numerical_violation_rate=0.2)
    equal = ScoreVector(mean_score=8.0, needs_review_rate=0.2, numerical_violation_rate=0.1)
    mixed = ScoreVector(mean_score=8.5, needs_review_rate=0.25, numerical_violation_rate=0.1)
    
    assert better.dominates(worse)  # 全维更好
    assert not worse.dominates(better)  # 反向不成立
    assert not better.dominates(equal)  # 全等不算 dominate
    assert not mixed.dominates(better)  # 一维更好但另一维更差


# === 4. Reflection editor ===

def test_edit_template_lint_rejects_empty():
    """Lint:空变体 → 保留当前。"""
    gateway = MagicMock()
    gateway.invoke.return_value = MagicMock(text="")
    
    current = "当前模板"
    result, reason = edit_template(current, [], gateway)
    assert result == current
    assert reason == "lint_rejected"  # #324 A-e:原因随值返回


def test_edit_template_lint_rejects_too_short():
    """Lint:太短(<30 字)→ 保留当前。"""
    gateway = MagicMock()
    gateway.invoke.return_value = MagicMock(text="太短")
    
    current = "当前模板"
    result, reason = edit_template(current, [], gateway)
    assert result == current
    assert reason == "lint_rejected"


def test_edit_template_lint_rejects_no_keywords():
    """Lint:缺核心引导词 → 保留当前。"""
    gateway = MagicMock()
    gateway.invoke.return_value = MagicMock(text="这是一段足够长的文本,但是完全不包含任何引导词,只有普通的描述性内容,没有任何教学引导")
    
    current = "当前模板包含思路"
    result, reason = edit_template(current, [], gateway)
    assert result == current
    assert reason == "lint_rejected"


def test_edit_template_accepts_valid():
    """Lint 通过 → 返回变体。"""
    gateway = MagicMock()
    gateway.invoke.return_value = MagicMock(text="请从头讲讲你的思路,先说说第一步做了什么,然后一步步往下讲,把整个解题过程都说清楚")
    
    current = "当前模板"
    result, reason = edit_template(current, [], gateway)
    assert result == "请从头讲讲你的思路,先说说第一步做了什么,然后一步步往下讲,把整个解题过程都说清楚"
    assert reason == "edited"


# === 5. Selection + population ===

def test_population_add_and_select():
    """Population 添加候选,select_parent 选最高 mean_score。"""
    pop = Population()
    c1 = Candidate(template="t1")
    c2 = Candidate(template="t2")
    
    id1 = pop.add(c1)
    id2 = pop.add(c2)
    
    scores = {
        id1: ScoreVector(mean_score=7.0, needs_review_rate=0.3, numerical_violation_rate=0.2),
        id2: ScoreVector(mean_score=8.5, needs_review_rate=0.2, numerical_violation_rate=0.1),
    }
    
    parent = pop.select_parent(scores)
    assert parent.template == "t2"


# === 6. Budget ===

def test_budget_exhausted():
    """Budget 耗尽判断:calls 超限。"""
    budget = Budget(max_calls=100)
    
    assert not budget.exhausted()
    
    budget.add(50)
    assert not budget.exhausted()
    
    budget.add(60)  # total 110 > 100
    assert budget.exhausted()


# === 契约:turns ↔ messages 形状 ===

def test_evaluate_batch_passes_messages_shape():
    """契约测试(#296 bug 防御):evaluate_batch 传给 judge_transcript 的 messages
    必须是 OpenAI chat 格式([{role, content}]),不是 raw turns。
    
    历史 bug:直接传 transcript['turns']({student, tutor, state})→ judge 见空 transcript → 全零分。
    修复:使用 corpus_round.transcript_messages() 转换。此测试锁死不再发生。
    """
    gateway = MagicMock()
    subject_mock = MagicMock()
    subject_mock.run_case.return_value = {
        "turns": [
            {"student": "", "tutor": "你好同学", "state": "first_question_ready", "elapsed_ms": 0},
            {"student": "答案是 42", "tutor": "很好!", "state": "ready_to_confirm", "elapsed_ms": 100},
        ],
        "summary": "学生掌握了加法。",
        "session_id": "test",
    }
    
    cases = [{"id": "c1", "question": {"text": "1+1=?"}, "grade": "三年级", "reference_answer": "2"}]
    
    captured = {}
    
    def fake_judge(gw, judge_case, role="judge_independent"):
        captured["messages"] = judge_case["messages"]
        captured["question"] = judge_case["question"]
        return {"total": 10, "verdict": "pass", "math_integrity": 2}
    
    with patch("edu_agent.evals.gepa.ElicitSubject", return_value=subject_mock), \
         patch("edu_agent.evals.gepa.judge_transcript", side_effect=fake_judge):
        evaluate_batch(cases, "template", gateway)
    
    # messages 必须是 list[dict],每个 dict 有 role+content
    msgs = captured["messages"]
    assert isinstance(msgs, list)
    assert len(msgs) >= 2  # at least tutor turn + summary
    for msg in msgs:
        assert "role" in msg and "content" in msg, f"messages 项缺 role/content: {msg}"
        assert msg["role"] in ("user", "assistant"), f"非法 role: {msg['role']}"
    # question 必须是字符串(从 dict 提取了 text),不是 dict
    assert isinstance(captured["question"], str), f"question 必须是 str,实际: {type(captured['question'])}"


# === 契约:硬失败 + 编辑器反馈(外审 P1,2026-09-16)===

def test_hard_failure_cannot_become_best():
    """契约测试:硬失败候选(answer_leaked/verdict=fail)不能成为最优。
    
    场景:12 分 + 泄答案 vs 11 分合格 → 合格者胜。
    外审确定性探针坐实,本测试锁死不再发生。
    """
    pop = Population()
    # 候选 A:12 分但 100% 硬失败(全泄答案)
    a = Candidate(template="A", candidate_id=0)
    pop.candidates.append(a)
    # 候选 B:11 分但 0% 硬失败(全合格)
    b = Candidate(template="B", candidate_id=1)
    pop.candidates.append(b)
    
    scores = {
        0: ScoreVector(mean_score=12.0, needs_review_rate=0.0,
                       numerical_violation_rate=0.0, hard_failure_rate=1.0),
        1: ScoreVector(mean_score=11.0, needs_review_rate=0.0,
                       numerical_violation_rate=0.0, hard_failure_rate=0.0),
    }
    
    best = pop.select_parent(scores)
    assert best.template == "B", "硬失败候选 A(12 分 + 泄答案)不可胜过合格候选 B(11 分)"


def test_hard_failure_dominates_block():
    """契约测试:硬失败率更高的候选不能 dominates 更干净的候选。"""
    dirty = ScoreVector(mean_score=12.0, needs_review_rate=0.0,
                        numerical_violation_rate=0.0, hard_failure_rate=0.5)
    clean = ScoreVector(mean_score=11.0, needs_review_rate=0.0,
                        numerical_violation_rate=0.0, hard_failure_rate=0.0)
    # dirty 分数高但硬失败多 → 不能 dominates clean(hard_failure_rate 维度更差)
    assert not dirty.dominates(clean)
    # 同分场景:clean dominates dirty(硬失败率维度严格更好,其他维度不劣)
    dirty_same = ScoreVector(mean_score=11.0, needs_review_rate=0.0,
                             numerical_violation_rate=0.0, hard_failure_rate=0.5)
    assert clean.dominates(dirty_same)


def test_evaluate_batch_collects_low_score_evidence():
    """契约测试:低分 case(total<10 或维度 0 分)的维度名+证据原句进 failures 列表。
    
    外审坐实:原 failures 只收 GatewayError,反思编辑器永远看到「无失败案例」。
    本测试锁死低分反馈进入 failures,kind='judge_low_score'。
    """
    gateway = MagicMock()
    subject_mock = MagicMock()
    subject_mock.run_case.return_value = {
        "turns": [{"student": "", "tutor": "好", "state": "x", "elapsed_ms": 0}],
        "summary": "",
        "session_id": "t",
    }
    cases = [{"id": "c_low", "question": "1+1?", "grade": "三年级", "reference_answer": "2"}]
    
    def fake_judge(gw, judge_case, role="judge_independent"):
        return {
            "total": 4,  # < 10 → 低分
            "verdict": "fail",
            "math_integrity": 2,
            "answer_leaked": False,
            "scores": {"first_question": 0, "socratic_followup": 2, "grade_fit": 2,
                       "pacing": 0, "summary_mastery": 0, "termination": 0},
            "evidence": {"first_question": "未切题讲解", "pacing": "无推进", "summary_mastery": "无总结", "termination": "无终止"},
        }
    
    with patch("edu_agent.evals.gepa.ElicitSubject", return_value=subject_mock), \
         patch("edu_agent.evals.gepa.judge_transcript", side_effect=fake_judge):
        sv, failures, _stats = evaluate_batch(cases, "t", gateway)
    
    # ScoreVector 含 hard_failure_rate(verdict=fail)
    assert sv.hard_failure_rate == 1.0
    # failures 列表含 judge_low_score 项
    low_score_frames = [f for f in failures if f["kind"] == "judge_low_score"]
    assert low_score_frames, f"failures 未收低分反馈: {failures}"
    # 证据包含维度名
    detail = low_score_frames[0]["detail"]
    assert any(dim in detail for dim in ("first_question", "pacing", "summary_mastery", "termination")), \
        f"detail 未含维度名: {detail}"


# === 7. 长跑断点与实测计数(#256 阶段0) ===


def test_write_checkpoint_and_restore_semantics(tmp_path):
    """checkpoint 落盘最优解+预算+代次;resume 语义字段齐(跨夜可恢复)。"""
    from edu_agent.evals import LoopState, write_checkpoint

    state = LoopState()
    state.population = Population()
    a = Candidate(template="模板A:说说思路和第一步")
    # #324 A-d:best 的 support_hint 属候选自身——与顶层 state.support_hint
    # 不同值,验证不拼接(旧 bug:写顶层值会串台)
    b_support = "拆小:你先看这一步里最小的一个数,能先算出什么?"
    b = Candidate(template="模板B:从头讲讲你的思路,先说第一步",
                  support_hint=b_support)
    state.scores[state.population.add(a)] = ScoreVector(8.0, 0.2, 0.1, 0.0)
    state.scores[state.population.add(b)] = ScoreVector(9.0, 0.1, 0.1, 0.0)
    state.support_hint = "顶层后来的 support(不应被写进 best)"  # 串台探针
    state.bind(1624)
    state.budget.add(300)
    state.budget.rounds = 2
    write_checkpoint(tmp_path, state, 3,
                      [{"case_id": "x", "kind": "k", "detail": "d"}])

    saved = json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))
    assert saved["next_round"] == 3
    assert saved["budget"]["calls"] == 300 and saved["budget"]["rounds"] == 2
    assert saved["best"]["template"].startswith("模板B")  # select_parent 选最高分
    assert saved["best"]["scores"]["mean_score"] == 9.0
    assert saved["best"]["support_hint"] == b_support  # 候选自身的,非顶层串台值
    assert saved["last_failures"][0]["case_id"] == "x"


def test_gepa_loop_resume_skips_initial_evaluation(tmp_path):
    """resume=True 且 checkpoint 在:初始评估不再跑(省预算),代次从 next_round 起。"""
    from edu_agent.evals import GepaConfig, gepa_loop
    from edu_agent.evals import search_identity

    train = [{"id": "c1", "question": "q", "student_turns": ["a"]}]
    checkpoint = {
        "next_round": 5,
        "identity": search_identity(GepaConfig(rounds=6, max_calls=1624), train),
        "budget": {"calls": 100, "rounds": 5, "wall_s": 1.0, "exhausted": False},
        "best": {"candidate_id": 0,
                 "template": "恢复模板:说说你的思路,先说第一步",
                 "support_hint": "恢复support:你先看这一步里最小的数?",
                 "scores": {"mean_score": 9.0, "needs_review_rate": 0.1,
                            "numerical_violation_rate": 0.1, "hard_failure_rate": 0.0}},
        "last_failures": [],
    }
    (tmp_path / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")

    with patch("edu_agent.evals.gepa.evaluate_batch") as mock_eval, \
         patch("edu_agent.evals.gepa.edit_template",
               return_value=("变体:讲讲思路的第一步", "edited")):  # #324 A-e 二元组
        mock_eval.return_value = (ScoreVector(9.0, 0.1, 0.1, 0.0), [],
                                  {"calls": 5, "tokens_in": 0, "tokens_out": 0,
                                   "env_failures": 0, "content_failures": 0, "wall_ms": 1})
        gepa_loop(train_cases=train,
                  initial_template="原始模板",
                  config=GepaConfig(rounds=6, max_calls=1624),
                  gateway=MagicMock(),
                  output_dir=tmp_path,
                  resume=True)
        # resume 后不再评估初始模板:唯一一次 evaluate_batch 是第 5 代变体批
        assert mock_eval.call_count == 1
    saved = json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))
    assert saved["budget"]["calls"] == 106  # 100(恢复)+ 1(编辑器)+ 5(变体批)
    assert saved["next_round"] == 6
    # #324 A-d:best 的 support_hint 属候选自身——恢复带回 checkpoint 里的值,
    # 不拼接顶层默认(旧 bug:写顶层 state.support_hint 会串台)
    assert saved["best"]["support_hint"] == "恢复support:你先看这一步里最小的数?"
    assert saved["best"]["template"].startswith("恢复模板")  # 同属恢复的 best 候选


def test_evaluate_batch_counts_calls_from_facts(tmp_path):
    """calls = facts 实测差值(长跑口径):估算 len+judged 低估 ~3x 会超预算。"""
    facts = tmp_path / f"model_calls-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
    facts.write_text("\n".join(json.dumps({"i": i}) for i in range(10)) + "\n",
                     encoding="utf-8")
    gateway = MagicMock()
    gateway.writer.root = tmp_path
    _wire_writer_counters(gateway)  # #324 C2:writer 进程内计数语义

    def fake_run_case(case):
        with facts.open("a", encoding="utf-8") as handle:  # 模拟 tutor 真实调用落账
            handle.write(json.dumps({"i": 99}) + "\n")
        gateway.writer.count += 1  # writer 进程内计数同步 +1(#324 C2)
        return {"turns": [{"student": "", "tutor": "好", "state": "dialogue"}]}

    def fake_judge(gateway, judge_case, role="judge"):
        with facts.open("a", encoding="utf-8") as handle:  # judge 侧真实落账 ×2
            handle.write(json.dumps({"i": 100}) + "\n")
            handle.write(json.dumps({"i": 101}) + "\n")
        gateway.writer.count += 2  # writer 进程内计数同步 +2
        return {"total": 10, "verdict": "pass", "answer_leaked": False,
                "math_integrity": 2, "evidence": {}, "scores": {}}

    with patch("edu_agent.evals.gepa.ElicitSubject") as mock_subject, \
         patch("edu_agent.evals.gepa.judge_transcript", side_effect=fake_judge):
        mock_subject.return_value.run_case.side_effect = fake_run_case
        _, _, stats = evaluate_batch([{"id": "c1", "question": "q", "student_turns": ["a"]}],
                                     "模板", gateway)
        assert stats["calls"] == 3  # tutor 1 + judge 2 的 writer 差值(#324 C2 进程内计数),
        # 不再用当天文件行数差(跨 UTC 日/旁路 run 归属会错)


# === 8. 双旋钮搜索空间(#256 阶段 2 选项 A,#304 头部可达族) ===


def test_elicit_subject_support_hint_roundtrip():
    """ElicitSubject 带 support_hint 时 monkeypatch 两个 seam,用完恢复。"""
    from edu_agent.evals import DEFAULT_SUPPORT_HINT

    subject = ElicitSubject("说说思路和第一步", MagicMock(), support_hint="拆小:你先看哪个数?")
    assert subject.variants["_SUPPORT_HINT"] == "拆小:你先看哪个数?"
    # 未提供 support 变体时 seam 集只有 elicit(向后兼容)
    plain = ElicitSubject("模板", MagicMock())
    assert set(plain.variants) == {"_ELICIT_TEMPLATE"}
    # run_case 全程两个 seam 真被注入、用完恢复(r2 崩溃根因回归钉:
    # seam 指向不存在的 kernel 属性时,这里会当场 AttributeError 而非静默)
    original_elicit = subject.get_active_template()
    original_support = subject.get_active_support_hint()
    seen = {}
    with patch.object(subject._kernel_subject, "run_case",
                      side_effect=lambda case: seen.update(
                          elicit=subject.get_active_template(),
                          support=subject.get_active_support_hint()) or {}):
        subject.run_case({"id": "c"})
    assert seen["elicit"] == "说说思路和第一步"
    assert seen["support"] == "拆小:你先看哪个数?"
    assert subject.get_active_template() == original_elicit  # 用完恢复
    assert subject.get_active_support_hint() == original_support
    assert DEFAULT_SUPPORT_HINT == original_support  # 常量与 kernel 默认一致


def test_edit_two_knobs_parity_routing():
    """偶代编辑 elicit(support 原样返回)、奇代编辑 support(elicit 原样)。"""
    from edu_agent.evals import edit_two_knobs

    with patch("edu_agent.evals.gepa_editors.edit_template",
                return_value=("新的elicit", "edited")) as m:  # #324 A-e:编辑器返回 (值, 原因)
        elicit, support, _r = edit_two_knobs("旧elicit", "旧support", 0, [], MagicMock())
        assert elicit == "新的elicit" and support == "旧support"
        m.assert_called_once()
    gateway = MagicMock()
    gateway.invoke.return_value.text = "拆小:先不想整道题,只看这一步里最小的那个数,你觉得能先算出什么?"
    elicit, support, _r = edit_two_knobs("旧elicit", "旧support", 1, [], gateway)
    assert elicit == "旧elicit"
    assert _r == "edited"  # #324 A-e
    assert support == "拆小:先不想整道题,只看这一步里最小的那个数,你觉得能先算出什么?"


def test_edit_two_knobs_lint_guards():
    """support 变体 lint:太短/无问号/与父代相同 → 保留父代(零退化)。"""
    from edu_agent.evals import edit_two_knobs

    for bad in ("太短", "这不是问句", "旧support"):
        gateway = MagicMock()
        gateway.invoke.return_value.text = bad
        elicit, support, _r = edit_two_knobs("旧elicit", "旧support", 1, [], gateway)
        assert (elicit, support) == ("旧elicit", "旧support"), bad
        assert _r in ("lint_rejected", "unchanged"), bad  # #324 A-e


# === 9. needs_review 靶向编辑(收敛#2 选项①准备件,默认关) ===


def test_edit_template_nr_lint_and_targeting():
    """nr 编辑器:review 靶向语与失败帧进 prompt;lint 不过(缺关键词/超窗)保留父代。"""
    from edu_agent.evals import edit_template_nr

    parent = "旧模板" * 15  # 45 字,合法父代
    gateway = MagicMock()
    ok = "复讲时请先说思路:第一步你算了什么、用哪个算式,把结论说出来,让老师能判定你懂了。"
    gateway.invoke.return_value.text = ok
    variant, reason = edit_template_nr(parent, [
        {"case_id": "c9", "kind": "judge_low_score", "detail": "total=9, verdict=review"}],
        gateway)
    assert variant == ok and reason == "edited"  # #324 A-e
    sent = gateway.invoke.call_args[0][0].messages[0]["content"]
    assert "review" in sent and "可判定" in sent  # 靶向指令真的进 prompt
    assert "c9" in sent  # 失败帧进 prompt
    for bad in ("太短", parent):  # 太短出窗 / 与父代相同 → 零退化
        gateway = MagicMock()
        gateway.invoke.return_value.text = bad
        assert edit_template_nr(parent, [], gateway)[0] == parent, bad


def test_edit_two_knobs_injected_editor_routes_even_rounds():
    """editor 显式注入:偶代 elicit 编辑走注入编辑器;不注入时晚绑定 edit_template。"""
    from edu_agent.evals import edit_two_knobs

    sentinel = MagicMock(return_value=("nr变体", "edited"))  # #324 A-e 二元组
    support_spy = MagicMock(return_value=("nr问句?", "edited"))
    elicit, support, _r = edit_two_knobs("旧elicit", "旧support", 0, [], MagicMock(),
                                     editors=(sentinel, support_spy))
    assert (elicit, support) == ("nr变体", "旧support")  # 偶代 support 原样
    assert sentinel.call_args.args[:2] == ("旧elicit", [])
    assert not support_spy.called
    elicit, support, _r = edit_two_knobs("旧elicit", "旧support", 1, [], MagicMock(),
                                     editors=(sentinel, support_spy))
    assert (elicit, support) == ("旧elicit", "nr问句?")  # 奇代 elicit 原样
    assert support_spy.call_args.args[:2] == ("旧support", [])


def test_gepa_loop_editor_focus_nr_uses_nr_editor(tmp_path):
    """全循环路由:two_knobs + editor_focus='nr' → 第 24 代(偶)编辑走 nr 编辑器,
    mean 编辑器不被调用;默认 focus='mean' 契约钉。"""
    from edu_agent.evals import GepaConfig, gepa_loop
    from edu_agent.evals import search_identity

    assert GepaConfig(rounds=1).editor_focus == "mean"  # 默认关,裁决②则永不打开
    train = [{"id": "c1", "question": "q", "student_turns": ["a"]}]
    checkpoint = {
        "next_round": 24,
        "identity": search_identity(
            GepaConfig(rounds=25, max_calls=1624, two_knobs=True,
                       editor_focus="nr"), train),
        "budget": {"calls": 1107, "rounds": 23, "wall_s": 1.0, "exhausted": False},
        "best": {"candidate_id": 0,
                 "template": "best:说说你的思路,先说第一步",
                 "scores": {"mean_score": 9.25, "needs_review_rate": 0.5,
                            "numerical_violation_rate": 0.0, "hard_failure_rate": 0.06}},
        "last_failures": [],
    }
    (tmp_path / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")

    with patch("edu_agent.evals.gepa.evaluate_batch") as mock_eval, \
         patch("edu_agent.evals.gepa.edit_template_nr",
               return_value=("nr变体", "edited")) as m_nr, \
         patch("edu_agent.evals.gepa.edit_template") as m_mean:
        mock_eval.return_value = (ScoreVector(9.0, 0.5, 0.0, 0.0), [],
                                  {"calls": 5, "tokens_in": 0, "tokens_out": 0,
                                   "env_failures": 0, "content_failures": 0, "wall_ms": 1})
        gepa_loop(train_cases=train,
                  initial_template="原始模板",
                  config=GepaConfig(rounds=25, max_calls=1624, two_knobs=True,
                                    editor_focus="nr"),
                  gateway=MagicMock(),
                  output_dir=tmp_path,
                  resume=True)
        assert m_nr.call_count == 1  # 第 24 代偶代:elicit 编辑走 nr 靶向
        assert m_mean.call_count == 0


# === 10. Net A:终答值泄露网进 loop(#310 试点,gate-01-r24 教训) ===


def test_evaluate_batch_leak_net_violation_counted(tmp_path):
    """泄露网违例:计数进 stats + 失败帧(kind=leak_net,带轮次原文)。"""
    facts = tmp_path / f"model_calls-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
    facts.write_text("", encoding="utf-8")
    gateway = MagicMock()
    gateway.writer.root = tmp_path
    case = {"id": "c1", "question": {"text": "妈妈36岁是小华的3倍,小华几岁?", "answer": "12"},
            "student_turns": ["x"]}
    with patch("edu_agent.evals.gepa.ElicitSubject") as mock_subject, \
         patch("edu_agent.evals.gepa.judge_transcript") as mock_judge:
        mock_subject.return_value.run_case.return_value = {
            "turns": [{"student": "", "tutor": "你用12乘3等于36验证了,很扎实", "state": "dialogue"}],
            "summary": "s"}
        mock_judge.return_value = {"total": 10, "verdict": "pass", "answer_leaked": False,
                                   "math_integrity": 2, "evidence": {}, "scores": {}}
        _, failures, stats = evaluate_batch([case], "模板", gateway)
    assert stats["leak_net_violations"] == 1
    leak_frames = [f for f in failures if f["kind"] == "leak_net"]
    assert len(leak_frames) == 1 and "12" in leak_frames[0]["detail"]
    # 干净转录零违例
    mock_subject.return_value.run_case.return_value = {
        "turns": [{"student": "", "tutor": "说说你的思路", "state": "dialogue"}], "summary": "s"}
    _, failures2, stats2 = evaluate_batch([case], "模板", gateway)
    assert stats2["leak_net_violations"] == 0 and not [f for f in failures2 if f["kind"] == "leak_net"]


def test_gepa_loop_leak_net_veto_blocks_selection(tmp_path):
    """否决双闸:泄露网违例变体 accepted=False 且不注册分数——
    checkpoint best 与下轮父代都不会是脏变体(即使四维全优)。"""
    from edu_agent.evals import GepaConfig, gepa_loop

    clean_stats = {"calls": 5, "tokens_in": 0, "tokens_out": 0, "env_failures": 0,
                   "content_failures": 0, "wall_ms": 1, "leak_net_violations": 0}
    dirty_stats = dict(clean_stats, leak_net_violations=2)
    returns = [
        (ScoreVector(8.0, 0.3, 0.1, 0.1), [], clean_stats),        # 初始评估
        (ScoreVector(9.5, 0.1, 0.0, 0.0), [], dirty_stats),        # r0:全优但泄露
        (ScoreVector(9.6, 0.1, 0.0, 0.0), [], dirty_stats),        # r1:全优但泄露
    ]
    with patch("edu_agent.evals.gepa.evaluate_batch", side_effect=returns), \
         patch("edu_agent.evals.gepa.edit_template",
               side_effect=[("脏变体A:讲讲思路的第一步", "edited"),
                            ("脏变体B:说说思路的第一步", "edited")]):  # #324 A-e
        _, _, reports = gepa_loop(
            train_cases=[{"id": "c1", "question": "q", "student_turns": ["a"]}],
            initial_template="初始:说说你的思路,先说第一步",
            config=GepaConfig(rounds=2, max_calls=100),
            gateway=MagicMock(), output_dir=tmp_path)
    assert all(r["leak_net_veto"] and not r["accepted"] for r in reports)
    saved = json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))
    assert saved["best"]["template"].startswith("初始")  # 脏变体永不被选为最优


# === 11. PM-RULING#5 两处置:同分布初始批 + nr 分母非 hard 案 ===


def test_evaluate_batch_nr_denominator_excludes_hard(tmp_path):
    """nr 分母 = 非 hard 案:4 案中 2 hard(fail/leaked)只 1 review → 0.5 而非 0.25。"""
    facts = tmp_path / f"model_calls-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
    facts.write_text("", encoding="utf-8")
    gateway = MagicMock()
    gateway.writer.root = tmp_path
    cases = [{"id": f"c{i}", "question": "q", "student_turns": ["a"]} for i in range(4)]
    verdicts = [
        {"total": 6, "verdict": "fail", "answer_leaked": False, "math_integrity": 2,
         "evidence": {}, "scores": {}},          # hard: fail
        {"total": 8, "verdict": "review", "answer_leaked": True, "math_integrity": 2,
         "evidence": {}, "scores": {}},          # hard: leaked(review 也不计 nr 分子分母)
        {"total": 9, "verdict": "review", "answer_leaked": False, "math_integrity": 2,
         "evidence": {}, "scores": {}},          # 非 hard 的 review → 计 nr
        {"total": 10, "verdict": "pass", "answer_leaked": False, "math_integrity": 2,
         "evidence": {}, "scores": {}},
    ]
    with patch("edu_agent.evals.gepa.ElicitSubject") as mock_subject, \
         patch("edu_agent.evals.gepa.judge_transcript", side_effect=verdicts):
        mock_subject.return_value.run_case.return_value = {
            "turns": [{"student": "s", "tutor": "t", "state": "dialogue"}], "summary": "x"}
        vector, _, _ = evaluate_batch(cases, "模板", gateway)
    assert vector.hard_failure_rate == 0.5
    assert vector.needs_review_rate == 0.5  # 1/(4-2),非 1/4


def test_fresh_run_initial_batch_same_distribution_as_rounds(tmp_path):
    """初始评估批 = sample_batch(seed=0),与代间批同分布(弃文件序前缀)。"""
    from edu_agent.evals import GepaConfig, gepa_loop, sample_batch

    train = [{"id": f"case-{i:02d}", "question": "q", "student_turns": ["a"]}
             for i in range(93)]
    stats = {"calls": 1, "tokens_in": 0, "tokens_out": 0, "env_failures": 0,
             "content_failures": 0, "wall_ms": 1, "leak_net_violations": 0}
    with patch("edu_agent.evals.gepa.evaluate_batch") as mock_eval, \
         patch("edu_agent.evals.gepa.edit_template",
               return_value=("变体:讲讲思路的第一步", "edited")):  # #324 A-e
        mock_eval.return_value = (ScoreVector(8.0, 0.2, 0.0, 0.0), [], stats)
        gepa_loop(train_cases=train, initial_template="初始:说说你的思路,先说第一步",
                  config=GepaConfig(rounds=1, batch_size=16, max_calls=100),
                  gateway=MagicMock(), output_dir=tmp_path)
        initial_cases = mock_eval.call_args_list[0].args[0]
    assert [c["id"] for c in initial_cases] == [c["id"] for c in sample_batch(train, 16, 0)]
