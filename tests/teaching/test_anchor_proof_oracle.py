"""#441 B′ containment 三层验收(B1 分析件 §8 / 终裁 5824408984;Team-Contract: fb232d86)。

① oracle fixture:edu_agent/evals/artifacts/anchor-proof-b1/oracle-anchor-proof.json
   ——23 dev 样本 + 16 合成钉 + 2 negative boundary gold。**expected 为人工冻结
   字面值,只从 JSON 读**;测试内无任何期望计算、无生产函数推导(反 common-mode
   铁条,B1 §8)。切片漂移哨兵:样本 fragment/value 必须逐字等于生产
   `_analysis_steps` 对该题切出的对应片段——bank 数据漂移即红,强制人工重裁。
② property/mutation:五组定向变形(去结果结构/改结果数字/加无关操作数/分母
   操作参数不因末尾成结果/equation RHS structural)钉「先找结果陈述,再绑定
   数字」的方向性与 fail-closed 姿态。
③ 全 bank delta census:263 题 production-exact 驱动(真实 `_reveal_stuck_hint`,
   非谓词复述)——after 恰等于冻结集 {6a631dcf 19.0, 6a631e95 1.04, 6a695670 96}
   且 after ⊆ before(七条件门 `_current_step_anchor_numbers`,B1 后未改);
   任何新增/消失都红,红即人审。双源(seed/snapshot)零锚(Phase A 口径冻结)。

规则本体 numeric.result_evidence 只描述 syntax/property classes(封闭语法类,
B1 §4.4 红线);需要新增内容词白名单的瞬间 = 停呈裁决——本测试面的 census 门
会先红,这是制度防线(B1 残留 R8)。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from edu_agent.agents.small_lecturer import (
    ResultEvidence,
    LearnerSession,
    _analysis_steps,
    _current_step_anchor_numbers,
    _reveal_stuck_hint,
    result_evidence,
)

_ROOT = Path(__file__).resolve().parents[2]
ORACLE_PATH = _ROOT / "edu_agent" / "evals" / "artifacts" / "anchor-proof-b1" / "oracle-anchor-proof.json"
BANK_PATH = _ROOT / "edu_agent" / "contracts" / "partner_bank.json"
_ORACLE = json.loads(ORACLE_PATH.read_text(encoding="utf-8"))
SAMPLES = _ORACLE["samples"]
PINS = _ORACLE["synthetic_pins"]
BOUNDARY = _ORACLE["negative_boundary"]
# ③ 冻结集(B1 §6 实测;#441 验收:after 恰等于此集,禁新增)
FROZEN_AFTER = {("6a631dcf", 1, 19.0), ("6a631e95", 1, 1.04), ("6a695670", 1, 96.0)}


def _bank_question(record: dict) -> dict:
    """题库 record → 内核题面(api/question_source.normalize 同款键映射)。"""
    return {"text": str(record.get("stem") or ""), "answer": str(record.get("answer") or ""),
            "analysis": str(record.get("original_analysis") or "")}


def _census(path: Path) -> tuple[list[tuple[str, int, float]], list[tuple[str, int, float]]]:
    """(before, after) census:before = 七条件门(`_current_step_anchor_numbers`,
    idx≥1 静态可达——B1 后该函数未改,即 containment 前的授权面);after = 生产
    reveal 路径(真实 `_reveal_stuck_hint` 逐级驱动,空历史无 skip)。"""
    before: list[tuple[str, int, float]] = []
    after: list[tuple[str, int, float]] = []
    for record in json.loads(path.read_text(encoding="utf-8"))["records"]:
        question = _bank_question(record)
        ladder = _analysis_steps(question["analysis"])
        if not ladder:
            continue
        gate = LearnerSession(question=question, learner={})
        gate.steps = ladder
        for idx, step in enumerate(ladder):
            if idx >= 1 and _current_step_anchor_numbers(gate, step):
                before.append((record["question_id"], idx, float(step["value"])))
        live = LearnerSession(question=question, learner={})
        live.steps = [dict(step) for step in ladder]
        for _ in range(len(ladder)):
            _reveal_stuck_hint(live)
        for event in live.guard_events:
            if event.get("branch") == "reveal" and event.get("anchor_numbers"):
                assert len(event["anchor_numbers"]) == 1  # 单数值门槛(#333)
                after.append((record["question_id"], event["hint_level"] - 1,
                              float(event["anchor_numbers"][0])))
    return before, after


# ---------- ① oracle fixture:冻结字面值逐条断言 ----------


@pytest.mark.parametrize("item", SAMPLES + PINS + BOUNDARY,
                         ids=[s.get("question_id") or f"pin{i}" for i, s in
                              enumerate(SAMPLES + PINS + BOUNDARY)])
def test_oracle_frozen_expected(item):
    """逐条:result_evidence(fragment, value) 的 kind == JSON 冻结 expected。
    span 结构健全性一并钉:切出的必须是等于 X 的数字段(绑定位,B1 §4.0)。"""
    evidence = result_evidence(item["fragment"], item["value"])
    if item["expected"] is None:
        assert evidence is None, f"{item['fragment']!r} 期望 None(冻结),实得 {evidence}"
    else:
        assert isinstance(evidence, ResultEvidence)
        assert evidence.kind == item["expected"]
        assert evidence.value == float(item["value"])
        assert float(item["fragment"][evidence.span[0]:evidence.span[1]]) == evidence.value


def test_oracle_composition_frozen():
    """oracle 组成冻结:23 样本(19 假 + 3 留 + 1 弃)+ 16 合成钉 + 2 边界。"""
    by_class = {c: [s for s in SAMPLES if s["class"] == c]
                for c in ("false_anchor", "correct_anchor_kept", "correct_anchor_dropped")}
    assert len(SAMPLES) == 23
    assert {c: len(v) for c, v in by_class.items()} == {
        "false_anchor": 19, "correct_anchor_kept": 3, "correct_anchor_dropped": 1}
    assert len(PINS) == 16 and len(BOUNDARY) == 2
    assert all(s["class"] == "negative_boundary" and s["expected"] is None for s in BOUNDARY)


def test_hard_gate_false_anchors_zero_residual():
    """硬门(#441 验收):19 条 false_anchor 期望恒 None 且实测 None——19/0 冻结。"""
    false_samples = [s for s in SAMPLES if s["class"] == "false_anchor"]
    assert all(s["expected"] is None for s in false_samples)
    residuals = [s for s in false_samples if result_evidence(s["fragment"], s["value"]) is not None]
    assert not residuals, f"19 假 anchor 硬门残留:{residuals}"


def test_frozen_fragments_match_production_slicing():
    """切片漂移哨兵:样本 fragment/value 必须逐字等于生产 `_analysis_steps` 对该题
    切出的对应片段——bank 数据或切梯被改动即红,强制人工重裁(防静默绕过 oracle)。"""
    bank = {r["question_id"]: r for r in
            json.loads(BANK_PATH.read_text(encoding="utf-8"))["records"]}
    for sample in SAMPLES + BOUNDARY:
        record = bank[sample["question_id"]]
        ladder = _analysis_steps(str(record.get("original_analysis") or ""))
        step = ladder[sample["idx"]]  # 梯变短 → IndexError = 红(数据漂移,须重裁)
        assert step["step"] == sample["fragment"], f"{sample['question_id']} 片段漂移"
        assert step["value"] == sample["value"], f"{sample['question_id']} 值漂移"


def test_result_evidence_kind_is_closed_set():
    """ResultEvidence 类型层面钉死两形态封闭集(kind 白名单外即 ValueError)。"""
    with pytest.raises(ValueError):
        ResultEvidence("verb_object_phrase", (0, 1), 1.0)


# ---------- ② property/mutation:定向变形钉方向性 ----------


@pytest.mark.parametrize("fragment,value", [
    ("全长400", "400"),                 # 系词删除(dev「全长是400」的变形)
    ("48÷3得16", "16"),                 # 等号删除:内容动词不得替代等式记号
    ("实际体重比标准19.0%", "19.0"),     # 差值标记删除(dev 6a631dcf 的变形)
    ("再增20%，原来的96%", "96"),        # 系词删除(dev 6a695670 的变形)
    ("再八折”得实际售价成本价的1.04倍", "1.04"),  # 系词删除(dev 6a631e95 的变形)
])
def test_mutation_remove_result_structure_revokes_authority(fragment, value):
    """mutation①:去掉结果结构(系词/等式记号/差值标记)→ authority 消失。
    数字还在、断言结构没了 → None(「先找到结果陈述,再绑定数字」:绑定以
    结构为前提,不以数字在场为前提)。"""
    assert result_evidence(fragment, value) is None


def test_mutation_change_result_number_loses_proof():
    """mutation②:改结果数字 → 原 value 失 proof。"""
    assert result_evidence("全长是400", "400") is not None    # 基线:结构齐全授权
    assert result_evidence("全长是500", "400") is None        # X 不在片内 → fail-closed
    assert result_evidence("16箱共48÷3=17", "16") is None     # X 在片但 RHS 首数≠X、非终位


@pytest.mark.parametrize("fragment,value", [
    ("全长是400，另加200", "200"),       # 操作数不从邻从句的系词取得证明
    ("再乘100，全长是400", "100"),       # 前缀操作数不因后句断言取得证明(终位失守)
    ("全长是400，另取7/18", "18"),       # 分母操作数不因同片断言从句取得证明
])
def test_mutation_unrelated_operand_does_not_hijack(fragment, value):
    """mutation③:加无关操作数 → 不抢——同片内的断言结构只授权它断言的值,
    操作数(算子宾语位)不因邻接取得 authority。"""
    assert result_evidence(fragment, value) is None


@pytest.mark.parametrize("fragment,value", [
    ("再取7/18", "18"),                 # 分母(数字在算子宾语位)
    ("再乘3/4", "4"),
    ("再除以3%", "3"),                   # % 过终位检查但无从句系词/比较式
    ("最后加100元办卡费", "100"),        # 加数+单位
])
def test_mutation_trailing_operand_not_result(fragment, value):
    """mutation④:分母/操作参数不因末尾成结果——尾位是必要条件(值头收尾),
    非充分条件(还须从句级断言结构);这正是 `_step_value` 取尾数抽到输入的
    错归因形态,规则必须整体拒绝。"""
    assert result_evidence(fragment, value) is None


def test_mutation_equation_rhs_structural_pinned():
    """mutation⑤:equation RHS structural 保持——绑 RHS **首数**(主结果),
    不绑尾数(余数/二级标注);「26÷3=8(套)…2(米)」取 2 正是审计已定性的
    错归因例,允许尾数作证=给错归因族发通行证。"""
    assert result_evidence("48÷3=16", "16").kind == "explicit_equation_rhs"
    assert result_evidence("26÷3=8(套)…2(米)", "2") is None
    pinned = result_evidence("26÷3=8(套)…2(米)", "8")
    assert pinned is not None and pinned.kind == "explicit_equation_rhs"
    assert "26÷3=8(套)…2(米)"[pinned.span[0]:pinned.span[1]] == "8"


# ---------- ③ 全 bank delta census(production-exact)----------


def test_full_bank_census_after_equals_frozen_and_subset_of_before():
    """③ census 硬门(263 题):after 恰等于冻结集 **且** after ⊆ before
    (禁新增——规则为纯合取,七条件门 B1 后未改,结构上不可能新增;实测再钉)。
    after 与 oracle 的 correct_anchor_kept 样本一致(两份冻结工件互证)。"""
    before, after = _census(BANK_PATH)
    assert set(after) <= set(before), "禁新增被违反:after ⊄ before"
    assert set(after) == FROZEN_AFTER, f"census 漂移:{set(after) ^ FROZEN_AFTER}"
    kept = {(s["question_id"], s["idx"], float(s["value"]))
            for s in SAMPLES if s["class"] == "correct_anchor_kept"}
    assert set(after) == kept


@pytest.mark.parametrize("source,path", [
    ("seed", _ROOT / "edu_agent" / "contracts" / "release_acceptance_seed_question_bank.json"),
    ("snapshot", _ROOT / "edu_agent" / "contracts" / "db_snapshot.json"),
])
def test_seed_snapshot_sources_zero_anchors(source, path):
    """双源零锚断言(Phase A 口径冻结):seed/snapshot 全量驱动 anchor=0
    (containment 前即为 0,containment 后仍为 0)。"""
    _before, after = _census(path)
    assert after == [], f"{source} 源出现 anchor:{after}"
