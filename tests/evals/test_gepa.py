"""#256 GEPA spike 单元测试:6 组件逐一验证,零 API。"""

from unittest.mock import MagicMock

from edu_agent.evals import (
    Budget,
    Candidate,
    ElicitSubject,
    Population,
    ScoreVector,
    edit_template,
    sample_batch,
)


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
    result = edit_template(current, [], gateway)
    assert result == current


def test_edit_template_lint_rejects_too_short():
    """Lint:太短(<30 字)→ 保留当前。"""
    gateway = MagicMock()
    gateway.invoke.return_value = MagicMock(text="太短")
    
    current = "当前模板"
    result = edit_template(current, [], gateway)
    assert result == current


def test_edit_template_lint_rejects_no_keywords():
    """Lint:缺核心引导词 → 保留当前。"""
    gateway = MagicMock()
    gateway.invoke.return_value = MagicMock(text="这是一段足够长的文本,但是完全不包含任何引导词,只有普通的描述性内容,没有任何教学引导")
    
    current = "当前模板包含思路"
    result = edit_template(current, [], gateway)
    assert result == current


def test_edit_template_accepts_valid():
    """Lint 通过 → 返回变体。"""
    gateway = MagicMock()
    gateway.invoke.return_value = MagicMock(text="请从头讲讲你的思路,先说说第一步做了什么,然后一步步往下讲,把整个解题过程都说清楚")
    
    current = "当前模板"
    result = edit_template(current, [], gateway)
    assert result == "请从头讲讲你的思路,先说说第一步做了什么,然后一步步往下讲,把整个解题过程都说清楚"


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
