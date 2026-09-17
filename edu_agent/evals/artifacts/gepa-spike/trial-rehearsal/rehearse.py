"""#332/#333 试跑彩排(零模型):真实命令路径 + 假上游 + 真计量面。

按 gepa_driver 的非配对分支路径跑:v2 93 案池 + GepaConfig + gepa_loop
真实现;只 patch 模型面(ElicitSubject/judge/编辑器,gepa 与 gepa_paired
两命名空间),每假调用写一条真 facts(FactWriter 落盘)——预算台账/
分项/facts 三方对账。

场景:A 典型(无替换)/ B 最坏(每代替换+配对)/ C 换批触发(7 代)/
D 新增 hard fail 拒 / E 阈值边界(0.125 过/0.124 拒)/ F fail→review。
跑法:python -m edu_agent.evals.artifacts.gepa-spike.trial-rehearsal.rehearse
(路径含连字符,直接 python edu_agent/evals/artifacts/gepa-spike/trial-rehearsal/rehearse.py)
"""

import itertools
import json
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[5]  # 仓库根(uv run 下项目已 editable
# install,edu_agent 无 cwd 依赖即可导入;ROOT 只用于定位语料与输出工件)

from edu_agent.agents.small_lecturer import kernel
from edu_agent.evals import GepaConfig, gepa_loop, sample_stratified_batch
from edu_agent.gateway.middleware.record import FactWriter

_STRATA = (("understanding", kernel._student_signals_understanding),
           ("stuck", kernel._student_signals_stuck),
           ("completion", kernel._student_signals_completion))


def _composition(cases):
    """批构成统计(与 sample_stratified_batch 同词形口径,彩排自含核验)。"""
    comp = {"understanding": 0, "stuck": 0, "completion": 0, "background": 0}
    for c in cases:
        turns = [t for t in c.get("student_turns") or [] if isinstance(t, str)]
        for name, fn in _STRATA:
            if any(fn(t) for t in turns):
                comp[name] += 1
                break
        else:
            comp["background"] += 1
    return comp

V2_CASES = [json.loads(line) for line in
            (ROOT / "edu_agent/evals/artifacts/corpus-round-v2/cases.jsonl")
            .read_text(encoding="utf-8").splitlines() if line.strip()]
INITIAL = "我们从头把思路串一遍——先说说你第一步算了什么、为什么这样算。"
OUT = Path(__file__).resolve().parent / "out"
BATCH_CASE_IDS = []  # main() 填充:分层批案 ID(场景覆盖键用批内案)

# 场景注入的假读数(探索批/初始/参考 → total;配对臂 → total)
SCENE: dict = {}


def _variant(n: int) -> str:
    """干支序变体名:无数字(Net A 扫描不撞答案值),含 lint 核心词。"""
    return f"变体{'甲乙丙丁戊己庚辛'[n - 1]}:讲讲思路的第一步,想想为什么"


def _facts(writer: FactWriter, kind: str, template: str) -> None:
    writer.write({"gen_ai.usage.input_tokens": 10, "gen_ai.usage.output_tokens": 5,
                  "trial_rehearsal": {"kind": kind, "template": template[:24]}})


class FakeSubject:
    """假上游转录面:写 1 条 facts(tutor),transcript 携带模板供判卷分流。"""

    def __init__(self, template, gateway, support_hint=None):
        self._template, self._gateway = template, gateway

    def run_case(self, case):
        _facts(self._gateway.writer, "tutor", self._template)
        # tutor 首轮 = 模板原文(elicit 注入的真实语义;模板无数字,Net A 安全)
        return {"turns": [{"student": "", "tutor": self._template,
                           "state": "dialogue"}],
                "summary": "s", "_template": self._template}


def _fake_score(gateway, judge_case, role="judge"):
    """假判卷(探索批):judge_case/messages 形态;按 messages 内模板分流给分。"""
    text = "".join(m.get("content", "") for m in judge_case.get("messages", []))
    _facts(gateway.writer, "judge", text[:24])
    total = 9.0
    for tpl, score in SCENE["scores"].items():
        if tpl in text:
            total = score
            break
    return {"total": total, "verdict": "pass", "answer_leaked": False,
            "math_integrity": 2, "evidence": {}, "scores": {}}


