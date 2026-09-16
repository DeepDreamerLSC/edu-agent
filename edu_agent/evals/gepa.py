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
from functools import partial
from pathlib import Path

from edu_agent.agents.small_lecturer import kernel
from edu_agent.gateway import Gateway, GatewayError, ModelRequest

from .corpus_round import transcript_messages
from .judge import judge_transcript
from .kernel_subject import KernelSubject
from .runner import EnvironmentFailure


# === 1. Prompt seam:旋钮变体注入 ===

# 搜索空间(#304 频次分析头部可达旋钮):elicit 复讲 + support 拆小问句。
# support 是 v2 训练池上唯一有数据面触发信号的旋钮(1/8 案 stuck 信号);
# reveal 依赖阶梯消耗状态、answer_collect 双前提缺失,不进此版搜索空间。
KNOB_SEAMS = ("_ELICIT_TEMPLATE", "_SUPPORT_HINT")

# kernel 默认 support 拆小问句(#198 确定性文本)——变体经 edit_two_knobs 生成
DEFAULT_SUPPORT_HINT = (
    "我们把这一步拆小:先不想整道题,你只看这一步里最小的一个数,从它开始你觉得能先算出什么?想到多少说多少。"
)



class ElicitSubject:
    """KernelSubject 包装:run_case 注入旋钮变体(monkeypatch,用完即恢复)。

    纪律:不动 kernel.py 常量;monkeypatch 是 spike 最小缝合面,生产化须外置。
    variants 键 = kernel 常量名(KNOB_SEAMS 子集);未提供变体的旋钮用 kernel 原值。
    """

    def __init__(self, template: str, gateway: Gateway,
                 support_hint: str | None = None) -> None:
        self.template = template
        self.gateway = gateway
        self.variants: dict[str, str] = {"_ELICIT_TEMPLATE": template}
        if support_hint is not None:
            self.variants["_SUPPORT_HINT"] = support_hint
        self._kernel_subject = KernelSubject(gateway)

    @property
    def name(self) -> str:
        return f"elicit-{hash(self.template) % 10000:04d}"

    def get_active_template(self) -> str:
        """获取当前激活的 elicit 模板(测试用,验证 monkeypatch 生效)。"""
        return kernel._ELICIT_TEMPLATE

    def get_active_support_hint(self) -> str:
        """当前激活的 support 拆小问句(测试用,seam 生效性验证)。"""
        return kernel._SUPPORT_HINT

    def run_case(self, case: dict) -> dict:
        saved = {name: getattr(kernel, name) for name in self.variants}
        try:
            for name, value in self.variants.items():
                setattr(kernel, name, value)
            return self._kernel_subject.run_case(case)
        finally:
            for name, value in saved.items():
                setattr(kernel, name, value)


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
    judge_role: str = "judge",
    support_hint: str | None = None,
) -> tuple[ScoreVector, list[dict], dict]:
    """跑批 + 判卷一步到位(calls = facts 实测,长跑口径:估算低估 ~3x 会超预算)。

    返回:(score_vector, failure_frames, stats)。
    stats = {calls, tokens_in, tokens_out, wall_ms, env_failures, content_failures}。
    """
    started = time.monotonic()
    facts_dir = gateway.writer.root
    facts_before = _count_facts_lines(facts_dir)
    subject = ElicitSubject(template, gateway, support_hint=support_hint)
    
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
    # facts 实测(01 §7,长跑口径):一案 = start+reply×N+finish + judge ≈ 4.23 调用,
    # 估算 len+judged 低估 ~3x,硬限预算必须用真实计数(paired_loop 同款)。
    stats["calls"] = _count_facts_lines(facts_dir) - facts_before
    
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
    judge_role: str = "judge",
) -> tuple[list[dict], list[dict], dict]:
    """配对实验:逐案跑 + 逐案判,返回 per-case scores 和转录快照。
    
    返回:(per_case_scores, snapshots, stats)。
    per_case_scores = [{case_id, total, verdict, leaked, mi, hard_fail}, ...]
    snapshots = [{case_id, first_question, tutor_turns, template_in_transcript}, ...]
      - first_question 来自 turns[0].tutor(transcript 无 first_question 键)
      - tutor_turns = 全部 tutor 轮文本(空转全转录扫描证据)
      - template_in_transcript = 模板文本是否出现在任意 tutor 轮(review-303-rerun:
        elicit 模板经 _ask_restatement 确定性注入后轮,首问扫描会漏检 → 全转录扫描)
    stats = {calls, tokens_in, tokens_out, wall_ms, env_failures, content_failures}
    
    调用计数:从 facts ledger 实测,不硬编码(01 §7)。
    """
    started = time.monotonic()
    subject = ElicitSubject(template, gateway)
    
    facts_dir = gateway.writer.root
    facts_before = _count_facts_lines(facts_dir)
    
    per_case_scores = []
    snapshots = []
    stats = {"calls": 0, "tokens_in": 0, "tokens_out": 0, "env_failures": 0, "content_failures": 0}
    
    for case in cases:
        try:
            transcript = subject.run_case(case)
            # 首问来自 turns[0].tutor(transcript 无 first_question 键)
            turns = transcript.get("turns", [])
            first_q = turns[0]["tutor"] if turns else ""
            tutor_turns = [t.get("tutor", "") for t in turns]
            snapshots.append({
                "case_id": case.get("id", ""),
                "first_question": first_q,
                "tutor_turns": tutor_turns,
                "template_in_transcript": template in "\n".join(tutor_turns),
            })
            
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
    return per_case_scores, snapshots, stats


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


