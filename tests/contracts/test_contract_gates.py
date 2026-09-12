"""M3 出口判据的三处"未上锁"缺口(#199 核对结论;00 §5.2 约定 4 + §8.5 合同终审覆盖点)。

本文件只补**既有套件未覆盖**的三处——其余覆盖点已有测试:
- SSE 六型帧序的**正常路径**:tests/contracts/test_api_streaming.py::test_stream_emits_contract_frame_order
- 401 真验签(假签/过期/空钥熔断/熔断开关):tests/contracts/test_auth_enforcement.py
- logout 返回 ok / 幂等:test_files_api.py

补的三处:
1. 客户端禁止字段:契约要求 4 项(`answer`/`analysis`/`verified`/`mastery_status`)**拒绝**,
   实现在**对话面 5 个入口**(统一 open / per-question open / create conversation /
   messages / messages-stream)都要 403。2026-09-12 前的两个缺口:①`verified` 漏在名单外
   (**且会透传进 learner → 模型 prompt**,不只是被忽略);②**两条学生轮路由完全没有闸**。
2. SSE **错误路径**:开流后内核故障 → `start(conversation_running=false)` + `error` 帧;
3. **logout 无状态语义**:登出后同一 token 仍有效——把"无状态 HMAC 不吊销"这个**已知取舍**
   写成测试,防止后人当 bug 改掉(文件头注释与实现都是这个口径)。
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from auth_testing import TEST_TOKEN
from partner_api import (ScriptedKernel, StubSummary, StubTurn, _serve, get,
                         open_session, parse_sse, post)

FORBIDDEN = ["answer", "analysis", "verified", "mastery_status"]


@contextmanager
def served(kernel):
    """本地测试服务:起来,退出时关闭(替代 7 处 try/finally 样板)。"""
    base, server = _serve(kernel)
    try:
        yield base
    finally:
        server.shutdown()
        server.server_close()


# ---------- 1. 客户端禁止字段:3 个入口 × 4 项 → 403 ----------

@pytest.mark.parametrize("field", FORBIDDEN)
def test_forbidden_fields_rejected_on_unified_open(field):
    """统一 open(`POST /api/prepared-questions/open`)拒绝全部 4 项禁止字段。"""
    with served(ScriptedKernel(["先看条件。"])) as base:
        response = post(base, "/api/prepared-questions/open", {field: "x"}, status=403)
        assert f"客户端不得提交字段:{field}" in response.json()["error"]["message"]


@pytest.mark.parametrize("field", FORBIDDEN)
def test_forbidden_fields_rejected_on_per_question_open(field):
    """App 主路径(`POST /api/prepared-questions/{id}/open`)同样拒绝 4 项。"""
    with served(ScriptedKernel(["先看条件。"])) as base:
        response = post(base, "/api/prepared-questions/q-101/open",
                        {"idempotency_key": "k-1", field: "x"}, status=403)
        assert f"客户端不得提交字段:{field}" in response.json()["error"]["message"]


@pytest.mark.parametrize("field", FORBIDDEN)
def test_forbidden_fields_rejected_on_student_turn(field):
    """学生轮(`POST /api/conversations/{id}/messages`)同样拒绝 4 项。

    00 §5.2 约定 4:掌握结论只能服务端产生——客户端想借学生轮注入 `mastery_status`
    这类字段的路径必须被堵死。
    """
    with served(ScriptedKernel(["你列了哪些已知量?"])) as base:
        opened = open_session(base)
        conversation_id = opened["conversation"]["conversation_id"]
        response = post(base, f"/api/conversations/{conversation_id}/messages",
                        {"content": "先看条件。", field: "x"}, status=403)
        assert f"客户端不得提交字段:{field}" in response.json()["error"]["message"]


@pytest.mark.parametrize("field", FORBIDDEN)
def test_forbidden_fields_rejected_on_create_conversation(field):
    """建会话(`POST /api/conversations`)同样拒绝 4 项。"""
    with served(ScriptedKernel(["先看条件。"])) as base:
        response = post(base, "/api/conversations",
                        {"external_question_id": "q-101", field: "x"}, status=403)
        assert f"客户端不得提交字段:{field}" in response.json()["error"]["message"]


@pytest.mark.parametrize("field", FORBIDDEN)
def test_forbidden_fields_rejected_on_student_turn_stream(field):
    """**流式**学生轮(`POST /api/conversations/{id}/messages/stream`)同样拒绝 4 项。

    这条是审查对抗探针 mutD 逼出来的:原测试只打非流式 `/messages`,
    单独删掉 `_stream` 里那一行闸时**全量测试仍全绿** ⇒ 流式闸零覆盖。
    请求类错误在**开流前**以 JSON 错误返回(与 409/422 同口径),不是流内 error 帧。
    """
    with served(ScriptedKernel(["你列了哪些已知量?"])) as base:
        opened = open_session(base)
        conversation_id = opened["conversation"]["conversation_id"]
        response = post(base, f"/api/conversations/{conversation_id}/messages/stream",
                        {"content": "先看条件。", field: "x"}, status=403)
        assert response.json()["error"]["message"].startswith("客户端不得提交字段:")
        assert not response.headers.get("content-type", "").startswith("text/event-stream")


# ---------- 2. SSE 错误路径:开流后内核故障 → start(false) + error 帧 ----------

class _ReplyExplodes:
    """start 正常、reply 抛错 → 服务层映射 503 → 流内 error 帧(流已开)。"""

    def start(self, question: dict, learner: dict) -> StubTurn:
        return StubTurn("我们先看已知条件,题目要我们求什么?")

    def reply(self, session: object, student_message: str) -> StubTurn:
        raise RuntimeError("kernel exploded")

    def finish(self, session: object) -> StubSummary:
        return StubSummary("小结")


def test_stream_emits_error_frame_when_kernel_fails():
    """契约 6 型里的 `error` 走流内帧(HTTP 200 + text/event-stream),不是 JSON 错误。"""
    with served(_ReplyExplodes()) as base:
        opened = open_session(base)
        conversation_id = opened["conversation"]["conversation_id"]
        response = post(base, f"/api/conversations/{conversation_id}/messages/stream",
                        {"content": "先看条件。",
                         "input": {"skill_session_id": opened["skill_session_id"],
                                   "expected_session_version": 1}})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        frames = parse_sse(response.content)
        assert [event for event, _ in frames] == ["start", "error"]
        assert dict(frames)["start"] == {"conversation_running": False}
        error = dict(frames)["error"]
        assert error["code"] == "SERVICE_UNAVAILABLE"
        # R5(审查):原断言只判真值 ⇒ 加强为"不得是裸异常串"(桩抛的是 RuntimeError("kernel exploded"))
        assert "kernel exploded" not in error["message"]
        assert "RuntimeError" not in error["message"]
        assert error["message"]  # 对学生可见的友好文案


# ---------- 3. logout 无状态语义(已知取舍,写死防误改) ----------

def test_logout_does_not_revoke_token():
    """登出后同一 token **仍然有效**(无状态 HMAC 不吊销名单,老系统口径的最小实现)。

    断言方式:登出后打一个**不存在**的会话 → 期望 404(已过鉴权闸)而非 401。
    ⇒ 若有人把"登出即失效"当 bug 修,这条会红,逼他先改契约与文件头注释。
    """
    with served(ScriptedKernel(["先看条件。"])) as base:
        assert post(base, "/api/auth/logout", {}, status=200).json() == {"ok": True}
        assert get(base, "/api/conversations/conv_after_logout", token=TEST_TOKEN).status_code == 404
        # R6(审查):登出既不放行也不提权——假 token 仍被闸拦(401)
        assert get(base, "/api/conversations/conv_after_logout", token="whatever").status_code == 401