def _fake_paired_score(gateway, case, transcript, judge_role="judge"):
    """假判卷(配对臂):写 1 条 facts(judge),分表 + 指定案 hard 覆盖。"""
    _facts(gateway.writer, "judge", transcript["_template"])
    tpl = transcript["_template"]
    if SCENE["hard"].get((tpl, case.get("id"))):
        return 0.0, "fail", 0, True, []
    if SCENE["review"].get((tpl, case.get("id"))):
        return SCENE["paired"].get(tpl, 9.0), "review", 2, False, []
    return SCENE["paired"].get(tpl, 9.0), "pass", 2, False, []


def _fake_editor_factory(counter):
    def edit(current, failures, gateway, role="judge_independent"):
        _facts(gateway.writer, "editor", current)
        return _variant(next(counter)), "edited"
    return edit


def run_scene(tag, rounds, scores, paired, hard=None, review=None):
    """跑一个场景:返回(对账 dict, round reports)。"""
    out = OUT / tag
    if out.exists():
        shutil.rmtree(out)  # 清场:防上轮失败跑的 facts 追加残留混入对账
    out.mkdir(parents=True)
    SCENE.clear()
    SCENE.update(scores=scores, paired=paired, hard=hard or {}, review=review or {})
    gateway = MagicMock()
    gateway.writer = FactWriter(out / "facts")
    counter = itertools.count(1)
    with patch("edu_agent.evals.gepa.ElicitSubject", FakeSubject), \
         patch("edu_agent.evals.gepa.judge_transcript", _fake_score), \
         patch("edu_agent.evals.gepa.edit_template",
               _fake_editor_factory(counter)), \
         patch("edu_agent.evals.gepa_paired.ElicitSubject", FakeSubject), \
         patch("edu_agent.evals.gepa_paired._score_one_case", _fake_paired_score):
        gepa_loop(train_cases=V2_CASES, initial_template=INITIAL,
                  config=GepaConfig(rounds=rounds, batch_size=16,
                                     max_calls=1_000_000),
                  gateway=gateway, output_dir=out, resume=False)
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    reports = [json.loads((out / f"round-{i:02d}.json").read_text(encoding="utf-8"))
               for i in range(rounds)]
    facts_lines = sum(1 for f in (out / "facts").glob("*.jsonl")
                      for _ in f.open(encoding="utf-8"))
    return {"tag": tag, "rounds": rounds,
            "budget_calls": summary["budget"]["calls"],
            "breakdown": summary["call_breakdown"],
            "facts_lines": facts_lines,
            "accepted": sum(1 for r in reports if r["accepted"]),
            "best": summary["best_candidate"]["template"][:12]}, reports


class Checker:
    """场景断言收集器(端到端 T1-T6 核验)。"""

    def __init__(self):
        self.ok = True

    def __call__(self, tag, cond, detail=""):
        self.ok = self.ok and bool(cond)
        print(f"  [{'PASS' if cond else 'FAIL'}] {tag} {detail}")


def _check_batch() -> dict:
    """T1:分层批构成(v2 池词形实测);返回构成统计,批案 ID 存模块级。"""
    batch = sample_stratified_batch(V2_CASES, 0)
    comp = _composition(batch)
    print(f"[T1] v2 93 案池分层批: {comp} 共 {len(batch)} 案")
    assert len(batch) == sum(comp.values())
    BATCH_CASE_IDS.extend(c.get("id", "") for c in batch)
    return comp