def edit_template(current: str, failure_frames: list[dict], gateway: Gateway,
                  role: str = "judge_independent") -> str:
    """一次 gateway 调用:当前模板 + 失败帧浓缩 → 变体;带 lint。
    
    Lint:必须保住核心引导词(「思路」「第一步」),防进化出废模板。
    角色:judge_independent(DeepSeek 直评,spike 复用,不加新角色)。
    三键裁决(2026-09-17,PM sha256=d7256fcc631e69e7)保留:编辑器非判分,
    走 judge_independent 属设计内(用户已追认);判分入口默认已改 "judge"
    (本地 mlx_27b 主选),judge_independent 留 #32 平行评分用途。
    """
    failure_summary = "\n".join(
        f"- {f['case_id']}: {f['kind']} — {f['detail'][:100]}"
        for f in failure_frames[:5]  # 浓缩前 5 个失败
    ) if failure_frames else "(无失败案例)"
    
    prompt = _EDITOR_PROMPT.format(current=current, n_failures=len(failure_frames), failure_summary=failure_summary)
    
    request = ModelRequest(
        role=role,
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
    """GEPA 循环配置:轮数 / 批次大小 / 预算上限 / 搜索空间旋钮族。"""
    rounds: int = 6
    batch_size: int = 16
    max_calls: int = 2000
    judge_role: str = "judge"
    two_knobs: bool = False  # True = elicit+support 双旋钮(#304 头部可达族,选项 A)
    editor_focus: str = "mean"  # "nr" = needs_review 靶向编辑(收敛#2 选项①)
    editor_role: str = "judge_independent"  # 编辑器后端(搜索机械件,非冻结判分面)


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


write_checkpoint = None  # 前向占位(定义后底部绑定公开名)


def _write_checkpoint(output_dir: Path, state: "LoopState",
                      next_round: int = 0, last_failures: list[dict] | None = None) -> None:
    """每代落盘断点(长跑跨夜:最优解+预算+代次+失败帧,进程挂掉可恢复)。"""
    population, scores = state.population, state.scores
    budget = state.bind(0)
    best = population.select_parent(scores)  # 返回 Candidate 对象本身
    payload = {
        "next_round": next_round,
        "budget": budget.summary(),
        "best": {"candidate_id": best.candidate_id, "template": best.template,
                 "support_hint": state.support_hint,
                 "scores": scores[best.candidate_id].__dict__},
        "last_failures": (last_failures or [])[:5],
    }
    tmp = output_dir / "checkpoint.json.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(output_dir / "checkpoint.json")




@dataclass
class LoopState:
    """gepa_loop 的语境束(断点恢复原语 + 循环常量,helper 只传一参)。"""

    train_cases: list = field(default_factory=list)
    initial_template: str = ""
    support_hint: str = DEFAULT_SUPPORT_HINT
    population: Population = field(default_factory=Population)
    scores: dict = field(default_factory=dict)
    budget: "Budget | None" = None

    def bind(self, max_calls: int) -> "Budget":
        if self.budget is None:
            self.budget = Budget(max_calls=max_calls)
        return self.budget


def _restore_or_seed(
    config: "GepaConfig",
    gateway: Gateway,
    output_dir: Path,
    resume: bool,
    state: LoopState,
) -> tuple[int, list[dict]]:
    """恢复或播种种群起点;返回(起始代次, 初始失败帧)。

    恢复:最优候选入种群、预算与代次延续、失败帧带回、不重评初始(省预算;
    种子 = round_idx 确定性,恢复后同代同批)。全新:评估初始模板并写 checkpoint。
    """
    population, scores = state.population, state.scores
    budget = state.bind(config.max_calls)
    checkpoint_path = output_dir / "checkpoint.json"
    if resume and checkpoint_path.exists():
        saved = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        restored = Candidate(template=saved["best"]["template"])
        restored_id = population.add(restored)
        scores[restored_id] = ScoreVector(**saved["best"]["scores"])
        budget.calls = saved["budget"]["calls"]
        if saved.get("support_hint"):
            state.support_hint = saved["support_hint"]
        budget.rounds = saved["budget"]["rounds"]
        print(f"[resume] 从 checkpoint 恢复:round={saved['next_round']}, "
              f"budget={budget.calls}/{budget.max_calls}, "
              f"best_mean={scores[restored_id].mean_score:.2f}")
        return saved["next_round"], saved.get("last_failures", [])
    initial_id = population.add(Candidate(template=state.initial_template))
    initial_scores, failures, initial_stats = evaluate_batch(
        state.train_cases[:config.batch_size], state.initial_template,
        gateway, config.judge_role)
    scores[initial_id] = initial_scores
    budget.add(initial_stats["calls"])
    _write_checkpoint(output_dir, state)
    return 0, failures


def gepa_loop(
    train_cases: list[dict],
    initial_template: str,
    config: GepaConfig,
    gateway: Gateway,
    output_dir: Path,
    resume: bool = True,
) -> tuple[Population, dict[int, ScoreVector], list[dict]]:
    """GEPA 主循环:轮数 / 预算计数 / 停止;每轮 dump prompt diff + 分数 + checkpoint。

    resume=True 且 output_dir 存在 checkpoint.json 时恢复:最优候选作为种群起点、
    预算余量与代次延续(种子 = round_idx,确定性,恢复后同代同批)。
    返回:(population, scores, round_reports)。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    state = LoopState(train_cases=train_cases, initial_template=initial_template)
    population, scores = state.population, state.scores
    budget = state.bind(config.max_calls)
    round_reports: list[dict] = []
    start_round, last_failures = _restore_or_seed(
        config, gateway, output_dir, resume, state)

    for round_idx in range(start_round, config.rounds):
        if budget.exhausted():
            break
        
        budget.rounds += 1
        batch = sample_batch(train_cases, config.batch_size, seed=round_idx)
        
        # 选父代
        parent = population.select_parent(scores)
        parent_scores = scores[parent.candidate_id]
        
        # 编辑模板:传入上一轮的失败(首轮传 initial 的,后续传上一变体的)
        # 修 P2-1:原始终传 initial_failures,编辑器看不到变体自身的失败模式
        editors = (
            partial(edit_template_nr if config.editor_focus == "nr" else edit_template,
                    role=config.editor_role),
            partial(edit_support_hint, role=config.editor_role),
        )
        if config.two_knobs:
            variant_template, state.support_hint = edit_two_knobs(
                parent.template, state.support_hint, round_idx, last_failures, gateway,
                editors=editors)
        else:
            variant_template = editors[0](parent.template, last_failures, gateway)
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
                batch, variant_template, gateway, config.judge_role,
                support_hint=state.support_hint if config.two_knobs else None)
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
            "support_hint": getattr(state, "support_hint", None),
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
        _write_checkpoint(output_dir, state, round_idx + 1, last_failures)

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
    parent_snaps: list[dict],
    variant_snaps: list[dict],
    initial_template: str,
    variant_template: str,
) -> list[dict]:
    """逐案配对 Δ + 全转录空转扫描(review-303-rerun P1-5)。

    空转判定改全转录口径:elicit 模板经 _ask_restatement(kernel.py 确定性零模型
    调用)注入**后续轮**,首问(start() 生成)不含模板——只扫 turns[0] 会漏检。
    - variant_template_in_transcript: 变体模板是否出现在变体转录任意 tutor 轮
      (False = 模板未注入 → 空转,该案 Δ 对 judge 敏感度零信息量)
    - transcripts_identical: parent/variant 转录逐字相同(空转辅证)
    """
    paired_cases = []
    for i, (p, v) in enumerate(zip(parent_scores, variant_scores, strict=True)):
        if "error" in p or "error" in v:
            paired_cases.append({
                "case_id": p.get("case_id", v.get("case_id", "")),
                "error": p.get("error") or v.get("error"),
            })
            continue
        p_snap = parent_snaps[i] if i < len(parent_snaps) else {}
        v_snap = variant_snaps[i] if i < len(variant_snaps) else {}
        p_turns = p_snap.get("tutor_turns", [])
        v_turns = v_snap.get("tutor_turns", [])
        p_fq = p_snap.get("first_question", "")
        v_fq = v_snap.get("first_question", "")
        variant_in_transcript = v_snap.get(
            "template_in_transcript", variant_template in "\n".join(v_turns))
        parent_in_transcript = p_snap.get(
            "template_in_transcript", initial_template in "\n".join(p_turns))
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
            "parent_template_in_transcript": parent_in_transcript,
            "variant_template_in_transcript": variant_in_transcript,
            "transcripts_identical": p_turns == v_turns and bool(p_turns),
            "idle": not variant_in_transcript,  # 全转录口径:模板未注入 = 空转
        })
    return paired_cases


def _compute_paired_verdict(
    all_deltas: list[int | float], idle_detected: bool = False,
) -> str:
    """判定逻辑(冻结协议,review-303-rerun P1-1 修正):

    - 空转(idle)→ **无效跑**(冻结前提:空转 = 无效,Δ 对 judge 敏感度
      零信息量——转录全同 + judge temp=0 确定性,Δ=0 只复述确定性,不测得敏感度)
    - Δ≈0 → 红灯
    - 稳定非零多数同向 → GO;否则 mixed
    """
    if idle_detected:
        return "无效跑"
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
    3. 模板命中:全转录扫描核对 elicit 模板真注入转录(经 _ask_restatement 后轮)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    budget = Budget(max_calls=config.max_calls)
    paired_reports: list[dict] = []
    
    facts_dir = gateway.writer.root
    facts_before = _count_facts_lines(facts_dir)
    
    # 跑 parent (全案例)
    parent_scores, parent_snaps, parent_stats = evaluate_batch_paired(
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
            variant_scores, variant_snaps = parent_scores, parent_snaps
            variant_stats = {"calls": 0, "tokens_in": 0, "tokens_out": 0,
                             "env_failures": 0, "content_failures": 0, "wall_ms": 0}
        else:
            variant_scores, variant_snaps, variant_stats = evaluate_batch_paired(
                cases, variant_template, gateway, config.judge_role)
            budget.add(variant_stats["calls"])
        budget.rounds += 1
        
        # 逐案配对 Δ + 全转录空转扫描
        paired_cases = _build_paired_cases(
            parent_scores, variant_scores, parent_snaps, variant_snaps,
            initial_template, variant_template,
        )
        
        # 模板命中验证(全转录扫描,逐案)
        template_hit_count = sum(1 for c in paired_cases if c.get("variant_template_in_transcript"))
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
    
    # 判定(冻结协议):空转 → 无效跑(override,先于 Δ 分支)
    idle_detected = any(c.get("idle") for r in paired_reports for c in r["paired_cases"])
    verdict = _compute_paired_verdict(all_deltas, idle_detected=idle_detected)
    
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
        "idle_detected": idle_detected,
        "verdict": verdict,
        "over_budget": over_budget,
    }
    (output_dir / "paired-report.json").write_text(
        json.dumps(paired_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    
    return paired_reports


write_checkpoint = _write_checkpoint  # 公开名(tests 只导公开入口,02 §6)


_SUPPORT_EDITOR_PROMPT = """你是一个提示词编辑器。当前「卡壳支持」问句模板:
---
{current}
---
失败案例摘要(共 {n_failures} 个):
{failure_summary}

任务:生成改进版本,保持核心意图(学生卡住时把这一步拆成最小的一个小问题、只问不揭示、
不含答案数字),但调整措辞以降低失败率。约束:
- 长度 20-70 字(中文);
- 必须是问句且以问号结尾;
- 不出现任何数字或方法名;
- 不要围栏、不要解释,只输出改进后的模板文本。"""


_NR_EDITOR_PROMPT = """你是一个提示词编辑器。当前复讲引导模板:
---
{current}
---
以下案例被评审判为 review(学习证据不足,无法确认掌握):
{failure_summary}

任务:调整模板措辞,让学生复讲时更容易给出**可判定的回答**——明确请他说出
具体步骤、算式或结论(而不是"说说想法"这类开放邀请),使评审能据以判定。
约束:
- 长度 30-100 字(中文);
- 必须包含「思路」「第一步」或「算式/步骤」等价引导词;
- 不要围栏、不要解释,只输出改进后的模板文本。"""


def edit_template_nr(current: str, failure_frames: list[dict], gateway: Gateway,
                      role: str = "judge_independent") -> str:
    """needs_review 靶向编辑(收敛#2 选项①准备件):与 edit_template 同 lint 同角色,
    唯一差异是指令瞄准 nr 维——让复讲引导产出可判定证据,而非更讨喜的开放邀请。"""
    failure_summary = "\n".join(
        f"- {f['case_id']}: {f['kind']} — {f['detail'][:100]}"
        for f in failure_frames[:5]
    ) if failure_frames else "(无失败案例)"
    prompt = _NR_EDITOR_PROMPT.format(current=current, failure_summary=failure_summary)
    try:
        response = gateway.invoke(ModelRequest(
            role=role, messages=[{"role": "user", "content": prompt}],
            max_tokens=200, temperature=0.3))
        variant = response.text.strip().strip("`").strip()
    except GatewayError:
        return current
    linted = _lint_common(variant, current, 30, 100, ("思路", "第一步", "算式", "步骤"))
    return variant if linted is not None else current


def _lint_common(variant: str, current: str, floor: int, cap: int,
                 keywords: tuple[str, ...]) -> str | None:
    """共享 lint:长度窗、关键词、非退化;不合规返回 None(调用方保留父代)。"""
    if variant == current or not (floor <= len(variant) <= cap):
        return None
    if not any(word in variant for word in keywords):
        return None
    return variant


def edit_support_hint(support: str, failure_frames: list[dict], gateway: Gateway,
                      role: str = "judge_independent") -> str:
    """「卡壳支持」问句编辑(双旋钮的 support 分支):lint 不过保留父代。"""
    failure_summary = "\n".join(
        f"- {f['case_id']}: {f['kind']} — {f['detail'][:100]}"
        for f in failure_frames[:5]
    ) if failure_frames else "(无失败案例)"
    prompt = _SUPPORT_EDITOR_PROMPT.format(
        current=support, n_failures=len(failure_frames), failure_summary=failure_summary)
    try:
        response = gateway.invoke(ModelRequest(
            role=role, messages=[{"role": "user", "content": prompt}],
            max_tokens=160, temperature=0.3))
        raw = response.text.strip().strip("`").strip()
    except GatewayError:
        return support
    linted = _lint_common(raw, support, 20, 70, ("?", "?"))
    return linted if linted is not None else support


def edit_two_knobs(
    elicit: str, support: str, round_idx: int,
    failure_frames: list[dict], gateway: Gateway,
    editors=None,
) -> tuple[str, str]:
    """双旋钮编辑(#256 阶段 2 选项 A 搜索空间):偶代编辑 elicit、奇代编辑 support。

    单次 gateway 调用(编辑器预算 1 call/代不变);被编辑旋钮拿失败帧反馈,
    另一旋钮原样保留。lint 失败保留父代(与 edit_template 同纪律)。
    editors=(elicit编辑器, support编辑器);None 时晚绑定默认对(保持可 patch)。
    """
    if editors is None:
        editors = (edit_template, edit_support_hint)
    elicit_editor, support_editor = editors
    if round_idx % 2 == 0:
        return elicit_editor(elicit, failure_frames, gateway), support
    return elicit, support_editor(support, failure_frames, gateway)
