"""分支跟随器(#178 方案 A):dialogue_scenarios/v2 gold 候选的 loader 接纳与
分支选择契约。零真模型:

- 真 60 条全量 dry 走查——兜底兜得住中性句、带关键词的句子必命中非兜底分支、
  同句重选同支(确定性可复算),并经 build_cases 不再被判「无剧本」;
- FakeGateway 驱动 KernelSubject 走 steps 口径,transcript 与 select_branch 对账;
- loader 对「跟随器跑不动」的 v2 写法(无兜底/不可达/空台词)显式红。

真模型批跑面(corpus_round 对 gold 数据集跑轮)不在本文件——那是运行期工件,
口径见 edu_agent/evals/corpus_round.py。
"""

from __future__ import annotations

import json

import pytest

from edu_agent.evals import (
    DATASETS_DIR,
    KernelSubject,
    build_cases,
    load_shortboard_corpus,
    select_branch,
    to_kernel_case,
)

from teachkit import FakeGateway

GOLD_DATASET = DATASETS_DIR / "small_lecturer_math_gold_candidates.json"


def test_gold_candidates_load_through_corpus_loader():
    """v2 接纳:真 60 条过校验,to_kernel_case 出 steps 口径(非 student_turns)。"""
    scenarios = load_shortboard_corpus(GOLD_DATASET)
    assert len(scenarios) == 60
    cases = [to_kernel_case(s) for s in scenarios]
    assert all(c.get("steps") and "student_turns" not in c for c in cases)
    # corpus_round 接线:分支剧本不算「无剧本」,不再进 skipped 名单
    ran, skipped = build_cases({f"gold_{s['id']}": s for s in scenarios})
    assert len(ran) == 60 and not skipped


def test_branch_selection_deterministic_and_fallback_covers():
    """dry 走查:中性句必落兜底且可复算;每条触发分支按关键词可达。"""
    scenarios = load_shortboard_corpus(GOLD_DATASET)
    for scenario in scenarios:
        for step in scenario["steps"]:
            fallback = select_branch(step["branches"], "嗯。")
            assert fallback["when"]["fallback"]
            assert select_branch(step["branches"], "嗯。") is fallback  # 同句重选同支
            for branch in step["branches"]:
                when = branch["when"]
                if when.get("fallback"):
                    continue
                keys = when.get("assistant_contains_any") or when.get("assistant_contains_all")
                probe = keys[0] if when.get("assistant_contains_any") else "".join(keys)
                selected = select_branch(step["branches"], probe)
                assert not selected["when"]["fallback"]  # 带关键词不该掉兜底
                if selected is not branch:  # 被更早分支截走:探针须真含其关键词
                    hit = (selected["when"].get("assistant_contains_any")
                           or selected["when"].get("assistant_contains_all"))
                    assert any(key in probe for key in hit)


def _when(any_keys=(), fallback=False):
    return {"assistant_contains_any": list(any_keys), "assistant_contains_all": [],
            "interaction_states": [], "fallback": fallback}


def _branch(bid, any_keys, response, fallback=False, kind="correct"):
    return {"id": bid, "response_kind": kind, "when": _when(any_keys, fallback),
            "student_response": response, "trajectory_tags": []}


STEPS_CASE = {
    "id": "equation_addition_complete_reasoning",
    "question": "解方程x+7=25，并说明每一步的依据。",
    "grade": "",
    "steps": [
        {"id": "first_response", "branches": [
            _branch("correct", ["先", "思路"], "先把两边同时减去7。"),
            _branch("correct_clarify", [], "没听懂,再说一遍好吗?", fallback=True, kind="request_hint"),
        ]},
        {"id": "follow_up", "branches": [
            _branch("correct", ["先", "思路"], "25减7等于18,x等于18。"),
            _branch("correct_clarify", [], "我不明白你问的是哪一步。", fallback=True, kind="request_hint"),
        ]},
    ],
}


def test_run_case_follows_branch_script():
    """KernelSubject 驱动 steps:模板首问含「思路」→ correct 分支;追问无关键词 → 兜底。

    首问可见文本是内核固定模板(模型生成文本一律不用),分支匹配跑在模板句上。"""
    gateway = FakeGateway(tutor_payloads=[
        {"acceptable": True, "transcription": "", "steps": [], "reply": "你打算先怎么做?"},
        {"reason": "引导", "reply": "为什么两边都能减7?", "ready_to_confirm": False, "cited_numbers": []},
        {"reason": "确认", "reply": "很好,再同时检查一遍。", "ready_to_confirm": False, "cited_numbers": []},
    ])
    transcript = KernelSubject(gateway).run_case(STEPS_CASE)
    assert [t["student"] for t in transcript["turns"][1:]] == [
        "先把两边同时减去7。", "我不明白你问的是哪一步。"]
    assert transcript["final_state"] == "needs_review"
    # start + 2 reply(needs_review 的 finish 不调模型;恰 3 = 无护栏重生成)
    assert len(gateway.requests) == 3


