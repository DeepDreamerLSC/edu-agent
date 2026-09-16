"""GEPA 手搓 spike(#256,2026-09-16):最小可用优化器循环,6 组件。

搜索空间:elicit 模板变体(kernel._ELICIT_TEMPLATE 注入,不动仓库常量);
度量:judge 总分均值 / needs_review 率 / 数值违规率(多指标 Pareto);
纪律:优化器只提案,合并键在人;train/held-out 切分;预算计数(calls/tokens/墙钟)。

前置:#238 件A/件B 已落地;判据新指纹 9551d149 生效。
预算:tier-2 已批(K=4×S=16×I=6=384 案次 / ≈1,624 calls);spike 从 tier-2 扣。
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from difflib import unified_diff
from pathlib import Path

from edu_agent.agents.small_lecturer import kernel
from edu_agent.gateway import Gateway, GatewayError, ModelRequest

from .corpus_round import transcript_messages
from .judge import judge_transcript
from .kernel_subject import KernelSubject
from .runner import EnvironmentFailure


# === 1. Prompt seam:elicit 模板变体注入 ===

class ElicitSubject:
    """KernelSubject 包装:run_case 注入 elicit 模板变体(monkeypatch,用完即恢复)。
    
    纪律:不动 kernel.py 常量;monkeypatch 是 spike 最小缝合面,生产化须外置。
    """
    
    def __init__(self, template: str, gateway: Gateway) -> None:
        self.template = template
        self.gateway = gateway
        self._kernel_subject = KernelSubject(gateway)
    
    @property
    def name(self) -> str:
        return f"elicit-{hash(self.template) % 10000:04d}"
    
    def get_active_template(self) -> str:
        """获取当前激活的 elicit 模板(测试用,验证 monkeypatch 生效)。"""
        return kernel._ELICIT_TEMPLATE
    
    def run_case(self, case: dict) -> dict:
        original = kernel._ELICIT_TEMPLATE
        try:
            kernel._ELICIT_TEMPLATE = self.template
            return self._kernel_subject.run_case(case)
        finally:
            kernel._ELICIT_TEMPLATE = original


# === 2. Mini-batch 采样 ===

def sample_batch(cases: list[dict], k: int, seed: int) -> list[dict]:
    """每轮从 train 抽 k 个;换种子 = 刷新基础(随机化切片,防过拟合单批)。"""
    rng = random.Random(seed)
    return rng.sample(cases, min(k, len(cases)))


# === 3. 打分向量 ===

@dataclass(frozen=True)
class ScoreVector:
    """四指标:judge 总分均值(/12) / needs_review 率 / 数值违规率(mi<2) / 硬失败率。
    
    硬失败 = answer_leaked=True 或 verdict='fail'(judge 判定一票否决)。
    硬失败候选不能成为最优(外审确定性探针坐实:12 分 + 泄答案不可胜过 11 分合格)。
    
    Pareto 简化:新批次不劣于父代且一维更好才留;不做 ε-domination 或 crowding distance。
    """
    mean_score: float
    needs_review_rate: float
    numerical_violation_rate: float
    hard_failure_rate: float = 0.0
    
    def dominates(self, other: ScoreVector) -> bool:
        """新批次不劣于父代(全维 ≥/≤)且至少一维严格更好。
        
        硬失败率维度:自身更高 = 更差,自身更低 = 更好。
        """
        not_worse = (
            self.mean_score >= other.mean_score
            and self.needs_review_rate <= other.needs_review_rate
            and self.numerical_violation_rate <= other.numerical_violation_rate
            and self.hard_failure_rate <= other.hard_failure_rate
        )
        strictly_better = (
            self.mean_score > other.mean_score
            or self.needs_review_rate < other.needs_review_rate
            or self.numerical_violation_rate < other.numerical_violation_rate
            or self.hard_failure_rate < other.hard_failure_rate
        )
        return not_worse and strictly_better


def _score_one_case(
    gateway: Gateway, case: dict, transcript: dict, judge_role: str,
) -> tuple[int, str, int, bool, list[dict]]:
    """单案判卷 + 失败帧收集(供 evaluate_batch 调用)。
    
    返回:(total, verdict, math_integrity, is_hard_failure, low_score_failure_frames)。
    GatewayError 直接抛出,由调用方捕获。
    """
    messages = transcript_messages(transcript)
    question = case.get("question", "")
    judge_case = {
        "question": question["text"] if isinstance(question, dict) else question,
        "grade": case.get("grade", ""),
        "reference_answer": case.get("reference_answer", ""),
        "messages": messages,
    }
    judge_output = judge_transcript(gateway, judge_case, role=judge_role)
    total = judge_output["total"]
    verdict = judge_output.get("verdict", "")
    leaked = judge_output.get("answer_leaked", False)
    mi = judge_output.get("math_integrity", 2)
    evidence = judge_output.get("evidence", {})
    dim_scores = judge_output.get("scores", {})
    
    is_hard_fail = leaked or verdict == "fail"
    
    low_frames: list[dict] = []
    low_dims = [dim for dim, s in dim_scores.items() if s == 0]
    if total < 10 or low_dims:
        parts: list[str] = []
        for dim in low_dims[:2]:  # 最多 2 个维度,防 prompt 过长
            parts.append(f"{dim}={dim_scores.get(dim, '?')} — {evidence.get(dim, '')[:80]}")
        if total < 10:
            parts.append(f"total={total}/12")
        low_frames.append({
            "case_id": case.get("id", ""),
            "kind": "judge_low_score",
            "detail": "; ".join(parts) if parts else f"total={total}",
        })
    
    return total, verdict, mi, is_hard_fail, low_frames


def evaluate_batch(
    cases: list[dict],
    template: str,
    gateway: Gateway,
    judge_role: str = "judge_independent",
) -> tuple[ScoreVector, list[dict], dict]:
    """跑批 + 判卷一步到位(无 checkpoint/resume,spike 简化)。
    
    返回:(score_vector, failure_frames, stats)。
    stats = {calls, tokens_in, tokens_out, wall_ms, env_failures, content_failures}。
    """
    started = time.monotonic()
    subject = ElicitSubject(template, gateway)
    
    transcripts = []
    failures = []
    stats = {"calls": 0, "tokens_in": 0, "tokens_out": 0, "env_failures": 0, "content_failures": 0}
    
    for case in cases:
        try:
            transcript = subject.run_case(case)
            transcripts.append((case, transcript))
        except EnvironmentFailure as exc:
            failures.append({"case_id": case.get("id", ""), "kind": "environment", "detail": str(exc)})
            stats["env_failures"] += 1
        except Exception as exc:  # noqa: BLE001
            failures.append({"case_id": case.get("id", ""), "kind": "content", "detail": str(exc)})
            stats["content_failures"] += 1
    
    scores = []
    needs_review = 0
    violations = 0
    hard_failures = 0
    judged = 0
    
    for case, transcript in transcripts:
        try:
            total, verdict, mi, is_hard_fail, low_frames = _score_one_case(
                gateway, case, transcript, judge_role)
        except GatewayError as exc:
            failures.append({"case_id": case.get("id", ""), "kind": "judge_error", "detail": str(exc)})
            continue
        scores.append(total)
        judged += 1
        if verdict == "review":
            needs_review += 1
        if mi < 2:
            violations += 1
        if is_hard_fail:
            hard_failures += 1
        if low_frames:
            failures.extend(low_frames)
    
    stats["wall_ms"] = int((time.monotonic() - started) * 1000)
    stats["calls"] = len(cases) + judged
    
    if not scores:
        return ScoreVector(0.0, 1.0, 1.0, 1.0), failures, stats
    
    mean_score = sum(scores) / len(scores)
    return ScoreVector(
        mean_score=mean_score,
        needs_review_rate=needs_review / judged if judged else 1.0,
        numerical_violation_rate=violations / judged if judged else 1.0,
        hard_failure_rate=hard_failures / judged if judged else 1.0,
    ), failures, stats


def _count_facts_lines(facts_dir: Path) -> int:
    """统计 facts 目录当天 JSONL 行数(真实调用计数,01 §7)。"""
    from datetime import datetime, timezone
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    target = facts_dir / f"model_calls-{day}.jsonl"
    if not target.exists():
        return 0
    with target.open(encoding="utf-8") as f:
        return sum(1 for _ in f)


def _sum_facts_tokens(facts_dir: Path, since_line: int) -> tuple[int, int]:
    """统计 facts 目录自 since_line 行起的 input_tokens + output_tokens。"""
    from datetime import datetime, timezone
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    target = facts_dir / f"model_calls-{day}.jsonl"
    tokens_in = 0
    tokens_out = 0
    if not target.exists():
        return tokens_in, tokens_out
    with target.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i < since_line:
                continue
            try:
                rec = json.loads(line)
                tokens_in += rec.get("gen_ai.usage.input_tokens") or 0
                tokens_out += rec.get("gen_ai.usage.output_tokens") or 0
            except (json.JSONDecodeError, TypeError):
                continue
    return tokens_in, tokens_out


def evaluate_batch_paired(
    cases: list[dict],
    template: str,
    gateway: Gateway,
    judge_role: str = "judge_independent",
) -> tuple[list[dict], list[dict], dict]:
    """配对实验:逐案跑 + 逐案判,返回 per-case scores 和首问快照。
    
    返回:(per_case_scores, first_questions, stats)。
    per_case_scores = [{case_id, total, verdict, leaked, mi, hard_fail}, ...]
    first_questions = [{case_id, first_question}, ...] (首问来自 turns[0].tutor)
    stats = {calls, tokens_in, tokens_out, wall_ms, env_failures, content_failures}
    
    调用计数:从 facts ledger 实测,不硬编码(01 §7)。
    """
    started = time.monotonic()
    subject = ElicitSubject(template, gateway)
    
    facts_dir = gateway.writer.root
    facts_before = _count_facts_lines(facts_dir)
    
    per_case_scores = []
    first_questions = []
    stats = {"calls": 0, "tokens_in": 0, "tokens_out": 0, "env_failures": 0, "content_failures": 0}
    
    for case in cases:
        try:
            transcript = subject.run_case(case)
            # 首问来自 turns[0].tutor(transcript 无 first_question 键)
            turns = transcript.get("turns", [])
            first_q = turns[0]["tutor"] if turns else ""
            first_questions.append({"case_id": case.get("id", ""), "first_question": first_q})
            
            total, verdict, mi, is_hard_fail, _low_frames = _score_one_case(
                gateway, case, transcript, judge_role)
            per_case_scores.append({
                "case_id": case.get("id", ""),
                "total": total,
                "verdict": verdict,
                "leaked": is_hard_fail and verdict != "fail",
                "mi": mi,
                "hard_fail": is_hard_fail,
            })
        except EnvironmentFailure as exc:
            per_case_scores.append({
                "case_id": case.get("id", ""),
                "error": f"environment: {str(exc)[:100]}",
            })
            stats["env_failures"] += 1
        except GatewayError as exc:
            per_case_scores.append({
                "case_id": case.get("id", ""),
                "error": f"judge_error: {str(exc)[:100]}",
            })
        except Exception as exc:  # noqa: BLE001
            per_case_scores.append({
                "case_id": case.get("id", ""),
                "error": f"content: {str(exc)[:100]}",
            })
            stats["content_failures"] += 1
    
    # facts 实测计数(不硬编码 +=2)
    facts_after = _count_facts_lines(facts_dir)
    stats["calls"] = facts_after - facts_before
    tokens_in, tokens_out = _sum_facts_tokens(facts_dir, facts_before)
    stats["tokens_in"] = tokens_in
    stats["tokens_out"] = tokens_out
    stats["wall_ms"] = int((time.monotonic() - started) * 1000)
    return per_case_scores, first_questions, stats


# === 4. 反思编辑器 ===

_EDITOR_PROMPT = """你是一个提示词编辑器。当前 elicit 模板:
---
{current}
---

