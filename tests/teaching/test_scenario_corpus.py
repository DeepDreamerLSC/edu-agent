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
    KernelSubject,
    UnknownCheck,
    datasets_dir,
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
                        f" source.session={source.get('session')}:短板未修(#185)。"
                        "修复后本用例转绿 → XPASS(strict)变红 → 把 status 翻成 guarded"),
                strict=True))
        params.append(pytest.param(scenario, id=scenario["id"], marks=marks))
    return params


@pytest.mark.parametrize("scenario", _corpus_params())
def test_shortboard_scenario(scenario):
    """遍历回归网 corpus:声明式 expect.checks 全过才绿;失败详情带来源与具体数字。"""
    failures = _run_scenario(scenario)
    assert not failures, format_failures(failures)


def test_old_datasets_still_parse():
    """老数据集零迁移:两个既有数据集的 envelope 仍可正常加载解析。"""
    for name in ("small_lecturer_dialogue_scenarios.json",
                 "small_lecturer_adaptive_shadow_pilot_20.json"):
        payload = json.loads((datasets_dir() / name).read_text(encoding="utf-8"))
        assert payload.get("schema_version"), name
        assert isinstance(payload.get("scenarios"), list) and payload["scenarios"], name


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
    """失败行格式:scenario + source.issue + source.session + 详情(红要红得可追溯)。"""
    line = format_failures([{
        "scenario": "ladder-step-leaks-final-answer-13",
        "source": {"issue": 185, "session": "6a6320ca"},
        "check": "text_excludes_answer_values",
        "detail": "终答值 13 出现在 turns[3]",
    }])
    assert "source.issue=185" in line
    assert "source.session=6a6320ca" in line
    assert "13" in line
