"""信号富化数据集 v2:匹配器级验证(#304 路线 a 落地件,零模型调用零网络)。

#304 knob-frequency 裁定「旋钮非死码,是 elicit 数据集缺触发信号」——本数据集补
12 案(understanding/stuck/completion 各 4),触发词形全部取自 kernel 既有信号函数
的匹配口径(不出新正则,口径同 knob-frequency/analyze.py)。本测试就是匹配器验证:
逐案断言期望信号族在期望轮触发、触发轮其余两族不误触、触发前轮零信号。合成学生
行为照 S2 信号模式建模,零真实学生数据。"""

from __future__ import annotations

import json
from collections import Counter

import pytest

from edu_agent.agents.small_lecturer import (
    _student_signals_completion,
    _student_signals_stuck,
    _student_signals_understanding,
)
from edu_agent.evals import DATASETS_DIR

SIGNALS = {
    "understanding": _student_signals_understanding,
    "stuck": _student_signals_stuck,
    "completion": _student_signals_completion,
}

_DATASET = DATASETS_DIR / "small_lecturer_signal_enrichment_v2.json"
SCENARIOS = json.loads(_DATASET.read_text(encoding="utf-8"))["scenarios"]


def test_dataset_shape():
    """12 案、三族各 4;触发轮在轮数范围内,触发词逐个出现在触发轮原文里。"""
    assert len(SCENARIOS) == 12
    buckets = Counter(s["bucket"] for s in SCENARIOS)
    assert buckets == {
        "signal_understanding": 4,
        "signal_stuck": 4,
        "signal_completion": 4,
    }
    for s in SCENARIOS:
        turns = s["student_turns"]
        exp = s["expected"]
        assert 0 <= exp["trigger_round"] < len(turns), s["id"]
        for word in exp["trigger_word"].split("+"):
            assert word in turns[exp["trigger_round"]], s["id"]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s["id"])
def test_signals_fire_as_expected(scenario):
    """期望族在期望轮触发且其余两族不误触;触发前每轮三族全零(干净基线轮)。"""
    turns = scenario["student_turns"]
    exp = scenario["expected"]
    hits = {name: [fn(t) for t in turns] for name, fn in SIGNALS.items()}
    for i in range(exp["trigger_round"]):
        for name in SIGNALS:
            assert not hits[name][i], f"{scenario['id']} 第 {i} 轮提前触发 {name}"
    family = exp["signal_family"]
    assert hits[family][exp["trigger_round"]], f"{scenario['id']} 期望轮未触发"
    for name in SIGNALS:
        if name != family:
            assert not hits[name][exp["trigger_round"]], (
                f"{scenario['id']} 触发轮 {name} 误触"
            )
