"""脚本化 OpenAI 兼容服务器(02 §6 tests/fixtures:故障注入基础设施,只依赖标准库)。

用法:FakeOpenAI([Reply(...), ...]) 按顺序逐请求消费脚本;requests 记录收到的
请求体(解析后的 JSON),供断言重试次数、模型名与消息内容。SSE 流不以 [DONE]
结尾即模拟流式中途断开。
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@dataclass
class Reply:
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    json_body: dict | None = None       # 正常 chat completion 响应
    raw_body: str | None = None         # 原样返回(非法 JSON 注入)
    sse_lines: list[str] | None = None  # SSE 流(data: 行,不含空行分隔)
    delay_s: float = 0.0                # 发送响应前的延迟(超时注入)
    partial_body: str | None = None     # 谎报 Content-Length 后只发一半即断(connection 注入)


def completion(text: str = "你好", *, finish_reason: str = "stop",
               usage: dict | None = None) -> Reply:
    """构造一个正常的非流式 chat completion Reply。"""
    return Reply(json_body={
        "model": "fake-model",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": finish_reason,
        }],
        "usage": usage if usage is not None else {"prompt_tokens": 11, "completion_tokens": 7},
    })


def sse(*events: dict, done: bool = True, finish_reason: str = "stop",
        usage: dict | None = None) -> Reply:
    """构造一段 SSE 流:每个 dict 是一个 delta content chunk,结尾带 finish_reason/usage。"""
    lines = []
    for text in events:
        content = text if isinstance(text, str) else text["text"]
        lines.append(f'data: {json.dumps({"choices": [{"delta": {"content": content}}]})}')
    final: dict = {"choices": [{"delta": {}, "finish_reason": finish_reason}]}
    final["usage"] = usage if usage is not None else {"prompt_tokens": 11, "completion_tokens": 7}
    lines.append(f"data: {json.dumps(final)}")
    if done:
        lines.append("data: [DONE]")
    return Reply(sse_lines=lines)


class _Handler(BaseHTTPRequestHandler):
    fixture: "FakeOpenAI"

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        try:
            self.fixture.requests.append(json.loads(body))
        except json.JSONDecodeError:
            self.fixture.requests.append({"raw": body.decode("utf-8", "replace")})
        reply = self.fixture.next_reply()
        if reply.delay_s:
            time.sleep(reply.delay_s)
        if reply.partial_body is not None:
            payload = reply.partial_body.encode("utf-8")
            self.send_response(reply.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload) + 64))  # 谎报长度,发一半即断
            self.end_headers()
            self.wfile.write(payload)
            self.close_connection = True
            return
        if reply.sse_lines is not None:
            self.send_response(reply.status)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for line in reply.sse_lines:
                self.wfile.write((line + "\n\n").encode("utf-8"))
                self.wfile.flush()
            return
        payload = (
            reply.raw_body.encode("utf-8")
            if reply.raw_body is not None
            else json.dumps(reply.json_body or {}).encode("utf-8")
        )
        self.send_response(reply.status)
        for key, value in reply.headers.items():
            self.send_header(key, value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


class FakeOpenAI:
    """按脚本回复的本地 OpenAI 兼容服务器;url 直接作为 provider base_url。"""

    def __init__(self, replies: list[Reply]) -> None:
        self.replies = list(replies)
        self.requests: list[dict] = []
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), type("Handler", (_Handler,), {"fixture": self}))

    def next_reply(self) -> Reply:
        with self._lock:
            if self.replies:
                return self.replies.pop(0)
        # 脚本耗尽:返回显式 599,测试失败信息里能看到原因,而不是模糊的连接错误
        return Reply(status=599, raw_body='{"error": "FakeOpenAI script exhausted"}')

    def start(self) -> "FakeOpenAI":
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