失败案例摘要(共 {n_failures} 个):
{failure_summary}

任务:生成改进版本,保持核心意图(引导学生从头讲思路、先说第一步),但调整措辞以降低失败率。
约束:
- 长度 30-100 字(中文);
- 必须包含「思路」「第一步」或等价引导词;
- 不要围栏、不要解释,只输出改进后的模板文本。"""


def edit_template(current: str, failure_frames: list[dict], gateway: Gateway) -> str:
    """一次 gateway 调用:当前模板 + 失败帧浓缩 → 变体;带 lint。
    
    Lint:必须保住核心引导词(「思路」「第一步」),防进化出废模板。
    角色:judge_independent(DeepSeek 直评,spike 复用,不加新角色)。
    """
    failure_summary = "\n".join(
        f"- {f['case_id']}: {f['kind']} — {f['detail'][:100]}"
        for f in failure_frames[:5]  # 浓缩前 5 个失败
    ) if failure_frames else "(无失败案例)"
    
    prompt = _EDITOR_PROMPT.format(current=current, n_failures=len(failure_frames), failure_summary=failure_summary)
    
    request = ModelRequest(
        role="judge_independent",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        temperature=0.3,
    )
    
    try:
        response = gateway.invoke(request)
        variant = response.text.strip().strip("`").strip()
    except GatewayError:
        return current  # 编辑失败,保守保留当前
    
    # Lint
    if len(variant) < 30 or len(variant) > 100:
        return current
    if "思路" not in variant and "第一步" not in variant and "从头" not in variant:
        return current
    if variant == current:
        return current
    
    return variant


# === 5. 选择 + 种群 ===

@dataclass
class Candidate:
    template: str
    parent_id: int | None = None
    round_idx: int = 0
    candidate_id: int = 0


@dataclass
class Population:
    candidates: list[Candidate] = field(default_factory=list)
    _next_id: int = 0
    
    def add(self, candidate: Candidate) -> int:
        candidate.candidate_id = self._next_id
        self.candidates.append(candidate)
        self._next_id += 1
        return candidate.candidate_id
    
    def select_parent(self, scores: dict[int, ScoreVector]) -> Candidate:
        """选最高 mean_score 的候选;硬失败候选不能成为最优(有非硬失败候选时)。
        
        外审确定性探针坐实:12 分 + 泄答案不可胜过 11 分合格。
        """
        clean = [c for c in self.candidates if scores[c.candidate_id].hard_failure_rate == 0]
        pool = clean if clean else self.candidates
        return max(pool, key=lambda c: scores[c.candidate_id].mean_score)


# === 6. 循环驱动 ===

@dataclass(frozen=True)
class GepaConfig:
    """GEPA 循环配置:轮数 / 批次大小 / 预算上限。"""
    rounds: int = 6
    batch_size: int = 16
    max_calls: int = 2000
    judge_role: str = "judge_independent"


@dataclass
class Budget:
    max_calls: int = 2000
    calls: int = 0
    rounds: int = 0
    wall_start: float = field(default_factory=time.monotonic)
    
    def exhausted(self) -> bool:
        return self.calls >= self.max_calls
    
    def add(self, calls: int) -> None:
        self.calls += calls
    
    def summary(self) -> dict:
        return {
            "calls": self.calls,
            "rounds": self.rounds,
            "wall_s": time.monotonic() - self.wall_start,
            "exhausted": self.exhausted(),
        }


def gepa_loop(
    train_cases: list[dict],
    initial_template: str,
    config: GepaConfig,
    gateway: Gateway,
    output_dir: Path,
) -> tuple[Population, dict[int, ScoreVector], list[dict]]:
    """GEPA 主循环:轮数 / 预算计数 / 停止;每轮 dump prompt diff + 分数。
    
    返回:(population, scores, round_reports)。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    population = Population()
    scores: dict[int, ScoreVector] = {}
    round_reports: list[dict] = []
    budget = Budget(max_calls=config.max_calls)
    
    # 初始候选
    initial = Candidate(template=initial_template)
    initial_id = population.add(initial)
    
    # 评估初始
    initial_scores, last_failures, initial_stats = evaluate_batch(
        train_cases[:config.batch_size], initial_template, gateway, config.judge_role)
    scores[initial_id] = initial_scores
    budget.add(initial_stats["calls"])
    
    for round_idx in range(config.rounds):
        if budget.exhausted():
            break
        
        budget.rounds += 1
        batch = sample_batch(train_cases, config.batch_size, seed=round_idx)
        
        # 选父代
        parent = population.select_parent(scores)
        parent_scores = scores[parent.candidate_id]
        
        # 编辑模板:传入上一轮的失败(首轮传 initial 的,后续传上一变体的)
        # 修 P2-1:原始终传 initial_failures,编辑器看不到变体自身的失败模式
        variant_template = edit_template(parent.template, last_failures, gateway)
        budget.add(1)
        
        # No-op 检查:编辑器返回与父代逐字相同 → 跳过评估,省预算
        is_noop = (variant_template == parent.template)
        
        # 评估变体
        variant = Candidate(
            template=variant_template,
            parent_id=parent.candidate_id,
            round_idx=round_idx,
        )
        variant_id = population.add(variant)
        if is_noop:
            variant_scores = parent_scores
            variant_failures = []
            variant_stats = {"calls": 0, "tokens_in": 0, "tokens_out": 0,
                             "env_failures": 0, "content_failures": 0, "wall_ms": 0}
            scores[variant_id] = variant_scores
            # no-op 时 last_failures 保留上一轮,下轮编辑器继续用
        else:
            variant_scores, variant_failures, variant_stats = evaluate_batch(
                batch, variant_template, gateway, config.judge_role)
            scores[variant_id] = variant_scores
            budget.add(variant_stats["calls"])
            last_failures = variant_failures
        
        # 选择:simplified Pareto
        accepted = False if is_noop else variant_scores.dominates(parent_scores)
        
        # dump round report
        report = {
            "round": round_idx,
            "parent_id": parent.candidate_id,
            "variant_id": variant_id,
            "parent_template": parent.template,
            "variant_template": variant_template,
            "noop": is_noop,
            "parent_scores": parent_scores.__dict__,
            "variant_scores": variant_scores.__dict__,
            "accepted": accepted,
            "diff": list(unified_diff(
                parent.template.splitlines(keepends=True),
                variant_template.splitlines(keepends=True),
                fromfile="parent",
                tofile="variant",
            )),
            "stats": variant_stats,
            "failures": variant_failures,
        }
        round_reports.append(report)
        (output_dir / f"round-{round_idx:02d}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # 最终报告
    summary = {
        "budget": budget.summary(),
        "population_size": len(population.candidates),
        "accepted_variants": sum(1 for r in round_reports if r["accepted"]),
        "best_candidate": max(population.candidates, key=lambda c: scores[c.candidate_id].mean_score).__dict__,
        "best_scores": scores[max(population.candidates, key=lambda c: scores[c.candidate_id].mean_score).candidate_id].__dict__,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    
    return population, scores, round_reports


def _validate_hard_fail(paired_cases: list[dict]) -> str:
    """硬失败筛选验证:硬失败变体不可胜出(对齐 #296 dominates 原则)。
    
    若变体存在硬失败(answer_leaked 或 verdict=fail)→ 必须 blocked。
    无「acceptable」分支:硬失败候选不能成为最优,无条件。
    """
    has_leaked = any(c.get("variant_hard_fail") for c in paired_cases if "error" not in c)
    if not has_leaked:
        return "pass (no leaked variant)"
    return "blocked (variant has hard_fail)"


def _build_paired_cases(
    parent_scores: list[dict],
    variant_scores: list[dict],
    parent_fqs: list[dict],
    variant_fqs: list[dict],
    initial_template: str,
    variant_template: str,
) -> list[dict]:
    """逐案配对 Δ + 首问对比(含空转检测)。"""
    paired_cases = []
    for i, (p, v) in enumerate(zip(parent_scores, variant_scores, strict=True)):
        if "error" in p or "error" in v:
            paired_cases.append({
                "case_id": p.get("case_id", v.get("case_id", "")),
                "error": p.get("error") or v.get("error"),
            })
            continue
        p_fq = parent_fqs[i].get("first_question", "") if i < len(parent_fqs) else ""
        v_fq = variant_fqs[i].get("first_question", "") if i < len(variant_fqs) else ""
        is_idle = (p_fq == v_fq and p_fq != "")
        paired_cases.append({
            "case_id": p["case_id"],
            "parent_total": p.get("total", 0),
            "variant_total": v.get("total", 0),
            "delta": v.get("total", 0) - p.get("total", 0),
            "parent_verdict": p.get("verdict"),
            "variant_verdict": v.get("verdict"),
            "parent_hard_fail": p.get("hard_fail", False),
            "variant_hard_fail": v.get("hard_fail", False),
            "parent_first_question": p_fq,
            "variant_first_question": v_fq,
            "template_text_in_variant_first_question": initial_template in v_fq or variant_template in v_fq,
            "idle": is_idle,
        })
    return paired_cases


def _compute_paired_verdict(all_deltas: list[int | float]) -> str:
    """判定逻辑(冻结协议):Δ≈0→红灯;稳定非零多数同向→GO;否则→mixed。"""
    nonzero = [d for d in all_deltas if d != 0]
    if abs(sum(all_deltas) / len(all_deltas)) < 0.5 and len(nonzero) == 0:
        return "红灯"
    if len(nonzero) <= len(all_deltas) / 2:
        return "mixed"
    mean = sum(all_deltas) / len(all_deltas)
    if abs(mean) < 0.5:
        return "mixed"
    same_sign = all(d > 0 for d in nonzero) or all(d < 0 for d in nonzero)
    return "GO" if same_sign else "mixed"


def paired_loop(
    cases: list[dict],
    initial_template: str,
    config: GepaConfig,
    gateway: Gateway,
    output_dir: Path,
) -> list[dict]:
    """配对实验:固定批次(全案例不重采样),逐案对比 parent vs variant。
    
    返回:paired_reports (每轮一个 report,含 per-case Δ)。
    输出:round-*.json + paired-report.json(逐案配对对比)。
    
    验证项:
    1. 编辑器反馈:日志记录传给 edit_template 的 failure_frames
    2. 硬失败筛选:断言无泄答案候选胜出
    3. 模板命中:逐案核对 elicit 模板真塑造 tutor 首问
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    budget = Budget(max_calls=config.max_calls)
    paired_reports: list[dict] = []
    
    facts_dir = gateway.writer.root
    facts_before = _count_facts_lines(facts_dir)
    
    # 跑 parent (全案例)
    parent_scores, parent_fqs, parent_stats = evaluate_batch_paired(
        cases, initial_template, gateway, config.judge_role)
    budget.add(parent_stats["calls"])
    budget.rounds += 1
    
    # 收集 parent 失败(供首轮编辑器,用完整 failure frames)
    parent_failures = []
    for s in parent_scores:
        if "error" not in s and (s.get("hard_fail") or s.get("total", 12) < 10):
            parent_failures.append({
                "case_id": s["case_id"],
                "kind": "judge_low_score",
                "detail": f"total={s.get('total', '?')}, verdict={s.get('verdict', '?')}, hard_fail={s.get('hard_fail', False)}",
            })
    
    for round_idx in range(config.rounds):
        if budget.exhausted():
            break
        
        # 编辑模板
        variant_template = edit_template(initial_template, parent_failures, gateway)
        budget.add(1)
        
        # No-op 检查
        is_noop = (variant_template == initial_template)
        
        # 跑 variant (同批全案例)
        if is_noop:
            variant_scores, variant_fqs = parent_scores, parent_fqs
            variant_stats = {"calls": 0, "tokens_in": 0, "tokens_out": 0,
                             "env_failures": 0, "content_failures": 0, "wall_ms": 0}
        else:
            variant_scores, variant_fqs, variant_stats = evaluate_batch_paired(
                cases, variant_template, gateway, config.judge_role)
            budget.add(variant_stats["calls"])
        budget.rounds += 1
        
        # 逐案配对 Δ + 首问对比
        paired_cases = _build_paired_cases(
            parent_scores, variant_scores, parent_fqs, variant_fqs,
            initial_template, variant_template,
        )
        
        # 模板命中验证(逐案,非抽样)
        template_hit_count = sum(1 for c in paired_cases if c.get("template_text_in_variant_first_question"))
        idle_count = sum(1 for c in paired_cases if c.get("idle"))
        
        report = {
            "round": round_idx,
            "parent_template": initial_template,
            "variant_template": variant_template,
            "noop": is_noop,
            "parent_stats": parent_stats,
            "variant_stats": variant_stats,
            "paired_cases": paired_cases,
            "hard_fail_validation": _validate_hard_fail(paired_cases),
            "template_hit_validation": {
                "hit_count": template_hit_count,
                "idle_count": idle_count,
                "total_cases": len(paired_cases),
            },
            "editor_feedback_sample": parent_failures[:3] if parent_failures else [],
        }
        paired_reports.append(report)
        (output_dir / f"round-{round_idx:02d}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # facts 实测总计数
    facts_after = _count_facts_lines(facts_dir)
    real_calls = facts_after - facts_before
    tokens_in, tokens_out = _sum_facts_tokens(facts_dir, facts_before)
    
    # 最终配对报告
    all_deltas = [
        c["delta"] for r in paired_reports for c in r["paired_cases"] if "error" not in c
    ]
    mean_delta = sum(all_deltas) / len(all_deltas) if all_deltas else 0.0
    
    # 判定(冻结协议)
    verdict = _compute_paired_verdict(all_deltas)
    
    # 超预算检测
    over_budget = real_calls > config.max_calls
    
    paired_summary = {
        "budget": budget.summary(),
        "real_calls": real_calls,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "total_paired_cases": len(all_deltas),
        "mean_delta": mean_delta,
        "deltas": all_deltas,
        "verdict": verdict,
        "over_budget": over_budget,
    }
    (output_dir / "paired-report.json").write_text(
        json.dumps(paired_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    
    return paired_reports

