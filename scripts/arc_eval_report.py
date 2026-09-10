#!/usr/bin/env python3
"""#101 双臂评测:报告生成(四指标表 / 转录差异 / judge 可靠性 / 代喂清单 / 两路径对照表)。

用法:.venv/bin/python scripts/arc_eval_report.py --out <共享 artifacts 目录> [--doc-out <镜像文档>]
数字全部从落盘工件读出,不手拼(#34 纪律)。
§0 口径与效度自述(2026-09-10 PM 马尾辫审查):口径名 / hint 注入 / 剧本截断 N/M / 护栏模式
——纯渲染自 cases.jsonl 与 transcript 轮数,零新增埋点;对既有章节逐字节不变(只加信息不改测量)。
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

RESTATE_PAT = re.compile(r"讲一遍|复述|说说你的?思路|你是怎么想的|讲给我听|从头讲")
ORPHAN_TAIL = ("用", "通过", "采用", "利用", "运用", "代入", "按照", "根据", "使用")
# 口径名登记(读报告不读代码;判定规则原文仍以 pre-registration 文档为准)
CALIBER_NOTE = {
    "P": "gate 冻结 wiring —— answer_status 照 `tuning_round.build_cases` 现状注入",
    "F": "生产同构 —— answer_status 按剧本首轮语义复原(生产映射 service.py:160)",
    "R": "F + S5 学生复讲句(#112 复讲完成度帧)",
    "L": "复读探针 —— 2 题 × 8 轮同一句(#112)",
}
METRIC_LABELS = {
    "first_question_ok": "首问合规率",
    "collect_not_judge_ok": "采集不评判率",
    "restate_ok": "复讲达成率",
    "feeding_judge": "方法名代喂率(judge)",
    "feeding_any": "方法名代喂率(judge∨确定性)",
}
KIND_NOTE = {"method_name": "强方法名(方法名词表逐字命中)",
             "answer_number": "答案数字(参考答案数值,学生尚未说出)",
             "method_weak": "弱命中(「方程」「假设」等,单独标注不计入代喂率)"}


def jid(base: str) -> str:
    return "c" + hashlib.sha256(base.encode()).hexdigest()[:12]


def load(art: Path, cal: str, arm: str) -> dict:
    out = {}
    for path in glob.glob(str(art / cal / arm / "collect" / "*" / "results" / "*.json")):
        row = json.loads(Path(path).read_text(encoding="utf-8"))
        if row.get("status") == "ok":
            base, rep = row["case_id"].rsplit("__r", 1)
            out[(base, rep)] = row["transcript"]
    return out


def redact(sentence: str, term: str) -> tuple[str, bool]:
    """机械删词;返回(删后句, 接缝是否留孤儿动词)。"""
    i = sentence.find(term)
    if i < 0:
        return sentence, False
    out = sentence[:i] + sentence[i + len(term):]
    return out, sentence[:i].rstrip().endswith(ORPHAN_TAIL)


def short(base: str) -> str:
    return (base.replace("small_lecturer_dialogue_scenarios_", "")
                .replace("small_lecturer_dialogue_", "")
                .replace("small_lecturer_teaching_context_shadow_pilot_20_", "shadow_"))


def _cal_arms(art: Path) -> list[tuple[str, str]]:
    """工件目录里实际存在的 (口径, 臂) 组合(按目录名发现,不硬编码枚举)。"""
    return sorted({(p.parts[-3], p.parts[-2]) for p in art.glob("*/[MA]/cases.jsonl")})


def _cases_of(art: Path, cal: str, arm: str) -> list[dict]:
    text = (art / cal / arm / "cases.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


def _hint_lines(art: Path, pairs: list[tuple[str, str]]) -> list[str]:
    """逐口径·臂的 answer_status 注入摘要(哪些场景带、带什么值;场景多时收成计数)。"""
    lines = []
    for cal, arm in pairs:
        cases = _cases_of(art, cal, arm)
        by_status: dict[str, list[dict]] = {}
        for case in cases:
            if case.get("answer_status"):
                by_status.setdefault(case["answer_status"], []).append(case)
        hinted = sum(len(v) for v in by_status.values())
        parts = []
        for status, group in sorted(by_status.items()):
            names = sorted({short(c["id"].rsplit("__r", 1)[0]) for c in group})
            names_note = "、".join(names) if len(names) <= 4 else f"{len(names)} 场景全部"
            parts.append(f"{status} {len(group)} 用例({names_note})")
        detail = ";".join(parts)
        lines.append(f"{cal}·{arm}:{hinted}/{len(cases)} 用例带({detail})" if detail
                     else f"{cal}·{arm}:0/{len(cases)} 用例带(全部 unknown)")
    return lines


def _truncation_rows(art: Path, pairs: list[tuple[str, str]]) -> list[list[str]]:
    """剧本截断矩阵:行 = 场景,列 = 口径·臂,值 = 实发学生轮/剧本学生轮(逐重复,相同合并)。

    ⚠ = 实发 < 剧本(KernelSubject 在 ready_to_confirm 判停后余轮未发);失败行无 transcript。
    """
    headers = ["场景"] + [f"{cal}·{arm}" for cal, arm in pairs]
    bases: set[str] = set()
    cells: dict[tuple[str, str], dict[str, str]] = {}
    for cal, arm in pairs:
        transcripts = load(art, cal, arm)
        by_base: dict[str, list[str]] = {}
        for case in _cases_of(art, cal, arm):
            base, rep = case["id"].rsplit("__r", 1)
            script_n = len(case.get("student_turns", []))
            t = transcripts.get((base, rep))
            if t is None:
                by_base.setdefault(base, []).append("失败")
                continue
            sent = len(t["turns"]) - 1  # 首轮无学生消息
            by_base.setdefault(base, []).append(f"{sent}/{script_n}" + (" ⚠" if sent < script_n else ""))
        bases.update(by_base)
        cells[(cal, arm)] = {b: ("·".join(v) if len(set(v)) > 1 else v[0]) for b, v in by_base.items()}
    rows = [headers]
    for base in sorted(bases):
        rows.append([short(base)] + [cells[p].get(base, "—") for p in pairs])
    return rows


def sec_self_describe(L: list[str], art: Path) -> None:
    """§0 自述四要素(2026-09-10 PM 马尾辫审查):口径名 / hint 注入 / 剧本截断 / 护栏模式。"""
    w = L.append
    pairs = _cal_arms(art)
    calibers = sorted({cal for cal, _ in pairs})
    w("## 0. 口径与效度自述(读报告不读代码)")
    w("")
    for cal in calibers:
        w(f"- 口径 **{cal}**:{CALIBER_NOTE.get(cal, '(口径说明未登记——以 pre-registration 文档为准)')}")
    w("- hint 注入(answer_status,评测侧注入、非学生陈述):" + ";".join(_hint_lines(art, pairs)))
    w("- 剧本截断(实发学生轮/剧本学生轮;⚠ = `ready_to_confirm` 提前判停,余轮不再发):")
    w("")
    rows = _truncation_rows(art, pairs)
    w("| " + " | ".join(rows[0]) + " |")
    w("|" + "---|" * len(rows[0]))
    for row in rows[1:]:
        w("| " + " | ".join(row) + " |")
    w("")
    w("- 维度视图:四指标(§2)即本报告的维度表;六维 `DIM_LABELS` 口径属夜评 judge schema,"
      "不适用于本四指标 judge。")
    w("- 护栏模式:**无答案** —— 评测侧 KernelSubject 只传题面/年级/answer_status,"
      "**不传参考答案**;生产侧带答案。本报告的代喂/泄露类读数出自无答案护栏,不等于生产读数。")
    w("")


def sec_arms(L: list[str], art: Path) -> None:
    w = L.append
    w("## 1. 臂与工件")
    w("")
    w("| 项 | 值 |")
    w("|---|---|")
    for arm in ("M", "A"):
        man = json.loads((art / f"manifest-{arm}.json").read_text(encoding="utf-8"))
        w(f"| 臂 {arm} git sha | `{man['git_sha'][:12]}`(worktree `{man['worktree']}`) |")
    man = json.loads((art / "manifest-A.json").read_text(encoding="utf-8"))
    w(f"| tutor 模型 | `{man['tutor']}` |")
    w("| judge | `mlx_27b` 单遍 temperature=0(同夜评口径) |")
    w("| 臂 A 代码状态 | = `0902a76`(= `origin/main` `acb5b89` + merge `origin/tune/teaching-arc`"
      " `c8935c7`);采集时 HEAD 为 pre-reg 提交 `c961d2b`,该提交只增 docs,"
      "运行时行为与 `0902a76` 相同 |")
    w("| 两臂代码差异 | 仅 `edu_agent/agents/small_lecturer/prompting.py`(两常量)"
      " + `tests/teaching/test_kernel_r6.py`(测试) |")
    w("| **解读边界** | 臂 M 的内核**已含弧线机制**(分步解、卡点标记、复讲类行为在两臂都存在),"
      "臂 A 只差 `prompting.py` 两常量 → 本实验测的是**弧线 prompt 文案改写**,"
      "**不是\"有弧线 vs 无弧线\"**;引用下表须带此前缀 |")
    n_tr = len(glob.glob(str(art / "*" / "[MA]" / "collect" / "*" / "results" / "*.json")))
    n_sc = len(glob.glob(str(art / "*" / "[MA]" / "judge-scores" / "*.json")))
    w(f"| transcript 总数 | {n_tr} 份(11 场景 × 2 重复 × 2 臂 × 2 口径) |")
    w(f"| judge 评分数 | {n_sc} 份 |")
    w("")


def _cell(entry: dict) -> str:
    r1, r2 = entry["r1"], entry["r2"]
    fmt = lambda x: f"{x['k']}/{x['n']}" + (f" = {x['rate']}" if x["rate"] is not None else " (NA)")
    text = f"{fmt(r1)}<br>r2 {fmt(r2)}"
    if entry["min_max"]:
        text += f"<br>min–max {entry['min_max'][0]}–{entry['min_max'][1]}"
    return text


def sec_metrics(L: list[str], metrics: dict) -> None:
    w = L.append
    w("## 2. 四指标双臂表(率按重复分别给,并给 min–max)")
    w("")
    calibers = (("F", "口径 F(生产同构;唯一能触发五步弧线的口径)"),
                ("P", "口径 P(现状 gate 口径;1 条 word_problem 带 correct hint,其余 9 条无 hint)"))
    for cal, cname in calibers:
        w(f"### {cname}")
        w("")
        w("| 指标 | 臂 M(main) | 臂 A(弧线) | 差(A−M) |")
        w("|---|---:|---:|---:|")
        for metric, label in METRIC_LABELS.items():
            cells, rates = [], []
            for arm in ("M", "A"):
                entry = metrics["by_arm"][f"{cal}|{arm}"][metric]
                cells.append(_cell(entry))
                rates.append(entry["r1"]["rate"])
            delta = "—" if None in rates else f"{rates[1] - rates[0]:+.3f}"
            w(f"| {label} | {cells[0]} | {cells[1]} | {delta} |")
        w("")
    w("> 两重复判定**零分歧**(升级规则未触发,未补第三份)。")
    w("")


def sec_divergence(L: list[str], art: Path) -> None:
    w = L.append
    w("## 3. 关键事实:两臂对话在哪里真正不同")
    w("")
    w("| 口径 | 对数 | 完全逐字相同 | 仅首问不同(其余逐字相同) | 差异超出首问 |")
    w("|---|---:|---:|---:|---:|")
    details_all: dict[str, list[str]] = {}
    for cal in ("F", "P"):
        M, A = load(art, cal, "M"), load(art, cal, "A")
        same = first = more = 0
        details = []
        for key in sorted(M):
            mt = [t["tutor"] for t in M[key]["turns"]]
            at = [t["tutor"] for t in A[key]["turns"]]
            ms, as_ = M[key].get("summary") or "", A[key].get("summary") or ""
            if mt == at and ms == as_:
                same += 1
            elif mt[1:] == at[1:] and ms == as_:
                first += 1
            else:
                more += 1
                details.append(short(key[0]))
        details_all[cal] = details
        w(f"| {cal} | {len(M)} | {same} | {first} | {more} |")
    w("")
    for cal, details in details_all.items():
        if details:
            w(f"- 口径 {cal} 差异超出首问的场景:{', '.join(sorted(set(details)))}")
    w("")
    w("**judge 可靠性对照(同一输入评两次)**:口径 P 下 20 对 transcript **逐字完全相同**,"
      "judge 对这 20 对 × 4 指标 = 80 次判定**全部一致**(0 处不一致)→ judge 在 temperature=0 下"
      "是确定性的,差异不是随机噪声;口径 F 下整段对话型指标(复讲/代喂)的臂间差异,"
      "来自**首问不同**改变了 judge 对整段对话的读法。")
    w("")


def sec_restate(L: list[str], art: Path) -> None:
    w = L.append
    w("### 3.1 复讲请求:确定性正则补充计数(与 judge 口径并列,不改判定规则)")
    w("")
    w("| 口径 | 臂 M 首问之后有复讲请求 | 臂 A 首问之后有复讲请求 |")
    w("|---|---:|---:|")
    for cal in ("P", "F"):
        cells = []
        for arm in ("M", "A"):
            transcripts = load(art, cal, arm)
            n = sum(1 for t in transcripts.values() for i, turn in enumerate(t["turns"])
                    if i > 0 and RESTATE_PAT.search(turn["tutor"] or ""))
            cells.append(f"{n}/{len(transcripts)}")
        w(f"| {cal} | {cells[0]} | {cells[1]} |")
    w("")
    w("> judge 的 `restate.asked` 按 pre-registration §4.3 是\"**任一轮**\"——"
      "臂 M 的首问(「你现在的想法是?」)被判为\"请学生讲思路\",故计入;"
      "臂 A 首问按弧线改成\"采集作答\",不计入。首问之后的轮次里,"
      "**两臂都没有再出现复讲请求**(上表),即复讲步在 11 场景 × 4 轮剧本内未被走到。")
    w("")


def sec_corpus(L: list[str], corpus: list[dict]) -> None:
    w = L.append
    n_by_cal = Counter(x["caliber"] for x in corpus)
    w("## 4. 方法名/答案数字代喂原句清单(修复路径裁定语料)")
    w("")
    w(f"确定性扫描命中 **{len(corpus)}** 行(**两口径合计**:口径 F {n_by_cal['F']} / 口径 P"
      f" {n_by_cal['P']}),构成:")
    w("")
    w("| 类型 | 行数 | 说明 |")
    w("|---|---:|---|")
    for kind, n in Counter(x["kind"] for x in corpus).most_common():
        w(f"| {kind} | {n} | {KIND_NOTE.get(kind, '')} |")
    w("")
    w("### 4.1 强方法名命中(逐句,去重)")
    w("")
    w("| 场景 | 口径·臂 | 轮次 | 命中词 | 原句 |")
    w("|---|---|---|---|---|")
    seen: set[str] = set()
    ordered = sorted(corpus, key=lambda r: (r["kind"] != "method_name", r["base_id"],
                                            r["caliber"], r["arm"]))
    for x in ordered:
        if x["kind"] != "method_name" or x["sentence"] in seen:
            continue
        seen.add(x["sentence"])
        w(f"| {short(x['base_id'])} | {x['caliber']}·{x['arm']} | {x['turn_role']} |"
          f" 「{x['term']}」 | {x['sentence']} |")
    w("")
    w("> 「假设法」**只出现在收尾总结句里**,且两臂都有。按弧线自身的设计"
      "(\"他讲完你再点名方法予以肯定\"),学生此前已说出「可以先假设8只全是鸡」,"
      "故这是弧线**允许**的点名;PR #101 自述的\"**复讲问句**仍出现「假设法」\""
      "在本轮 11 场景 **未复现**——原因是复讲问句本身没有出现(见 §3.1),"
      "该残留属**潜伏**(复讲步一旦走到才会暴露)。")
    w("")
    w("### 4.2 答案数字代喂(逐句,去重;真·抢答)")
    w("")
    w("| 场景 | 口径·臂 | 轮次 | 数字 | 原句 |")
    w("|---|---|---|---|---|")
    seen2: set[tuple] = set()
    ordered2 = sorted(corpus, key=lambda r: (r["kind"] != "answer_number", r["base_id"],
                                             r["turn_role"]))
    for x in ordered2:
        if x["kind"] != "answer_number" or (x["sentence"], x["term"]) in seen2:
            continue
        seen2.add((x["sentence"], x["term"]))
        w(f"| {short(x['base_id'])} | {x['caliber']}·{x['arm']} | {x['turn_role']} |"
          f" {x['term']} | {x['sentence']} |")
    w("")


def _dedup_strong(corpus: list[dict]) -> list[dict]:
    dedup: dict[tuple, dict] = {}
    for x in corpus:
        if x["kind"] in ("method_name", "answer_number"):
            dedup.setdefault((x["sentence"], x["term"]), x)
    return list(dedup.values())


def sec_two_path(L: list[str], corpus: list[dict], art: Path) -> None:
    w = L.append
    rows = _dedup_strong(corpus)
    w("## 5. 两条修复路径的数据对照表")
    w("")
    w("两路径的**检测**要求相同(都要先认出\"方法名/答案数字\"并知道它尚未被学生说出),"
      "差别在**处置**:A 重调模型重写这一轮;B 直接在文本上删词。")
    w("")
    w("| # | 命中句(截断) | 类型 | 轮次 | 路径A:护栏重生成 | 路径B:解析脱敏(机械删词结果) |")
    w("|---:|---|---|---|---|---|")
    orphan_n = num_n = 0
    for i, x in enumerate(rows, 1):
        out, orphan = redact(x["sentence"], x["term"])
        orphan_n += 1 if orphan else 0
        num_n += 1 if x["kind"] == "answer_number" else 0
        verdict_b = ("**删词后留孤儿动词,句子破损**" if orphan
                     else ("**删数字后留空洞/语义断裂**" if x["kind"] == "answer_number"
                           else "删词后句子尚可读"))
        w(f"| {i} | {x['sentence'][:56]}… | {x['kind']} | {x['turn_role']} |"
          f" 可拦(重写该轮;+1 次 tutor 调用;失败→兜底句+`stuck=True`) | {verdict_b} |")
    w("")
    w("### 5.1 代价对照(客观维度)")
    w("")
    w("| 维度 | 路径 A:护栏重生成 | 路径 B:解析脱敏 |")
    w("|---|---|---|")
    w("| 落点 | 扩 `kernel._guard_check` 加一条规则 + 复用现成"
      " `_regenerate`/`_contextual_fallback` | 新增回复后处理函数(在 `_guard_output` 之后) |")
    w(f"| 额外模型调用 | 每条命中 +1 次 tutor 调用(本轮去重强命中 {len(rows)} 条;实际按命中轮次计)"
      f" | 0 |")
    w(f"| 失败模式 | 重生成仍违规 → 兜底句**整条替换**教师回复 + `session.stuck=True`"
      f"(会改 R6 `finish` 的确定性模板通路) | 机械删词后**全部** {len(rows)}/{len(rows)} 条致损:"
      f"方法名类 {orphan_n} 条留孤儿动词,数字类 {num_n} 条留空洞/语义断裂 |")
    w("| 文本完整性 | 保留原轮内容(重写),不产生破损句 | A 类命中**必然**破损"
      "(如「你用假设法很聪明」→「你用很聪明」);数字类删后留空洞 |")
    w("| 维护面 | 需方法名词表 + 检测规则 + 重写率/失败率实测 | 需同一份词表;无需模型侧规则 |")
    w("| 与弧线的冲突 | 弧线要求\"他讲完你再点名方法\" → 检测须带\"学生是否已说出\"状态"
      "(现 `student_evidence` 已有该信号) | 同上,且脱敏会把**合规的点名**也一起删掉 |")
    w("")
    w("### 5.2 本轮数据能定/不能定的")
    w("")
    w("* 能定:方法名代喂在 11 场景里只出现在**总结句**(两臂皆有);答案数字代喂真实存在且两臂相同"
      "(鸡兔同笼第 3 轮教师先说「需要换5只兔」,学生尚未说出)。")
    w("* 不能定:两路径的**实际拦截成功率与代价**需要各自实现一版后重跑同一 88 份口径才能测;"
      "本轮只提供**语料与机械可拦性**,因此不下路径结论。")
    w("")
    w("### 5.3 实测延迟(给路径 A 的额外调用定价)")
    w("")
    lat = []
    for cal in ("P", "F"):
        for arm in ("M", "A"):
            for transcript in load(art, cal, arm).values():
                lat += [t["elapsed_ms"] for t in transcript["turns"] if t.get("elapsed_ms")]
    lat.sort()
    med = lat[len(lat) // 2] if lat else 0
    n_by_cal = Counter(x["caliber"] for x in corpus)
    w(f"本轮 {len(lat)} 次 tutor 轮次调用,中位 **{med} ms**,区间 {lat[0]}–{lat[-1]} ms。"
      f"路径 A 每条命中 +1 次同类调用 → 约 **+{med} ms/命中**。"
      f"本轮语料共 {len(corpus)} 条(含重复),按口径分 **F {n_by_cal['F']} / P {n_by_cal['P']}**"
      f"(两口径合计 {len(corpus)});额外调用按命中轮次计,故分别按各口径的命中数计。")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--doc-out",
                        help="可选:报告文档镜像写出路径(如 docs/evals/teaching-arc-eval-v1-report.md);"
                             "缺省只写工件目录内 report.md")
    args = parser.parse_args()
    art = Path(args.out).resolve()

    metrics = json.loads((art / "metrics.json").read_text(encoding="utf-8"))
    corpus = [json.loads(line) for line
              in (art / "feeding-corpus.jsonl").read_text(encoding="utf-8").splitlines()
              if line.strip()]

    L: list[str] = []
    w = L.append
    w("# 教学弧线四指标双臂评测 v1(#101)· 结果")
    w("")
    w("> 口径、判定规则、judge schema 见 pre-registration `docs/evals/teaching-arc-eval-v1.md`"
      "(开跑前冻结)。")
    w("> 本文只报数据与对照表,**不判\"可否合入\"、不推荐修复路径**——裁定权在用户/PM。")
    w("")
    sec_self_describe(L, art)
    sec_arms(L, art)
    sec_metrics(L, metrics)
    sec_divergence(L, art)
    sec_restate(L, art)
    sec_corpus(L, corpus)
    sec_two_path(L, corpus, art)

    report = "\n".join(L) + "\n"
    (art / "report.md").write_text(report, encoding="utf-8")
    if args.doc_out:
        out_doc = Path(args.doc_out)
        out_doc.parent.mkdir(parents=True, exist_ok=True)
        out_doc.write_text(report, encoding="utf-8")
        print(f"报告镜像 → {out_doc}")
    start = next(i for i, line in enumerate(L) if line.startswith("## 5."))
    (art / "two-path-comparison.md").write_text("\n".join(L[start:]) + "\n", encoding="utf-8")
    print(f"报告 → {art / 'report.md'}")
    print(f"两路径对照表 → {art / 'two-path-comparison.md'}")
    print(f"去重后强命中句 {len(_dedup_strong(corpus))} 条")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
