"""#446 B 路线:analysis step.value = 已证明的结果(step metadata 类型契约修正)。

用户终裁(2026-09-25,六门验收冻结):对 provenance=analysis 的 trusted step,
value 不再表示「从片段里抽到的最后一个数字」,只表示「已经由 result_evidence
证明是该步结果的值」;无法证明时 **step 保留、rung 保留、value=""**。修复形态
= 入库门(`_analysis_steps` 内 candidate 在场即入梯、value 过 proof 才承载),
消费面(`_next_step`/`_support_move`/anchor 门)零改动——空值语义自然生效
(reveal fail-open 照发 / support 恒 telling / anchor 弃锚)。

本文件钉两条不变量(#442 规则类型:invariant 修正,非新词表):
· 门 3 硬钉(property):三源(bank/seed/snapshot)全量 analysis step,
  非空 value ⇒ result_evidence(step, value) is not None——非空=已验证、
  空=无验证,不加 value_verified 布尔(YAGNI);
· 持久化红线:入库步键集恰为 {step, value, provenance}——raw candidate 禁入
  dict(不设 candidate_value 字段,`value or candidate_value` 的复活路径在
  schema 层堵死;census/debug 用离线计算)。

门 1(19 poisoned 文本保留+value 空)与门 6(3 verified anchor 值不清空)由
oracle 哨兵 test_anchor_proof_oracle.py::test_frozen_fragments_match_production_slicing
(值语义版)与 live census 门钉住;门 2/4/5(B2 三面复测/shape 零变化/无新增
model fallback)属修复时点的前后对照验收,见 #446 PR 回执。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from edu_agent.agents.small_lecturer import _analysis_steps, result_evidence

_ROOT = Path(__file__).resolve().parents[2]
SOURCES = [
    ("bank", _ROOT / "edu_agent" / "contracts" / "partner_bank.json"),
    ("seed", _ROOT / "edu_agent" / "contracts" / "release_acceptance_seed_question_bank.json"),
    ("snapshot", _ROOT / "edu_agent" / "contracts" / "db_snapshot.json"),
]


def _ladders(path: Path):
    """题库全量记录 → (question_id, ladder);空梯不入(census 同口径)。"""
    for record in json.loads(path.read_text(encoding="utf-8"))["records"]:
        ladder = _analysis_steps(str(record.get("original_analysis") or ""))
        if ladder:
            yield record["question_id"], ladder


@pytest.mark.parametrize("source,path", SOURCES)
def test_nonempty_value_implies_result_evidence(source, path):
    """门 3 硬钉:非空 value ⇒ result_evidence(step, value) 非 None(#446 修复
    契约的全局 invariant)。任何未经证明的数字进入 step.value 即红。"""
    proven = 0
    for _qid, ladder in _ladders(path):
        for step in ladder:
            if step["value"]:
                evidence = result_evidence(step["step"], step["value"])
                assert evidence is not None, (
                    f"{source} {step['step']!r} value={step['value']!r} 无 result-assertion proof")
                assert evidence.value == float(step["value"])
                proven += 1
    if source == "bank":
        # 非空转退化防护:bank 必保有 ≥3 个 proof-backed value(B1 冻结集
        # {6a631dcf, 6a631e95, 6a695670},与 oracle census FROZEN_AFTER 对齐)。
        assert proven >= 3, f"bank proof-backed value 跌破冻结下限:{proven}"


@pytest.mark.parametrize("source,path", SOURCES)
def test_step_schema_forbids_raw_candidate_field(source, path):
    """持久化红线(#446 铁律):入库步键集恰为 {step, value, provenance}——
    raw candidate 禁入 session 持久化(不设 candidate_value 字段);键集变化
    (新增/改名/丢失)即红。"""
    for _qid, ladder in _ladders(path):
        for step in ladder:
            assert set(step) == {"step", "value", "provenance"}, (
                f"{source} 入库步键集漂移:{sorted(step)}")
            assert step["provenance"] == "analysis"


def test_admission_gate_minimal_form():
    """入库门最小形态(#446 用户给定):candidate 在场即入梯(admission 不变,
    无数字片仍不入梯),value = candidate if result_evidence else ""——同片内
    操作数候选(「先取7/18」的分母,B2 审计 6a61b67e 形态)被降格为空,
    等式 RHS 候选保留。"""
    steps = _analysis_steps("先取7/18。再算实际用时:240÷4=60。")
    assert [(s["step"], s["value"]) for s in steps] == [
        ("先取7/18", ""),            # 无 proof:step 保留、value 空
        ("再算实际用时:240÷4=60", "60"),  # explicit_equation_rhs 出证:值保留
    ]
    assert all(s["provenance"] == "analysis" for s in steps)
