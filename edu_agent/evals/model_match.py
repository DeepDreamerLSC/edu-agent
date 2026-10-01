"""模型身份比较公共 helper(#490 M2):只回答"实际观察到的模型身份与预注册是否一致"。

输入是调用方已提取好的 observed_models 与 expected_model(哪个字段承载模型身份、
哪些行算数,由调用方决定);输出只是身份比较事实(matched/mismatched + 回显 +
稳定 reason)。本模块不知道任何专项结果 schema,不输出领域裁决词——身份不一致后
如何处置(整轮作废/禁计分/允许部分诊断)由调用方持有。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ModelComparison:
    matched: bool                # True ⟺ 观察到恰一个不同值且等于 expected_model
    observed_models: list[str]   # sorted 去重快照(回显,报告可直接嵌)
    expected_model: str          # 回显
    reason: str                  # 稳定词表,见 compare_models docstring


def compare_models(observed_models: Iterable[str], expected_model: str) -> ModelComparison:
    """observed 非空 ∧ 恰一个不同值 ∧ 该值 == expected_model ⟺ matched。

    observed_models 物化为 sorted 去重快照回显,接受任意可迭代(含生成器);
    expected_model 原样回显。不做输入形状校验:传单个字符串会按字符散开成
    mismatched(垃圾进垃圾出);expected_model 为 None 同样走纯比较得
    mismatched。reason 词表(仅此四种):
      matched
      no models observed
      multiple models observed: a, b            (sorted,逗号+空格连接)
      observed model does not equal expected model: X vs Y
    """
    observed = sorted(set(observed_models))
    if not observed:
        return ModelComparison(False, [], expected_model, "no models observed")
    if len(observed) > 1:
        return ModelComparison(False, observed, expected_model,
                               f"multiple models observed: {', '.join(observed)}")
    if observed[0] != expected_model:
        return ModelComparison(
            False, observed, expected_model,
            f"observed model does not equal expected model: "
            f"{observed[0]} vs {expected_model}")
    return ModelComparison(True, observed, expected_model, "matched")
