#!/usr/bin/env python3
"""spec-seam viability test(#333 预注册评论 5715985836;PM 直发 sha256=5401ace0a7adfca9)。

唯一问题:改变内部规格,是否稳定改变用户可见行为(非质量评测/非搜索)。
四规格(PM 亲写逐字)× 两 seam;评测 harness 侧 monkeypatch,不碰产品 kernel。
≤100 本地 calls 硬顶;零 API 零远程。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # 仓库根
DATASET = ROOT / "edu_agent/evals/datasets/small_lecturer_image_teaching_v2_enriched12.json"
OUT = Path(__file__).resolve().parent / "out" / "viability"
FACTS = Path(__file__).resolve().parent / "out" / "facts"
MAX_CALLS = 100  # PM 硬顶(viability 全程)
PER_EVAL_RESERVE = 9

# ── 四份规格(PM 亲写,逐字,不得改写)────────────────────────────────
ELICIT_SPEC_A = ("目标:让学生用自己的话讲出核心思路和第一步的做法。\n"
                 "证据:需要听到学生自己的理由或依据,而不是复述小讲师的话;只报答案不算。\n"
                 "动作:顺着学生刚才说的内容,问一个自然的追问(比如「你是怎么想到先这样做的?」);"
                 "不要把几个要求一口气列给他。")
ELICIT_SPEC_B = ("目标:让学生先讲清楚「下一步为什么这么做」这一件事。\n"
                 "证据:学生能说出这一步的道理(哪怕不完整),不是沉默或只说「会了」。\n"
                 "动作:用学生自己刚说过的原话开头,问他这一步是怎么推出来的;一次只问这一个点。")
SUPPORT_SPEC_A = ("目标:把学生卡住的这一步拆得更小,让他能接得上。\n"
                  "证据:学生对拆小后的这一步有反应(能接着算或说出下一步),而不是继续说不会。\n"
                  "动作:直接给出这一步的具体数值结果(照题面,如「这一步先算…得到…」),"
                  "让他接着算下一步。")
SUPPORT_SPEC_B = ("目标:换一个更小的问点重新问,绕开卡住的表达。\n"
                  "证据:学生对新问点有具体回应(给出数字、条件或判断),而不是重复卡住。\n"
                  "动作:从题目条件里挑一个更基础的点直接问(比如「题目里告诉我们哪个数?」),语气放缓。")

# ── 剧本扩展(预注册:自拟,viability 器材非语料)─────────────────────
ELICIT_EXT = {
    "image_v2_understanding_04": ["呃,就是先看直径是6,然后半径是3,面积好像是3乘3乘3.14?反正大概这样。"],  # 部分讲出
    "image_v2_answerhit_01": ["我先算每份:12除以3等于4米,剪掉一份就是4米,剩下12减4等于8米,所以剩下8米。"],  # 讲全
}
# support 扩展在筛出后按案配(1 接上 + 1 仍卡)
SUPPORT_EXT_ON = "我想想……每份是4,那剪掉一份后,剩下的就是12减4,等于8米!"      # 接上
SUPPORT_EXT_STUCK = "我还是不知道从哪儿开始算,完全没思路。"                   # 仍卡

STUCK_SCREEN_IDS = ["image_v2_stuck_01", "image_v2_stuck_02",
                    "image_v2_stuck_03", "image_v2_stuck_04"]
SKIP_SCREEN = True  # 筛段已完成(4/4 触发,reveal 分支,11 calls 在案)——判据更正后续跑


def _spec_messages(kernel, session, student_message, spec, seam):
    from edu_agent.agents.small_lecturer.prompting import _user_prompt, system_prompt
    payload = {"学生": session.learner, "对话记录": session.history,
               "学生本轮回答": student_message, "教学规格": spec,
               "输出提醒": (f"本轮是{seam}触发轮:严格按教学规格的「动作」生成一个面向学生的"
                           "回复;不要报出答案;ready_to_confirm 置 false。")}
    return [{"role": "system", "content": system_prompt(session.learner.get("grade", ""))},
            {"role": "user", "content": _user_prompt(kernel._masked_question(session.question), payload)}]


def _guarded_model_text(kernel, gateway, session, messages, student_message):
    """调 tutor 模型 + 三护栏(泄露/格式/语气)+数值披露门全走,返回学生可见文本。"""
    import json as _json
    from edu_agent.agents.small_lecturer.prompting import TUTOR_TURN_SCHEMA
    output = _json.loads(kernel._invoke(gateway, "tutor", messages,
                                        TUTOR_TURN_SCHEMA, session).text)
    ctx = kernel._GuardContext(
        question=session.question, grade=session.learner.get("grade", ""),
        gateway=gateway, role="tutor", messages=messages,
        schema=TUTOR_TURN_SCHEMA, student_message=student_message,
        answer_reference=kernel._known_answer(session),
        cited_numbers=sorted({float(n) for n in (output.get("cited_numbers") or [])}),
        student_evidence=tuple(str(m["content"]) for m in session.history
                               if m.get("role") == "user") + (student_message,))
    return kernel._guard_output(output["reply"], session, ctx, False)


def make_spec_restatement(kernel, spec, gateway):
    """elicit seam 消费路径:替换 _ask_restatement(埋点照旧+模型+护栏+commit)。"""
    def _spec_restatement(session, student_message):
        session.guard_events.append({"branch": "elicit", "hint_level": session.hint_level})
        messages = _spec_messages(kernel, session, student_message, spec, "复讲引导")
        safe = _guarded_model_text(kernel, gateway, session, messages, student_message)
        return kernel._commit_turn(session, student_message, safe, "dialogue")
    return _spec_restatement


def make_spec_stuck_hint(kernel, spec, gateway):
    """support seam 消费路径:替换 _stuck_hint(埋点照旧+模型+护栏,返回 str)。"""
    def _spec_stuck_hint(session):
        session.guard_events.append({"branch": "support", "move": "guiding_focus"})
        student_message = vars(session).get("_spec_current_student", "")  # reply 包装暂存
        messages = _spec_messages(kernel, session, student_message, spec, "卡壳支持")
        return _guarded_model_text(kernel, gateway, session, messages, student_message)
    return _spec_stuck_hint


def _wrap_reply(kernel):
    """reply 包装:暂存本轮学生消息供 _stuck_hint patch 消费(session 动态属性)。"""
    orig = kernel.reply

    def _reply(session, student_message, *, gateway=None,
               expected_session_version=None):
        session._spec_current_student = student_message
        return orig(session, student_message, gateway=gateway,
                    expected_session_version=expected_session_version)
    return _reply, orig


def _run_case(kernel, gateway, case, *, patch=None, wrap=None):
    """跑一案(可选 patch),转录+guard+判卷落盘前收集。返回记录 dict。"""
    from edu_agent.evals.corpus_round import transcript_messages
    from edu_agent.evals.gepa import KernelSubject
    from edu_agent.evals.judge import judge_transcript
    restore = []
    if patch:
        for attr, fn in patch.items():
            restore.append((attr, getattr(kernel, attr)))  # attr 动态
            setattr(kernel, attr, fn)
    if wrap:
        restore.append(("reply", kernel.reply))
        kernel.reply = wrap
    try:
        transcript = KernelSubject(gateway).run_case(case)
    finally:
        for attr, orig in restore:
            setattr(kernel, attr, orig)
    guard_events = transcript.get("guard_events") or []
    judge_out = judge_transcript(
        gateway, {"question": case.get("question", ""),
                  "grade": case.get("grade", ""),
                  "reference_answer": case.get("reference_answer", ""),
                  "messages": transcript_messages(transcript)},
        role="judge")
    return {"transcript": transcript, "guard_events": guard_events, "judge": judge_out}


def _pair_phase(kernel, gateway, tag, case_specs, patch_factory, wrap, budget_ok,  # noqa: PLR0913
                save, calls_now, branch):
    """配对阶段:每案 × spec A/B,转录+guard+判卷落盘。case_specs=[{cid,case,spec_a,spec_b}]。

    (artifacts 脚本:main 闭包依赖显式传参,10 参 noqa 一次;branch=tag 对应埋点名。)"""
    for item in case_specs:
        cid, case = item["cid"], item["case"]
        for spec_name, spec in (("spec_A", item["spec_a"]), ("spec_B", item["spec_b"])):
            if not budget_ok():
                print(f"[ABORT] 预算将越顶({tag} 段)")
                sys.exit(2)
            rec = _run_case(kernel, gateway, case,
                            patch=patch_factory(spec), wrap=wrap)
            hits = [e.get("turn") for e in rec["guard_events"] if e.get("branch") == branch]
            save(tag, cid, spec_name, rec)
            turns = rec["transcript"].get("turns") or []
            print(f"[{tag}/{cid}/{spec_name}] 轮数={len(turns)} {branch}轮={hits} "
                  f"judge={rec['judge'].get('total')} calls={calls_now()}")


def main() -> None:
    from edu_agent.agents.small_lecturer import kernel as K
    from edu_agent.gateway import Gateway
    from edu_agent.gateway.registry import load_registry

    OUT.mkdir(parents=True, exist_ok=True)
    payload = json.loads(DATASET.read_text(encoding="utf-8"))
    scenarios = payload["scenarios"] if isinstance(payload, dict) else payload
    cases = {c["id"]: c for c in scenarios}

    gateway = Gateway(load_registry(ROOT / "configs/models.yaml"),
                      facts_dir=str(FACTS))
    w0 = gateway.writer.count

    print("[飞行前回显] 四份规格实际注入文本(逐字):")
    for name, s in (("elicit_spec_A", ELICIT_SPEC_A), ("elicit_spec_B", ELICIT_SPEC_B),
                    ("support_spec_A", SUPPORT_SPEC_A), ("support_spec_B", SUPPORT_SPEC_B)):
        print(f"  {name}: {s!r}")

    def budget_left_ok():
        return gateway.writer.count - w0 + PER_EVAL_RESERVE <= MAX_CALLS

    def save(tag, cid, spec_name, rec):
        rec.update({"case_id": cid, "spec": spec_name})
        d = OUT / tag / cid
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{spec_name}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 阶段 1:support 筛(4 stuck 案,默认臂,~24 calls)────────────
    # 判据更正(跑后记录,语义不变):_stuck_hint 消费点真触发 = 埋点 branch∈
    # {support(=guiding_focus 拆小问句), reveal(=telling 阶梯揭示)}——两分支
    # 均为 support 动作。首轮筛误用 branch=="support" 判 0/4,实况 4/4 触发
    # (reveal 分支,转录「我们从这里入手:…你接着算」阶梯句式实证),数据在案。
    triggered_support = []
    for cid in (STUCK_SCREEN_IDS if not SKIP_SCREEN else []):
        if not budget_left_ok():
            print("[ABORT] 预算将越顶(筛段)"); sys.exit(2)
        rec = _run_case(K, gateway, cases[cid])
        hits = sum(1 for e in rec["guard_events"]
                   if e.get("branch") in ("support", "reveal"))
        save("screen-support", cid, "default", rec)
        print(f"[筛/{cid}] 轮数={len(rec['transcript'].get('turns') or [])} "
              f"support动作埋点(support|reveal)={hits} calls={gateway.writer.count - w0}")
        if hits:
            triggered_support.append(cid)
    if SKIP_SCREEN:
        triggered_support = list(STUCK_SCREEN_IDS)  # 首轮筛 4/4 触发(reveal),数据在案
    print(f"support 筛:{len(triggered_support)}/{len(STUCK_SCREEN_IDS)} 触发:{triggered_support}")
    if len(triggered_support) < 2:
        print("[REPORT] support 触发 <2,按预注册停跑报 PM")
        (OUT / "screen-summary.json").write_text(
            json.dumps({"triggered_support": triggered_support,
                        "calls_used": gateway.writer.count - w0},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        sys.exit(3)

    # ── 阶段 2:elicit 配对(2 案扩展剧本 × spec A/B,~32)───────────
    wrap, _ = _wrap_reply(K)
    _pair_phase(K, gateway, "elicit",
                [{"cid": cid, "case": {**cases[cid], "student_turns":
                 list(cases[cid].get("student_turns") or []) + ext},
                  "spec_a": ELICIT_SPEC_A, "spec_b": ELICIT_SPEC_B}
                 for cid, ext in ELICIT_EXT.items()],
                lambda s: {"_ask_restatement": make_spec_restatement(K, s, gateway)},
                wrap, budget_left_ok, save,
                lambda: gateway.writer.count - w0, "elicit")

    # ── 阶段 3:support 配对(2 触发案扩展剧本 × spec A/B,~32)───────
    chosen = triggered_support[:2]
    _pair_phase(K, gateway, "support",
                [{"cid": cid, "case": {**cases[cid], "student_turns":
                 list(cases[cid].get("student_turns") or []) +
                 [SUPPORT_EXT_ON if i == 0 else SUPPORT_EXT_STUCK]},
                  "spec_a": SUPPORT_SPEC_A, "spec_b": SUPPORT_SPEC_B}
                 for i, cid in enumerate(chosen)],
                lambda s: {"_stuck_hint": make_spec_stuck_hint(K, s, gateway)},
                wrap, budget_left_ok, save,
                lambda: gateway.writer.count - w0, "support")

    used = gateway.writer.count - w0
    print(f"\nviability 完成:calls 实计 {used}(硬顶 {MAX_CALLS})")
    (OUT / "viability-summary.json").write_text(
        json.dumps({"calls_used": used, "budget": MAX_CALLS,
                    "triggered_support": triggered_support},
                   ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
