"""#255 硬验证件1:SSE 生成中断线 + 幂等重放(试点出口判据 2 前置)。

场景:学生端流式生成中途断线(没读到 done 帧,不知轮次是否已提交)→ 应用以同
message_idempotency_key 重放 → 必须拿到**同一轮**、不产生第二个 committed turn;
服务重启后同键重放同样幂等——内存缓存(_turn_cache)冷启动,由随会话原子落盘的
幂等存根(extras["turn_idem"],只存最后一轮)兜底。

断线模拟:裸 socket 发流式请求,收到响应首字节即关闭连接。_stream 是"先算完
service.send(提交轮次)再写流",所以首字节到达 = 轮次已提交、流已开——正是
"客户端不知是否提交"的中断现场;此后服务仍存活(断线不炸服务)由后续重放请求
隐式验证。
"""

from __future__ import annotations

import json
import socket
import time
from urllib.parse import urlparse

import pytest

from edu_agent.api import build_service
from edu_agent.store import FileConversationStore, FileSessionStore

from auth_testing import TEST_TOKEN
from partner_api import ScriptedKernel, get, open_session, parse_sse, post

REPLY = "你列了哪些已知量?"


def _file_service(root, kernel):
    """文件级会话表服务(重启复现的关键:两个服务实例只共享磁盘目录)。"""
    return build_service(kernel, store=FileConversationStore(root / "conversations"),
                         sessions=FileSessionStore(root / "sessions"))


