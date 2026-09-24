"""KernelSubject 契约(00 §8.4 阶段 3:被测对象换内核,评测线零改动)。

假 gateway(FakeOpenAI)驱动 start→reply×N→finish;断言 transcript 形态与
适配器同口径(turns/summary/final_state)、判停语义(ready 后余剧本不发)、
环境失败映射。零真实模型;Gateway 构造与剧本构造器在 tests/fixtures/teachkit.py。
"""

from __future__ import annotations

import json

import pytest
from fake_openai import Reply, completion

from edu_agent.evals import EnvironmentFailure, KernelSubject

from teachkit import FakeGateway, kernel_env, open_json, tutor_json

# Gate B 段(#414 §四)改据:completed 需当轮 CompletionEvidence——题面带 answer_spec
# 声明面(**测试本地**;现网题库无此面,缺口留人审),学生末轮「x=6,检验通过了。」
# 经 equation_form 窄面命中即当轮证据;剧本结构与轮数不变。
CASE = {
    "id": "stability_equation_subtract",
    "question": {"text": "解方程 3x+7=25,并说明每一步为什么这样做。",
                 "answer": "x=6", "answer_spec": {"answer_type": "equation_form"}},
    "grade": "五年级",
    "student_turns": ["我想两边都减去7。", "再同时除以3。", "x=6,检验通过了。"],
}


def test_run_case_drives_full_script(tmp_path):
    def slow(reply: Reply) -> Reply:
        """回复轮注入 5ms 延迟:elapsed_ms 的计时断言由 sleep 保证下界(≥5ms)。

        无延迟时快 runner 上亚毫秒往返会被 int() 地板成 0,`> 0` 断言随机红
        (2026-09-10 run 34470133408 的 flake:同一代码 10:58 绿 / 11:13 红)。"""
        reply.delay_s = 0.005
        return reply

    with kernel_env(tmp_path, [
        completion(open_json("题目要我们求什么?")),
        slow(completion(tutor_json("为什么两边都能减7?"))),
        slow(completion(tutor_json("很好,再同时除以3。", ready=True))),
        # Gate B 段(#414 §四)改据:t3 学生终述「x=6」→ close 路径在轮内直接走
        # finish(不再有 t3 的 reply 模型轮),此处即收束 finish 消费的 summary。
        slow(completion(json.dumps({"summary": "你用等式性质解出 x=6 并检验。"},
                                   ensure_ascii=False))),
    ]) as (fake, gateway):
        transcript = KernelSubject(gateway).run_case(CASE)
        assert transcript["final_state"] == "completed"
        assert transcript["summary"] == "你用等式性质解出 x=6 并检验。"
        # close-loop-fix:ready 后剧本轮照发(产线忠实——客户端 ready 后继续发
        # 消息,444a/2c85 死环正是 ready 后续轮);completed 才断。
        assert [t["student"] for t in transcript["turns"]] == [
            "", "我想两边都减去7。", "再同时除以3。", "x=6,检验通过了。"]
        # open + 2 reply + 收束 finish(t3 走 close 路径,finish 模型总结即第 4 调用)
        assert len(fake.requests) == 4
        # P1-5 回归:elapsed_ms 是真实耗时,不是 session_version 假数据(首问恒 0;
        # 回复轮 ≥ 注入延迟 5ms——session_version 假数据 1/2/3 过不了这条)
        assert transcript["turns"][0]["elapsed_ms"] == 0
        assert all(turn["elapsed_ms"] >= 5 for turn in transcript["turns"][1:])


def test_run_case_environment_failure_is_retryable(tmp_path):
    with kernel_env(tmp_path, [Reply(status=500), Reply(status=500)]) as (fake, gateway):
        with pytest.raises(EnvironmentFailure):
            KernelSubject(gateway).run_case(CASE)


# ---------- same_turn_ready_and_evidence_would_complete 探针(用户裁 2026-09-24 ②) ----------

# 4531 形态(holdout socraticmath_train_4531 的忠实摘录):t1 代数终答句
# (完整推导收尾「6a+2b」,ratio_or_expression 窄面当轮 evidence)+ t2 代数
# 表达理解延伸轮(无答案)。answer_spec = 测试本地声明面(组装契约
# kernel._answer_spec;现网题库无此面)。
CASE_4531 = {
    "id": "socraticmath_train_4531",
    "question": {"text": "为鼓励居民节约用水，某市规定，每户每月用水不超过6m3按每"
                         "立方米a元收费，超过6m3的部分按每立方米b元收费．小涛家上月"
                         "用水8m3，他家应交水费(____）元．",
                 "answer": "6a+2b",
                 "answer_spec": {"answer_type": "ratio_or_expression"}},
    "grade": "六年级",
    "student_turns": [
        "对于小涛家的情况，他上个月用了8立方米的水，所以前6立方米按照每立方米a元"
        "计算，之后两立方米按每立方米b元计算。所以总的水费就是6a+2b。",
        "这种式子是一种代数表达方式，字母代表未知的数，等到知道数的确切值的时候，"
        "就可以替换掉字母，得到结果。",
    ],
}


