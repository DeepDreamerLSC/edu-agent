"""老系统适配器雏形(00 §4.2/§8.2 阶段 1):驱动老仓库测试环境的合作方流程接口。

实现 #31 的 Subject 协议:M1 的被测对象。spike 雏形——流程跑通优先于完美:
- 登录态每用例新建(TTL 8h,1.1s 量级;缓存留到基线夜跑按实测决定,见 spike 结论);
- token 失效(401)自动重登录并重试一次(spike 边界三验实测的恢复路径);
- 会话按交互信封的 session_version 推进(服务端对陈旧版本宽容,spike 边界二验实测);
- 流式走 messages/stream,SSE 事件 start/status/interaction/delta/done/error,TTFT≈端到端(安全分片流);
- 凭据只从环境变量读(EDU_LEGACY_ACCOUNT/PASSWORD),不进代码不进日志(issue #3 判例)。

已知留桩(M1 阶段 2 接 runner 实战时补):attempt 复用策略(fresh student / attempt_action
restart)、confirm 信封应答词表、per-case 账号池分配。
"""

from __future__ import annotations

import json
import os
import time
import uuid

import httpx

from .runner import EnvironmentFailure

DEFAULT_BASE_URL = "https://edu-test.chiraliumai.cn"
SKILL_ID = "small_lecturer_coaching"
TERMINAL_STATES = frozenset({"completed", "failed", "cancelled", "incomplete"})
_TIMEOUT = httpx.Timeout(120.0, connect=10.0)


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Source-Channel": "owned_student_web",
        "X-Request-Id": f"legacy:{uuid.uuid4().hex[:12]}",
    }


class LegacyAdapter:
    """单条用例 = 登录 → open(幂等键)→ [refresh] → 学生回合(流式)直至终态或脚本耗尽。"""

    name = "legacy-partner-flow"

    def __init__(self, base_url: str | None = None,
                 account_env: str = "EDU_LEGACY_ACCOUNT",
                 password_env: str = "EDU_LEGACY_PASSWORD") -> None:
        self.base_url = base_url or os.environ.get("EDU_LEGACY_BASE_URL", DEFAULT_BASE_URL)
        self._account_env = account_env
        self._password_env = password_env

    def run_case(self, case: dict) -> dict:
        account = os.environ.get(self._account_env, "")
        password = os.environ.get(self._password_env, "")
        if not account or not password:
            raise EnvironmentFailure(f"环境变量 {self._account_env}/{self._password_env} 未设置")
        started = time.monotonic()
        client = httpx.Client(base_url=self.base_url, timeout=_TIMEOUT)
        session = {"token": "", "account": account, "password": password}
        try:
            session["token"] = self._login(client, account, password)
            return self._drive(client, session, case, started)
        except httpx.HTTPError as exc:
            raise EnvironmentFailure(f"老系统接口不可达:{type(exc).__name__}") from exc
        finally:
            client.close()

    # ---------- 流程驱动(00 §4.2:open → refresh → messages → confirm) ----------

    def _drive(self, client: httpx.Client, session: dict, case: dict, started: float) -> dict:
        question_id = str(case["question_id"])
        opened = self._send(client, session, "POST", f"/api/prepared-questions/{question_id}/open",
                            json_body={"idempotency_key": f"eval:{uuid.uuid4().hex}"})
        skill_session = opened["question"].get("active_session") or {}
        conversation = opened["conversation"]["conversation"]
        conversation_id = skill_session.get("conversation_id") or conversation["conversation_id"]
        session_id = skill_session.get("skill_session_id")
        version = opened.get("session_version")
        turns: list[dict] = []
        first = next((m for m in reversed(opened["conversation"].get("messages") or [])
                      if m.get("role") == "assistant"), None)
        if first is not None:
            turns.append({"student": "", "tutor": first.get("content", ""),
                          "state": skill_session.get("state", ""), "elapsed_ms": 0})
        self._send(client, session, "POST",
                   f"/api/conversations/{conversation_id}/skill-sessions/{session_id}/refresh")
        final_state = skill_session.get("state", "")
        for index, answer in enumerate(case.get("student_turns") or ["12", "3", "我讲完了", "确认结束"]):
            turn, version, final_state = self._turn(client, session,
                                                    (conversation_id, session_id),
                                                    version, answer, index)
            turns.append(turn)
            if final_state in TERMINAL_STATES:
                break
        return {
            "question_id": question_id,
            "attempt_id": skill_session.get("attempt_id"),
            "conversation_id": conversation_id,
            "final_state": final_state,
            "turns": turns,
            "total_ms": int((time.monotonic() - started) * 1000),
        }

    def _turn(self, client: httpx.Client, session: dict, target: tuple[str, str],
              version: int, answer: str, index: int) -> tuple[dict, int, str]:
        conversation_id, session_id = target
        body = {
            "content": answer,
            "skill_id": SKILL_ID,
            "input": {"skill_session_id": session_id, "expected_session_version": version},
            "client_turn_id": f"eval:{uuid.uuid4().hex[:8]}:{index}",
            "idempotency_key": f"eval:{uuid.uuid4().hex[:8]}:{index}",
        }
        started = time.monotonic()
        event_name = ""
        done: dict = {}
        path = f"/api/conversations/{conversation_id}/messages/stream"
        response = self._stream_once(client, session, path, body)
        try:
            if response.status_code != 200:
                response.read()
                raise EnvironmentFailure(f"messages/stream HTTP {response.status_code}")
            for line in response.iter_lines():
                if line.startswith("event:"):
                    event_name = line[6:].strip()
                elif line.startswith("data:") and event_name:
                    if event_name == "error":
                        raise EnvironmentFailure(f"流式错误事件:{line[5:].strip()[:120]}")
                    if event_name == "done":
                        done = json.loads(line[5:].strip())
        finally:
            response.close()
        message = done.get("assistant_message") or {}
        interaction = (message.get("metadata") or {}).get("interaction") or {}
        return (
            {"student": answer, "tutor": message.get("content", ""),
             "state": interaction.get("state", ""),
             "elapsed_ms": int((time.monotonic() - started) * 1000)},
            interaction.get("session_version") or version,
            interaction.get("state", ""),
        )

    def _stream_once(self, client: httpx.Client, session: dict, path: str, body: dict):
        """流式请求;401 时重登录重试一次(幂等键保证重发安全)。"""
        request = client.build_request("POST", path, json=body, headers=_headers(session["token"]))
        response = client.send(request, stream=True)
        if response.status_code == 401:
            response.close()
            session["token"] = self._login(client, session["account"], session["password"])
            request = client.build_request("POST", path, json=body, headers=_headers(session["token"]))
            response = client.send(request, stream=True)
        return response

    def _login(self, client: httpx.Client, account: str, password: str) -> str:
        response = client.post("/api/auth/login",
                               json={"account": account, "password": password, "remember": False})
        if response.status_code != 200:
            raise EnvironmentFailure(f"登录失败 HTTP {response.status_code}(不打印凭据)")
        return response.json()["access_token"]

    def _send(self, client: httpx.Client, session: dict, method: str, path: str,
              *, json_body: dict | None = None) -> dict:
        response = client.request(method, path, json=json_body, headers=_headers(session["token"]))
        if response.status_code == 401:
            # spike 边界三验:token 过期(401)→ 重登录后重试一次
            session["token"] = self._login(client, session["account"], session["password"])
            response = client.request(method, path, json=json_body, headers=_headers(session["token"]))
        if response.status_code != 200:
            raise EnvironmentFailure(f"{path} HTTP {response.status_code}:{response.text[:120]}")
        return response.json()
