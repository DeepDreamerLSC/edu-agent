"""#185 对话质量回归网 v1:确定性 corpus 参数化遍历(断言即规格,零真模型)。

机制(刻意的,PR 描述里写明):`known_red` 用 xfail(strict=True)——今天该红
(短板未修,main 实测);一旦有人修好泄漏,用例转绿 → XPASS(strict)把 CI 变红,
**逼人把 status 翻成 guarded**。`guarded` 用真实断言,永久防回归。
网只记录现实:标注跟 main 的实测走,不为好看而写。

分层(teachkit,#192):FakeGateway 在测试侧构造(罐头剧本来自场景的 fake_model),
注入 KernelSubject;edu_agent.evals 不 import tests/(生产代码不依赖测试夹具)。
"""

from __future__ import annotations

import json

import pytest

from edu_agent.evals import (
    DATASETS_DIR,
    KernelSubject,
    UnknownCheck,
    format_failures,
    load_shortboard_corpus,
    run_check,
    run_scenario_checks,
    to_kernel_case,
)

from teachkit import FakeGateway


def _run_scenario(scenario: dict) -> list[dict]:
    """罐头剧本 → FakeGateway → KernelSubject → check 失败清单(零网络零端口)。"""
    gateway = FakeGateway(tutor_payloads=[entry["json"] for entry in scenario["fake_model"]])
    result = KernelSubject(gateway).run_case(to_kernel_case(scenario))
    return run_scenario_checks(scenario, result)


def _corpus_params() -> list:
    """确定性子集 → 参数列表;known_red 挂 xfail(strict=True),guarded 挂真实断言。"""
    from edu_agent.evals import deterministic_scenarios

    params = []
    for scenario in deterministic_scenarios(load_shortboard_corpus()):
        marks = []
        if scenario["status"] == "known_red":
            source = scenario.get("source") or {}
            marks.append(pytest.mark.xfail(
                reason=(f"known_red source.issue={source.get('issue')}"
                        f" source.question_id={source.get('question_id')}:短板未修(#185)。"
                        "修复后本用例转绿 → XPASS(strict)变红 → 把 status 翻成 guarded"),
                strict=True))
        params.append(pytest.param(scenario, id=scenario["id"], marks=marks))
    return params


@pytest.mark.parametrize("scenario", _corpus_params())
def test_shortboard_scenario(scenario):
    """遍历回归网 corpus:声明式 expect.checks 全过才绿;失败详情带来源与具体数字。"""
    failures = _run_scenario(scenario)
    assert not failures, format_failures(failures)


@pytest.mark.parametrize("answer,tutor_text,catches", [
    ("0.8", "结果是五分之四", False),    # 中文数字
    ("0.25", "结果是 1/4", False),      # 分数形态:数字段 1/4 ≠ 0.25
    ("2.4", "等于 12/5", False),        # 分数形态
    ("0.8", "写成 80%", False),         # 百分数
    ("13次", "第十三次必形成", False),   # 中文序数
    ("0.8", "结果是 0.80", True),       # 等值小数 → 命中
    ("13次", "把 13.5 记下来", False),   # 相近数 → 不误命中(精度正确)
])
def test_ascii_digit_boundary_is_pinned(answer, tutor_text, catches):
    """钉住判定力边界(审查实测):终答的等价表达不在此口径内,网目前看不见。

    这是**已知**盲区(不是未知盲区):中文数字/分数形态/百分数/中文序数全漏,
    本 corpus 恰是小数×分数题集。做等价归一时先更新本表与 checks.py docstring,
    再放开 text_excludes_unauthorized_numbers 的适用面。"""
    ok, _ = run_check({"name": "text_excludes_answer_values"},
                      {"question": {"answer": answer}},
                      {"turns": [{"tutor": tutor_text}]})
    assert ok != catches, (answer, tutor_text)


def test_old_datasets_still_parse():
    """老数据集零迁移:envelope + 每文件首条场景关键字段(id/title/question)。

    零迁移成立的原因是本单未触碰任何老路径;v1/v3 更深的语义解析不在本单范围。"""
    for name in ("small_lecturer_dialogue_scenarios.json",
                 "small_lecturer_adaptive_shadow_pilot_20.json"):
        payload = json.loads((DATASETS_DIR / name).read_text(encoding="utf-8"))
        assert payload.get("schema_version"), name
        first = payload["scenarios"][0]
        assert first.get("id") and first.get("title") and first.get("question"), name


def test_unknown_check_name_is_visible_error():
    """未注册 check 名(拼写错误)即刻抛 UnknownCheck——加用例不改代码的安全网。"""
    with pytest.raises(UnknownCheck):
        run_check({"name": "text_excludes_answer_valus"}, {}, {"turns": []})


def test_finish_status_and_state_is_not_detail():
    """check 详情必须指名到具体状态(可定位,不写空话)。"""
    ok, detail = run_check({"name": "finish_status", "status": "needs_review"},
                           {}, {"final_state": "completed"})
    assert not ok and "completed" in detail and "needs_review" in detail
    ok, detail = run_check(
        {"name": "state_is_not", "state": "ready_to_confirm"},
        {}, {"turns": [{"student": "我不会", "state": "ready_to_confirm"}]})
    assert not ok and "turns[0]" in detail and "ready_to_confirm" in detail


