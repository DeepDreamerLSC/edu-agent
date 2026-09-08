"""KernelSubject 契约(00 §8.4 阶段 3:被测对象换内核,评测线零改动)。

假 gateway(FakeOpenAI)驱动 start→reply×N→finish;断言 transcript 形态与
适配器同口径(turns/summary/final_state)、判停语义(ready 后余剧本不发)、
环境失败映射。零真实模型。
"""

from __future__ import annotations

import json

import pytest
from fake_openai import FakeOpenAI, Reply, completion

from edu_agent.evals import EnvironmentFailure, KernelSubject
from edu_agent.gateway import Gateway, ModelConfig, ModelRegistry, ProviderConfig, RoleConfig


def gateway_for(base_url: str, facts_dir) -> Gateway:
    providers = {"fake": ProviderConfig("fake", base_url, None, True)}
    models = {"m": ModelConfig("m", "fake", "fake-model")}
    role = RoleConfig(
        name="tutor", primary="m", fallback=None, json_strict=True,
        concurrency=2, first_token_timeout_s=2.0, total_timeout_s=5.0,
        max_attempts=2, backoff_base_ms=1, backoff_cap_ms=8,
    )
    return Gateway(ModelRegistry(providers=providers, models=models, roles={"tutor": role}), facts_dir)


CASE = {
    "id": "stability_equation_subtract",
    "question": "解方程 3x+7=25,并说明每一步为什么这样做。",
    "grade": "五年级",
    "student_turns": ["我想两边都减去7。", "再同时除以3。", "检验通过了。"],
}


def tutor_json(text: str, ready: bool = False) -> str:
    return json.dumps({"reply": text, "ready_to_confirm": ready,
                       "cited_numbers": []}, ensure_ascii=False)


def open_json(text: str) -> str:
    """统一 open 响应(任务包2步4):start 一次调用产出的 schema。"""
    return json.dumps({"acceptable": True, "transcription": "", "steps": [],
                       "reply": text}, ensure_ascii=False)


def test_run_case_drives_full_script(tmp_path):
    fake = FakeOpenAI([
        completion(open_json("题目要我们求什么?")),
        completion(tutor_json("为什么两边都能减7?")),
        completion(tutor_json("很好,再同时除以3。", ready=True)),
        completion(json.dumps({"summary": "你用等式性质解出 x=6 并检验。"}, ensure_ascii=False)),
    ]).start()
    gateway = gateway_for(fake.url, tmp_path)
    transcript = KernelSubject(gateway).run_case(CASE)
    gateway.close()
    fake.stop()
    assert transcript["final_state"] == "completed"
    assert transcript["summary"] == "你用等式性质解出 x=6 并检验。"
    assert [t["student"] for t in transcript["turns"]] == ["", "我想两边都减去7。", "再同时除以3。"]
    # 判停:第三轮 ready 后余下剧本轮("检验通过了。")不再发
    assert len(fake.requests) == 4 and transcript["turns"][-1]["state"] == "ready_to_confirm"


def test_run_case_environment_failure_is_retryable(tmp_path):
    fake = FakeOpenAI([Reply(status=500), Reply(status=500)]).start()
    gateway = gateway_for(fake.url, tmp_path)
    with pytest.raises(EnvironmentFailure):
        KernelSubject(gateway).run_case(CASE)
    gateway.close()
    fake.stop()


def test_run_case_content_failure_reraises(tmp_path):
    fake = FakeOpenAI([completion("我不会"), completion("还是不会")]).start()  # 非 JSON → 修复重试一次后 schema_violation(内容类)
    gateway = gateway_for(fake.url, tmp_path, )
    with pytest.raises(Exception) as excinfo:
        KernelSubject(gateway).run_case(CASE)
    gateway.close()
    fake.stop()
    assert not isinstance(excinfo.value, EnvironmentFailure)
