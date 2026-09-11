"""tests/teaching 与评测面共享的教学内核测试基础设施(02 §6 tests/fixtures:不计测试比分子)。

一处定义、多处引用(与 partner_api.py 同款决策):指向假上游的 Gateway 构造
(tutor_gateway / kernel_gateway)、内核 schema 剧本构造器(open_json / tutor_json)、
对象注入假 gateway(FakeGateway)与 FakeOpenAI+Gateway 生命周期上下文
(kernel_env / tutor_env)。原散落在 tests/teaching/teachkit.py 与
test_kernel_state_machine.py / test_drift_and_tone.py,收拢后各测试文件只保留
自己的剧本与断言。

谁在用:tests/teaching 全目录(内核状态机/护栏/首问/复读)与
tests/evals 的 test_kernel_subject / test_image_teaching(经 kernel_env)。
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from fake_openai import FakeOpenAI

from edu_agent.gateway import (
    Gateway,
    ModelConfig,
    ModelRegistry,
    ProviderConfig,
    RoleConfig,
)


def tutor_gateway(base_url: str, facts_dir: Path) -> Gateway:
    """单 tutor 角色(json_strict false,不带 schema)指向假上游。"""
    providers = {"fake": ProviderConfig("fake", base_url, None, False)}
    models = {"m": ModelConfig("m", "fake", "fake-model")}
    role = RoleConfig(
        name="tutor", primary="m", fallback=None, json_strict=False,
        concurrency=2, first_token_timeout_s=2.0, total_timeout_s=5.0,
        max_attempts=2, backoff_base_ms=1, backoff_cap_ms=8,
    )
    return Gateway(ModelRegistry(providers=providers, models=models, roles={"tutor": role}), facts_dir)


def kernel_gateway(tutor_url: str, facts_dir: Path) -> Gateway:
    """tutor(json_strict=true,grammar 路径)角色指向假上游(教学内核全链路用)。"""
    providers = {"fake_tutor": ProviderConfig("fake_tutor", tutor_url, None, True)}
    models = {"m": ModelConfig("m", "fake_tutor", "fake-model")}
    role = RoleConfig(
        name="tutor", primary="m", fallback=None, json_strict=True,
        concurrency=2, first_token_timeout_s=2.0, total_timeout_s=5.0,
        max_attempts=2, backoff_base_ms=1, backoff_cap_ms=8,
    )
    return Gateway(ModelRegistry(providers=providers, models=models, roles={"tutor": role}), facts_dir)


@contextmanager
def _started(base_url_factory: Callable[[str, Path], Gateway],
             tmp_path: Path, replies: list) -> Iterator[tuple[FakeOpenAI, Gateway]]:
    """FakeOpenAI(按 replies 剧本)+ Gateway 的生命周期:进入即启动,退出即关闭。

    断言可在块内或块后进行(fake.requests 在 stop 后仍可读);脚本耗尽/断言失败
    同样保证关闭(比旧的手工 close/stop 更稳)。
    """
    fake = FakeOpenAI(replies).start()
    gateway = base_url_factory(fake.url, tmp_path)
    try:
        yield fake, gateway
    finally:
        gateway.close()
        fake.stop()


def kernel_env(tmp_path: Path, replies: list):
    """kernel_gateway 版假上游环境(教学内核全链路:json_strict=true)。"""
    return _started(kernel_gateway, tmp_path, replies)


def tutor_env(tmp_path: Path, replies: list):
    """tutor_gateway 版假上游环境(护栏单函数经 ModelRequest 直调,非 strict)。"""
    return _started(tutor_gateway, tmp_path, replies)


def tutor_json(reply_text: str, ready: bool = False,
               cited_numbers: list[float] | None = None) -> str:
    # reason 首位(#146 M1):镜像真模型 grammar 输出的字段序;内核不读该值(规划装置)
    return json.dumps({"reason": "先引导学生自己想到下一步", "reply": reply_text,
                       "ready_to_confirm": ready,
                       "cited_numbers": cited_numbers or []}, ensure_ascii=False)


def open_json(reply_text: str, *, acceptable: bool = True, transcription: str = "",
              steps: list[dict] | None = None) -> str:
    """统一 open schema(任务包2步4):一次调用产出 转写 + 分步解 + 首问。"""
    return json.dumps({
        "acceptable": acceptable,
        "transcription": transcription,
        "steps": steps or [],
        "reply": reply_text,
    }, ensure_ascii=False)


class FakeGateway:
    """对象注入假 gateway(零网络零端口,确定性):tutor/vision 按剧本出牌,记录全部请求。"""

    def __init__(self, tutor_payloads: list[dict],
                 vision_payloads: list[dict] | None = None):
        self.tutor_queue = list(tutor_payloads)
        self.vision_queue = list(vision_payloads or [])
        self.requests: list[dict] = []

    def invoke(self, request):
        self.requests.append({"role": request.role, "messages": request.messages})
        payload = (self.vision_queue.pop(0) if request.role == "vision" and self.vision_queue
                   else self.tutor_queue.pop(0) if self.tutor_queue
                   else {"reply": "先回到当前小问。", "ready_to_confirm": False,
                         "cited_numbers": []})
        response = type("R", (), {})()
        response.text = json.dumps(payload, ensure_ascii=False)
        return response