def test_format_failures_carries_source_attribution():
    """失败行格式:scenario + issue + question_id + lesson_name + 详情(可追溯)。"""
    line = format_failures([{
        "scenario": "ladder-step-leaks-final-answer-13",
        "source": {"issue": 185, "question_id": "6a6320ca184f723b3592d18c",
                   "lesson_name": "6-4鸽巢问题(2)"},
        "check": "text_excludes_answer_values",
        "detail": "终答值 13 出现在 turns[3]",
    }])
    assert "source.issue=185" in line
    assert "source.question_id=6a6320ca184f723b3592d18c" in line
    assert "source.lesson_name=6-4鸽巢问题(2)" in line
    assert "13" in line


# ---- loader 拒绝合同:写错数据在加载期红,不用等到运行期 KeyError/TypeError ----

_TEMPLATE = {
    "schema_version": "small_lecturer_regression_shortboard/v1",
    "scenarios": [{
        "id": "loader-contract-demo",
        "status": "guarded",
        "source": {"issue": 185, "question_id": "6a6320ca184f723b3592d18c"},
        "tags": ["loader 合同"],
        "question": {
            "text": "一辆汽车每小时行60千米,行了3小时,一共行了多少千米?",
            "answer": "180千米",
        },
        "answer_status": "incorrect",
        "fake_model": [{"json": {"acceptable": True, "transcription": "",
                                 "reply": "你怎么想?",
                                 "steps": [{"step": "先看速度", "value": "60"}]}}],
        "student_turns": ["我不会做。"],
        "expect": {"checks": [{"name": "text_excludes_answer_values", "note": "demo"}]},
    }],
}


def _mutate(**changes):
    """深拷贝模板并按「顶层键 → 替换值」打补丁。"""
    corpus = json.loads(json.dumps(_TEMPLATE))
    corpus["scenarios"][0].update(changes)
    return corpus


@pytest.mark.parametrize("changes,match", [
    ({"question": {"text": "同上", "answer": "一百八十千米"}},
     r"取不到 ASCII 数字"),  # 静默失效通道:answer 写中文数字 → check 恒真
    ({"expect": {"checks": [{"name": "finish_status", "status": "completed"},
                            {"name": "finish_status", "status": "completed"}]}},
     r"重名"),
    ({"fake_model": [{}]}, r"fake_model\[0\]"),        # 缺 json 键 → 原本运行期 KeyError
    ({"student_turns": [{"text": "我不会做。"}]}, r"student_turns\[0\]"),
    ({"status": "known_red", "source": {"issue": 185}}, r"question_id"),
    ({"source": {}}, r"source\.issue"),
    ({"source": {"issue": 185, "question_id": "6a6320ca"}},
     r"24 位"),  # 截断 id(上轮修掉的溯源错位形态)不得静默通过
    ({"status": "known_red",
      "source": {"issue": 185, "question_id": "不是id"}}, r"24 位"),
    # 挂错轮次(第 4 条):计算轮剧本引入导出数字 → 本 check 只适用纯引用轮,拒载
    ({"expect": {"checks": [{"name": "text_excludes_unauthorized_numbers", "note": "demo"}]},
      "fake_model": [{"json": {"acceptable": True, "transcription": "",
                               "reply": "这道题你怎么想?",
                               "steps": [{"step": "把 60 写成 600/10 再约分,得到 6",
                                          "value": "6"}]}}]},
     r"纯引用"),
])
def test_loader_rejects_bad_data(tmp_path, changes, match):
    """写错数据的用例在加载期即红(审查跟进):恒真通道/重名/形状/来源缺失。"""
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(_mutate(**changes), ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        load_shortboard_corpus(path)


# ---- #197 第二批:真模型口径(shadow pilot 两数据集迁入 corpus)----


def test_pilot_datasets_load_through_corpus_loader():
    """迁入合同:两个 shadow pilot 经 corpus loader 加载——question 带 bank 对回
    的 answer、source.issue 可追溯(adaptive 无剧本/无 checks,按真模型口径放行)。"""
    for name in ("small_lecturer_teaching_context_shadow_pilot_20.json",
                 "small_lecturer_adaptive_shadow_pilot_20.json"):
        scenarios = load_shortboard_corpus(DATASETS_DIR / name)
        assert len(scenarios) == 20, name
        for scenario in scenarios:
            assert scenario["question"]["text"] and scenario["question"]["answer"], \
                (name, scenario["id"])
            assert scenario["source"]["issue"], (name, scenario["id"])


def test_real_model_scenarios_stay_out_of_deterministic_replay():
    """口径分流:无 fake_model 的真模型场景不进确定性回放(pytest 只跑罐头剧本,
    真模型判定由运行面消费)。"""
    from edu_agent.evals import deterministic_scenarios

    pilots = load_shortboard_corpus(
        DATASETS_DIR / "small_lecturer_teaching_context_shadow_pilot_20.json")
    assert deterministic_scenarios(pilots) == []


def test_real_model_caliber_rejects_missing_answer(tmp_path):
    """真模型口径的必填:去掉 question.answer → 加载期红(不是运行期 KeyError)。"""
    payload = json.loads(
        (DATASETS_DIR / "small_lecturer_teaching_context_shadow_pilot_20.json")
        .read_text(encoding="utf-8"))
    payload["scenarios"][0]["question"].pop("answer")
    path = tmp_path / "pilot.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match=r"question\.answer 必填"):
        load_shortboard_corpus(path)
