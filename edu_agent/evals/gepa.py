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
from dataclasses import asdict, dataclass, field
from difflib import unified_diff
from functools import partial
from pathlib import Path

from edu_agent.agents.small_lecturer import kernel
from edu_agent.gateway import Gateway, GatewayError
from .checks import text_excludes_answer_values
from .gepa_editors import (  # 编辑器族(#310 预算拆分:817/800 超限,要加就先删)
    edit_support_hint,
    edit_template,
    edit_template_nr,
    edit_two_knobs,
)

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


# #332 采样规格:信号族非存储字段,matcher 词形一手分类(复用 kernel 信号
# #332 采样规格:信号族非存储字段,matcher 词形一手分类(复用 kernel 信号
# 判据,与 knob-frequency 分类同款口径)。
_SIGNAL_STRATA = (
    ("understanding", kernel._student_signals_understanding),
    ("stuck", kernel._student_signals_stuck),
    ("completion", kernel._student_signals_completion),
)

# #335 采样源接通:信号族源 = #327 富集集(彩排实测 v2 93 池词形 0u/2s/0c,
# 规格的「自富化 12 案」从未接到真实语料路径;enriched12 就为此造)。
ENRICHED12_PATH = Path(__file__).resolve().parent / "datasets" / \
    "small_lecturer_image_teaching_v2_enriched12.json"


def load_enriched12() -> list[dict]:
    """加载 #327 富集 12 案(4u/4s/2c 词形可认 + 2 answerhit 词形归背景)。

    answerhit 2 案的完成表达带答案数字,kernel 设计先判答案命中分支,
    词形函数不重复计(#198 口径)——分层抽取按词形一手分类,它们不进
    信号层(completion 层词形可认 2 案,取满即 2)。
    """
    payload = json.loads(ENRICHED12_PATH.read_text(encoding="utf-8"))
    return [c for c in (payload.get("scenarios") or []) if isinstance(c, dict)]


def sample_stratified_batch(
    train_cases: list[dict], seed: int, *,
    per_stratum: int = 3, background: int = 7,
    enriched: "list[dict] | None | str" = "default",
) -> list[dict]:
    """#332+#335 分层采样:3u+3s+3c 自 enriched12 + 7 背景自 train 池。

    信号族源 = enriched(#327 富集集,词形一手分类后每层抽 per_stratum,
    层内不足取全部——completion 词形可认 2 案即取 2,批实际 3+3+2+7=15);
    背景自 train_cases 抽(排除批内已选 id,两源合批同一去重/洗牌逻辑)。
    enriched:"default"=加载 ENRICHED12_PATH 真文件(真实路径,防 fixture 绿
    真语料红);None=空(纯背景,退化旧语义);list=显式注入(单测)。
    """
    if enriched == "default":
        enriched = load_enriched12()
    elif enriched is None:
        enriched = []
    rng = random.Random(seed)
    strata: dict[str, list[dict]] = {name: [] for name, _ in _SIGNAL_STRATA}
    for case in enriched:
        turns = [t for t in case.get("student_turns") or [] if isinstance(t, str)]
        for name, fn in _SIGNAL_STRATA:
            if any(fn(t) for t in turns):
                strata[name].append(case)
                break
        # enriched 内词形无命中的案不进任何层也不冒充背景(信号源语义)
    picked: list[dict] = []
    for name, _ in _SIGNAL_STRATA:
        picked += rng.sample(strata[name], min(per_stratum, len(strata[name])))
    chosen_ids = {c.get("id") for c in picked}
    rest = [c for c in train_cases if c.get("id") not in chosen_ids]
    picked += rng.sample(rest, min(background, len(rest)))
    return picked


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