def test_probe_flags_4531_form_same_turn_ready_and_evidence(tmp_path):
    """探针(用户裁 2026-09-24 ②,diagnostic-only):4531 型消耗形态——t1 学生
    终答句与导师 ready 判定同轮(evidence 当轮在场)→ 探针 True;t2 延伸轮
    evidence 覆写 None → False。纯观测:final_state 语义不变(剧本尽头 finish
    被 completion 门拒 → needs_review,消费时机差一拍形态原样呈现),探针
    不进任何 PASS 判定。"""
    with kernel_env(tmp_path, [
        completion(open_json("这道题要我们求什么?")),
        completion(tutor_json("很好，你把分段计费的道理讲完整了。", ready=True)),
        completion(tutor_json("对的，字母换成具体数值就能算出结果。", ready=True)),
    ]) as (fake, gateway):
        transcript = KernelSubject(gateway).run_case(CASE_4531)
    # t0 首问:无学生消息、未达 ready → False
    assert transcript["turns"][0]["same_turn_ready_and_evidence_would_complete"] is False
    # t1:state=ready_to_confirm 且当轮 evidence 在 → True(4531 形态标记)
    assert transcript["turns"][1]["state"] == "ready_to_confirm"
    assert transcript["turns"][1]["same_turn_ready_and_evidence_would_complete"] is True
    # t2:延伸轮,evidence 覆写 None → False
    assert transcript["turns"][2]["state"] == "ready_to_confirm"
    assert transcript["turns"][2]["same_turn_ready_and_evidence_would_complete"] is False
    # 纯观测零行为:final_state 仍是 needs_review(production 语义不改)
    assert transcript["final_state"] == "needs_review"
    # 分诊信号:t1 配对在场但未同轮消费 → 尽头 finish 被 completion 门拒
    # (guard_events 另含每模型轮的数字守卫观测事件,只按分支过滤断言)
    assert [event for event in transcript["guard_events"]
            if event.get("branch") == "completion_gate_rejected"] == [
        {"branch": "completion_gate_rejected", "turn": 2}]


def test_run_case_content_failure_reraises(tmp_path):
    # 非 JSON → 修复重试一次后 schema_violation(内容类)
    with kernel_env(tmp_path, [completion("我不会"), completion("还是不会")]) as (fake, gateway):
        with pytest.raises(Exception) as excinfo:
            KernelSubject(gateway).run_case(CASE)
    assert not isinstance(excinfo.value, EnvironmentFailure)


# ---------- parity 口径(#333 方向修正单 2026-09-19 裁①,取代 #178 feed_answer 断点) ----------

_QA = {"text": "鸡和兔一共有8只，共有26只脚。鸡和兔各有多少只？说明思路。",
       "answer": "鸡3只，兔5只"}
_OPEN_MIN = {"acceptable": True, "transcription": "", "steps": [],
             "reply": "我们先看题目里给了什么。"}


def _start_request_body(case: dict) -> str:
    gateway = FakeGateway(tutor_payloads=[_OPEN_MIN])
    KernelSubject(gateway).run_case(case)
    return json.dumps(gateway.requests[0]["messages"], ensure_ascii=False)


def test_parity_kernel_sees_authoritative_answer():
    """parity 裁①:对齐生产 resolve() 契约,question.answer 照进内核 start 入参。"""
    assert "鸡3只" in _start_request_body(
        {"id": "x", "question": _QA, "grade": "六年级", "student_turns": []})


def test_parity_reference_answer_fills_gap_and_analysis_from_steps():
    """question 缺 answer 时由场景 reference_answer(value/steps)补,steps 拼 analysis。"""
    body = _start_request_body({"id": "x", "question": {"text": "某数是500的两倍。"},
                                "grade": "", "student_turns": [],
                                "reference_answer": {"value": "1000",
                                                     "steps": ["先算 500×2", "得 1000"]}})
    assert "1000" in body


def test_parity_answer_status_defaulted():
    """answer_status 恒有:案缺省补 incorrect(生产 answer_correct 映射对齐)。"""
    body = _start_request_body({"id": "x", "question": {"text": "鸡和兔一共有8只。"},
                                "grade": "", "student_turns": []})
    assert "incorrect" in body
