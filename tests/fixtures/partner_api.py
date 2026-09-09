"""合作方接口合同测试的共享助手(02 §6 tests/fixtures 同类;不计测试比分子)。

确定性假内核(ScriptedKernel)+ 本地测试服务器起停(_serve)+ HTTP 助手
(post/open_session)+ SSRF 边界断言(_assert_local_base)。原散落在
test_api_service.py,被 10 个合同测试文件导入——搬到 fixtures 只改导入路径,
零断言变化(决策 1:精简不开白名单,共享助手下移出比值分子)。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from edu_agent.api import build_service, build_server


@dataclass
class StubTurn:
    text: str
    ready_to_confirm: bool = False


@dataclass
class StubSummary:
    text: str
    status: str = "needs_review"


class ScriptedKernel:
    """确定性假内核:预置回合序列;第 N 轮后可进入 ready。"""

    def __init__(self, replies: list[str], ready_at: int | None = None,
                 start_text: str = "我们先看已知条件,题目要我们求什么?",
                 start_error: Exception | None = None) -> None:
        self.replies = list(replies)
        self.ready_at = ready_at
        self.start_text = start_text
        self.start_error = start_error
        self.start_calls = 0
        self.reply_calls = 0
        self.finish_calls = 0

    def start(self, question: dict, learner: dict) -> StubTurn:
        self.start_calls += 1
        if self.start_error:
            raise self.start_error
        return StubTurn(self.start_text)

    def reply(self, session: dict, student_message: str) -> StubTurn:
        index = min(self.reply_calls, len(self.replies) - 1)
        text = self.replies[index]
        self.reply_calls += 1
        ready = self.ready_at is not None and self.reply_calls >= self.ready_at
        return StubTurn(text, ready_to_confirm=ready)

    def finish(self, session: dict) -> StubSummary:
        self.finish_calls += 1
        return StubSummary("学习小结", "needs_review")


def _assert_local_base(base: str) -> None:
    """SSRF 边界:测试只允许打 127.0.0.1 环回上的本地测试服务器。"""
    parsed = urlparse(base)
    assert parsed.scheme == "http" and parsed.hostname == "127.0.0.1", base


def post(base: str, path: str, payload: dict | None = None, auth: bool = True) -> httpx.Response:
    _assert_local_base(base)
    headers = {"Authorization": "Bearer test-token"} if auth else {}
    return httpx.post(f"{base}{path}", json=payload or {}, headers=headers, timeout=5.0, trust_env=False)


def _serve(kernel: ScriptedKernel) -> tuple[str, object]:
    server = build_server(build_service(kernel))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}", server


def open_session(base: str, question_id: str = "q-101", key: str = "idem-1") -> dict:
    response = post(base, f"/api/prepared-questions/{question_id}/open", {"idempotency_key": key})
    assert response.status_code == 200
    return response.json()