def _transcribe_with_net_a(
    subject: "ElicitSubject", cases: list[dict],
) -> tuple[list, list[dict], dict]:
    """转录循环 + Net A 逐案早停(#324 C-a/C-b)。

    每案转录生成后立即扫泄露网;命中 = 候选级硬否决,停整批后续评估
    (剩余案 Tutor 与全部 Judge 都不跑),失败转录保留在帧里。
    """
    transcripts = []
    failures = []
    stats = {"calls": 0, "tokens_in": 0, "tokens_out": 0, "env_failures": 0,
             "content_failures": 0, "tutor_calls": 0, "judge_calls": 0,
             "leak_net_violations": 0, "hard_vetoed": False}

    for case in cases:
        try:
            transcript = subject.run_case(case)
        except EnvironmentFailure as exc:
            failures.append({"case_id": case.get("id", ""), "kind": "environment", "detail": str(exc)})
            stats["env_failures"] += 1
            continue
        except Exception as exc:  # noqa: BLE001
            failures.append({"case_id": case.get("id", ""), "kind": "content", "detail": str(exc)})
            stats["content_failures"] += 1
            continue
        # Net A 逐案立即扫描:命中 = 候选级硬否决,停后续全部评估
        ok, why = text_excludes_answer_values({}, case, transcript)
        if not ok:
            stats["leak_net_violations"] += 1
            stats["hard_vetoed"] = True
            failures.append({
                "case_id": case.get("id", ""), "kind": "leak_net",
                "detail": why[:200],
                "transcript": transcript,  # 失败转录保留(#324 C1)
            })
            break
        transcripts.append((case, transcript))
    return transcripts, failures, stats


def evaluate_batch(
    cases: list[dict],
    template: str,
    gateway: Gateway,
    judge_role: str = "judge",
    support_hint: str | None = None,
) -> tuple[ScoreVector, list[dict], dict]:
    """跑批 + 判卷一步到位(calls = facts 实测,长跑口径:估算低估 ~3x 会超预算)。

    #324 C-a/C-b:每案转录生成后立即 Net A 扫描;命中 = 该候选硬否决,
    停整批后续评估(剩余案 Tutor 与全部 Judge 都不跑),失败转录保留在帧里。
    #324 C2:计量改 FactWriter 进程内计数器差值(跨 UTC 日/旁路 run 归属正确),
    分项 tutor_calls/judge_calls 之和 = 本批 facts 增量。

    返回:(score_vector, failure_frames, stats)。
    stats = {calls, tokens_in, tokens_out, wall_ms, env_failures, content_failures,
             tutor_calls, judge_calls, leak_net_violations, hard_vetoed}。
    """
    started = time.monotonic()
    writer = gateway.writer
    w0_count, w0_in, w0_out = writer.count, writer.tokens_in, writer.tokens_out
    subject = ElicitSubject(template, gateway, support_hint=support_hint)

    transcripts, failures, stats = _transcribe_with_net_a(subject, cases)

    scores = []
    needs_review = 0
    violations = 0
    hard_failures = 0
    judged = 0

    hnu_u = 0  # #332 U:verdict∈{fail,review} 案数
    if not stats["hard_vetoed"]:
        # tutor 臂分项 = 转录阶段 writer 增量
        stats["tutor_calls"] = writer.count - w0_count
        for case, transcript in transcripts:
            try:
                total, verdict, mi, is_hard_fail, low_frames = _score_one_case(
                    gateway, case, transcript, judge_role)
            except GatewayError as exc:
                failures.append({"case_id": case.get("id", ""), "kind": "judge_error", "detail": str(exc)})
                continue
            scores.append(total)
            hnu_u += verdict in ("fail", "review")
            judged += 1
            if verdict == "review" and not is_hard_fail:
                needs_review += 1  # 分子分母同口径(RULING#5):hard 案不计 nr
            if mi < 2:
                violations += 1
            if is_hard_fail:
                hard_failures += 1
            if low_frames:
                failures.extend(low_frames)
        # judge 臂分项 = 判卷阶段增量
        stats["judge_calls"] = writer.count - w0_count - stats["tutor_calls"]

    stats["wall_ms"] = int((time.monotonic() - started) * 1000)
    # facts 实测(#324 C2:进程内计数器,不用当天文件行数差——跨日/旁路归属正确)
    stats["calls"] = writer.count - w0_count
    stats["tokens_in"] = writer.tokens_in - w0_in
    stats["tokens_out"] = writer.tokens_out - w0_out

    if stats["hard_vetoed"]:
        # 硬否决批(#324 C1:提前失败不计全批成功):返回 hard-fail 向量,
        # gepa_loop 侧 leak_veto 不注册分数,候选永不可被选
        stats.update(h=stats["leak_net_violations"], n=0, u=len(transcripts) + 1,
                     mean=0.0)
        return ScoreVector(0.0, 1.0, 1.0, 1.0), failures, stats

    if not scores:
        stats.update(h=0, n=0, u=0, mean=0.0)
        return ScoreVector(0.0, 1.0, 1.0, 1.0), failures, stats

    mean_score = sum(scores) / len(scores)
    # #332 HNU 逐案计数:U = verdict∈{fail,review}(含 hard 案,合并口径——
    # fail→review 在 U 上中性,不再被 review 率误判退化);报告字段
    # needs_review_rate 等保留旧口径不动,仅接受判定换轨
    stats.update(
        h=hard_failures, n=violations,
        u=hnu_u,
        mean=mean_score)
    # nr 分母 = 非 hard 案(PM-RULING#5:fail 案不计 review,verdict 互斥使
    # hard 高的批 nr 虚低,四维独立 Pareto 对此盲);全 hard 时保守 1.0
    non_hard = judged - hard_failures
    return ScoreVector(
        mean_score=mean_score,
        needs_review_rate=needs_review / non_hard if non_hard else 1.0,
        numerical_violation_rate=violations / judged if judged else 1.0,
        hard_failure_rate=hard_failures / judged if judged else 1.0,
    ), failures, stats


