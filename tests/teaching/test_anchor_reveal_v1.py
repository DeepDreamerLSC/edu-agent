"""#333 泄露网 V1 锚/终答测试面——三层测试之①②(裁定 c5717512971;PM 49255c5dba108a0b)。

①Q5 第二层四断言(首次 stuck 不给数值 / 再次 stuck 给当前级非终答锚 / 单步题
repeated stuck 仍不给 / 部件重叠仍不给)+ ②Q5 第一层边界对 C/D/F(support 零锚 /
ready_to_confirm 禁 / 答案不可判定 fail-closed)。种子 = 同目录 seeds-anchor-v1.json
(A-D/M/F 七对);走**公开面驱动**(start/reply + FakeGateway,与 test_kernel_restate
同款口径),steps 经 open payload 注入(种子里 steps 为合成 plan 步,已标注)。
92/93 泄漏=0 硬门 = 既有套件(test_answer_leak_guardrails + test_kernel_invariants)
保持全绿,merge blocker 口径见 docs/plan/07-leak-net-v1.md。

V1 授权面(裁定原文):终答数字永远 protected;中间步锚仅 deterministic reveal/telling
路径 × 仅当前 next step 的 value × anchor=value数字−answer_pool 非空且 ∩answer_pool=∅
× 仅 hint_level>0 且再次 stuck × ready_to_confirm 禁止;模型自由生成路径零例外。
埋点:reveal 事件 additive 键 `anchor_numbers`(Q6,只在授权轮写;未授权轮不加键)。
"""

from __future__ import annotations

import json
from pathlib import Path

from edu_agent.agents.small_lecturer import FIRST_QUESTION_COLLECT, reply, start

from teachkit import FakeGateway

SEEDS_PATH = (
    Path(__file__).resolve().parents[2]
    / "edu_agent" / "evals" / "artifacts" / "leak-net-v1-testface" / "seeds-anchor-v1.json"
)
SEEDS = {s["name"]: s for s in json.loads(SEEDS_PATH.read_text(encoding="utf-8"))["seeds"]}


def _open_payload(reply_text: str, steps: list[dict]) -> dict:
    return {"acceptable": True, "transcription": "", "steps": steps, "reply": reply_text}


def _tutor_payload(reply_text: str, ready: bool = False) -> dict:
    return {"reply": reply_text, "ready_to_confirm": ready, "cited_numbers": []}


def _drive(seed: dict, stuck_rounds: int, student_messages=None):
    """种子 → 会话弧:open 注入合成 steps;每轮把上一轮学生可见文本喂给模型复读
    (复读→重生成仍复读→兜底揭示下一级,同 test_kernel_restate 口径)。
    第 1 次 reveal = 首次 stuck(hint_level 0→1);第 2 次起 = 再次 stuck。
    student_messages:分轮学生消息(缺省每轮同句卡壳话姿)。"""
    fx = seed["session"]
    gateway = FakeGateway(tutor_payloads=[_open_payload(FIRST_QUESTION_COLLECT, [dict(s) for s in fx["steps"]])])
    question = {"text": fx["question"]["text"], "answer": fx["question"]["answer"],
                "analysis": "", "knowledge_points": []}
    first = start(question, dict(fx["learner"]), gateway=gateway)
    messages = ([student_messages] * stuck_rounds if isinstance(student_messages, str)
                else list(student_messages or ["嗯,我看看,还是不会。"] * stuck_rounds))
    prev, turn = FIRST_QUESTION_COLLECT, None
    for message in messages:
        gateway.tutor_queue.extend([_tutor_payload(prev), _tutor_payload(prev)])
        turn = reply(first.session if turn is None else turn.session, message, gateway=gateway)
        prev = turn.text
    return turn


def _reveal_events(turn) -> list[dict]:
    return [e for e in turn.session.guard_events if e.get("branch") == "reveal"]


# ---------- ① Q5 第二层四断言(PM 派单任务③) ----------


def test_first_stuck_gives_no_numbers():
    """首次 stuck(hint_level 0→1)只给动作化步骤,**不给任何数值锚**
    (现状 soften 行为保持;V1 不放宽首次——本级 16 也不上学生面)。"""
    turn = _drive(SEEDS["A_anchor_legal_intermediate_not_answer"], stuck_rounds=1)
    for value in ("16", "10", "5"):
        assert value not in turn.text
    assert not _reveal_events(turn)[-1].get("anchor_numbers")


