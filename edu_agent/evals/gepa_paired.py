"""GEPA 配对实验循环(#256,2026-09-16):paired_loop 族。

单文件 800 行上限拆分自 gepa.py(02 §2,同 gepa_editors.py 拆分先例);
gepa.py 保留 evaluate_batch_paired(配对执行面)与配对验收闸。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from edu_agent.gateway import Gateway

from .gepa import Budget, GepaConfig, ElicitSubject, _score_one_case, edit_template


def evaluate_batch_paired(
    cases: list[dict],
    template: str,
    gateway: Gateway,
    judge_role: str = "judge",
    support_hint: str | None = None,
) -> tuple[list[dict], list[dict], dict]:
    """配对实验:逐案跑 + 逐案判,返回 per-case scores 和转录快照。

    #324 B2:加 support_hint 参数——配对臂注入自身完整旋钮组合
    (父子两臂 template+support 各自独立,不再共用顶层状态)。
    #324 C2:计数改 FactWriter 进程内差值(跨 UTC 日/旁路 run 归属正确)。

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
    subject = ElicitSubject(template, gateway, support_hint=support_hint)
    writer = gateway.writer
    w0_count, w0_in, w0_out = writer.count, writer.tokens_in, writer.tokens_out

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

    # facts 实测计数(#324 C2:进程内计数器差值,不硬编码也不用文件行数差)
    stats["calls"] = writer.count - w0_count
    stats["tokens_in"] = writer.tokens_in - w0_in
    stats["tokens_out"] = writer.tokens_out - w0_out
    stats["wall_ms"] = int((time.monotonic() - started) * 1000)
    return per_case_scores, snapshots, stats


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
    
    writer = gateway.writer
    w0_count, w0_in, w0_out = writer.count, writer.tokens_in, writer.tokens_out

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
        
        # 编辑模板(#324 A-e:二元组返回,reason 不进本实验报告)
        variant_template, _edit_reason = edit_template(
            initial_template, parent_failures, gateway)
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
    real_calls = writer.count - w0_count
    tokens_in = writer.tokens_in - w0_in
    tokens_out = writer.tokens_out - w0_out
    
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