# === 3.5 #332 接受函数:H/N/U 合并口径 + 单一阈值 ===

# 预注册工程阈值(#332 规格原表述,不许美化):0.125 = 16 案净增 2 分,
# 是预注册的工程阈值,不是测得的噪声边界,不证明总体教学效果提升
# (配对 null 实验实测 |Δ|≈0.0625,阈值≈2×观测配对噪声——工程裕度合理)。
ACCEPT_DELTA = 0.125

# 每 5 个评估候选共用同一批(#332 采样规格);换批时重评当前最优作初筛参考。
CANDIDATES_PER_BATCH = 5


@dataclass(frozen=True)
class HnuOutcome:
    """#332 逐案计数口径:H=hard fail 数;N=数值违规数(mi<2);
    U=verdict∈{fail,review} 案数(含 hard 案——U 合并替代 review 率单独
    比较,fail→review 在 U 上中性,不再被误判退化)。"""

    h: int
    n: int
    u: int
    mean: float

    def as_dict(self) -> dict:
        return asdict(self)


def hnu_from_stats(stats: dict) -> HnuOutcome:
    """探索/初筛批(evaluate_batch stats)→ HNU。"""
    return HnuOutcome(
        h=stats.get("h", 0), n=stats.get("n", 0), u=stats.get("u", 0),
        mean=stats.get("mean", 0.0))


def hnu_from_per_case(per_case_scores: list[dict]) -> HnuOutcome:
    """配对臂(evaluate_batch_paired per-case)→ HNU;error 案不计(结果不完整
    由调用方另行保守处理)。"""
    judged = [c for c in per_case_scores if "error" not in c]
    if not judged:
        return HnuOutcome(0, 0, 0, 0.0)
    return HnuOutcome(
        h=sum(1 for c in judged if c.get("hard_fail")),
        n=sum(1 for c in judged if c.get("mi", 2) < 2),
        u=sum(1 for c in judged if c.get("verdict") in ("fail", "review")),
        mean=sum(c["total"] for c in judged) / len(judged))