def test_restuck_gives_current_level_non_answer_anchor():
    """再次 stuck → 给**当前级非终答**锚(A 类:10 ∉ answer_pool{3,5};
    只当前级,不扫全 steps——16 不出现,5=终答部件不出现)。"""
    turn = _drive(SEEDS["A_anchor_legal_intermediate_not_answer"], stuck_rounds=2)
    assert "10" in turn.text
    assert "16" not in turn.text and "5" not in turn.text
    assert _reveal_events(turn)[-1]["anchor_numbers"] == [10.0]  # Q6:additive 字段


def test_single_step_repeated_stuck_still_withholds():
    """单步题(value=终答)repeated stuck **仍不给**——唯一可锚级=终答,永无 value 锚
    (第 2 轮耗尽 → bottom-out 披露终答 = 设计内路径,不记锚)。"""
    for name in ("B_single_step_collision_stuck02", "B_single_step_collision_answerhit01"):
        turn = _drive(SEEDS[name], stuck_rounds=2)
        assert not any(e.get("anchor_numbers") for e in _reveal_events(turn))


def test_step_value_overlapping_answer_part_still_withholds():
    """step value 与 answer **部件**重叠仍不给(C 类多部件全保护,
    understanding_04:answer_pool={6,3},两级 value 均重叠 → 整梯无锚)。"""
    turn = _drive(SEEDS["M_multi_part_overlap_still_withheld"], stuck_rounds=2)
    assert not any(e.get("anchor_numbers") for e in _reveal_events(turn))
    assert "3" not in turn.text and "6" not in turn.text


# ---------- ② Q5 第一层边界对 C/D/F(七条件单面验证) ----------


def test_C_support_guiding_focus_gives_no_anchor():
    """C 非 telling 路径 → 零锚:学生上一轮复述了当前级数字(「脚数差是10」)→
    下一轮卡住走 guiding_focus 拆小问句(只问不揭示,#169 不含数字)——
    support 轮无 reveal 事件、无 anchor_numbers(此前轮的合法锚不受影响)。"""
    seed = SEEDS["C_support_guiding_focus_no_anchor"]
    turn = _drive(seed, stuck_rounds=3,
                  student_messages=["嗯,我看看,还是不会。", "哦,全部按鸡是16只脚,然后呢。", "还是不会。"])
    assert turn.session.guard_events[-1]["branch"] == "support"
    assert turn.session.guard_events[-1]["move"] == "guiding_focus"
    assert not any(ch.isdigit() for ch in turn.text)


def test_D_ready_state_demoted_by_stuck_anchor_resumes():
    """D ready_to_confirm → 禁(#333 七条件,kernel 保留防直接调用方)。公开流实证:
    学生卡壳信号先把确认态降回 dialogue(t2)→ re-stuck 锚按**当前态**授权——
    本测试钉住「state 检查读当前态」:若误用陈旧 ready 旗,t3 的合法锚会被错拦。
    ready 态与 re-stuck 在公开流互斥(卡壳即降态),防御条件由源读核验。"""
    seed = SEEDS["D_ready_to_confirm_blocks_anchor"]
    fx = seed["session"]
    gateway = FakeGateway(tutor_payloads=[_open_payload(FIRST_QUESTION_COLLECT, [dict(s) for s in fx["steps"]])])
    question = {"text": fx["question"]["text"], "answer": fx["question"]["answer"],
                "analysis": "", "knowledge_points": []}
    first = start(question, dict(fx["learner"]), gateway=gateway)
    # 轮1:学生自述答案 + 模型 ready → 合法确认态(test_kernel_restate 同款口径)
    gateway.tutor_queue.extend([_tutor_payload("我们把思路理清楚了。", ready=True)])
    turn1 = reply(first.session, "鸡3只,兔5只。", gateway=gateway)
    assert turn1.state == "ready_to_confirm"
    # 轮2/3:确认态下卡壳 → 降回 dialogue → 背板揭示第2级 → 锚按当前态授权
    gateway.tutor_queue.extend([_tutor_payload(turn1.text)] * 2)
    turn2 = reply(turn1.session, "嗯,我看看,还是不会。", gateway=gateway)
    assert turn2.session.state == "dialogue"  # 卡壳信号降态
    gateway.tutor_queue.extend([_tutor_payload(turn2.text)] * 2)
    turn3 = reply(turn2.session, "嗯,我看看,还是不会。", gateway=gateway)
    assert _reveal_events(turn3)[-1]["anchor_numbers"] == [10.0]


def test_F_answer_undeterminable_fail_closed():
    """F 答案侧不可判定(纯文字答案)→ 保守不给:answer_pool=∅ 时锚数字面无从
    验证保护,空 value 步不入梯(_store_steps 口径)→ 首轮耗尽 bottom-out,全程零锚。"""
    turn = _drive(SEEDS["F_answer_undeterminable_fail_closed"], stuck_rounds=2)
    assert not any(e.get("anchor_numbers") for e in _reveal_events(turn))
