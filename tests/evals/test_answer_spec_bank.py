"""answer_spec 声明面编译合同(用户裁令⑥ 2026-09-23):确定性规则 + 真实题库钉死 + 透传。

三块(与 test_answer_census.py 同纪律:题库或编译规则变更必须显式更新本测试):
  · 编译规则边界:choice letter_choices 只认 stem 内 'A' 起连续完整前缀(题库无
    结构化 options 字段——不可识别即留空 fail-closed,裁令①负例);composite 不编
    (裁令②);ground_truth 恒为 answer 原文(等价形态识别交给 A 段 verifier);
    自回喂不命中留空(A 段口径外原文,如 equation 尾句号);
  · 真实题库(partner_bank.json)数据有效性:142 编译/9 留空/112 composite 不编
    可复算钉死;逐条断言 schema 形状/枚举/ground_truth 非空/复合零声明面;
  · question_source 透传(PR #422 缺口②):在场才传(bank 题源真实 resolve 链路)、
    无声明面不传(seed,零行为变化)、非 dict 不传(防护与 kernel._answer_spec 同口径)。
不做端到端 kernel 门测试:#422 未合;全链验证在 #422+本件合入后由 PM/C 段做。
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from answer_census import DEFAULT_BANK, classify, load_bank
from compile_answer_spec import (
    REASON_CHOICE,
    REASON_COMPOSITE,
    REASON_INCOMPATIBLE,
    choice_letter_choices,
    compile_bank,
    compile_spec,
)
from edu_agent.agents.small_lecturer import ANSWER_TYPES, AnswerSpec, verify_completion
from edu_agent.api import SeedQuestionSource, SnapshotQuestionSource

# 真实题库钉死数(263 records;eligible 上限 151 = 87+13+0+3+48,裁令⑥)
COMPILED_BY_TYPE = {
    "numeric_with_unit": 87,
    "short_text_exact": 48,
    "choice_letter": 5,       # 13 choice 中 8 条 stem 无可识别选项列表 → 留空
    "equation_form": 2,       # 3 equation 中 6a69af4b 原文尾句号自回喂不命中 → 留空
    "true_false": 0,
}
CHOICE_LEFT_EMPTY = {
    "6a61aba2", "6a61b66a", "6a61ba35", "6a61baec", "6a61bd68",
    "6a62bdbc", "6a62cb44", "6a695a81",
}
INCOMPATIBLE_LEFT_EMPTY = {"6a69af4b"}


def _spec_of(spec: dict) -> AnswerSpec:
    """声明面 dict → A 段 AnswerSpec(与 kernel _answer_spec 同字段口径)。"""
    return AnswerSpec(
        answer_type=spec["answer_type"],
        ground_truth=spec["ground_truth"],
        aliases=tuple(spec.get("aliases") or ()),
        unit_optional=bool(spec.get("unit_optional", False)),
        letter_choices=tuple(spec.get("letter_choices") or ()),
    )


# ---------- 编译规则边界(choice letter_choices 来源判定,裁令①) ----------


def test_choice_marker_complete_prefix_compiles():
    """完整选项列表(stem 内 A–D 连续标记)→ 编 letter_choices。"""
    stem = "一个数除以分数所得的商（ ）这个数。A.大于 B.小于 C.等于 D.以上都有可能"
    assert choice_letter_choices(stem, "D") == ("A", "B", "C", "D")


def test_choice_markers_incomplete_or_malformed_rejected():
    """缺 A/跳号/重复/无标记/粘连数字/答案不在集 → 一律 None(宁留空不猜)。"""
    assert choice_letter_choices("B.x C.y D.z", "C") is None          # 不从 A 起
    assert choice_letter_choices("A.x C.y D.z", "C") is None          # 跳号 B
    assert choice_letter_choices("A.x B.y A.z B.w", "A") is None      # 重复标记
    assert choice_letter_choices("下面路线描述不正确的是（ ）。", "C") is None  # 无标记
    assert choice_letter_choices("3A.x B.y", "A") is None             # 标记前粘连数字
    assert choice_letter_choices("A.x B.y C.z", "D") is None          # 答案字母不在集


def test_compile_spec_choice_without_reliable_options_leaves_empty():
    """裁令①负例:choice 无可靠 letter_choices 即整条留空——不编半吊子 spec。"""
    record = {"question_id": "t-choice", "stem": "下面路线描述不正确的是（ ）。", "answer": "C"}
    spec, reason = compile_spec(record)
    assert spec is None and reason == REASON_CHOICE
    bank, reasons, left = compile_bank([record])
    assert "answer_spec" not in bank[0]
    assert left[REASON_CHOICE] == ["t-choice"]


def test_compile_spec_ground_truth_is_answer_verbatim():
    """ground_truth 恒为 answer 原文(逐字,含句读)——等价形态识别归 A 段。"""
    record = {"question_id": "t-num", "stem": "s", "answer": "29/72米。"}
    spec, reason = compile_spec(record)
    assert reason is None
    assert spec == {
        "answer_type": "numeric_with_unit",
        "ground_truth": "29/72米。",
        "aliases": [],
        "unit_optional": False,
    }


def test_compile_spec_selffeed_gate_leaves_incompatible_original_empty():
    """自回喂门:eligible 形态但 A 段判不了原文(equation 尾句号)→ 留空 fail-closed。"""
    record = {"question_id": "t-eq", "stem": "s", "answer": "35/56÷24/56=35/24。"}
    assert compile_spec(record) == (None, REASON_INCOMPATIBLE)


def test_compile_spec_composite_not_compiled():
    """裁令②:composite 整体不判定,零声明面(局部槽命中不构造 evidence)。"""
    record = {"question_id": "t-comp", "stem": "s", "answer": "鸡3只，兔5只"}
    assert compile_spec(record) == (None, REASON_COMPOSITE)


def test_compile_bank_idempotent():
    """幂等:重算不叠加(先剥旧 answer_spec 再按规则 1–4 全量重算)。"""
    once, _, _ = compile_bank(load_bank(DEFAULT_BANK))
    twice, _, _ = compile_bank(once)
    assert once == twice


# ---------- 真实题库(partner_bank.json)数据有效性 ----------


def test_bank_compiled_counts_and_left_empty_pinned():
    """仓内数据 = 可复算产物:分型计数/留空清单/全库重算一致性钉死。"""
    records = load_bank(DEFAULT_BANK)
    assert len(records) == 263
    compiled, reasons, left = compile_bank(records)
    by_type = Counter(
        r["answer_spec"]["answer_type"] for r in compiled if "answer_spec" in r)
    assert {cat: by_type.get(cat, 0) for cat in COMPILED_BY_TYPE} == COMPILED_BY_TYPE
    assert reasons[REASON_COMPOSITE] == 112
    assert set(left[REASON_CHOICE]) == CHOICE_LEFT_EMPTY
    assert set(left[REASON_INCOMPATIBLE]) == INCOMPATIBLE_LEFT_EMPTY
    assert compiled == records                  # 已写回数据与重算结果逐字一致


def test_bank_spec_schema_shape_valid():
    """逐条:answer_type 枚举/ground_truth=answer 原文且非空/aliases 空/unit_optional
    False/letter_choices 仅 choice 且非空且含答案字母;键集精确防漂。"""
    for record in load_bank(DEFAULT_BANK):
        spec = record.get("answer_spec")
        if spec is None:
            continue
        assert isinstance(spec, dict), record["question_id"]
        assert spec["answer_type"] in ANSWER_TYPES, record["question_id"]
        assert spec["ground_truth"] == record["answer"], record["question_id"]
        assert spec["ground_truth"].strip(), record["question_id"]
        assert spec["aliases"] == [], record["question_id"]
        assert spec["unit_optional"] is False, record["question_id"]
        if spec["answer_type"] == "choice_letter":
            assert list(spec) == ["answer_type", "ground_truth", "aliases",
                                  "unit_optional", "letter_choices"], record["question_id"]
            assert spec["letter_choices"], record["question_id"]
            assert spec["ground_truth"] in spec["letter_choices"], record["question_id"]
        else:
            assert "letter_choices" not in spec, record["question_id"]
            assert list(spec) == ["answer_type", "ground_truth", "aliases",
                                  "unit_optional"], record["question_id"]


def test_bank_composite_zero_declaration():
    """裁令②断言:112 composite 零声明面(加了也是 needs_review,纯噪声)。"""
    for record in load_bank(DEFAULT_BANK):
        if classify(record.get("answer")) == "composite":
            assert "answer_spec" not in record, record["question_id"]


def test_bank_specs_selffeed_through_verifier():
    """与编译门同口径的快照断言:每条声明面经 A 段 verify_completion 自回喂命中。"""
    for record in load_bank(DEFAULT_BANK):
        spec = record.get("answer_spec")
        if spec is None:
            continue
        evidence = verify_completion(_spec_of(spec), record["answer"], 1)
        assert evidence is not None, record["question_id"]


# ---------- question_source 透传(PR #422 缺口②) ----------


def test_bank_source_resolves_answer_spec_passthrough():
    """在场才透传:bank 题源真实 resolve 链路,内容与题库声明面逐字一致。"""
    source = SnapshotQuestionSource(DEFAULT_BANK)
    resolved = source.resolve("6a61afaa")                       # numeric_with_unit
    assert resolved["answer_spec"]["answer_type"] == "numeric_with_unit"
    assert resolved["answer_spec"]["ground_truth"] == "0.4kg"
    resolved = source.resolve("6a62cc86")                       # choice_letter(可靠)
    assert resolved["answer_spec"]["letter_choices"] == ["A", "B", "C", "D"]
    bank = {r["question_id"]: r for r in load_bank(DEFAULT_BANK)}
    assert resolved["answer_spec"] == bank["6a62cc86"]["answer_spec"]


def test_seed_source_resolution_has_no_answer_spec_key():
    """零行为变化:无声明面题源(seed)resolve 输出不含 answer_spec 键。"""
    resolved = SeedQuestionSource().resolve("equation_subtract")
    assert resolved["answer"] == "x=6"
    assert "answer_spec" not in resolved


def test_normalize_skips_non_dict_answer_spec(tmp_path: Path):
    """防护与 kernel._answer_spec 同口径:非 dict 声明面不透传(fail-closed)。"""
    bank = tmp_path / "mini_bank.json"
    bank.write_text(json.dumps({"records": [
        {"question_id": "m1", "stem": "s", "answer": "42",
         "original_analysis": "", "grade": "", "knowledge_points": [],
         "question_image": None, "answer_spec": "garbage"},
        {"question_id": "m2", "stem": "s", "answer": "43",
         "original_analysis": "", "grade": "", "knowledge_points": [],
         "question_image": None, "answer_spec": None}]},
        ensure_ascii=False), encoding="utf-8")
    source = SnapshotQuestionSource(bank)
    assert "answer_spec" not in source.resolve("m1")
    assert "answer_spec" not in source.resolve("m2")
