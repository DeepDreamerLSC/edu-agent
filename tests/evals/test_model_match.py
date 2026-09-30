"""#490 M2 合同:模型身份比较公共 helper——四类样本、回显确定性、禁词卫队。

全部经公开入口 edu_agent.evals 导入;禁词卫队把「公共层无领域裁决词」从约定变成红灯。
"""

from __future__ import annotations

from dataclasses import fields

from edu_agent.evals import ModelComparison, compare_models

# 八禁词(#490 §二:公共层只共享验证机制,不共享领域裁决词)
FORBIDDEN_WORDS = ("VOID", "judge_model", "S2a", "GA", "GB",
                   "answer_exposed", "fallback", "score")


def test_matched_when_single_observed_equals_expected():
    result = compare_models(["m-a", "m-a"], "m-a")
    assert result.matched is True
    assert result.reason == "matched"
    assert result.observed_models == ["m-a"]
    assert result.expected_model == "m-a"


def test_mismatch_when_nothing_observed():
    result = compare_models([], "m-a")
    assert result.matched is False
    assert result.reason == "no models observed"
    assert result.observed_models == []


def test_mismatch_when_multiple_models_observed():
    result = compare_models(["m-b", "m-a", "m-b"], "m-a")
    assert result.matched is False
    assert result.reason == "multiple models observed: m-a, m-b"
    assert result.observed_models == ["m-a", "m-b"]


def test_mismatch_when_single_observed_differs_from_expected():
    result = compare_models(["m-b"], "m-a")
    assert result.matched is False
    assert result.reason == "observed model does not equal expected model: m-b vs m-a"


def test_observed_snapshot_is_sorted_deduped_and_independent():
    """回显是物化快照:sorted 去重、不依赖输入迭代器存活(生成器可传)。"""
    result = compare_models(["m-c", "m-a", "m-c", "m-b"], "m-a")
    assert result.observed_models == ["m-a", "m-b", "m-c"]
    assert compare_models(iter(["m-a"]), "m-a").observed_models == ["m-a"]


def test_garbage_in_garbage_out_no_shape_validation():
    """docstring 钉契约:不做输入形状校验——单个字符串按字符散开得 mismatched;
    expected 为 None 同样走纯比较得 mismatched。"""
    scattered = compare_models("m-a", "m-a")
    assert scattered.matched is False
    assert scattered.observed_models == ["-", "a", "m"]
    assert scattered.reason == "multiple models observed: -, a, m"
    none_expected = compare_models(["m-a"], None)
    assert none_expected.matched is False
    assert none_expected.reason == "observed model does not equal expected model: m-a vs None"


def test_reason_vocabulary_is_stable():
    """reason 词表恰四条且文案稳定(调用方/报告可锚定;#490 M2 输出合同)。"""
    assert compare_models(["m"], "m").reason == "matched"
    assert compare_models([], "m").reason == "no models observed"
    assert compare_models(["b", "a"], "m").reason == "multiple models observed: a, b"
    assert compare_models(["b"], "m").reason == (
        "observed model does not equal expected model: b vs m")


def test_output_surface_free_of_domain_verdict_words():
    """禁词卫队:全部 reason、字段名、函数/参数名不得出现八个领域裁决词。"""
    samples = [
        compare_models([], "m-a"),
        compare_models(["m-a"], "m-a"),
        compare_models(["m-b"], "m-a"),
        compare_models(["m-a", "m-b"], "m-a"),
        compare_models("m-a", "m-a"),
        compare_models(["m-a"], None),
    ]
    surfaces = [result.reason for result in samples]
    surfaces += [str(result.expected_model) for result in samples]
    surfaces += [f.name for f in fields(ModelComparison)]
    surfaces += ["compare_models", "observed_models", "expected_model"]
    for surface in surfaces:
        for word in FORBIDDEN_WORDS:
            assert word not in surface, f"公共层输出面出现领域词 {word!r}: {surface!r}"