def accept_variant(parent: HnuOutcome, variant: HnuOutcome) -> tuple[bool, dict]:
    """#332 接受函数(替代四维 dominates 判定),规格块伪代码逐条:

        身份一致、同16案、结果完整,且通过泄露硬否决(调用方保证)。
        若新增 hard fail 案例:本次不替换,保留证据。
        若 H、N、U 任一增加:本次不替换。
        否则,满足任一才替换:
          ① 配对均值提升 ≥ 0.125;
          ② H、N、U 至少一项减少,且配对均值不下降。
        其余情况保留父代。

    返回 (accepted, 证据 dict);证据含拒绝原因,落 round report 留证。
    """
    ev = {"parent": parent.as_dict(), "variant": variant.as_dict(),
          "delta_mean": round(variant.mean - parent.mean, 6)}
    # 新增 hard fail 案(同批同案集配对口径 = H 增加):即使均值大涨也拒,留证
    if variant.h > parent.h:
        ev["decision"] = "new_hard_fail"
        return False, ev
    # (H 增已被上一支接住,这里只查 N/U)
    if variant.n > parent.n or variant.u > parent.u:
        ev["decision"] = "hnu_increase"
        return False, ev
    if ev["delta_mean"] >= ACCEPT_DELTA:
        ev["decision"] = "delta_ge_threshold"
        return True, ev
    if (variant.h < parent.h or variant.n < parent.n or variant.u < parent.u) \
            and ev["delta_mean"] >= 0:
        ev["decision"] = "hnu_reduced_mean_not_worse"
        return True, ev
    ev["decision"] = "keep_parent"
    return False, ev


# === 4. 反思编辑器 ===

# === 5. 选择 + 种群 ===

@dataclass
class Candidate:
    """#324 A-a:候选身份 = template + support_hint 完整组合(不只 template)。

    support_hint=None = 单旋钮模式;双旋钮模式下 support-only 改写是新候选,
    noop 判定与 checkpoint 归属都以完整组合为准。
    """
    template: str
    support_hint: str | None = None
    parent_id: int | None = None
    round_idx: int = 0
    candidate_id: int = 0


