#!/usr/bin/env python3
"""restore-into-service 演练(#255 硬验证件2 的补齐项,试点出口判据 2 前置)。

诚实账:2026-09-14 恢复演练已覆盖备份完整性(integrity_check + 行数对账)与
远端往返四方一致,本脚本不重做;只补 restore-into-service——干净目录恢复 →
起服 → 冒烟(healthz + 一轮 stub 会话),全程逐步留痕([OK] 行进 stdout,
evidence JSON 可选)。

链路(可复跑):
  0) 源库无会话时,先经同 wiring 服务灌入标记会话(备份产物要有真实形状的行,
     恢复读证才有对象);
  1) 快照:VACUUM INTO 一致性副本 + integrity_check + .sha256 侧车
     —— backup-db.sh 步骤 1-3 同机制;OSS 上传段属既有演练,本机无凭据不重复,
     生产机可用 --backup 直接指定 backup-db.sh 产物;
  2) 恢复:干净目录 → sha256 校验(侧车)→ 落位 → integrity_check → 行数;
  3) 起服:SqliteStore(恢复库)+ FileService + IdentityService + build_server
     —— wiring 同 serve_partner_api.build(),唯一差异 = 内核为确定性 stub
     (零模型调用:冒烟只验恢复链路,不烧模型预算)与端口可指定;
  4) 冒烟:演示登录 → /healthz(store 探针)→ 恢复读证(备份内每条会话 GET 200
     且 state/version 与产物一致)→ 新 stub 会话全链(open→message→confirm)
     → 写穿证(新会话行落恢复库)。

用法:
  python scripts/restore_drill.py [--live-db PATH] [--backup FILE] [--port N]
                                  [--out evidence.json] [--keep]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

from edu_agent.agents.small_lecturer import LearnerSession
from edu_agent.api import build_server, build_service
from edu_agent.api.files import FileService
from edu_agent.api.identity import IdentityService
from edu_agent.store import SqliteStore

STUB_FIRST_QUESTION = "我们先看已知条件,题目要我们求什么?"
STUB_REPLY = "很好,你用等式两边同时减去 7。"
STUB_SUMMARY = "演练小结:方法你讲清楚了。"
QUESTION_TEXT = "解方程 3x+7=25,并说明每一步为什么这样做。(restore-drill 标记会话)"


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


class DrillStubKernel:
    """演练确定性内核(零模型调用):与 serve_partner_api.PartnerKernel 同协议
    换插点(api 层经 Kernel 协议注入),件2 冒烟只验恢复链路。"""

    name = "restore-drill-stub"

    def start(self, question: dict, learner: dict) -> _Turn:
        session = LearnerSession(question=question, learner=learner)
        session.state = "first_question_ready"
        return _Turn(STUB_FIRST_QUESTION, session=session)

    def reply(self, session: LearnerSession, student_message: str) -> _Turn:
        session.state = "ready_to_confirm"
        session.session_version += 1
        session.history.append({"role": "user", "content": student_message})
        return _Turn(STUB_REPLY, session=session, ready_to_confirm=True)

    def finish(self, session: LearnerSession) -> _Summary:
        session.state = "completed"
        return _Summary(STUB_SUMMARY)


class Drill:
    """逐步留痕:每步 [OK] 打印 + evidence 行累积(失败抛 AssertionError)。"""

    def __init__(self) -> None:
        self.steps: list[dict] = []

    def ok(self, name: str, detail: str = "") -> None:
        self.steps.append({"step": name, "ok": True, "detail": detail})
        print(f"[OK] {name}" + (f" — {detail}" if detail else ""), flush=True)


# ---------- 只读库探查(备份产物与恢复库的期望值都从这里来) ----------

def _counts(db: Path) -> dict:
    conn = sqlite3.connect(db)
    try:
        rows = dict(conn.execute("SELECT kind, COUNT(*) FROM records GROUP BY kind"))
        return {"conversations": rows.get("conversation", 0),
                "sessions": rows.get("session", 0),
                "files": conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]}
    finally:
        conn.close()


def _conversation_rows(db: Path) -> list[dict]:
    """备份产物内全部会话的 (id, state, session_version)——恢复读证期望值。"""
    conn = sqlite3.connect(db)
    try:
        rows = []
        for cid, payload in conn.execute(
                "SELECT id, payload FROM records WHERE kind='conversation' ORDER BY rowid"):
            data = json.loads(payload)
            rows.append({"conversation_id": cid, "state": data["state"],
                         "session_version": data["session_version"]})
        return rows
    finally:
        conn.close()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _integrity_ok(db: Path) -> bool:
    conn = sqlite3.connect(db)
    try:
        return conn.execute("PRAGMA integrity_check;").fetchone()[0] == "ok"
    finally:
        conn.close()


# ---------- 阶段 0:灌数(条件) / 阶段 1:快照 / 阶段 2:恢复 ----------

def _snapshot(live_db: Path, workdir: Path, drill: Drill) -> Path:
    """一致性快照:VACUUM INTO + integrity_check + .sha256 侧车(backup-db.sh
    步骤 1-3 同机制;OSS 上传段属 2026-09-14 既有演练,不重复)。"""
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    snap = workdir / f"edu-agent-{stamp}.db"
    source = sqlite3.connect(live_db)
    try:
        source.execute("VACUUM INTO ?", (str(snap),))
    finally:
        source.close()
    assert snap.exists() and _integrity_ok(snap), "快照 integrity_check 未通过"
    (workdir / f"{snap.name}.sha256").write_text(
        f"{_sha256(snap)}  {snap.name}\n", encoding="utf-8")
    drill.ok("snapshot", f"{snap.name}({snap.stat().st_size}B,integrity ok,sha256 侧车同目录)")
    return snap


def _restore(snap: Path, target_dir: Path, drill: Drill) -> Path:
    """干净目录恢复:侧车 sha256 校验 → 落位 → integrity_check。"""
    sidecar = snap.with_name(snap.name + ".sha256")
    if sidecar.exists():
        recorded = sidecar.read_text(encoding="utf-8").split()[0]
        assert recorded == _sha256(snap), "备份 sha256 与侧车不符"
    target_dir.mkdir(parents=True, exist_ok=True)
    restored = target_dir / "edu-agent.db"
    shutil.copy2(snap, restored)
    assert _integrity_ok(restored), "恢复库 integrity_check 未通过"
    drill.ok("restore", f"干净目录 {target_dir} 落位,sha256 与侧车一致,integrity ok")
    return restored


def _seed_if_empty(live_db: Path, drill: Drill) -> None:
    """源库无会话时,先经同 wiring 服务灌入标记会话(1 completed + 1 dialogue),
    让备份产物带真实形状的行。"""
    if (counts := _counts(live_db))["conversations"]:
        drill.ok("seed", f"源库已有 {counts['conversations']} 会话,跳过灌数")
        return
    server, db, base = _boot(live_db, port=0)
    try:
        token = _login(base)
        _run_session(base, token, confirm=True)
        _run_session(base, token, confirm=False)
    finally:
        server.shutdown()
        server.server_close()
        db.close()
    drill.ok("seed", "经服务真实链路灌入 2 条 restore-drill 标记会话")


# ---------- 阶段 3:起服 / HTTP 面 ----------

def _boot(db_path: Path, port: int) -> tuple[object, SqliteStore, str]:
    """起服:wiring 同 serve_partner_api.build(),差异仅内核=stub、端口可指定。"""
    db = SqliteStore(db_path)
    files = FileService(records_store=db)
    service = build_service(DrillStubKernel(), store=db, sessions=db,
                            image_resolver=files.data_url)
    server = build_server(service, IdentityService(revocation_store=db), files=files, db=db,
                          host="127.0.0.1", port=port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, db, f"http://127.0.0.1:{server.server_address[1]}"


_SAFE_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _assert_safe_url(url: str) -> None:
    """Mimosa 安全约束:仅 http/https,目标主机白名单(本脚本目标=本机服务)。"""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"仅允许 http/https:{parsed.scheme}")
    hostname = parsed.hostname or ""
    if hostname not in _SAFE_HOSTS:
        raise ValueError(f"目标主机不在白名单:{hostname}")


def _request(base: str, path: str, token: str = "",
             body: dict | None = None) -> tuple[int, dict]:
    """一发 POST/GET(演练服务在环回;4xx/5xx 返回状态码,不当网络错误)。"""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    url = base.rstrip("/") + path
    _assert_safe_url(url)
    request = urllib.request.Request(url, data=data,
                                     method="POST" if data is not None else "GET")
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw.startswith("{") else {}
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8")
        return error.code, json.loads(raw) if raw.startswith("{") else {}


def _login(base: str) -> str:
    status, body = _request(base, "/api/auth/login", body={
        "account": os.environ["DEMO_ACCOUNT"], "password": os.environ["DEMO_PASSWORD"]})
    assert status == 200 and body.get("access_token"), f"login {status}:{body}"
    return str(body["access_token"])


def _run_session(base: str, token: str, *, confirm: bool) -> str:
    """一条 stub 会话:统一 Open(question_text 自由材料)→ 一轮 →(可选)confirm。"""
    status, opened = _request(base, "/api/conversations", token=token, body={
        "idempotency_key": f"restore-drill-{uuid.uuid4().hex[:8]}",
        "question_text": QUESTION_TEXT})
    assert status == 201, f"open {status}:{opened}"
    cid, sid = opened["conversation_id"], opened["skill_session_id"]
    status, turn = _request(base, f"/api/conversations/{cid}/messages", token=token, body={
        "content": "两边同时减去 7。",
        "input": {"skill_session_id": sid, "expected_session_version": 1}})
    assert status == 200 and turn["session_version"] == 2, f"message {status}:{turn}"
    assert turn["assistant_message"]["content"] == STUB_REPLY
    if confirm:
        status, done = _request(base, f"/api/conversations/{cid}/messages", token=token, body={
            "content": "确认结束", "input": {"interaction_action": "confirm",
                                            "skill_session_id": sid}})
        assert status == 200 and done["status"] == "completed", f"confirm {status}:{done}"
    return cid


# ---------- 阶段 4:冒烟 ----------

def _smoke(base: str, token: str, restored: Path,
           expected: list[dict], drill: Drill) -> None:
    status, body = _request(base, "/healthz")
    assert status == 200 and body.get("store", {}).get("ok") is True, f"healthz {status}:{body}"
    drill.ok("healthz", "200,store.ok=true(SELECT 1 探针打恢复库)")

    for row in expected:  # 恢复读证:备份内每条会话可读且 state/version 与产物一致
        status, served = _request(
            base, f"/api/conversations/{row['conversation_id']}", token=token)
        assert status == 200, f"恢复会话读 {status}:{served}"
        assert served["state"] == row["state"], f"{row['conversation_id']} state 不一致"
        assert served["session_version"] == row["session_version"], "version 不一致"
    drill.ok("restore-proof",
             f"备份内 {len(expected)} 条会话全部 GET 200,state/version 与产物一致")

    before = _counts(restored)["conversations"]
    _run_session(base, token, confirm=True)
    after = _counts(restored)["conversations"]
    assert after == before + 1, f"写穿失败:{before}→{after}"
    drill.ok("stub-session",
             f"新会话 open→message→confirm 全链 200(写穿恢复库 {before}→{after})")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live-db", default="data/edu-agent.db",
                        help="源库(快照对象;默认 data/edu-agent.db)")
    parser.add_argument("--backup", default=None,
                        help="既有备份产物(backup-db.sh 产出);不给则本机快照")
    parser.add_argument("--port", type=int, default=0, help="起服端口(0=临时端口)")
    parser.add_argument("--out", default=None, help="evidence JSON 输出路径")
    parser.add_argument("--keep", action="store_true", help="保留演练工作目录")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    # 演练自含身份面:已有 env(生产 .env)不覆盖,缺省用演练值
    os.environ.setdefault("IDENTITY_TOKEN_HMAC_KEY", "restore-drill-hmac-key")
    os.environ.setdefault("DEMO_ACCOUNT", "drill-student")
    os.environ.setdefault("DEMO_PASSWORD", "restore-drill-password")
    drill = Drill()
    workdir = Path(tempfile.mkdtemp(prefix="edu-agent-restore-drill-"))
    server = db = None
    try:
        live = Path(args.live_db)
        assert live.exists(), f"源库不存在:{live}"
        _seed_if_empty(live, drill)
        snap = Path(args.backup) if args.backup else _snapshot(live, workdir, drill)
        expected = _conversation_rows(snap)
        assert expected, "备份产物内无会话——恢复读证无对象"
        drill.ok("artifact", f"{snap} 行数 {_counts(snap)}")
        restored = _restore(snap, workdir / "restored", drill)

        server, db, base = _boot(restored, args.port)
        drill.ok("serve", f"起服 {base}(wiring 同 serve_partner_api,内核 stub 零模型调用)")
        token = _login(base)
        drill.ok("login", f"演示登录 200(account={os.environ['DEMO_ACCOUNT']})")
        _smoke(base, token, restored, expected, drill)
        drill.ok("drill", "restore-into-service 演练通过(#255 件2 补齐项)")
        return 0
    except AssertionError as error:
        print(f"[FAIL] {error}", file=sys.stderr, flush=True)
        return 1
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if db is not None:
            db.close()
        if args.out:
            Path(args.out).write_text(json.dumps({
                "drill": "restore-into-service(#255 件2)",
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "steps": drill.steps}, ensure_ascii=False, indent=1), encoding="utf-8")
        if not args.keep:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
