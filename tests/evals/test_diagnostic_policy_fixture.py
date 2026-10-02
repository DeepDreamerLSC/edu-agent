"""#501 E1 diagnostic fixture(C17-ext-cor8)入仓不变量 + 冻结剧本锁定。

fixture 是 /tmp/p12-out/e1-frozen.json 的逐字转写(证据目录 /tmp/p12-out,见 PR 正文);
本测试把结构不变量与三轮剧本钉死在 CI:t1/t2 = 原 C17-phasec 逐字(原案不在仓库、
一字不改),t3 = 冻结件唯一新增文本;question 纯文本无 answer(完成证据 fail-closed,
冻结设计);t3 后停、不调 finish。diagnostic 定位:不进 benchmark 权重,不适用
load_shortboard_corpus 真模型口径(该口径 answer 必填,见 scenario.source.design_notes)。
"""

from __future__ import annotations

import json
from pathlib import Path

DATASET = (Path(__file__).resolve().parents[2] / "edu_agent" / "evals" / "datasets"
           / "small_lecturer_diagnostic_policy_regression_v1.json")

# 三轮剧本逐字冻结(来源:e1-frozen.json turns;改一字 = 重开实验,不是改测试)。
T1_C17_VERBATIM = "把 6 看成六分之六,三分之二乘六分之六 = 十八分之三十六,约分 = 4。"
T2_C17_VERBATIM = "25 减 7 等于 18,x 等于 18。"
T3_EXTENSION = (
    "那我回到这道题重新算:三分之二乘六,还是把 6 看成六分之六,"
    "分子乘分子是 2 乘 6 等于 12,分母乘分母是 3 乘 6 等于 18,"
    "得十二分之十八,约分是三分之二,所以答案是三分之二。"
)


def _scenario() -> dict:
    payload = json.loads(DATASET.read_text(encoding="utf-8"))
    (scenario,) = payload["scenarios"]
    return scenario


def test_fixture_shape_diagnostic_caliber():
    """单案、新 id、diagnostic/regression 双标注、来源可追溯(#501)。"""
    scenario = _scenario()
    assert scenario["id"] == "C17-ext-cor8"
    assert scenario["caliber"] == "diagnostic/regression"
    assert {"diagnostic", "regression"} <= set(scenario["tags"])
    assert scenario["source"]["issue"] == 501
    assert scenario["source"]["derived_from"]["original_case"] == "C17-phasec"
    assert scenario["source"]["derived_from"]["original_case_untouched"] is True


def test_fixture_text_only_question_fail_closed():
    """纯文本题面:question 只有 text、无 answer/answer_spec——完成证据 fail-closed,
    不给学生文本侧的 premature completion 通道(冻结设计,观察面只落在 tutor 行为)。"""
    scenario = _scenario()
    assert scenario["question"] == {"text": "三分之二乘以六等于多少?"}
    assert scenario["grade"] == "六年级" and scenario["answer_status"] == "incorrect"


def test_fixture_frozen_script_eligibility_and_stop():
    """t1/t2 逐字 = 原 C17-phasec;t3 = 唯一新增;eligible 旗标 [F,F,T];
    t3 后停(stop_after_turn=3)、不调 finish(finish 总结不属于该构念)。"""
    scenario = _scenario()
    assert scenario["student_turns"] == [T1_C17_VERBATIM, T2_C17_VERBATIM, T3_EXTENSION]
    assert scenario["eligible_correction_turns"] == [False, False, True]
    assert scenario["stop_after_turn"] == 3
    assert scenario["call_finish"] is False
