"""假老系统服务器(02 §6 tests/fixtures):合作方流程接口的最小脚本化实现。

覆盖适配器雏形依赖的端点:auth/login、prepared-questions/{id}/open、
skill-sessions/{id}/refresh、conversations/{cid}/messages(stream)。
可注入:token 中途失效(401 一次)、流式 error 事件。
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _Handler(BaseHTTPRequestHandler):
    fixture: "FakeLegacy"

    def _reply(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse(self, events: list[tuple[str, dict]]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for name, payload in events:
            self.wfile.write(f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()

    def _authed(self) -> bool:
        token = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        with self.fixture._lock:
            return token in self.fixture.valid_tokens

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        path = self.path
        with self.fixture._lock:
            self.fixture.requests.append({"path": path, "body": body})
        if path == "/api/auth/login":
            self._handle_login()
        elif not self._authed():
            self._reply(401, {"error": {"code": "USER_LOGIN_REQUIRED", "status_code": 401}})
        elif path.endswith("/open"):
            self._handle_open()
        elif "/skill-sessions/" in path and path.endswith("/refresh"):
            self._reply(200, {"interaction": {"state": "collecting_inputs",
                                              "session_version": self.fixture.version}})
        elif path.endswith("/messages/stream") or path.endswith("/messages"):
            self._handle_message(path)
        else:
            self._reply(404, {"error": {"code": "NOT_FOUND", "status_code": 404}})

    def _handle_login(self) -> None:
        with self.fixture._lock:
            self.fixture.login_count += 1
            token = f"tok-{self.fixture.login_count}"
            self.fixture.valid_tokens.add(token)
        self._reply(200, {"access_token": token, "expires_in": 28800,
                          "user": {"user_id": "u1", "tenant_id": "capacity-test-school"}})

    def _handle_open(self) -> None:
        fake = self.fixture
        with fake._lock:
            if fake.revoke_token_after_open and fake.valid_tokens:
                fake.valid_tokens.clear()  # 模拟登录态中途过期
        self._reply(200, {
            "question": {"active_session": {
                "conversation_id": fake.conversation_id,
                "skill_session_id": fake.session_id,
                "attempt_id": fake.attempt_id, "state": "collecting_inputs"}},
            "conversation": {"conversation": {"conversation_id": fake.conversation_id},
                             "messages": [{"role": "assistant", "content": "先看看图上有几个圆片?"}]},
            "session_version": fake.version, "first_question_ready": True, "restored": False})

    def _handle_message(self, path: str) -> None:
        fake = self.fixture
        with fake._lock:
            fake.version += 1
            version = fake.version
            remaining = len(fake.tutor_replies)
            reply = fake.tutor_replies.pop(0) if fake.tutor_replies else "很好,你讲清楚了。"
            state = "collecting_inputs" if remaining > 0 else "completed"
            turn_index = len(fake.requests)
        message = {"message_id": f"msg_{turn_index}", "content": reply,
                   "metadata": {"interaction": {"state": state, "session_version": version}}}
        if not path.endswith("/stream"):
            self._reply(200, {"assistant_message": message})
            return
        if fake.stream_error_on_turn == turn_index:
            self._sse([("status", {"stage": "generating"}),
                       ("error", {"code": "MODEL_GATEWAY_TIMEOUT", "retryable": True})])
            return
        self._sse([
            ("status", {"stage": "generating"}),
            ("interaction", {"interaction": {"state": state}}),
            ("delta", {"delta": reply[:4]}),
            ("done", {"assistant_message": message}),
        ])

    def log_message(self, format: str, *args: object) -> None:
        return


class FakeLegacy:
    """有状态假服务:登录发 token;open 建会话;每条消息出一条脚本回复,耗尽即 completed。"""

    def __init__(self, tutor_replies: list[str], *, revoke_token_after_open: bool = False,
                 stream_error_on_turn: int | None = None) -> None:
        self.tutor_replies = list(tutor_replies)
        self.revoke_token_after_open = revoke_token_after_open
        self.stream_error_on_turn = stream_error_on_turn
        self.login_count = 0
        self.valid_tokens: set[str] = set()
        self.version = 3
        self.conversation_id = "conv_fake"
        self.session_id = "skillsess_fake"
        self.attempt_id = "qat_fake"
        self.requests: list[dict] = []
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), type("Handler", (_Handler,), {"fixture": self}))

    def start(self) -> "FakeLegacy":
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