def main():
    comp = _check_batch()
    batch_size = 2 * len(BATCH_CASE_IDS)

    rows = []
    check = Checker()

    # A 典型(无替换):变体探索读数低于参考 → 初筛拒,零配对
    acc, rep = run_scene("A_typical", 2, {INITIAL: 9.0}, {})
    print(f"[A 典型] {acc}")
    check("A-无替换", acc["accepted"] == 0)
    check("A-keep_parent", all(r["screen_evidence"]["decision"] == "keep_parent"
                               for r in rep))
    check("A-best 不变", acc["best"].startswith("我们从头"))
    rows.append(("典型(无替换,2 代)", acc))

    # B 最坏(每代替换+配对)
    acc, rep = run_scene(
        "B_worst", 2,
        {INITIAL: 9.0, _variant(1): 9.5, _variant(2): 11.0},
        {INITIAL: 10.0, _variant(1): 10.5, _variant(2): 11.0})
    print(f"[B 最坏] {acc}")
    check("B-每代替换", acc["accepted"] == 2)
    check("B-lineage", rep[1]["parent_template"] == _variant(1))
    check("B-best=最后确认", acc["best"].startswith("变体乙"))
    rows.append(("最坏(每代替换+配对,2 代)", acc))

    # C 换批触发(7 代无替换):候选 6 起换 cohort 1 + 重评参考
    acc, rep = run_scene("C_cohort", 7, {INITIAL: 9.0}, {})
    print(f"[C 换批] {acc}")
    cohorts = [r["cohort_idx"] for r in rep]
    check("C-前5候选同批", cohorts[:5] == [0] * 5)
    check("C-候选6换批", cohorts[5:] == [1, 1])
    # 评估批数:初始 1 + 参考 2(cohort0/1)+ 变体 7 = 10 批
    per_case = batch_size  # tutor+judge 每案(2×批案数)
    expect = (1 + 2 + 7) * per_case + 7  # +7 编辑器
    check("C-换批重评计入台账", acc["budget_calls"] == expect,
          f"calls={acc['budget_calls']} expect={expect}")
    rows.append(("换批触发(7 代,2 次换批重评)", acc))

    # D 新增 hard fail(配对子臂 1 案)→ 拒
    acc, rep = run_scene(
        "D_hardfail", 3, {INITIAL: 9.0, _variant(1): 9.5, _variant(2): 9.5,
                          _variant(3): 9.5},
        {INITIAL: 10.0, _variant(1): 11.8, _variant(2): 11.8, _variant(3): 11.8},
        hard={(_variant(i), BATCH_CASE_IDS[0]): True for i in (1, 2, 3)})
    print(f"[D hard-fail] {acc}")
    check("D-均值大涨也拒", acc["accepted"] == 0)
    check("D-new_hard_fail", all(
        r["paired_evidence"]["accept_reason"] == "new_hard_fail" for r in rep))
    rows.append(("新增 hard fail(每代配对拒,3 代)", acc))

    # E 阈值边界:Δ=0.125 恰过 → Δ=0.124 恰拒
    acc, rep = run_scene(
        "E_threshold", 2,
        {INITIAL: 9.0, _variant(1): 9.125, _variant(2): 9.25},
        {INITIAL: 9.0, _variant(1): 9.125, _variant(2): 9.249})
    print(f"[E 边界] {acc}")
    check("E-0.125 恰过", rep[0]["accepted"] is True
          and rep[0]["paired_evidence"]["accept_reason"] == "delta_ge_threshold")
    check("E-0.124 恰拒", rep[1]["accepted"] is False
          and rep[1]["paired_evidence"]["accept_reason"] == "keep_parent")
    rows.append(("阈值边界(过/拒各 1 代)", acc))

    # F fail→review:父臂 1 案 fail,子臂同案 review → H 减 U 平 → 接受
    acc, rep = run_scene(
        "F_fail2review", 1, {INITIAL: 9.0, _variant(1): 9.5},
        {INITIAL: 9.0, _variant(1): 9.5},
        hard={(INITIAL, BATCH_CASE_IDS[0]): True},
        review={(_variant(1), BATCH_CASE_IDS[0]): True})
    print(f"[F fail→review] {acc}")
    check("F-不被 U 拒", acc["accepted"] == 1
          and rep[0]["paired_evidence"]["parent_hnu"]["h"] == 1
          and rep[0]["paired_evidence"]["variant_hnu"]["h"] == 0
          and rep[0]["paired_evidence"]["variant_hnu"]["u"] ==
          rep[0]["paired_evidence"]["parent_hnu"]["u"])
    rows.append(("fail→review(1 代)", acc))

    # T6:三方对账(全场景)
    for name, acc in rows:
        bd = acc["breakdown"]
        check(f"T6-{name}", acc["facts_lines"] == acc["budget_calls"] ==
              bd["tutor_calls"] + bd["judge_calls"] + bd["editor_calls"])

    report = {"batch_composition": comp, "batch_size": batch_size // 2,
              "scenarios": [{"name": name, **acc} for name, acc in rows],
              "all_checks_passed": check.ok}
    (OUT / "budget-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== 预算表(实测,facts 三方对账)===")
    for name, acc in rows:
        bd = acc["breakdown"]
        print(f"{name}: calls={acc['budget_calls']} "
              f"(tutor {bd['tutor_calls']} / judge {bd['judge_calls']} / "
              f"editor {bd['editor_calls']})")
    print(f"\nALL CHECKS: {'PASS' if check.ok else 'FAIL'}")
    sys.exit(0 if check.ok else 1)


if __name__ == "__main__":
    main()
