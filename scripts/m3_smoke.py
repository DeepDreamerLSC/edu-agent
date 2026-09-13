#!/usr/bin/env python3
"""M3 合同冒烟(#221 裁定 6):合作方真路径黑盒走查——真内核 + 真模型。

覆盖:login → open(idempotency_key)→ refresh → messages(expected_session_version
一律**响应回读**,不硬编码)→ confirm;open 幂等重试(同 key → 同结果)、
409(版本过期/换题固定)/422(未知键)/403(禁交键)错误信封形状、
messages/stream 的 SSE 帧序。六型帧:本流断言 happy 五型
(status→start→interaction→delta→done,序即合同);第六型 error 帧走
--error-base-url(坏网关实例,503 → start/error 两帧)。

黑盒约束:只走 HTTP,不 import 生产代码;断言贴 00 §5.2 合同形状。
用法:
  python scripts/m3_smoke.py --base-url http://127.0.0.1:8300 \
      --account student1 --password "$DEMO_PASSWORD" \
      [--error-base-url http://127.0.0.1:8310] --out m3_smoke_result.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid


class SmokeFailure(AssertionError):
    """冒烟断言失败(带阶段名,输出里直接可定位)。"""


def _request(base_url: str, path: str, token: str, body: dict | None = None) -> tuple[int, dict, dict]:
    """POST/GET 一发;返回 (status, headers, parsed_body)。SSE 端点同函数(文本帧在 body['_raw'])。"""
    url = base_url.rstrip("/") + path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, dict(resp.headers), json.loads(raw) if raw.startswith("{") else {"_raw": raw}
    except urllib.error.HTTPError as error:  # 4xx/5xx 也是合同面,不当网络错误
        raw = error.read().decode("utf-8")
        return error.code, dict(error.headers), json.loads(raw) if raw.startswith("{") else {"_raw": raw}


def _sse_events(raw: str) -> list[tuple[str, dict]]:
    """SSE 文本 → [(event, data)];帧格式见 server._encode_sse(event/data 两行一帧)。"""
    events: list[tuple[str, dict]] = []
    for block in raw.strip().split("\n\n"):
        if not block.strip():
            continue
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        events.append((lines.get("event", ""), json.loads(lines.get("data", "{}"))))
    return events


def phase_auth_and_open(args: argparse.Namespace, ctx: dict, results: list, evidence: dict) -> None:
    """login → open(idempotency_key)→ 幂等重试 → 409 换题固定(阶段 1-4)。"""
    def phase(name: str) -> dict:
        entry = {"phase": name, "ok": True}
        results.append(entry)
        print(f"[RUN] {name} ...", flush=True)
        return entry

    def check(entry: dict, condition: bool, detail: str) -> None:
        if not condition:
            entry["ok"] = False
            entry["fail"] = detail
            raise SmokeFailure(f"{entry['phase']}: {detail}")

    entry = phase("login")
    t0 = time.monotonic()
    status, _, body = _request(args.base_url, "/api/auth/login", "",
                               {"account": args.account, "password": args.password})
    check(entry, status == 200, f"期望 200,实际 {status}: {body}")
    ctx["token"] = body.get("access_token") or ""
    check(entry, bool(ctx["token"]) and body.get("token_type") == "bearer", f"token 形状不对: {body}")
    s1, _, b1 = _request(args.base_url, "/api/auth/login", "",
                         {"account": args.account, "password": f"wrong-{uuid.uuid4()}"})
    check(entry, s1 == 401 and b1.get("error", {}).get("code") == "USER_LOGIN_FAILED",
          f"错密应 401 USER_LOGIN_FAILED,实际 {s1}: {b1}")
    entry["ms"] = round((time.monotonic() - t0) * 1000)

    entry = phase("open")
    idem = f"m3-smoke-{uuid.uuid4()}"
    evidence["idempotency_key"] = idem
    t0 = time.monotonic()
    status, _, body = _request(args.base_url, "/api/prepared-questions/open", ctx["token"], {
        "idempotency_key": idem, "external_question_id": args.question_id,
        "grade": args.learner_grade})
    check(entry, status == 200, f"期望 200,实际 {status}: {body}")
    session = ((body.get("question") or {}).get("active_session") or {})
    ctx.update(cid=session.get("conversation") or "", ssid=session.get("skill_session_id") or "",
               version=session.get("session_version"))
    check(entry, bool(ctx["cid"]) and bool(ctx["ssid"]) and isinstance(ctx["version"], int)
          and session.get("first_question_ready") is True and session.get("retry_after_ms") == 0
          and body.get("pending") is False,
          f"open 响应形状不符 §5 统一形态(question.active_session): {body}")
    entry["ms"] = round((time.monotonic() - t0) * 1000)

    entry = phase("open-idempotent-retry")
    status, _, body2 = _request(args.base_url, "/api/prepared-questions/open", ctx["token"], {
        "idempotency_key": idem, "external_question_id": args.question_id,
        "grade": args.learner_grade})
    session2 = ((body2.get("question") or {}).get("active_session") or {})
    check(entry, status == 200 and session2.get("conversation") == ctx["cid"]
          and session2.get("session_version") == ctx["version"],
          f"同幂等键应返回同一会话(合同:重试原样复用),实际 {body2}")

    entry = phase("open-409-question-pinned")
    status, _, body = _request(args.base_url, "/api/prepared-questions/open", ctx["token"], {
        "idempotency_key": idem, "external_question_id": "another-question-id",
        "grade": args.learner_grade})
    err = body.get("error") or {}
    check(entry, status == 409 and err.get("code") == "QUESTION_SOURCE_PINNED",
          f"同 key 换题应 409 QUESTION_SOURCE_PINNED,实际 {status}: {body}")
    check(entry, set(err) == {"code", "message", "request_id", "details"},
          f"错误信封四键形状不符: {err}")


def phase_refresh_and_messages(args: argparse.Namespace, ctx: dict, results: list, evidence: dict) -> None:
    """refresh → messages(回读版本)→ 消息幂等 → 409/422/403(阶段 5-10)。"""

    def phase(name: str) -> dict:
        entry = {"phase": name, "ok": True}
        results.append(entry)
        print(f"[RUN] {name} ...", flush=True)
        return entry

    def check(entry: dict, condition: bool, detail: str) -> None:
        if not condition:
            entry["ok"] = False
            entry["fail"] = detail
            raise SmokeFailure(f"{entry['phase']}: {detail}")

    token, cid, ssid = ctx["token"], ctx["cid"], ctx["ssid"]
    entry = phase("refresh")
    t0 = time.monotonic()
    status, _, body = _request(args.base_url,
                               f"/api/prepared-questions/{args.question_id}"
                               f"/skill-sessions/{ssid}/refresh", token, {})
    check(entry, status == 200, f"期望 200,实际 {status}: {body}")
    interaction = body.get("skill_interaction") or {}
    first_question = (body.get("assistant_message") or {}).get("content") or ""
    ctx["version"] = body.get("session_version")
    check(entry, first_question.strip() != "" and interaction.get("state")
          and interaction.get("kind") == "input_request"
          and isinstance(ctx["version"], int)
          and body.get("agent_run", {}).get("status") == "completed",
          f"refresh 响应形状不符 B3 信封: {body}")
    entry["ms"] = round((time.monotonic() - t0) * 1000)
    evidence["first_question"] = first_question

    entry = phase("messages-turn-1")
    t0 = time.monotonic()
    status, _, body = _request(args.base_url, f"/api/conversations/{cid}/messages", token, {
        "content": "我想两边都减去7,得到3x等于18。",
        "input": {"skill_session_id": ssid, "expected_session_version": ctx["version"]}})
    check(entry, status == 200, f"期望 200,实际 {status}: {body}")
    reply1 = (body.get("assistant_message") or {}).get("content") or ""
    ctx["version"] = body.get("session_version")
    check(entry, reply1.strip() != "" and isinstance(ctx["version"], int) and ctx["version"] >= 2
          and (body.get("skill_interaction") or {}).get("kind") == "input_request",
          f"messages 响应形状不符: {body}")
    entry["ms"] = round((time.monotonic() - t0) * 1000)
    evidence["turn_1_assistant"] = reply1

    entry = phase("messages-idempotent-retry")
    payload = {"content": "然后两边都除以3,所以x等于6。代回去3乘6加7等于25。",
               "message_idempotency_key": f"m3-smoke-msg-{uuid.uuid4()}",
               "input": {"skill_session_id": ssid, "expected_session_version": ctx["version"]}}
    status, _, body_a = _request(args.base_url, f"/api/conversations/{cid}/messages", token, payload)
    check(entry, status == 200, f"期望 200,实际 {status}: {body_a}")
    status, _, body_b = _request(args.base_url, f"/api/conversations/{cid}/messages", token, payload)
    check(entry, status == 200
          and body_b.get("session_version") == body_a.get("session_version")
          and (body_b.get("assistant_message") or {}).get("content")
          == (body_a.get("assistant_message") or {}).get("content"),
          f"同 message_idempotency_key 应原样返回同 Turn(不重调模型不 version++),"
          f"实际 {body_b.get('session_version')} vs {body_a.get('session_version')}")
    ctx["version"] = body_b.get("session_version")
    evidence["turn_2_assistant"] = (body_b.get("assistant_message") or {}).get("content")

    entry = phase("messages-409-stale-version")
    status, _, body = _request(args.base_url, f"/api/conversations/{cid}/messages", token, {
        "content": "再说一遍?", "input": {"skill_session_id": ssid,
                                          "expected_session_version": ctx["version"] - 1}})
    check(entry, status == 409 and (body.get("error") or {}).get("code") == "SKILL_SESSION_CONFLICT",
          f"旧版本应 409 SKILL_SESSION_CONFLICT(约定 3,不静默覆盖),实际 {status}: {body}")

    entry = phase("messages-422-unknown-key")
    status, _, body = _request(args.base_url, f"/api/conversations/{cid}/messages", token, {
        "content": "检查未知键拒绝", "unexpected_field": "x",
        "input": {"skill_session_id": ssid, "expected_session_version": ctx["version"]}})
    check(entry, status == 422, f"未知键应 422,实际 {status}: {body}")

    entry = phase("messages-403-forbidden-field")
    status, _, body = _request(args.base_url, f"/api/conversations/{cid}/messages", token, {
        "content": "检查禁交键拒绝", "answer": "x=6",
        "input": {"skill_session_id": ssid, "expected_session_version": ctx["version"]}})
    check(entry, status == 403, f"禁交键 answer 应 403(00 §5.2 约定 4),实际 {status}: {body}")


def phase_sse_and_confirm(args: argparse.Namespace, ctx: dict, results: list, evidence: dict) -> None:
    """SSE happy 五型帧序 → confirm → 终态 409(阶段 11-12)。"""

    def phase(name: str) -> dict:
        entry = {"phase": name, "ok": True}
        results.append(entry)
        print(f"[RUN] {name} ...", flush=True)
        return entry

    def check(entry: dict, condition: bool, detail: str) -> None:
        if not condition:
            entry["ok"] = False
            entry["fail"] = detail
            raise SmokeFailure(f"{entry['phase']}: {detail}")

    token, cid, ssid = ctx["token"], ctx["cid"], ctx["ssid"]
    entry = phase("sse-happy-frames")
    t0 = time.monotonic()
    status, headers, body = _request(args.base_url, f"/api/conversations/{cid}/messages/stream", token, {
        "content": "为什么两边能同时减7?",
        "input": {"skill_session_id": ssid, "expected_session_version": ctx["version"]}})
    events = _sse_events(body.get("_raw") or "")
    names = [name for name, _ in events]
    check(entry, status == 200 and "text/event-stream" in headers.get("Content-Type", ""),
          f"stream 应 200 + event-stream,实际 {status} {headers.get('Content-Type')}")
    check(entry, names == ["status", "start", "interaction", "delta", "done"],
          f"帧序应为 status→start→interaction→delta→done,实际 {names}")
    frames = dict(events)
    delta_text = (frames.get("delta") or {}).get("text") or ""
    done = frames.get("done") or {}
    check(entry, delta_text.strip() != ""
          and delta_text == (done.get("assistant_message") or {}).get("content")
          and isinstance(done.get("session_version"), int),
          f"delta 载全文且与 done.assistant_message 一致:delta={delta_text[:40]!r}")
    ctx["version"] = done.get("session_version")
    check(entry, (frames.get("status") or {}).get("session_version") == ctx["version"],
          "status 帧与 done 帧同源(response 构造后一次编码,版本一致)")
    entry["ms"] = round((time.monotonic() - t0) * 1000)
    evidence["sse_delta_text"] = delta_text

    entry = phase("confirm")
    t0 = time.monotonic()
    status, _, body = _request(args.base_url, f"/api/conversations/{cid}/messages", token, {
        "content": "", "input": {"skill_session_id": ssid, "expected_session_version": ctx["version"],
                                 "interaction_action": "confirm"}})
    check(entry, status == 200, f"期望 200,实际 {status}: {body}")
    check(entry, isinstance(body.get("ready_to_confirm"), bool)
          and body.get("status") in ("completed", "needs_review"),
          f"confirm 响应键形状不符: {body}")
    if body.get("status") == "completed":
        summary = body.get("summary") or {}
        check(entry, summary.get("status") == "completed" and summary.get("text", "").strip(),
              f"completed 应带真实 summary 文本: {summary}")
        evidence["summary"] = summary
    status, _, body = _request(args.base_url, f"/api/conversations/{cid}/messages", token, {
        "content": "终态后再发", "input": {"skill_session_id": ssid,
                                           "expected_session_version": ctx["version"]}})
    check(entry, status == 409, f"终态后 messages 应 409,实际 {status}: {body}")
    entry["ms"] = round((time.monotonic() - t0) * 1000)


def phase_error_frame(args: argparse.Namespace, ctx: dict, results: list) -> None:
    """第六型 error 帧:坏网关实例 503 → 流内 start/error 两帧(阶段 13)。"""
    entry = {"phase": "sse-error-frame", "ok": True}
    results.append(entry)
    print("[RUN] sse-error-frame ...", flush=True)

    def check(condition: bool, detail: str) -> None:
        if not condition:
            entry["ok"] = False
            entry["fail"] = detail
            raise SmokeFailure(f"{entry['phase']}: {detail}")

    # 坏网关实例与主实例共库(EDU_DB_PATH 同一),模型主备全死:其上 open 即
    # 503 JSON 信封(首问走 tutor 模型);再在主实例(活网关)开会话,回坏实例
    # 发流式轮 → 503 → 流内 error 帧(第六型)开出来
    status, _, body = _request(args.error_base_url, "/api/prepared-questions/open", ctx["token"], {
        "idempotency_key": f"m3-smoke-err-{uuid.uuid4()}",
        "external_question_id": args.question_id, "grade": args.learner_grade})
    check(status == 503, f"坏网关(主备全死)上 open 应 503,实际 {status}: {body}")
    status, _, body = _request(args.base_url, "/api/prepared-questions/open", ctx["token"], {
        "idempotency_key": f"m3-smoke-stream-err-{uuid.uuid4()}",
        "external_question_id": args.question_id, "grade": args.learner_grade})
    check(status == 200, f"主实例另开会话应 200,实际 {status}: {body}")
    session2 = ((body.get("question") or {}).get("active_session") or {})
    status, headers, body = _request(
        args.error_base_url, f"/api/conversations/{session2.get('conversation')}/messages/stream",
        ctx["token"], {
            "content": "这一轮会打到坏网关",
            "input": {"skill_session_id": session2.get("skill_session_id"),
                      "expected_session_version": session2.get("session_version")}})
    events = _sse_events(body.get("_raw") or "")
    names = [name for name, _ in events]
    frames = dict(events)
    check(status == 200 and names == ["start", "error"]
          and (frames.get("start") or {}).get("conversation_running") is False
          and (frames.get("error") or {}).get("code"),
          f"503 应走流内 start/error 两帧(conversation_running=false + 错误码),实际 {names}: "
          f"{(body.get('_raw') or '')[:120]!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8300")
    parser.add_argument("--error-base-url", default="",
                        help="坏网关实例(EDU_MODELS_YAML 指向死端口)——断言第六型 error 帧;空则跳过")
    parser.add_argument("--account", default="student1")
    parser.add_argument("--password", required=True)
    parser.add_argument("--question-id", default="equation_subtract",
                        help="seed 题库题号(EDU_QUESTION_SOURCE=seed 时的合同题源)")
    parser.add_argument("--learner-grade", default="五年级")
    parser.add_argument("--out", default="", help="证据 JSON 落盘路径(产物入库用)")
    args = parser.parse_args()

    results: list[dict] = []
    evidence: dict = {"base_url": args.base_url, "question_id": args.question_id, "phases": results}
    ctx: dict = {}

    phase_auth_and_open(args, ctx, results, evidence)
    phase_refresh_and_messages(args, ctx, results, evidence)
    phase_sse_and_confirm(args, ctx, results, evidence)
    if args.error_base_url:
        phase_error_frame(args, ctx, results)

    ok = all(r["ok"] for r in results)
    evidence["ok"] = ok
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(evidence, fh, ensure_ascii=False, indent=1)
    print(("\nM3 冒烟通过:" if ok else "\nM3 冒烟失败:") +
          f"{len(results)} 阶段,证据{'已落盘 ' + args.out if args.out else '未落盘(--out)'}")
    for r in results:
        print(f"  {'PASS' if r['ok'] else 'FAIL'}  {r['phase']}"
              + (f"  ({r['ms']}ms)" if r.get("ms") else "")
              + (f"  [fail: {r['fail']}]" if not r["ok"] else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
