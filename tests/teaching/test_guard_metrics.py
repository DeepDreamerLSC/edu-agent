"""护栏埋点合同(任务包1步1):命中规则 id 与被替换原文随会话落盘,兜底率可度量。

零真实模型(假 gateway);断言三护栏各自的 event 形态与干净输出零事件。
"""

from __future__ import annotations

import json

from fake_openai import FakeOpenAI, completion

from edu_agent.agents.small_lecturer import reply, start

from test_kernel_state_machine import QUESTION_TEXT, kernel_gateway, open_json, tutor_json


def test_leak_hit_records_rule_and_original(tmp_path):
    """泄露命中:guard_events 记 {guard:answer_leak, rule_ids, original=违规原文, regenerated}。"""
    clean = open_json("你打算从条件入手,一步步来。")
    fake = FakeOpenAI([completion(open_json("答案是 x=6。对吗?")), completion(clean)]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start({"text": "解方程 3x+7=25。", "answer": "x=6"},
                 {"grade": "五年级"}, gateway=gateway)
    gateway.close()
    fake.stop()
    events = turn.session.guard_events
    assert len(events) == 1
    event = events[0]
    assert event["guard"] == "answer_leak"
    assert "grounded_answer_disclosure" in event["rule_ids"]
    assert "x=6" in event["original"]  # 被替换原文在案(judge 可见)
    # 任务包2步2 修复重生成优先:命中后重调 tutor 拿到干净回复
    assert event["regenerated"] is True
    assert turn.text == json.loads(clean)["reply"]  # 重生成成功,干净回复到达学生面
    assert "x=6" not in turn.text


def test_clean_output_records_nothing(tmp_path):
    fake = FakeOpenAI([completion(open_json("你打算从哪一步开始?"))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start({"text": "解方程 3x+7=25。", "answer": "x=6"},
                 {"grade": "五年级"}, gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.session.guard_events == []


def test_events_persist_through_file_store(tmp_path):
    """guard_events 随 FileSessionStore 落盘并可恢复(asdict 全字段自动带上)。"""
    fake = FakeOpenAI([completion(open_json("答案是 x=6。")),
                       completion(open_json("你从条件入手,一步步来。")),  # 重生成(open schema)
                       completion(tutor_json("再想想?"))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start({"text": "解方程 3x+7=25。", "answer": "x=6"},
                  {"grade": "五年级"}, gateway=gateway)
    reply(first.session, "我不知道", gateway=gateway)
    gateway.close()
    fake.stop()
    from edu_agent.api import FileSessionStore
    store = FileSessionStore(tmp_path / "sessions")
    store.save(first.session)
    restored = store.load(first.session.session_id)
    assert restored is not None
    assert len(restored.guard_events) == 2  # 泄露事件 + 确定性揭示埋点(branch 分流)
    assert restored.guard_events[0]["guard"] == "answer_leak"
    assert restored.guard_events[1]["branch"] == "reveal"


def test_kernel_subject_transcript_carries_events(tmp_path):
    """评测面:KernelSubject transcript 带 guard_events(runner 可汇总兜底率)。"""
    from edu_agent.evals import KernelSubject
    from edu_agent.gateway import Gateway, ModelConfig, ModelRegistry, ProviderConfig, RoleConfig

    fake = FakeOpenAI([
        completion(open_json("答案是 x=6。")),
        completion(open_json("你打算从题目条件入手,一步步来。")),  # 泄露 → 重生成(open schema)
        completion(tutor_json("很好,你从条件入手了。")),             # student_turn 1
        completion(tutor_json("那你先算算 3x 等于多少?")),          # student_turn 2
    ]).start()
    providers = {"fake": ProviderConfig("fake", fake.url, None, True)}
    models = {"m": ModelConfig("m", "fake", "fake-model")}
    roles = {"tutor": RoleConfig(name="tutor", primary="m", fallback=None, json_strict=True,
                                 concurrency=2, first_token_timeout_s=2.0, total_timeout_s=5.0,
                                 max_attempts=2, backoff_base_ms=1, backoff_cap_ms=8)}
    gateway = Gateway(ModelRegistry(providers=providers, models=models, roles=roles), tmp_path)
    transcript = KernelSubject(gateway).run_case({
        "id": "eq", "question": "解方程 3x+7=25。", "grade": "五年级",
        "reference_answer": "x=6",
        "student_turns": ["我不会", "我想想"]})
    gateway.close()
    fake.stop()
    assert len(transcript["guard_events"]) == 3  # 泄露 + 两轮模型数字守卫埋点
    assert transcript["guard_events"][0]["guard"] == "answer_leak"
    assert transcript["guard_events"][1]["branch"] == "model"
    assert transcript["guard_events"][2]["branch"] == "model"