def test_steps_honor_ready_to_confirm_stop():
    """判停语义对分支剧本同样成立:ready 后余下步骤不再发。"""
    case = {**STEPS_CASE, "steps": STEPS_CASE["steps"] + [
        {"id": "extra", "branches": [_branch("correct", ["先"], "不应该被发出去。")]}]}
    gateway = FakeGateway(tutor_payloads=[
        {"acceptable": True, "transcription": "", "steps": [], "reply": "你打算先怎么做?"},
        {"reason": "确认掌握", "reply": "很好,你已经说出了每一步的做法。", "ready_to_confirm": True,
         "cited_numbers": []},
        {"summary": "学生解出 x=18。"},
    ])
    transcript = KernelSubject(gateway).run_case(case)
    assert [t["student"] for t in transcript["turns"][1:]] == ["先把两边同时减去7。"]
    assert transcript["final_state"] == "completed"
    assert len(gateway.requests) == 3  # start + 1 reply + finish,第三步没被消费


def _write_v2(tmp_path, scenarios):
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(
        {"schema_version": "small_lecturer_dialogue_scenarios/v2", "scenarios": scenarios},
        ensure_ascii=False), encoding="utf-8")
    return path


def test_v2_loader_rejects_unrunnable_branch_scripts(tmp_path):
    """只拦跟随器跑不动的写法:无兜底/非兜底无触发条件(不可达)/空台词。"""
    good = _branch("correct", ["先"], "先算这一步。")
    fallback = _branch("fb", [], "没懂。", fallback=True, kind="request_hint")

    def payload(branches):
        return {"id": "x", "question": "1+1=?", "gold": {"status": "candidate"},
                "steps": [{"id": "s", "branches": branches}]}

    with pytest.raises(ValueError, match="fallback"):
        load_shortboard_corpus(_write_v2(tmp_path, [payload([good])]))
    with pytest.raises(ValueError, match="不可达"):
        load_shortboard_corpus(_write_v2(tmp_path, [payload([{**good, "when": _when()}, fallback])]))
    with pytest.raises(ValueError, match="student_response"):
        load_shortboard_corpus(_write_v2(tmp_path, [payload([{**good, "student_response": ""}, fallback])]))


def test_gold_follow_up_keywords_widened_for_real_tutor_questions():
    """回归测试(#178 c5653783697):follow_up 主分支关键词集加宽后,
    真实导师问句(「25 加 7 是多少?」)不再落兜底句。

    首轮 13 条非边界 needs_review 中 11 条末轮落兜底,机制 = 导师苏格拉底问句
    不含剧本关键词集 → 学生落兜底句不带终答 → 判停闸不过。加宽 follow_up 主分支
    的 assistant_contains_any,补「多少/哪一步/变成/等于」类问数词。"""
    scenarios = load_shortboard_corpus(GOLD_DATASET)
    WIDENED_WORDS = {"多少", "哪一步", "变成", "等于"}
    REAL_TUTOR_QUESTION = "25 加 7 是多少?"

    for scenario in scenarios:
        follow_up = next((st for st in scenario["steps"] if st["id"] == "follow_up"), None)
        if not follow_up:
            continue
        # 主分支(id="correct")的关键词集须含至少一个加宽词
        primary = next((b for b in follow_up["branches"] if b["id"] == "correct"), None)
        assert primary is not None, f"{scenario['id']}: follow_up 缺 correct 分支"
        any_keys = set(primary["when"].get("assistant_contains_any", []))
        assert any_keys & WIDENED_WORDS, (
            f"{scenario['id']}: follow_up correct 分支关键词未加宽 {WIDENED_WORDS}")
        # 真实导师问句须命中非兜底分支
        selected = select_branch(follow_up["branches"], REAL_TUTOR_QUESTION)
        assert not selected["when"].get("fallback"), (
            f"{scenario['id']}: 真实问句「{REAL_TUTOR_QUESTION}」落兜底(应命中加宽关键词)")
