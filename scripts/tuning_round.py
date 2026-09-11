#!/usr/bin/env python3
"""M2 调优循环一轮(00 §8.4 阶段 3):收集(内核)→ 评分(judge)→ 对照两轮基线。

用法:uv run python scripts/tuning_round.py --out var/tuning/round-N [--nightly]
      uv run python scripts/tuning_round.py --render-from <run 目录>   # 不跑批,纯重渲染
11 场景 = 基线同款三数据集;judge 单遍 primary(调优轮口径;双评留正式轮);
对照值 = 基线报告 §3 R1×R2 两轮固定值(docs/evals/baseline-run1-run2.md,#58 落盘快照),
容差口径 = #34 2026-09-09 人批:场景两轮分差 ≤1 → 单值判(本轮 ≥ max(R1,R2) 才达标);
分差 ≥2 → 区间判([min,max] 落入即"不劣(噪声主导)",不判反超)。
数字全部落盘不手拼;判停/状态读 transcript 内部字段,不从学生文本反推。
comparison.md 开头自述四行(2026-09-10 PM 马尾辫审查):口径名 / 剧本截断 N/M /
逐维均分 / 护栏模式——零新增埋点(纯渲染自落盘工件),既有行逐字节不变(只加信息不改测量)。
随后**另加一行**「五维总分(0-10,去 first_question)」试算(2026-09-10 PM 裁定:撤回
judge 退休、改零成本替代):同一批六维分去首问后再报一个 10 分制读数,六维 judge 与门判定
(12 分制 vs 老基线)一字不动,该行不参与判定。
--nightly(每晚 23:00,evals-nightly.yml):先预检(注册表全部 provider 端口可达,
不可达退出 1)并落溯源 manifest(git sha、models.yaml 哈希、launchctl 服务快照)
——劣化起始日的环境可解释性(1b 教训:蹭机服务几个月无人察觉)。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from scripts.json_first_pass import json_first_pass_report

from edu_agent.evals import EvalRunner, KernelSubject, RunnerConfig, judge_transcript, load_results
from edu_agent.evals.judge import DIMENSIONS
from edu_agent.evals.report import DIM_LABELS
from edu_agent.gateway import Gateway, ModelRegistry, load_registry

REPO = Path(__file__).resolve().parents[1]
DATASETS = REPO / "edu_agent" / "evals" / "datasets"

# 两轮固定基线(基线报告 §3 R1/R2,#58 落盘快照;case_id → (R1, R2))
BASELINE = {
    "small_lecturer_dialogue_scenarios_equation_complete_reasoning": (8, 8),
    "small_lecturer_dialogue_stability_20_stability_chicken_rabbit": (6, 9),
    "small_lecturer_dialogue_stability_20_stability_equation_subtract": (7, 7),
    "small_lecturer_dialogue_stability_20_stability_fraction_addition": (3, 4),
    "small_lecturer_dialogue_stability_20_stability_triangle_area": (3, 3),
    "small_lecturer_dialogue_stability_20_stability_word_problem": (11, 5),
    "small_lecturer_teaching_context_shadow_pilot_20_stability_chicken_rabbit": (5, 5),
    "small_lecturer_teaching_context_shadow_pilot_20_stability_equation_subtract": (4, 4),
    "small_lecturer_teaching_context_shadow_pilot_20_stability_fraction_addition": (3, 4),
    "small_lecturer_teaching_context_shadow_pilot_20_stability_triangle_area": (2, 3),
    "small_lecturer_teaching_context_shadow_pilot_20_stability_word_problem": (11, 8),
}


def tolerance_verdict(got: int, r1: int, r2: int) -> str:
    """#34 2026-09-09 人批容差:两轮分差 ≤1 单值判(≥max 达标);≥2 区间判(≥min 不劣)。"""
    if abs(r1 - r2) <= 1:
        return "达标" if got >= max(r1, r2) else "低于基线"
    return "不劣(噪声主导)" if got >= min(r1, r2) else "低于基线"


def _probe(url: str, timeout: float = 2.0) -> str:
    """provider base_url 的 host:port TCP 可达性;返回 ok/失败原因。"""
    parsed = urlparse(url)
    host, port = parsed.hostname or "127.0.0.1", parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "ok"
    except OSError as exc:
        return f"不可达:{exc.__class__.__name__}"