def _interrupted_stream(base: str, path: str, payload: dict) -> None:
    """发流式请求,收到响应首字节即断线(不读 done 帧,模拟生成中断线)。"""
    parsed = urlparse(base)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = (
        f"POST {path} HTTP/1.1\r\n"
        f"Host: {parsed.hostname}:{parsed.port}\r\n"
        f"Authorization: Bearer {TEST_TOKEN}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("utf-8") + body
    with socket.create_connection((parsed.hostname, parsed.port), timeout=5) as sock:
        sock.sendall(request)
        sock.recv(64)  # 首字节已到:轮次已提交、流已开;此处弃流


def _await_version(base: str, conversation_id: str, version: int,
                   timeout: float = 5.0) -> dict:
    """轮询状态端点直到会话版本到位(断线请求提交时序的收口)。"""
    deadline = time.monotonic() + timeout
    status: dict = {}
    while time.monotonic() < deadline:
        status = get(base, f"/api/conversations/{conversation_id}").json()
        if status.get("session_version", 0) >= version:
            return status
        time.sleep(0.01)
    raise AssertionError(f"轮次未在 {timeout}s 内提交:{status}")


def _committed_turn(base: str, *, key: str, question_id: str) -> dict:
    """开会话 + 提交一轮(带幂等键,非流式),返回 open 响应。"""
    opened = open_session(base, question_id=question_id)
    response = post(base, f"/api/conversations/{opened['conversation']['conversation_id']}/messages",
                    {"content": "先看条件。", "message_idempotency_key": key,
                     "input": {"skill_session_id": opened["skill_session_id"],
                               "expected_session_version": 1}})
    assert response.status_code == 200
    return opened


# ---------- 同进程:断线 → 同键重放,只提交一轮 ----------

@pytest.mark.parametrize("replay_path", ["/messages", "/messages/stream"])
def test_interrupted_stream_replay_same_process_single_turn(serve, tmp_path, replay_path):
    """断线 → 同进程同键重放(非流式/流式两路共用同一幂等缓存):同一轮原样
    返回,内核只调一次,会话只前进一版。"""
    kernel = ScriptedKernel(replies=[REPLY, "第二轮的回复"])
    base = serve(kernel)
    opened = open_session(base, question_id="q-sse-inproc")
    cid = opened["conversation"]["conversation_id"]
    body = {"content": "先看条件。", "message_idempotency_key": "midem-inproc",
            "input": {"skill_session_id": opened["skill_session_id"],
                      "expected_session_version": 1}}
    _interrupted_stream(base, f"/api/conversations/{cid}/messages/stream", body)
    _await_version(base, cid, 2)

    replay = post(base, f"/api/conversations/{cid}{replay_path}", body)
    assert replay.status_code == 200  # 断线后的重放拿到那一轮,不是 409
    if replay_path.endswith("/stream"):
        frames = parse_sse(replay.content)
        assert [event for event, _ in frames] == \
            ["status", "start", "interaction", "delta", "done"]
        done = dict(frames)["done"]
        assert done["assistant_message"]["content"] == REPLY
        assert done["session_version"] == 2
    else:
        assert replay.json()["assistant_message"]["content"] == REPLY
        assert replay.json()["session_version"] == 2
    assert kernel.reply_calls == 1  # 断线重放不重调模型
    status = get(base, f"/api/conversations/{cid}").json()
    assert status["session_version"] == 2 and status["turn_count"] == 2  # 只提交一轮


# ---------- #255 原文口径:服务重启 → 重放仍幂等 ----------

def test_interrupted_stream_replay_after_restart_single_turn(serve, tmp_path):
    """断线客户端拿不回 done 帧,重放时可能连 expected_session_version 都没有——
    重启后内存幂等缓存冷启动,落盘存根必须兜底:同一轮原样返回、新进程内核
    零调用、无第二轮提交(省略版本号的重放若落进版本门之后,会二次提交)。"""
    first = ScriptedKernel(replies=[REPLY])
    base = serve(service=_file_service(tmp_path, first))
    opened = open_session(base, question_id="q-sse-restart")
    cid = opened["conversation"]["conversation_id"]
    _interrupted_stream(base, f"/api/conversations/{cid}/messages/stream",
                        {"content": "先看条件。", "message_idempotency_key": "midem-restart",
                         "input": {"skill_session_id": opened["skill_session_id"],
                                   "expected_session_version": 1}})
    _await_version(base, cid, 2)

    restarted = ScriptedKernel(replies=["重启后若真调了内核,内容会是这句"])
    base = serve(service=_file_service(tmp_path, restarted))
    replay = post(base, f"/api/conversations/{cid}/messages", {
        "content": "先看条件。", "message_idempotency_key": "midem-restart",
        "input": {"skill_session_id": opened["skill_session_id"]}})  # 断线重放:无版本号
    assert replay.status_code == 200
    assert replay.json()["assistant_message"]["content"] == REPLY  # 原轮原样
    assert replay.json()["session_version"] == 2
    assert restarted.reply_calls == 0  # 重启后重放不重调模型
    status = get(base, f"/api/conversations/{cid}").json()
    assert status["session_version"] == 2 and status["turn_count"] == 2  # 无第二轮提交


def test_replay_after_restart_stale_version_returns_turn_not_conflict(serve, tmp_path):
    """原请求原样重放(带已过期的 expected_session_version=1):首次已成功,
    重试不该被新版本门槛拦住——该语义重启后同样成立(409 即回归)。"""
    first = ScriptedKernel(replies=[REPLY])
    base = serve(service=_file_service(tmp_path, first))
    opened = _committed_turn(base, key="midem-stale", question_id="q-sse-stale")
    cid = opened["conversation"]["conversation_id"]

    restarted = ScriptedKernel(replies=["第二轮的回复"])
    base = serve(service=_file_service(tmp_path, restarted))
    replay = post(base, f"/api/conversations/{cid}/messages", {
        "content": "先看条件。", "message_idempotency_key": "midem-stale",
        "input": {"skill_session_id": opened["skill_session_id"],
                  "expected_session_version": 1}})  # 原请求原样重放
    assert replay.status_code == 200  # 不是 409
    assert replay.json()["assistant_message"]["content"] == REPLY
    assert replay.json()["session_version"] == 2
    assert restarted.reply_calls == 0


# ---------- 边界:存根只认最后一轮的同键,防过幂等 ----------

def test_new_turn_after_restart_different_key_advances(serve, tmp_path):
    """换新键的新一轮照常推进(存兜底不是全局去重)。"""
    first = ScriptedKernel(replies=[REPLY])
    base = serve(service=_file_service(tmp_path, first))
    opened = _committed_turn(base, key="midem-old", question_id="q-sse-newkey")
    cid = opened["conversation"]["conversation_id"]

    restarted = ScriptedKernel(replies=["第二轮的回复"])
    base = serve(service=_file_service(tmp_path, restarted))
    turn = post(base, f"/api/conversations/{cid}/messages", {
        "content": "第二轮。", "message_idempotency_key": "midem-new",
        "input": {"skill_session_id": opened["skill_session_id"],
                  "expected_session_version": 2}})
    assert turn.status_code == 200
    assert turn.json()["assistant_message"]["content"] == "第二轮的回复"
    assert turn.json()["session_version"] == 3  # 正常推进
    assert restarted.reply_calls == 1


def test_unknown_key_stale_version_after_restart_conflicts_no_commit(serve, tmp_path):
    """边界钉:不是最后一轮的键(陌生键)不享受存根,落回版本门——过期版本
    409、零内核调用、零提交(00 §5.2 约定 3 的重启面)。"""
    first = ScriptedKernel(replies=[REPLY])
    base = serve(service=_file_service(tmp_path, first))
    opened = _committed_turn(base, key="midem-mine", question_id="q-sse-other")
    cid = opened["conversation"]["conversation_id"]

    restarted = ScriptedKernel(replies=["第二轮的回复"])
    base = serve(service=_file_service(tmp_path, restarted))
    replay = post(base, f"/api/conversations/{cid}/messages", {
        "content": "旧轮重放。", "message_idempotency_key": "midem-other",
        "input": {"skill_session_id": opened["skill_session_id"],
                  "expected_session_version": 1}}, status=409)
    assert replay.json()["error"]["code"] == "SKILL_SESSION_CONFLICT"
    assert restarted.reply_calls == 0
    status = get(base, f"/api/conversations/{cid}").json()
    assert status["session_version"] == 2 and status["turn_count"] == 2