def search_identity(config: "GepaConfig", train_cases: list[dict]) -> str:
    """#324 A3 搜索身份指纹:配置/判据/案集/搜索参数,任一变化拒绝复用旧分数。

    命名避开 corpus_round.run_identity(切片运行身份,已有语义)。

    口径:rounds/max_calls 不算身份(续跑调大合法);判据 = judge SYSTEM_PROMPT
    哈希(rubric/dimension guide 任一改动即换身份);案集 = case id 序列
    ∪ enriched12 案 id(#335 采样源接通后批构成含富集案,采样域变化即换
    身份,拒复用旧分——保守方向)。
    """
    from hashlib import sha256

    from . import judge as judge_mod

    payload = {
        "judge_role": config.judge_role,
        "batch_size": config.batch_size,
        "two_knobs": config.two_knobs,
        "editor_focus": config.editor_focus,
        "editor_role": config.editor_role,
        "judge_prompt_sha": sha256(
            judge_mod.SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:16],
        "case_ids": sorted({c.get("id", "") for c in train_cases}
                           | {c.get("id", "") for c in load_enriched12()}),
    }
    return sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


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
        无分数候选 = 被否决未注册(Net A 泄露网 veto,#310)或未评估——不可选。
        """
        eligible = [c for c in self.candidates if c.candidate_id in scores]
        clean = [c for c in eligible if scores[c.candidate_id].hard_failure_rate == 0]
        pool = clean if clean else eligible
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
    """每代落盘断点(长跑跨夜:最优解+预算+代次+失败帧,进程挂掉可恢复)。

    #324 A-d:best 的 support_hint 取候选自身(不拼接顶层状态)。
    #324 A3:落运行身份指纹——恢复时任一不匹配拒绝复用旧分数。
    #324 C2:分项调用累计(tutor/judge/editor)跨恢复延续,不归零。
    """
    population, scores = state.population, state.scores
    budget = state.bind(0)
    # #332 选择器:best = 配对确认的当前最优(历史跨批池 max 不参与;
    # 兜底 select_parent 仅防 current_best 未初始化的异常路径)
    best = state.current_best or population.select_parent(scores)
    payload = {
        "next_round": next_round,
        "identity": state.run_id,
        "budget": budget.summary(),
        "best": {"candidate_id": best.candidate_id, "template": best.template,
                 "support_hint": best.support_hint,
                 "scores": scores[best.candidate_id].__dict__},
        "call_breakdown": dict(state.call_breakdown),
        # 失败帧瘦身:transcript 留在 round 报告,断点只留定位字段
        "last_failures": [
            {k: v for k, v in f.items() if k != "transcript"}
            for f in (last_failures or [])[:5]
        ],
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
    run_id: str = ""  # #324 A3 运行身份指纹(checkpoint 写/恢复核对)
    current_best: "Candidate | None" = None  # #332:只维护配对确认的当前最优
    # #332 循环状态(批管理;入语境束使 _process_round 只传一参)
    batch: list = field(default_factory=list)
    ref_outcome: "HnuOutcome | None" = None  # 当前批初筛参考(当前最优重评)
    cohort_idx: int = -1
    variant_evals: int = 0  # 非 noop 评估候选计数(每 5 候选同批)
    last_failures: list = field(default_factory=list)
    call_breakdown: dict = field(default_factory=lambda: {
        "tutor_calls": 0, "judge_calls": 0, "editor_calls": 0})  # #324 C2

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
) -> tuple[int, list[dict], bool]:
    """恢复或播种种群起点;返回(起始代次, 初始失败帧, 种子硬否决)。

    #324 A3 身份门:checkpoint 的 identity 与当前 run_identity 不符
    (配置/判据/案集/搜索参数任一变化,或旧格式无指纹)→ 拒绝复用旧分数,
    走全新路径(拒绝发生在任何模型调用前;旧模板要复用只能显式提取当种子)。
    #324 A-d:恢复完整组合(template+support_hint+score 均属同一 best 候选)。
    #324 C1:种子批 Net A 硬否决 → 返回 seed_vetoed,主循环停在开跑前。
    """
    population, scores = state.population, state.scores
    budget = state.bind(config.max_calls)
    checkpoint_path = output_dir / "checkpoint.json"
    if resume and checkpoint_path.exists():
        saved = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        saved_identity = saved.get("identity")
        if saved_identity != state.run_id:
            print(f"[resume] 拒绝恢复:身份不匹配(checkpoint={saved_identity!r}, "
                  f"当前={state.run_id!r})——判据/案集/搜索参数有变,旧分数不复用")
        else:
            best_saved = saved["best"]
            restored = Candidate(template=best_saved["template"],
                                 support_hint=best_saved.get("support_hint"))
            restored_id = population.add(restored)
            state.current_best = restored  # #332:恢复单一最优 lineage
            scores[restored_id] = ScoreVector(**best_saved["scores"])
            budget.calls = saved["budget"]["calls"]
            if restored.support_hint:
                state.support_hint = restored.support_hint
            budget.rounds = saved["budget"]["rounds"]
            state.call_breakdown.update(saved.get("call_breakdown", {}))
            print(f"[resume] 从 checkpoint 恢复:round={saved['next_round']}, "
                  f"budget={budget.calls}/{budget.max_calls}, "
                  f"best_mean={scores[restored_id].mean_score:.2f}")
            return saved["next_round"], saved.get("last_failures", []), False
    initial = Candidate(
        template=state.initial_template,
        support_hint=state.support_hint if config.two_knobs else None)
    initial_id = population.add(initial)
    state.current_best = initial  # #332:种子 = 初始最优(确认基线)
    # 初始批与代间批同分布(PM-RULING#5:文件序前缀有偏;#332 分层批
    # seed=0 与 cohort 0 批一致)
    initial_scores, failures, initial_stats = evaluate_batch(
        sample_stratified_batch(state.train_cases, 0), state.initial_template,
        gateway, config.judge_role,
        support_hint=state.support_hint if config.two_knobs else None)
    budget.add(initial_stats["calls"])
    state.call_breakdown["tutor_calls"] += initial_stats.get("tutor_calls", 0)
    state.call_breakdown["judge_calls"] += initial_stats.get("judge_calls", 0)
    if initial_stats.get("hard_vetoed"):
        # 种子硬失败(#324 C1):停在开跑前,初始分不注册(候选永不可被选)
        print("[seed] 初始模板 Net A 硬否决,run 终止(停在开跑前)")
        return 0, failures, True
    scores[initial_id] = initial_scores
    _write_checkpoint(output_dir, state)
    return 0, failures, False


def _edit_variant(
    config: "GepaConfig",
    state: "LoopState",
    parent: "Candidate",
    round_idx: int,
    last_failures: list[dict],
    gateway: Gateway,
) -> tuple[str, str]:
    """编辑器选择 + 单次调用(#324 A-e:返回 (variant, reason))。

    传入上一轮的失败(修 P2-1:编辑器看到变体自身的失败模式);
    双旋钮按代次奇偶路由,编辑器调用计入分项(编辑预算 1 call/代不变)。
    state.support_hint 原地更新(双旋钮 support 臂)。
    """
    editors = (
        partial(edit_template_nr if config.editor_focus == "nr" else edit_template,
                role=config.editor_role),
        partial(edit_support_hint, role=config.editor_role),
    )
    if config.two_knobs:
        variant_template, state.support_hint, reason = edit_two_knobs(
            parent.template, state.support_hint, round_idx, last_failures, gateway,
            editors=editors)
    else:
        variant_template, reason = editors[0](parent.template, last_failures, gateway)
    state.call_breakdown["editor_calls"] += 1  # #324 C2 分项累计
    return variant_template, reason


def _paired_gate(
    batch: list[dict],
    parent: "Candidate",
    variant: "Candidate",
    gateway: Gateway,
    config: "GepaConfig",
    state: "LoopState",
) -> tuple[bool, dict | None]:
    """#324 B 配对验收闸(PM 默认粒度:探索代不配,只在替换时刻配)。

    父子两臂同批 case IDs、同运行身份、各注入自身完整旋钮组合;
    #332 起配对判定走 HNU 接受函数(accept_variant:新增 hard fail 拒 /
    H·N·U 不增 / Δ≥0.125 或 HNU 减且 Δ≥0)。
    返回(accepted, 同批配对证据)。
    """
    from .gepa_paired import evaluate_batch_paired  # 晚绑定:配对面住 gepa_paired
    budget = state.bind(0)  # 已绑定时返回既有 Budget(max_calls 不变)
    p_pcs, _, p_gate_stats = evaluate_batch_paired(
        batch, parent.template, gateway, config.judge_role,
        support_hint=parent.support_hint)
    v_pcs, _, v_gate_stats = evaluate_batch_paired(
        batch, variant.template, gateway, config.judge_role,
        support_hint=variant.support_hint)
    budget.add(p_gate_stats["calls"] + v_gate_stats["calls"])
    state.call_breakdown["tutor_calls"] += (
        p_gate_stats.get("calls", 0) + v_gate_stats.get("calls", 0))
    # #332:配对判定换 HNU 接受函数(替代四维 dominates);两臂 per-case
    # 聚合口径见 hnu_from_per_case(U 含 hard 案,fail→review 中性)
    parent_hnu = hnu_from_per_case(p_pcs)
    variant_hnu = hnu_from_per_case(v_pcs)
    accepted, accept_ev = accept_variant(parent_hnu, variant_hnu)
    paired_evidence = {
        "case_ids": [c.get("id", "") for c in batch],
        "parent_hnu": parent_hnu.as_dict(),
        "variant_hnu": variant_hnu.as_dict(),
        "per_case": [
            {"case_id": p.get("case_id"),
             "parent_total": p.get("total"),
             "variant_total": v.get("total"),
             "delta": (v.get("total", 0) - p.get("total", 0))
                      if "error" not in p and "error" not in v else None}
            for p, v in zip(p_pcs, v_pcs, strict=False)
        ],
        "gate_calls": p_gate_stats["calls"] + v_gate_stats["calls"],
        "accepted": accepted,
        "accept_reason": accept_ev["decision"],
        "delta_mean": accept_ev["delta_mean"],
    }
    return accepted, paired_evidence


def _noop_stats() -> dict:
    """noop 跳过评估的空 stats(计数全零,口径与 evaluate_batch 对齐)。"""
    return {"calls": 0, "tokens_in": 0, "tokens_out": 0, "wall_ms": 0,
            "env_failures": 0, "content_failures": 0,
            "tutor_calls": 0, "judge_calls": 0,
            "leak_net_violations": 0, "hard_vetoed": False,
            "h": 0, "n": 0, "u": 0, "mean": 0.0}


def _refresh_batch_reference(
    batch: list[dict], state: "LoopState", config: "GepaConfig",
    gateway: Gateway,
) -> tuple["HnuOutcome", list[dict]]:
    """#332 换批时重评当前最优作初筛参考(调用计入台账,T6)。

    返回 (参考 HNU, 失败帧);参考失败帧并给编辑器(当前最优自身的短板)。
    """
    _, ref_failures, ref_stats = evaluate_batch(
        batch, state.current_best.template, gateway, config.judge_role,
        support_hint=state.current_best.support_hint)
    budget = state.bind(0)
    budget.add(ref_stats["calls"])
    state.call_breakdown["tutor_calls"] += ref_stats.get("tutor_calls", 0)
    state.call_breakdown["judge_calls"] += ref_stats.get("judge_calls", 0)
    return hnu_from_stats(ref_stats), ref_failures


def _process_round(
    round_idx: int, state: "LoopState", config: "GepaConfig", gateway: Gateway,
) -> dict:
    """单代处理(#332):编辑 → noop 判定 → 评估 → 初筛 → 配对闸 → 替换/留证。

    状态全走 state(语境束);返回 round report。泄露否决/初筛否决/配对
    否决的候选都不成为父代或 best;配对确认才前进单一最优 lineage。
    """
    population, scores = state.population, state.scores
    budget = state.bind(0)
    parent = state.current_best  # #332 选择器:只认配对确认的当前最优
    parent_scores = scores.get(parent.candidate_id)

    variant_template, edit_reason = _edit_variant(
        config, state, parent, round_idx, state.last_failures, gateway)
    budget.add(1)

    # No-op 检查(#324 A-b):完整组合比较——双旋钮下 support-only 改写
    # 是新候选不再误判 noop;单旋钮 support 恒 None,保持原语义
    variant_support = state.support_hint if config.two_knobs else None
    is_noop = (variant_template == parent.template
               and variant_support == parent.support_hint)

    variant = Candidate(
        template=variant_template,
        support_hint=variant_support,
        parent_id=parent.candidate_id,
        round_idx=round_idx,
    )
    variant_id = population.add(variant)
    if is_noop:
        variant_scores = parent_scores
        variant_failures = []
        variant_stats = _noop_stats()
        scores[variant_id] = variant_scores
        # no-op 时 last_failures 保留上一轮,下轮编辑器继续用
    else:
        state.variant_evals += 1  # #332:评估候选计数(批切换依据)
        variant_scores, variant_failures, variant_stats = evaluate_batch(
            state.batch, variant_template, gateway, config.judge_role,
            support_hint=variant_support)
        budget.add(variant_stats["calls"])
        state.call_breakdown["tutor_calls"] += variant_stats.get("tutor_calls", 0)
        state.call_breakdown["judge_calls"] += variant_stats.get("judge_calls", 0)
        state.last_failures = variant_failures

    # Net A veto(#310 + #324 C):泄露网违例变体不注册分数
    leak_veto = bool(variant_stats.get("leak_net_violations")) and not is_noop

    # #332 初筛:接受函数(当前最优重评参考 vs 变体探索结果,同批)——
    # 初筛决定是否值得配对(替 #329 的跨批 dominates 预判);泄露/noop 不进闸
    if (not is_noop) and (not leak_veto) and state.ref_outcome is not None:
        worth_pairing, screen_evidence = accept_variant(
            state.ref_outcome, hnu_from_stats(variant_stats))
    else:
        worth_pairing, screen_evidence = False, None

    # 配对验收闸(#324 B 既定 + #332 判定换轨):拟替换时父子同批配对;
    # 配对确认才替换当前最优,配对成本计预算
    if worth_pairing:
        accepted, paired_evidence = _paired_gate(
            state.batch, parent, variant, gateway, config, state)
        if accepted:
            state.current_best = variant  # #332:单一最优 lineage 前进
            # 参考刷新:配对子臂即新最优在本批的逐案结果,零额外成本
            state.ref_outcome = HnuOutcome(**paired_evidence["variant_hnu"])
    else:
        accepted, paired_evidence = False, None

    # 分数注册:泄露否决/配对否决的候选不进池(0 次成为父代/best);
    # noop 候选继承父代分进池;#332:池只作运行工件留证,选择走 current_best
    if leak_veto or (worth_pairing and not accepted):
        scores.pop(variant_id, None)
    elif not leak_veto and variant_id not in scores and not is_noop:
        scores[variant_id] = variant_scores

    return {
        "round": round_idx,
        "parent_id": parent.candidate_id,
        "variant_id": variant_id,
        "parent_template": parent.template,
        "variant_template": variant_template,
        "support_hint": variant_support,
        "parent_support_hint": parent.support_hint,
        "noop": is_noop,
        "edit_reason": edit_reason,  # #324 A-e:编辑尝试原因 100% 落报告
        "parent_scores": parent_scores.__dict__,
        "variant_scores": variant_scores.__dict__,
        "accepted": accepted,
        "leak_net_veto": leak_veto,
        "screen_evidence": screen_evidence,  # #332:初筛证据(值得配对与否)
        "cohort_idx": state.cohort_idx,  # #332:批代(每 5 评估候选同批)
        "paired_evidence": paired_evidence,  # #324 B:最优替换 100% 附同批证据
        "diff": list(unified_diff(
            parent.template.splitlines(keepends=True),
            variant_template.splitlines(keepends=True),
            fromfile="parent",
            tofile="variant",
        )),
        "stats": variant_stats,
        "failures": variant_failures,
    }


def gepa_loop(
    train_cases: list[dict],
    initial_template: str,
    config: GepaConfig,
    gateway: Gateway,
    output_dir: Path,
    resume: bool = True,
) -> tuple[Population, dict[int, ScoreVector], list[dict]]:
    """GEPA 主循环(薄循环):批管理(#332 每 5 评估候选同批+换批重评)+ 单代处理。

    resume=True 且 checkpoint 在:恢复单一最优 lineage、预算与代次延续;
    身份不匹配拒绝复用(#324 A3)。#332 选择器:只维护配对确认的当前最优,
    历史跨批池 max 不参与选父代(池仅作工件留证)。
    返回:(population, scores, round_reports)。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    state = LoopState(train_cases=train_cases, initial_template=initial_template)
    state.run_id = search_identity(config, train_cases)  # #324 A3
    population, scores = state.population, state.scores
    budget = state.bind(config.max_calls)
    round_reports: list[dict] = []
    start_round, failures, seed_vetoed = _restore_or_seed(
        config, gateway, output_dir, resume, state)
    state.last_failures = failures

    if seed_vetoed:
        # 种子硬失败(#324 C1):停在开跑前——不进代循环,不烧剩余预算
        summary = {
            "budget": budget.summary(),
            "population_size": len(population.candidates),
            "accepted_variants": 0,
            "seed_hard_vetoed": True,
        }
        (output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return population, scores, round_reports

    for round_idx in range(start_round, config.rounds):
        if budget.exhausted():
            break
        budget.rounds += 1

        # #332 批管理:每 5 个评估候选同批;换批时重评当前最优作初筛参考
        # (调用计入台账,T6);恢复后计数归零 → 首轮换批重评,保守方向
        new_cohort = state.variant_evals // CANDIDATES_PER_BATCH
        if new_cohort != state.cohort_idx:
            state.cohort_idx = new_cohort
            state.batch = sample_stratified_batch(train_cases, seed=new_cohort)
            ref_outcome, ref_failures = _refresh_batch_reference(
                state.batch, state, config, gateway)
            state.ref_outcome = ref_outcome
            state.last_failures = ref_failures or state.last_failures

        report = _process_round(round_idx, state, config, gateway)
        round_reports.append(report)
        (output_dir / f"round-{round_idx:02d}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_checkpoint(output_dir, state, round_idx + 1, state.last_failures)

    # 最终报告
    summary = {
        "budget": budget.summary(),
        "call_breakdown": dict(state.call_breakdown),  # #324 C2:分项累计
        "run_identity": state.run_id,
        "population_size": len(population.candidates),
        "accepted_variants": sum(1 for r in round_reports if r["accepted"]),
        # #332:单一最优 lineage(配对确认),历史池 max 不参与
        "best_candidate": state.current_best.__dict__,
        "best_scores": scores[state.current_best.candidate_id].__dict__,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return population, scores, round_reports


write_checkpoint = _write_checkpoint  # 公开名(tests 只导公开入口,02 §6)
