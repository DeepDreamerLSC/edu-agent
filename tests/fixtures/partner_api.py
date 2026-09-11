"""合作方接口合同测试的共享助手(02 §6 tests/fixtures 同类;不计测试比分子)。

确定性假内核(ScriptedKernel / RecordingKernel)+ 题源桩(MapSource)+ 本地测试
服务器起停(serving/_serve)+ HTTP 助手(post/put/get/open_session/parse_sse)
+ gateway 假响应面(text_response/VISION_OK)+ SSRF 边界断言(_assert_local_base)。
原散落在各合同测试文件——共享助手下移出比值分子(决策 1:精简不开白名单,零断言变化)。

谁在用:tests/contracts 全目录(18 个文件;serving/HTTP 助手/内核桩共享)。
"""

from __future__ import annotations

import contextlib
import json
import threading
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from edu_agent.api import build_service, build_server

from auth_testing import TEST_TOKEN

# vision 检查的假响应载荷(内核 adapter / 交互信封测试共用同一确定性面)
VISION_OK = {"acceptable": True, "reason": "单题清晰", "transcription": ""}


@dataclass
class StubTurn:
    text: str
    session: object = None
    ready_to_confirm: bool = False
    status: str = "completed"


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
        ready = self.ready_at is not None and self.reply_calls >= self.ready_at
        return StubSummary("学习小结", "completed" if ready else "needs_review")


class RecordingKernel:
    """确定性内核桩:记录收到的题面 dict,固定回复序列。"""

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.questions: list[dict] = []
        self.learners: list[dict] = []

    def start(self, question: dict, learner: dict) -> StubTurn:
        self.questions.append(question)
        self.learners.append(learner)
        reply = self.replies[min(len(self.questions) - 1, len(self.replies) - 1)]
        return StubTurn(reply)

    def reply(self, session: object, student_message: str) -> StubTurn:
        return StubTurn("思路对。")

    def finish(self, session: object) -> StubTurn:
        return StubTurn("总结")


class MapSource:
    """确定性题源:命中返回 seed 同构面,未命中 KeyError(题库未命中信号)。"""

    def resolve(self, question_id: str) -> dict:
        if question_id != "equation_subtract":
            raise KeyError(f"题源不含 question_id:{question_id}")
        return {"text": "解方程 3x+7=25,并说明每一步为什么这样做。", "answer": "x=6",
                "analysis": "等式两边先同时减去 7。", "image": None,
                "knowledge_points": ["简易方程"], "grade": "五年级",
                "answer_correct_provenance": "partner_question_bank"}


def text_response(text: str):
    """gateway 假响应:仅 .text 字段(与真 gateway 返回面同构的最小对象)。"""
    response = type("R", (), {})()
    response.text = text
    return response


def _assert_local_base(base: str) -> None:
    """SSRF 边界:测试只允许打 127.0.0.1 环回上的本地测试服务器。"""
    parsed = urlparse(base)
    assert parsed.scheme == "http" and parsed.hostname == "127.0.0.1", base


@contextlib.contextmanager
def serving(kernel=None, *, service=None, identity=None, files=None, **service_kwargs):
    """起本地测试服务(daemon 线程)并托管停机;yield http://127.0.0.1:{port}。

    service 已构造时直接用(不再过 build_service);identity/files 传给
    build_server——依赖 env 的装配(如 HMAC 密钥、CORS 白名单)在 build_server
    时读取,须在进入本上下文前就位。
    """
    svc = service if service is not None else build_service(kernel, **service_kwargs)
    server = build_server(svc, identity, files)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def post(base: str, path: str, payload: dict | None = None, auth: bool = True,
         status: int | None = None) -> httpx.Response:
    _assert_local_base(base)
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"} if auth else {}
    response = httpx.post(f"{base}{path}", json=payload or {}, headers=headers,
                          timeout=5.0, trust_env=False)
    if status is not None:
        assert response.status_code == status, response.text
    return response


def put(base: str, path: str, content: bytes, content_type: str, *,
        token: str | None = TEST_TOKEN, status: int | None = None) -> httpx.Response:
    """PUT 二进制形态(上传面);超时放宽到 10s(整图字节体)。"""
    _assert_local_base(base)
    headers = {"Content-Type": content_type}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    response = httpx.put(f"{base}{path}", content=content, headers=headers,
                         timeout=10.0, trust_env=False)
    if status is not None:
        assert response.status_code == status, response.text
    return response


def get(base: str, path: str, *, token: str | None = TEST_TOKEN,
        headers: dict[str, str] | None = None, status: int | None = None) -> httpx.Response:
    _assert_local_base(base)
    all_headers = dict(headers or {})
    if token is not None:
        all_headers.setdefault("Authorization", f"Bearer {token}")
    response = httpx.get(f"{base}{path}", headers=all_headers, timeout=5.0, trust_env=False)
    if status is not None:
        assert response.status_code == status, response.text
    return response


def _serve(kernel: ScriptedKernel) -> tuple[str, object]:
    server = build_server(build_service(kernel))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}", server


def open_session(base: str, question_id: str = "q-101",
                 key: str | None = None) -> dict:
    if key is None:
        key = f"idem-{question_id}"
    response = post(base, f"/api/prepared-questions/{question_id}/open",
                    {"idempotency_key": key})
    assert response.status_code == 200
    return response.json()


def parse_sse(raw: bytes) -> list[tuple[str, dict]]:
    """SSE 字节流 → (event, data) 列表(流式合同共用的最小解析)。"""
    frames = []
    for block in raw.decode("utf-8").strip().split("\n\n"):
        lines = block.split("\n")
        frames.append((lines[0].removeprefix("event: "),
                       json.loads(lines[1].removeprefix("data: "))))
    return frames