def nightly_preflight(registry: ModelRegistry, out: Path) -> None:
    """预检 + 溯源 manifest(--nightly):端口不可达直接退出 1(流水线红灯)。"""
    probes = {name: _probe(p.base_url) for name, p in registry.providers.items()}
    unreachable = {k: v for k, v in probes.items() if v != "ok"}
    sha = os.environ.get("GITHUB_SHA", "").strip() or subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
        cwd=REPO).stdout.strip()
    models_sha = hashlib.sha256((REPO / "configs" / "models.yaml").read_bytes()).hexdigest()[:16]
    try:
        services = subprocess.run(["launchctl", "list"], capture_output=True,
                                  text=True, check=True).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        services = []  # 非 macOS 环境只留空快照
    (out / "manifest.json").write_text(json.dumps({
        "git_sha": sha, "models_yaml_sha256": models_sha,
        "provider_probes": probes, "launchctl_services": services,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    if unreachable:
        for name, why in unreachable.items():
            print(f"nightly 预检失败:provider {name} {why}", file=sys.stderr)
        sys.exit(1)


def build_cases() -> list[dict]:
    """11 场景:dialogue_scenarios 1 + stability_20 5 + teaching_context 5(基线同款)。"""
    bank = {r["question_id"]: r for r in json.loads(
        (REPO / "edu_agent" / "contracts" / "release_acceptance_seed_question_bank.json").read_text(encoding="utf-8"))["records"]}
    stability_ids = ["chicken_rabbit", "equation_subtract", "fraction_addition",
                     "triangle_area", "word_problem"]
    cases = []

    def scenario_row(dataset_name: str, wanted_id: str) -> dict:
        rows = json.loads((DATASETS / f"{dataset_name}.json").read_text(encoding="utf-8"))["scenarios"]
        return next(r for r in rows if r["id"] == wanted_id)

    by_stem = {r["stem"]: r for r in bank.values()}

    def bank_record(key: str, question: str) -> dict:
        return bank.get(key) or by_stem.get(question) or {}  # id 优先,题干文本兜底(同题不同 id)

    for dataset, sid in [("small_lecturer_dialogue_scenarios", "equation_complete_reasoning")] + \
                        [("small_lecturer_dialogue_stability_20", f"stability_{s}") for s in stability_ids] + \
                        [("small_lecturer_teaching_context_shadow_pilot_20", f"stability_{s}") for s in stability_ids]:
        row = scenario_row(dataset, sid)
        bank_key = sid.removeprefix("stability_") if sid.startswith("stability_") else sid
        record = bank_record(bank_key, row["question"])
        # R6 评测数据侧(任务书第 3 条):word_problem 补传 answer_status 验证策略分派
        # 与结构化 summary 通路;其余场景不带(unknown → 首问无提示、finish 走原路径)。
        answer_status = "correct" if bank_key == "word_problem" else None
        cases.append({
            "id": f"{dataset}_{sid}",
            "question": row["question"],
            "student_turns": row["student_turns"],
            "grade": record.get("grade", ""),
            "reference_answer": record.get("answer", ""),
            **({"answer_status": answer_status} if answer_status else {}),
        })
    return cases


def to_judge_cases(rows: list[dict]) -> list[dict]:
    """run 结果 → judge 输入(judge_score.py 同款形态;transcript 的 turns 展开)。"""
    judge_cases = []
    for row in rows:
        if row["status"] != "ok":
            continue
        t = row["transcript"]
        messages = []
        for turn in t["turns"]:
            if turn["student"]:
                messages.append({"role": "user", "content": turn["student"]})
            messages.append({"role": "assistant", "content": turn["tutor"]})
        if t.get("summary"):
            messages.append({"role": "assistant", "content": t["summary"]})
        judge_cases.append({
            "id": row["case_id"],
            "question": next(c["question"] for c in CASES if c["id"] == row["case_id"]),
            "grade": t.get("learner", {}).get("grade", ""),
            "reference_answer": next(c["reference_answer"] for c in CASES if c["id"] == row["case_id"]),
            "messages": messages,
        })
    return judge_cases


CASES = build_cases()


def sent_vs_script(rows: list[dict], cases: list[dict]) -> dict[str, str]:
    """每场景「实发学生轮/剧本学生轮」(零新增埋点:transcript 轮数 vs 用例剧本长度)。

    ⚠ = 实发 < 剧本,即 KernelSubject 在 `ready_to_confirm` 判停后余轮未发;
    失败行无 transcript,标「失败」。PM 马尾辫审查:截断必须出现在报告里,不能只活在代码里。
    """
    by_id = {r["case_id"]: r for r in rows}
    out: dict[str, str] = {}
    for case in cases:
        row = by_id.get(case["id"])
        script_n = len(case.get("student_turns", []))
        if row is None or row.get("status") != "ok":
            out[case["id"]] = "失败"
            continue
        sent = len(row["transcript"]["turns"]) - 1  # 首轮无学生消息
        out[case["id"]] = f"{sent}/{script_n}" + (" ⚠" if sent < script_n else "")
    return out


def dim_average_line(scores: dict) -> str:
    """逐维均分一行:复用 report.DIM_LABELS 渲染、维度顺序 = judge.DIMENSIONS(不新造维度表)。"""
    ok = [v["scores"] for v in scores.values() if isinstance(v, dict) and "scores" in v]
    if not ok:
        return "逐维均分(0-2):(无 ok 评分)"
    parts = [f"{DIM_LABELS[dim]} {sum(s[dim] for s in ok) / len(ok):.2f}" for dim in DIMENSIONS]
    return "逐维均分(0-2):" + " | ".join(parts)


def five_dim_total_line(scores: dict) -> str:
    """五维总分(0-10,去 first_question)试算一行:纯渲染既有 judge 分数,**零新增埋点、零重算**。

    口径来源(2026-09-10 PM 裁定「撤回退休、改零成本替代」):六维 judge、判决阈值与门
    (R1×R2 12 分制「不劣」)全部不动,本行只是把同一批六维分去掉 first_question 后再报一个
    10 分制数,供新口径有数可看。**门仍按 12 分制与老基线比,本行不参与判定。**
    不换算老基线的理由:老基线逐 case 逐维数据已丢失,无法反推 10 分制;且首问是「带图能力」
    的测量落点,不能退休 —— 故只加一行读数,不改测量。维度名复用 report.DIM_LABELS(不新造表)。
    """
    first = DIMENSIONS[0]  # first_question(judge.DIMENSIONS 首维;标签由 report.DIM_LABELS 提供)
    ok = [(cid, v["scores"]) for cid, v in scores.items()
          if isinstance(v, dict) and "scores" in v]
    if not ok:
        return f"五维总分(0-10,去 {first};新口径试算,门仍按 12 分制与老基线比):(无 ok 评分)"
    per_case = [(cid, sum(s[dim] for dim in DIMENSIONS) - s[first]) for cid, s in ok]
    listed = "、".join(f"{cid} {total}" for cid, total in per_case)
    avg = sum(total for _, total in per_case) / len(per_case)
    return (f"五维总分(0-10,去 {first};新口径试算,门仍按 12 分制与老基线比):"
            f"均分 {avg:.2f}(逐 case:{listed})")


# ---------- #146 M2:逐轮判定字段并入夜评口径 ----------
# **字段预注册**(复用 #143 预注册口径 + kernel 侧结构化留痕,不即兴加列):
#   轮      = 0 起(0 = 首问);
#   状态    = 该轮末 KernelSubject 状态(dialogue/ready_to_confirm/…;会话终态另段);
#   分支    = 该轮的确定性/模型路径,取自 `guard_events` 的 branch(model/elicit/reveal/…);
#   护栏/守卫 = 该轮 guard 命中(guard 名 + rule_ids + mode,如 `feeds_method(假设法;regenerated)`);
#   数字    = 该轮 `cited`(模型自报,影子)/`extracted`(确定性抽取)/违规(来源标签 answer|hallucinated)。
# 事件配对零新增埋点:`guard_events` 按轮序消费——确定性轮恰一个 branch 事件,模型轮以
# `branch:"model"` 收尾(其前可挂 guard 事件)。数值口径与 `_record_event`/漂移事件同源。
_TURN_LEDGER_LEGEND = (
    "字段预注册(#143 口径,全部从落盘件复算):**状态**=该轮末 KernelSubject 状态;"
    "**分支**=`guard_events` 的 branch(确定性 elicit/reveal vs 模型轮);"
    "**护栏/守卫**=该轮 guard 命中 `名(rule_ids;mode)`;"
    "**数字**=`cited`(模型自报,影子)/`extracted`(抽取)/违规(来源标签 answer|hallucinated)。"
)

# 首问轮(start(),不入 history)只可能产生的护栏:`_guard_output` 的三类
# (answer_leak/tone/format)——旧工件无事件轮号时据此做**尽力**配对(新工件有 `turn`)。
_OPEN_PATH_GUARDS = frozenset({"answer_leak", "tone", "format"})


def _clip(text: object, limit: int) -> str:
    """表格单元格截断 + 竖线转义(不破坏 Markdown 表结构)。"""
    flat = " ".join(str(text or "").split()).replace("|", "\\|")
    return flat[:limit] + ("…" if len(flat) > limit else "") or "—"


def _turn_events(transcript: dict) -> list[tuple[dict, list[dict]]]:
    """transcript → [(轮 dict, 该轮事件)]:**优先按事件自带轮号 `turn` 归并**
    (`_stamp_turn` 在提交点写入,精确;旧工件无该字段时按序退回配对)。

    退回规则(与 kernel 埋点写入顺序一一对应):
    - **首问**(轮 0)由 `start()` 产出 → **没有** `branch:"model"` 漂移事件,只可能有
      挂在其前的 guard 事件(如首问泄露被 `answer_leak` 换掉):只消费 branch 前的事件;
    - 其余轮:确定性轮(elicit/reveal)恰一个 branch 事件;模型轮以 `branch:"model"`
      收尾(其前可挂 guard 事件)。
    事件数不足/多余时余额挂最后一轮(如实呈现,不静默丢)。
    """
    turns = transcript.get("turns") or []
    events = list(transcript.get("guard_events") or [])
    if events and all("turn" in e for e in events):  # 精确路径:事件自带轮号(_stamp_turn 写入)
        buckets: dict[int, list[dict]] = {}
        for event in events:
            buckets.setdefault(int(event["turn"]), []).append(event)
        pairs = [(turn, buckets.get(index, [])) for index, turn in enumerate(turns)]
        for index in sorted(k for k in buckets if k >= len(turns)):  # 余额如实挂末轮
            if pairs:
                pairs[-1][1].extend(buckets[index])
        return pairs
    index, pairs = 0, []
    for turn_no, turn in enumerate(turns):
        mine: list[dict] = []
        if turn_no == 0:  # 首问:start() 只可能落 _guard_output 的护栏事件(answer_leak/tone/format)
            while (index < len(events) and "branch" not in events[index]
                   and events[index].get("guard") in _OPEN_PATH_GUARDS):
                mine.append(events[index])
                index += 1
        else:
            while index < len(events):
                event = events[index]
                mine.append(event)
                index += 1
                if "branch" in event:  # 该轮最后一个事件
                    break
        pairs.append((turn, mine))
    if index < len(events) and pairs:
        pairs[-1][1].extend(events[index:])  # 余额挂末轮(报告如实呈现,不静默丢)
    return pairs


def _cell_guards(events: list[dict]) -> str:
    """该轮护栏/守卫命中摘要:`guard(rule_ids;mode)`;漂移违规另由 `_cell_numbers` 记。"""
    parts = []
    for event in events:
        guard = event.get("guard")
        if not guard:
            continue
        rules = ",".join(str(r) for r in (event.get("rule_ids") or []))
        mode = event.get("mode")
        detail = ";".join(x for x in (rules, mode) if x)
        parts.append(f"{guard}({detail})" if detail else str(guard))
    return " ".join(parts) or "—"


def _cell_numbers(events: list[dict]) -> str:
    """该轮数字口径:cited(自报影子)/extracted(抽取)/违规(来源标签)。

    分隔用 `; `(Markdown 表格单元格内不能出现裸竖线)。"""
    for event in reversed(events):
        if event.get("branch") == "model":
            cited = ",".join(f"{n:g}" for n in (event.get("cited") or []))
            extracted = ",".join(f"{n:g}" for n in (event.get("extracted") or []))
            violations = ",".join(
                f"{v.get('source')}:{v.get('number'):g}" for v in (event.get("violation_sources") or []))
            cell = f"cited {cited or '—'}; extracted {extracted or '—'}"
            return f"{cell}; 违规 {violations}" if violations else cell
    return "—"


def turn_ledger_report(rows: list[dict], cases: list[dict]) -> list[str]:
    """逐轮结构表(#146 M2 验收:夜评 comparison 出现逐轮列)。

    纯增量:插在主表**之前**,既有行(标题/自述/截断表/主表/均值差)逐字节不变。
    失败行如实标注、不静默跳过(与截断表同口径)。
    """
    report = ["", "## 逐轮结构(#146 M2;结构性结论从人工通读变为报告可读)", "",
              _TURN_LEDGER_LEGEND, "",
              "| 场景 | 轮 | 学生 | 教师 | 状态 | 分支 | 护栏/守卫 | 数字 |",
              "|---|---:|---|---|---|---|---|---|"]
    by_id = {r["case_id"]: r for r in rows}
    for case in cases:
        case_id = case["id"]
        row = by_id.get(case_id)
        short = case_id.split("stability_")[-1]
        if row is None or row.get("status") != "ok":
            report.append(f"| {short} | — | — | — | — | — | — | 失败(无 transcript) |")
            continue
        for turn_no, (turn, events) in enumerate(_turn_events(row["transcript"])):
            branch = next((str(e["branch"]) for e in events if e.get("branch")), "—")
            hint = next((f"(hint={e['hint_level']})" for e in events if "hint_level" in e), "")
            report.append("| {} | {} | {} | {} | {} | {}{} | {} | {} |".format(
                short, turn_no, _clip(turn.get("student"), 14), _clip(turn.get("tutor"), 26),
                _clip(turn.get("state"), 16), branch, hint,
                _cell_guards(events), _cell_numbers(events)))
    return report


def comparison_report(scores: dict, rows: list[dict], cases: list[dict]) -> list[str]:
    """comparison.md 的 gate 段行(数字全部从落盘件重算,不手拼)。

    结构:自述四行(纯增量,2026-09-10 PM 审查)+ 既有主表(逐字节不变——验收线
    「现有报告字段的数字必须逐字节不变」)。
    """
    hint_groups: dict[str, list[str]] = {}
    for case in cases:
        if case.get("answer_status"):
            hint_groups.setdefault(case["answer_status"], []).append(case["id"])
    hinted = sum(len(ids) for ids in hint_groups.values())
    hint_note = "; ".join(
        f"`answer_status=\"{status}\"`({'、'.join(ids)})"
        for status, ids in hint_groups.items())
    if hint_note:
        caliber_line = (f"口径:**P(gate 冻结 wiring)** —— `build_cases` {len(cases)} 场景;"
                        f"hint 注入:{hinted}/{len(cases)} 场景带 {hint_note},"
                        f"其余 {len(cases) - hinted} 场景不带(unknown → 首问无提示)。")
    else:
        caliber_line = (f"口径:**P(gate 冻结 wiring)** —— `build_cases` {len(cases)} 场景;"
                        "hint 注入:无(全部 unknown → 首问无提示)。")
    report = ["# 调优轮对照(vs 基线 R1×R2,#34 容差口径:分差≤1 单值判/≥2 区间判)", ""]
    report += [
        caliber_line,
        "",
        "剧本截断(实发学生轮/剧本学生轮;⚠ = `ready_to_confirm` 提前判停,余轮不再发"
        "——KernelSubject 判停语义):",
        "",
        "| 场景 | 学生轮(实发/剧本) |",
        "|---|---|",
    ]
    for case_id, cell in sent_vs_script(rows, cases).items():
        report.append(f"| {case_id} | {cell} |")
    report += ["", dim_average_line(scores),
               five_dim_total_line(scores),  # 新口径试算行(纯渲染;门判定不变)
               "护栏模式:**无答案** —— 评测侧 KernelSubject 只传题面/年级/answer_status,"
               "**不传参考答案**;生产侧带答案。本报告的代喂/泄露类读数出自无答案护栏,"
               "不等于生产读数。", ""]
    report += turn_ledger_report(rows, cases)  # #146 M2:逐轮列(主表之前,既有行不动)
    report += ["", "| 场景 | R1 | R2 | 本轮 | 判定 |", "|---|---:|---:|---:|---|"]
    deltas = []
    for case_id, (r1, r2) in BASELINE.items():
        got = scores.get(case_id, {}).get("total")
        if got is None:
            report.append(f"| {case_id} | {r1} | {r2} | 失败 | FAIL |")
            continue
        deltas.append(got - (r1 + r2) / 2)
        report.append(f"| {case_id} | {r1} | {r2} | {got} | {tolerance_verdict(got, r1, r2)} |")
    report += ["", f"逐维均分:见 judge-scores.json;对两轮均值差:{sum(deltas) / len(deltas):+.2f}"]
    return report


def render_from(run_dir: Path) -> int:
    """--render-from:不跑批,从既有 run 目录重渲染 comparison.md(Mac 纪律:优先重渲染)。

    gate 段数字从 run 目录落盘件重算(cases.jsonl / collect 结果 / judge-scores.json);
    json_first_pass 段承接原 comparison.md 原文(facts 记录不在 run 目录,无法重算)并
    标注「未重算」——报告自述哪些段重算、哪些段承接(#154 审查观察 2)。
    """
    cases = [json.loads(line) for line
             in (run_dir / "cases.jsonl").read_text(encoding="utf-8").splitlines() if line]
    rows = load_results(_latest_run(run_dir / "collect"))
    scores = json.loads((run_dir / "judge-scores.json").read_text(encoding="utf-8"))
    report = comparison_report(scores, rows, cases)
    text = "\n".join(report) + "\n"
    old_path = run_dir / "comparison.md"
    if old_path.exists():
        old = old_path.read_text(encoding="utf-8")
        jfp_at = old.find("## json_first_pass")
        if jfp_at >= 0:
            marker = ("> 注:json_first_pass 段**承接原 comparison.md、未重算**"
                      "(facts 记录不在 run 目录;上方 gate 段数字已从落盘件重算)。")
            text += "\n" + marker + "\n\n" + old[jfp_at:]
    old_path.write_text(text, encoding="utf-8")
    print(text)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="输出目录,如 var/tuning/round-1(跑批模式必填)")
    parser.add_argument("--nightly", action="store_true",
                        help="夜评模式:预检 provider 可达性 + 落溯源 manifest(evals-nightly.yml)")
    parser.add_argument("--render-from", metavar="RUN_DIR",
                        help="不跑批:从既有 run 目录(cases.jsonl/collect/judge-scores.json)"
                             "重渲染 comparison.md;jfp 段承接原文件(facts 不在 run 目录)")
    args = parser.parse_args()
    if args.render_from:
        return render_from(Path(args.render_from))
    if not args.out:
        parser.error("跑批模式需要 --out;纯重渲染用 --render-from <run 目录>")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    registry = load_registry(REPO / "configs" / "models.yaml")
    if args.nightly:
        nightly_preflight(registry, out)
    facts_dir = Path(os.environ.get("EDU_FACTS_DIR") or REPO / "facts")
    gateway = Gateway(registry, facts_dir=facts_dir)
    try:
        print(f"收集:11 场景,KernelSubject(tutor 主选 {registry.roles['tutor'].primary})")
        run_dir = out / "collect"
        cases_file = out / "cases.jsonl"
        cases_file.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in CASES) + "\n",
                              encoding="utf-8")
        EvalRunner(KernelSubject(gateway), RunnerConfig(concurrency=2), run_dir).run(
            cases_file, CASES)
        rows = load_results(_latest_run(run_dir))
        judge_input = to_judge_cases(rows)
        (out / "judge-cases.jsonl").write_text(
            "\n".join(json.dumps(c, ensure_ascii=False) for c in judge_input) + "\n", encoding="utf-8")
        print(f"评分:{len(judge_input)} case(judge 27B,单遍 primary)")
        scores = {}
        for case in judge_input:
            verdict = judge_transcript(gateway, case)
            scores[case["id"]] = verdict
            print(f"  {case['id'][:58]:60s} total={verdict['total']:2d} {verdict['verdict']}")
    finally:
        gateway.close()

    (out / "judge-scores.json").write_text(json.dumps(scores, ensure_ascii=False, indent=1), encoding="utf-8")
    report = comparison_report(scores, rows, CASES)
    # #34 M2 出口条件:json 一次通过率(结构化输出合规率,01 §6)
    jfp_text = json_first_pass_report(facts_dir)
    report += jfp_text.splitlines() + [""]
    text = "\n".join(report) + "\n"
    (out / "comparison.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


def _latest_run(root: Path) -> Path:
    return sorted(root.glob("*-*Z-*"))[-1] if sorted(root.glob("*-*Z-*")) else root


if __name__ == "__main__":
    sys.exit(main())
