"""#333 泄露网 V1 锚/终答测试面——预期断言骨架(PM 88ccdbcabde5da82 任务 4)。

**全部用例 skip**:裁定 c5717512971 的 V1(kernel `_reveal_stuck_hint` 窄授权)**未实现**
——本文件是实现 PR 的激活底稿:断言按裁定 Q5 写死,实现落地后删 skip 即进回归网。
种子(A-D 纯函数边界对,含 viability 4 案)= edu_agent/evals/artifacts/leak-net-v1-testface/
seeds-anchor-v1.json;此处走**公开面驱动**(start/reply + FakeGateway,与 test_kernel_restate
同款口径),steps 经 open payload 注入(数据集不落盘 session.steps,种子里 steps 为合成 plan 步)。

V1 授权面(裁定原文):终答数字永远 protected;中间步锚仅 deterministic reveal/telling
路径 × 仅当前 next step 的 value × anchor=value数字−answer_pool 非空且 ∩answer_pool=∅
× 仅 hint_level>0 且再次 stuck × ready_to_confirm 禁止;模型自由生成路径零例外。
埋点:reveal 事件 additive 键 `anchor_numbers`(Q6);既有键(hint_level/soften/dropped)不动。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from edu_agent.agents.small_lecturer import FIRST_QUESTION_COLLECT, reply, start

from teachkit import FakeGateway

SEEDS_PATH = (
    Path(__file__).resolve().parents[2]
    / "edu_agent" / "evals" / "artifacts" / "leak-net-v1-testface" / "seeds-anchor-v1.json"
)
SEEDS = {s["name"]: s for s in json.loads(SEEDS_PATH.read_text(encoding="utf-8"))["seeds"]}
SKIP_REASON = "#333 V1 未实现——实现 PR 激活(裁定 c5717512971)"


def _open_payload(reply_text: str, steps: list[dict]) -> dict:
    return {"acceptable": True, "transcription": "", "steps": steps, "reply": reply_text}


def _tutor_payload(reply_text: str) -> dict:
    return {"reply": reply_text, "ready_to_confirm": False, "cited_numbers": []}


def _drive(seed: dict, stuck_rounds: int):
    """种子 → 会话弧:open 注入合成 steps,随后 N 轮复读逼出 N 次阶梯揭示
    (第 1 次=首次 stuck,第 2 次起=hint_level>0 再次 stuck)。返回最后一个 Turn。"""
    fx = seed["session"]
    steps = [dict(s) for s in fx["steps"]]
    payloads = [_open_payload(FIRST_QUESTION_COLLECT, steps)]
    payloads += [_tutor_payload(FIRST_QUESTION_COLLECT) for _ in range(stuck_rounds * 2)]
    gateway = FakeGateway(tutor_payloads=payloads)
    question = {"text": fx["question"]["text"], "answer": fx["question"]["answer"],
                "analysis": "", "knowledge_points": []}
    first = start(question, dict(fx["learner"]), gateway=gateway)
    turn = None
    for _ in range(stuck_rounds):
        turn = reply(first.session, "嗯,我看看,还是不会。", gateway=gateway)
    return turn


def _reveal_event(turn) -> dict:
    return [e for e in turn.session.guard_events if e.get("branch") == "reveal"][-1]


@pytest.mark.skip(reason=SKIP_REASON)
def test_first_stuck_gives_no_numbers():
    """Q5 第二层①:首次 stuck(hint_level 0→1)只给动作化步骤,**不给任何数值锚**
    (现状 soften 行为保持;V1 不放宽首次——种 A 的第 1 级 16 也不上学生面)。"""
    turn = _drive(SEEDS["A_anchor_legal_intermediate_not_answer"], stuck_rounds=1)
    for value in ("16", "10", "5"):
        assert value not in turn.text
    assert not _reveal_event(turn).get("anchor_numbers")


@pytest.mark.skip(reason=SKIP_REASON)
def test_restuck_gives_current_level_non_answer_anchor():
    """Q5 第二层②:再次 stuck → 给**当前级非终答**锚(A 类:10 ∉ answer_pool{3,5};
    只当前级,不扫全 steps——16 不出现,5=终答部件不出现)。"""
    turn = _drive(SEEDS["A_anchor_legal_intermediate_not_answer"], stuck_rounds=2)
    assert "10" in turn.text
    assert "16" not in turn.text and "5" not in turn.text
    assert _reveal_event(turn)["anchor_numbers"] == [10.0]  # Q6:additive 字段


@pytest.mark.skip(reason=SKIP_REASON)
def test_single_step_repeated_stuck_still_withholds():
    """Q5 第二层③:单步题(value=终答)repeated stuck **仍不给**——唯一可锚级=终答,
    永无 value 锚;终答只走 bottom-out(设计内披露点,不变量锁在 test_kernel_invariants)。"""
    for name in ("B_single_step_collision_stuck02", "B_single_step_collision_answerhit01"):
        turn = _drive(SEEDS[name], stuck_rounds=2)
        assert not _reveal_event(turn).get("anchor_numbers")
        assert not any(e.get("anchor_numbers") for e in turn.session.guard_events)


@pytest.mark.skip(reason=SKIP_REASON)
def test_step_value_overlapping_answer_part_still_withholds():
    """Q5 第二层④:step value 与 answer **部件**重叠仍不给(C 类多部件全保护,
    understanding_04:answer_pool={6,3},value=3 重叠 → 禁)。"""
    turn = _drive(SEEDS["M_multi_part_overlap_still_withheld"], stuck_rounds=2)
    assert not _reveal_event(turn).get("anchor_numbers")
    assert "3" not in turn.text and "6" not in turn.text
