"""老系统适配器(00 §4.2/§8.2 阶段 1-2):驱动老仓库测试环境的合作方流程接口。

实现 #31 的 Subject 协议:M1 的被测对象。接口行为依据 spike 结论
(docs/evals/spike-legacy-adapter.md,实测合同):
- token 失效(401)自动重登录并重试一次(幂等键保证重发安全);
- 会话按交互信封的 session_version 推进(服务端对陈旧版本宽容);
- 流式走 messages/stream,SSE 事件 start/status/interaction/delta/done/error,TTFT≈端到端;
- attempt 对(学生,题目)粘性 → fresh 学生池轮换(看板 #34 阶段 2 参数):
  池文件路径由环境变量 EDU_LEGACY_STUDENT_POOL 注入(老仓库只读引用),
  按 case_id 稳定哈希选学生(续跑重入用同一学生,恢复既有 attempt);
  账号/密码只经内存,不进代码不进日志(issue #3 判例)。

留桩:confirm 信封应答词表(阶段 3 场景驱动);attempt_action=restart 不碰(未实测)。
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path

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


def load_student_pool(path: Path | str) -> list[tuple[str, str]]:
    """从 capacity 账号库文件读 (account, password) 列表;只在此处触值,不外传不打印。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    students = [s for s in data.get("students", []) if s.get("role") == "student"]
    pool = [(s["account"], s["password"]) for s in students if s.get("account") and s.get("password")]
    if not pool:
        raise EnvironmentFailure(f"学生池为空:{path}")
    return pool


class LegacyAdapter:
    """单条用例 = 选 fresh 学生登录 → open(幂等键)→ [refresh] → 流式回合直至终态。"""

    name = "legacy-partner-flow"

    def __init__(self, base_url: str | None = None,
                 pool_env: str = "EDU_LEGACY_STUDENT_POOL") -> None:
        self.base_url = base_url or os.environ.get("EDU_LEGACY_BASE_URL", DEFAULT_BASE_URL)
        self._pool_env = pool_env
        self._pool: list[tuple[str, str]] | None = None
        self._pool_lock = threading.Lock()

    def _student_for(self, case: dict) -> tuple[str, str]:
        with self._pool_lock:
            if self._pool is None:
                path = os.environ.get(self._pool_env, "")
                if not path:
                    raise EnvironmentFailure(f"环境变量 {self._pool_env} 未设置(学生池文件路径)")
                self._pool = load_student_pool(path)
        # 驱动侧按批次顺序显式分配(续跑确定性、批内无碰撞);缺省按 case_id 稳定哈希兜底
        if isinstance(case.get("student_index"), int):
            return self._pool[case["student_index"] % len(self._pool)]
        digest = hashlib.sha256(str(case.get("id", "")).encode("utf-8")).hexdigest()
        return self._pool[int(digest[:8], 16) % len(self._pool)]

    def run_case(self, case: dict) -> dict:
        account, password = self._student_for(case)
        started = time.monotonic()
        client = httpx.Client(base_url=self.base_url, timeout=_TIMEOUT)
        session = {"token": "", "account": account, "password": password}
        try:
            login_started = time.monotonic()
            session["token"] = self._login(client, account, password)
            session["login_ms"] = int((time.monotonic() - login_started) * 1000)
            return self._drive(client, session, case, started)
        except httpx.HTTPError as exc:
            raise EnvironmentFailure(f"老系统接口不可达:{type(exc).__name__}") from exc
        finally:
            client.close()

    # ---------- 流程驱动(00 §4.2:open → refresh → messages → confirm) ----------

    def _drive(self, client: httpx.Client, session: dict, case: dict, started: float) -> dict:
        question_id = str(case["question_id"])
        case_tag = hashlib.sha256(str(case.get("id", question_id)).encode("utf-8")).hexdigest()[:8]
        open_started = time.monotonic()
        opened = self._send(client, session, "POST", f"/api/prepared-questions/{question_id}/open",
                            json_body={"idempotency_key": f"eval:{case_tag}:open"})
        open_ms = int((time.monotonic() - open_started) * 1000)
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
        # refresh 端点已在 spike 实测(0.6s);批跑不做 open 后的冗余刷新——
        # open 响应的信封即新鲜状态,多一次刷新多占一次老系统模型队列(429 实测)
        final_state = skill_session.get("state", "")
        for index, answer in enumerate(case.get("student_turns") or ["12", "3", "我讲完了", "确认结束"]):
            turn, version, final_state = self._turn(client, session,
                                                    (conversation_id, session_id),
                                                    version, (index, answer, case_tag))
            turns.append(turn)
            if final_state in TERMINAL_STATES:
                break
        return {
            "question_id": question_id,
            "attempt_id": skill_session.get("attempt_id"),
            "conversation_id": conversation_id,
            "final_state": final_state,
            "turns": turns,
            "login_ms": session.get("login_ms"),
            "open_ms": open_ms,
            "total_ms": int((time.monotonic() - started) * 1000),
        }

    def _turn(self, client: httpx.Client, session: dict, target: tuple[str, str],
              version: int, turn: tuple[int, str, str]) -> tuple[dict, int, str]:
        conversation_id, session_id = target
        index, answer, case_tag = turn
        # 幂等键从 case_id+回合号稳定推导(非随机):中断续跑重发同键,
        # 服务端幂等返回已提交结果(spike 实测 message 级幂等),避免并发更新 409(试跑实测)
        turn_key = f"eval:{case_tag}:t{index}"
        body = {
            "content": answer,
            "skill_id": SKILL_ID,
            "input": {"skill_session_id": session_id, "expected_session_version": version},
            "client_turn_id": turn_key,
            "idempotency_key": turn_key,
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
