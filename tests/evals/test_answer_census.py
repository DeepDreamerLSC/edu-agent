"""answer_census 普查脚本合同(#417):互斥分类边界 + 空输入/异常字段冒烟 + 真实题库实跑。

教训 A7:顺手件必须带自己的冒烟——本件独立 PR 不夹带。分类规则边界、263 分布
可复现性、fingerprint 追溯全部钉在这里;题库或分类规则变更必须显式更新本测试。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from answer_census import (
    CATEGORY_ORDER,
    DEFAULT_BANK,
    census,
    classify,
    fingerprint,
    load_bank,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "answer_census.py"


# ---------- 互斥分类规则(优先级从高到低,首中即归类;边界案钉死) ----------


def test_numeric_with_unit_forms():
    """规则1:整答=单数值(整数/小数/分数/百分号)+可选单位后缀+可选句读终止符。"""
    for answer in (
        "30",
        "0.5m",
        "7/36",
        "25.8度",
        "20%",
        "2 m",
        "5天。",
        "1250万瓶",
        "93/4平方厘米",
    ):
        assert classify(answer) == "numeric_with_unit", answer


def test_numeric_rejects_multi_value_and_prose():
    """多值/叙述不入纯数值:分号槽、逗号多值归复合;动词/约字前缀落后续规则。"""
    assert classify("14dm³；10公顷；15时。") == "composite"
    assert classify("0.8，0.48，2.4，0.25；方法是先化分数。") == "composite"
    assert classify("赚4元") == "short_text_exact"
    assert classify("约5233米。") == "short_text_exact"


def test_choice_letter_exact_match_only():
    """规则2:整答恰为一个选项字母(题面字母表 A–D)——与设计件选择 13 同口径。"""
    assert classify("A") == "choice_letter"
    assert classify("C") == "choice_letter"
    # 字母+标点/内容不是「字母精确匹配」,落入后续规则
    assert classify("A。") == "short_text_exact"
    assert classify("B. 15") == "short_text_exact"
    assert classify("B，93.75%。") == "short_text_exact"


def test_true_false_whole_answer():
    """规则3:去句读终止符后整答∈{对,错,√,×,✓,✗,正确,错误};判断+理由落后续规则。"""
    assert classify("对") == "true_false"
    assert classify("×。") == "true_false"
    assert classify("正确") == "true_false"
    assert classify("正确，现价比原价低4%。") == "short_text_exact"


def test_equation_form_pure_math_only():
    """规则4:整答仅数学 token、含 '='、无分号槽分隔;叙述/多方程归复合。"""
    assert classify("x=6") == "equation_form"
    assert classify("3/4×1/3=1/4") == "equation_form"
    assert classify("35/56÷24/56=35/24。") == "equation_form"
    assert classify("列式2/3×1/4，结果1/6公顷。") == "composite"
    assert classify("x=5/9；x=14；x=65/7。") == "composite"
    assert classify("相同，都是S=πr²") == "short_text_exact"


def test_short_text_max_chars_and_slots():
    """规则5:≤12字且数值槽≤1;多槽(设计件 §三:鸡3只兔5只)与超长归复合。"""
    assert classify("易变形") == "short_text_exact"
    assert classify("无法确定") == "short_text_exact"
    assert classify("正确，现价比原价低4%。") == "short_text_exact"  # 恰 12 字
    assert classify("鸡3只，兔5只") == "composite"
    assert classify("（1）错；（2）错") == "composite"
    assert classify("甲数比乙数多60%，乙数比甲数少37.5%。") == "composite"


def test_abnormal_answer_fields_do_not_crash():
    """异常字段冒烟:非字符串/空串 answer 不崩;非字符串/空归 composite,纯标点按 1 字文本入短文本。"""
    assert classify(None) == "composite"
    assert classify(123) == "composite"
    assert classify("") == "composite"
    assert classify("   ") == "composite"
    assert classify("。") == "short_text_exact"


# ---------- 空输入/异常题库冒烟(02 §6:脚本自带冒烟钉在 tests) ----------


def test_census_empty_input():
    counts, ids = census([])
    assert sum(counts.values()) == 0
    assert all(ids[category] == [] for category in CATEGORY_ORDER)


def test_census_missing_or_nonstring_answer_counts_as_composite():
    counts, ids = census([{"question_id": "q1"}, {"question_id": "q2", "answer": 42}])
    assert counts["composite"] == 2
    assert ids["composite"] == ["q1", "q2"]


def test_load_bank_tolerates_malformed(tmp_path):
    """损坏 JSON/records 非列表/非 dict 成员:按空或跳过处理,不崩。"""
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_bank(bad) == []
    wrong_shape = tmp_path / "wrong_shape.json"
    wrong_shape.write_text(json.dumps({"records": "oops"}), encoding="utf-8")
    assert load_bank(wrong_shape) == []
    mixed = tmp_path / "mixed.json"
    mixed.write_text(json.dumps({"records": [{"answer": "A"}, "junk", 3]}), encoding="utf-8")
    assert [record["answer"] for record in load_bank(mixed)] == ["A"]


# ---------- 真实题库实跑(263 分布仓内可复现;#417 exit 判据) ----------


def test_real_bank_distribution_reproducible():
    """实跑分布钉死:题库或分类规则变更必须显式更新本表并重报设计件 §三口径。"""
    records = load_bank(DEFAULT_BANK)
    assert len(records) == 263
    counts, _ = census(records)
    assert sum(counts.values()) == 263
    actual = {category: counts[category] for category in CATEGORY_ORDER}
    assert actual == {
        "numeric_with_unit": 87,
        "choice_letter": 13,
        "true_false": 0,
        "equation_form": 3,
        "short_text_exact": 48,
        "composite": 112,
    }


def test_fingerprint_is_bank_sha256_hex16():
    """fingerprint=题库文件 sha256 前 16 位 hex:「263 是哪些题」可追溯。"""
    digest = hashlib.sha256(DEFAULT_BANK.read_bytes()).hexdigest()
    assert fingerprint(DEFAULT_BANK) == digest[:16]
    assert len(fingerprint(DEFAULT_BANK)) == 16


def test_cli_smoke_real_bank_and_empty_bank(tmp_path):
    """CLI 冒烟:真实题库出数(总数+fingerprint 落 stdout);空题库出零表不崩。"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, check=True
    )
    assert "total                  263" in result.stdout
    assert fingerprint(DEFAULT_BANK) in result.stdout
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"records": []}), encoding="utf-8")
    empty_result = subprocess.run(
        [sys.executable, str(SCRIPT), "--bank", str(empty)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "total                    0" in empty_result.stdout
    assert "0/0 = 0.0%" in empty_result.stdout


def test_cli_missing_bank_errors_cleanly(tmp_path):
    """题库文件缺失:干净报错退 2,不是栈崩溃。"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--bank", str(tmp_path / "nope.json")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "不存在" in result.stderr
