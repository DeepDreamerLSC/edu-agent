#!/usr/bin/env python3
"""classroom burst 小压测(#255 硬验证件3,试点出口判据 2 前置)。

「大家现在拍这道题」模式:N 个学生近同时开**同一道题**(同一 question_text、
各自幂等键),各自走 open→turns→confirm。观测 #255 点名六项:
- SQLite busy:服务是单连接+锁串行(02 §5),进程内本无 SQLITE_BUSY 之路;观测
  面 = 5xx/错误明细里有无 locked/sqlite 字样,以及写延迟分布;
- 请求错误:按(阶段, 端点, 状态码)分面计数,含传输层错误(status=0);
- 模型队列:生成端为模拟真实延迟档的 stub(start≈1.5s / reply≈1.2s /
  finish≈0.8s,±0.4s 抖动)——零真实模型预算;并发在飞峰值 = 模型侧并发观测
  (stub 全并发不排队;真模型队列读数不属本件,需另批);
- P95:各阶段延迟 P50/P95/P99/max;
- SSE 掉线:部分学生走 /messages/stream,统计 done 帧完整到达率;
- 重复状态提交:每 replay-every 名学生在末轮同键重放一次,断言同响应且
  version 不前进;压后逐会话对账 version==1+turns 且 state=completed。

起服 wiring 同 serve_partner_api.build()(SqliteStore 临时库 + FileService +
IdentityService + build_server,含生产同款 listen backlog),内核为延迟 stub。
这是观测性小压测,不是平台:单脚本、stdlib、一次打满即出报告。

用法:
  python scripts/classroom_burst.py [--students 40] [--turns 2] [--port 0]
      [--replay-every 5] [--stream-every 2] [--out metrics.json] [--keep]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from edu_agent.agents.small_lecturer import LearnerSession
from edu_agent.api import build_server, build_service
from edu_agent.api.files import FileService
from edu_agent.api.identity import IdentityService
from edu_agent.store import SqliteStore

QUESTION_TEXT = "解方程 3x+7=25,并说明每一步为什么这样做。(burst 同题:大家现在拍这道题)"
EXPECTED = {"open": 201, "turn": 200, "replay": 200, "confirm": 200, "status": 200}


@dataclass
class _Turn:
    text: str
    session: object = None
    ready_to_confirm: bool = False
    state: str = "first_question_ready"


@dataclass
class _Summary:
    text: str
    status: str = "completed"


class LatencyStubKernel:
    """模拟真实延迟档的假生成端(零模型预算),带并发在飞计数(模型侧观测)。"""

    name = "classroom-burst-stub"
    LATENCIES = {"start": 1500, "reply": 1200, "finish": 800}

    def __init__(self) -> None:
        self._rng = random.Random(20260914)
        self._lock = threading.Lock()
        self._in_flight = 0
        self.peak_in_flight = 0
        self.calls = {"start": 0, "reply": 0, "finish": 0}

    def _simulate(self, kind: str) -> None:
        with self._lock:
            self.calls[kind] += 1
            self._in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self._in_flight)
        time.sleep((self.LATENCIES[kind] + self._rng.uniform(0, 400)) / 1000)
        with self._lock:
            self._in_flight -= 1

    def start(self, question: dict, learner: dict) -> _Turn:
        self._simulate("start")
        session = LearnerSession(question=question, learner=learner)
        session.state = "first_question_ready"
        return _Turn("我们先看已知条件,题目要我们求什么?", session=session)

    def reply(self, session: LearnerSession, student_message: str) -> _Turn:
        self._simulate("reply")
        session.state = "ready_to_confirm"
        session.session_version += 1
        session.history.append({"role": "user", "content": student_message})
        return _Turn("很好,你用等式两边同时减去 7。", session=session,
                     ready_to_confirm=True)

    def finish(self, session: LearnerSession) -> _Summary:
        self._simulate("finish")
        session.state = "completed"
        return _Summary("burst 小结:方法你讲清楚了。")


@dataclass
class Cfg:
    students: int
    turns: int
    stream_every: int
    replay_every: int
    tag: str


class Metrics:
    """线程安全记账:请求记录、流式完成率、重放命中、终态对账、失败明细。"""

    def __init__(self) -> None:
        self.records: list[dict] = []
        self.failures: list[dict] = []
        self.consistency: list[dict] = []
        self.streams = {"attempted": 0, "complete": 0}
        self.replays = {"attempted": 0, "deduped": 0}
        self._lock = threading.Lock()

    def record(self, phase: str, endpoint: str, status: int,
               ms: float, student: int, detail: str = "") -> None:
        with self._lock:
            self.records.append({"phase": phase, "endpoint": endpoint, "status": status,
                                 "ms": round(ms, 1), "student": student, "detail": detail[:120]})

    def stream(self, complete: bool) -> None:
        with self._lock:
            self.streams["attempted"] += 1
            self.streams["complete"] += complete

    def replay(self, deduped: bool) -> None:
        with self._lock:
            self.replays["attempted"] += 1
            self.replays["deduped"] += deduped

    def consistency_row(self, row: dict) -> None:
        with self._lock:
            self.consistency.append(row)

    def fail(self, student: int, detail: str) -> None:
        with self._lock:
            self.failures.append({"student": student, "fail": detail})


class StudentFlow:
    """单学生会话流(open→turns→末轮重放→confirm→终态对账);失败记账不抛。"""

    def __init__(self, base: str, token: str, index: int,
                 cfg: Cfg, metrics: Metrics) -> None:
        self.base, self.token, self.i = base, token, index
        self.cfg, self.metrics = cfg, metrics
        self.tag = f"{cfg.tag}-s{index}"
        self.cid = self.sid = ""
        self.version = 1
        self.last_content = ""

    def _fail(self, detail: str) -> None:
        self.metrics.fail(self.i, detail)

    def run(self, barrier: threading.Barrier) -> None:
        barrier.wait()  # 「大家现在拍这道题」:同一栅栏放行
        if self._open() and self._turns() and self._confirm():
            self._final()

    def _open(self) -> bool:
        status, body, ms = _request(self.base, "/api/conversations", self.token, {
            "idempotency_key": self.tag, "question_text": QUESTION_TEXT})
        self.metrics.record("open", "conversations", status, ms, self.i,
                            "" if status == 201 else json.dumps(body, ensure_ascii=False))
        if status != 201:
            self._fail(f"open {status}:{body}")
            return False
        self.cid, self.sid = body["conversation_id"], body["skill_session_id"]
        self.version = body["session_version"]
        return True

    def _send_turn(self, body: dict, use_stream: bool, phase: str) -> dict | None:
        path = f"/api/conversations/{self.cid}/messages" + ("/stream" if use_stream else "")
        status, payload, ms = _request(self.base, path, self.token, body)
        self.metrics.record(phase, "messages/stream" if use_stream else "messages",
                            status, ms, self.i,
                            "" if status == 200 else json.dumps(payload, ensure_ascii=False))
        if status != 200:
            self._fail(f"{phase} {status}:{payload}")
            return None
        if not use_stream:
            return payload
        events = _sse_events(payload.get("_raw", ""))
        names = [name for name, _ in events]
        done = dict(events).get("done")
        self.metrics.stream(done is not None)
        if done is None:
            self._fail(f"stream 未收 done 帧:{names}")
            return None
        return done

    def _turns(self) -> bool:
        use_stream = self.i % self.cfg.stream_every == 0
        for k in range(1, self.cfg.turns + 1):
            body = {"content": f"第 {k} 轮:两边同时减去 7。",
                    "message_idempotency_key": f"{self.tag}-t{k}",
                    "input": {"skill_session_id": self.sid,
                              "expected_session_version": self.version}}
            response = self._send_turn(body, use_stream, "turn")
            if response is None:
                return False
            self.version = response["session_version"]
            self.last_content = response["assistant_message"]["content"]
            if self._replay_due(k) and not self._replay(body, use_stream):
                return False
        return True

    def _replay_due(self, k: int) -> bool:
        return bool(self.cfg.replay_every) and k == self.cfg.turns \
            and self.i % self.cfg.replay_every == 0

    def _replay(self, body: dict, use_stream: bool) -> bool:
        response = self._send_turn(body, use_stream, "replay")
        if response is None:
            return False
        deduped = (response["session_version"] == self.version
                   and response["assistant_message"]["content"] == self.last_content)
        self.metrics.replay(deduped)
        if not deduped:
            self._fail(f"重放未命中幂等(version {self.version}→{response['session_version']})")
            return False
        return True

    def _confirm(self) -> bool:
        status, body, ms = _request(
            self.base, f"/api/conversations/{self.cid}/messages", self.token,
            {"content": "确认结束", "input": {"interaction_action": "confirm",
                                             "skill_session_id": self.sid}})
        self.metrics.record("confirm", "messages", status, ms, self.i)
        if status != 200 or body.get("status") != "completed":
            self._fail(f"confirm {status}:{body.get('status')}")
            return False
        return True

    def _final(self) -> None:
        status, body, ms = _request(
            self.base, f"/api/conversations/{self.cid}", self.token)
        self.metrics.record("status", "conversations", status, ms, self.i)
        if status != 200:
            self._fail(f"final {status}")
            return
        expected = 1 + self.cfg.turns
        ok = body["session_version"] == expected and body["state"] == "completed"
        self.metrics.consistency_row(
            {"student": self.i, "expected": expected,
             "actual": body["session_version"], "state": body["state"], "ok": ok})
        if not ok:
            self._fail(f"终态对账失败 version={body['session_version']} "
                       f"state={body['state']}(期望 {expected}/completed)")


# ---------- HTTP / SSE / 报告 ----------

def _request(base: str, path: str, token: str = "",
             body: dict | None = None) -> tuple[int, dict, float]:
    """一发 POST/GET(压测服务在环回);传输错误 status=0,毫秒延迟一并返回。"""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = urllib.request.Request(base.rstrip("/") + path, data=data,
                                     method="POST" if data is not None else "GET")
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    start = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw, status = response.read().decode("utf-8"), response.status
    except urllib.error.HTTPError as error:  # 4xx/5xx 是合同面,不当传输错误
        raw, status = error.read().decode("utf-8"), error.code
    except OSError as error:  # URLError/超时/连接重置等传输层
        return 0, {"error": f"{type(error).__name__}: {error}"}, (time.monotonic() - start) * 1000
    payload = json.loads(raw) if raw.startswith("{") else {"_raw": raw}
    return status, payload, (time.monotonic() - start) * 1000


def _sse_events(raw: str) -> list[tuple[str, dict]]:
    events = []
    for block in raw.strip().split("\n\n"):
        if not block.strip():
            continue
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        events.append((lines.get("event", ""), json.loads(lines.get("data", "{}"))))
    return events


def _percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    return sorted_values[min(len(sorted_values) - 1, round(fraction * (len(sorted_values) - 1)))]


def _boot(db_path: Path, port: int, kernel: LatencyStubKernel):
    """起服:wiring 同 serve_partner_api.build()(含生产同款 listen backlog)。"""
    db = SqliteStore(db_path)
    files = FileService(records_store=db)
    service = build_service(kernel, store=db, sessions=db, image_resolver=files.data_url)
    server = build_server(service, IdentityService(), files=files, db=db,
                          host="127.0.0.1", port=port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, db, f"http://127.0.0.1:{server.server_address[1]}"


def _login(base: str) -> str:
    status, body, _ = _request(base, "/api/auth/login", body={
        "account": os.environ["DEMO_ACCOUNT"], "password": os.environ["DEMO_PASSWORD"]})
    assert status == 200 and body.get("access_token"), f"login {status}:{body}"
    return str(body["access_token"])


def _report(metrics: Metrics, wall: float, kernel: LatencyStubKernel,
            cfg: Cfg, base: str) -> bool:
    print(f"[burst] students={cfg.students} turns={cfg.turns} wall={wall:.1f}s base={base}")
    for phase in ("open", "turn", "replay", "confirm", "status"):
        rows = [r for r in metrics.records if r["phase"] == phase]
        if not rows:
            continue
        errors = [r for r in rows if r["status"] != EXPECTED[phase]]
        latencies = sorted(r["ms"] for r in rows)
        print(f"[requests] {phase:8s} n={len(rows):3d} err={len(errors)} "
              f"p50={_percentile(latencies, .50):7.1f}ms "
              f"p95={_percentile(latencies, .95):7.1f}ms "
              f"p99={_percentile(latencies, .99):7.1f}ms max={latencies[-1]:7.1f}ms")
        for row in errors[:3]:
            print(f"           错误样例 s{row['student']} status={row['status']} {row['detail']}")
    busy = [r for r in metrics.records if r["status"] >= 500
            or (r["status"] == 0 and ("sqlite" in r["detail"].lower()
                                      or "lock" in r["detail"].lower()))]
    transport = [r for r in metrics.records if r["status"] == 0]
    server_errors = [r for r in metrics.records if r["status"] >= 500]
    print(f"[sqlite] busy/locked 观测:{len(busy)} 例;5xx={len(server_errors)};"
          f"传输错误={len(transport)}(单连接+锁串行,进程内无 SQLITE_BUSY 之路)")
    print(f"[model] stub 延迟档 start≈{LatencyStubKernel.LATENCIES['start']}ms/"
          f"reply≈{LatencyStubKernel.LATENCIES['reply']}ms/"
          f"finish≈{LatencyStubKernel.LATENCIES['finish']}ms(±400ms 抖动);"
          f"调用数={kernel.calls};并发在飞峰值={kernel.peak_in_flight}"
          f"(stub 全并发不排队;真模型队列读数不属本件)")
    print(f"[sse] 流式请求 done 帧完整:{metrics.streams['complete']}"
          f"/{metrics.streams['attempted']}(掉线 "
          f"{metrics.streams['attempted'] - metrics.streams['complete']})")
    print(f"[replay] 同键重放幂等命中:{metrics.replays['deduped']}"
          f"/{metrics.replays['attempted']}(重复提交 "
          f"{metrics.replays['attempted'] - metrics.replays['deduped']})")
    consistent = [row for row in metrics.consistency if row["ok"]]
    print(f"[consistency] {len(consistent)}/{cfg.students} 会话 version==1+turns"
          f" 且 completed(无重复状态提交)")
    for row in metrics.failures[:5]:
        print(f"[fail] s{row['student']}: {row['fail']}")
    passed = (not metrics.failures and len(consistent) == cfg.students
              and metrics.streams["attempted"] == metrics.streams["complete"]
              and metrics.replays["attempted"] == metrics.replays["deduped"])
    print(f"[verdict] {'PASS' if passed else 'FAIL'}")
    return passed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--students", type=int, default=40, help="近同时会话数(30-50)")
    parser.add_argument("--turns", type=int, default=2, help="每生轮数")
    parser.add_argument("--port", type=int, default=0, help="起服端口(0=临时端口)")
    parser.add_argument("--replay-every", type=int, default=5,
                        help="每 N 名学生在末轮做一次同键重放(0=关)")
    parser.add_argument("--stream-every", type=int, default=2,
                        help="每 N 名学生走 SSE 流式(1=全流式;0 视作 1)")
    parser.add_argument("--out", default=None, help="metrics JSON 输出路径")
    parser.add_argument("--keep", action="store_true", help="保留临时库目录")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    os.environ.setdefault("IDENTITY_TOKEN_HMAC_KEY", "classroom-burst-hmac-key")
    os.environ.setdefault("DEMO_ACCOUNT", "burst-student")
    os.environ.setdefault("DEMO_PASSWORD", "burst-password")
    kernel = LatencyStubKernel()
    workdir = Path(tempfile.mkdtemp(prefix="edu-agent-burst-"))
    server = db = None
    try:
        server, db, base = _boot(workdir / "burst.db", args.port, kernel)
        print(f"[serve] 起服 {base}(wiring 同 serve_partner_api,内核延迟 stub 零模型预算)")
        token = _login(base)
        cfg = Cfg(students=args.students, turns=args.turns,
                  stream_every=max(1, args.stream_every), replay_every=args.replay_every,
                  tag=f"burst-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}")
        metrics = Metrics()
        barrier = threading.Barrier(cfg.students)
        flows = [StudentFlow(base, token, i, cfg, metrics)
                 for i in range(1, cfg.students + 1)]
        threads = [threading.Thread(target=flow.run, args=(barrier,)) for flow in flows]
        start = time.monotonic()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        wall = time.monotonic() - start
        passed = _report(metrics, wall, kernel, cfg, base)
        if args.out:
            Path(args.out).write_text(json.dumps({
                "drill": "classroom burst(#255 件3)", "cfg": cfg.__dict__,
                "wall_s": round(wall, 1), "kernel_calls": kernel.calls,
                "peak_in_flight": kernel.peak_in_flight,
                "streams": metrics.streams, "replays": metrics.replays,
                "consistency": metrics.consistency, "failures": metrics.failures,
                "records": metrics.records}, ensure_ascii=False, indent=1), encoding="utf-8")
        return 0 if passed else 1
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if db is not None:
            db.close()
        if not args.keep:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
