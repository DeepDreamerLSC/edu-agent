"""migrate_json_to_sqlite.py 合同(M3 DB 存储:一次性迁移,幂等 + 对账 + 原件保留)。

源数据用**真 FileConversationStore/FileSessionStore 写出**(不是手拼 JSON——
迁移的输入就是它们的落盘形状);断言:条数对账、恢复对象逐字段相等、原件不动、
user_version 幂等门、坏文件隔离。
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

from edu_agent.agents.small_lecturer import LearnerSession, Summary
from edu_agent.store import Conversation, FileConversationStore, FileSessionStore, SqliteStore

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "migrate_json_to_sqlite.py"


def _write_source(root: Path, count: int = 3) -> None:
    """用文件版 store 写出真实源数据 + 一个坏文件 + 一个图片本体。"""
    conversations = FileConversationStore(root / "data" / "conversations")
    for i in range(count):
        conversations.create(Conversation(
            conversation_id=f"conv_{i}", question_id="q-1", attempt_id=f"attempt_{i}",
            skill_session_id=f"skill_{i}",
            extras={"kernel_session_id": f"kernel_{i}",
                    "history": [{"role": "user", "content": f"第{i}轮"}]}), f"idem-{i}")
    sessions = FileSessionStore(root / "data" / "sessions")
    for i in range(count):
        session = LearnerSession(question={"text": f"题{i}", "answer": "x"},
                                 learner={"grade": "五年级"})
        session.state = "dialogue"
        session.history = [{"role": "user", "content": "hi"}]
        if i == 0:
            session.summary = Summary(text="小结", status="completed", session_version=1)
        sessions.save(session)
    (root / "data" / "conversations" / "broken.json").write_text("{ not json", encoding="utf-8")
    (root / "data" / "files").mkdir(parents=True)
    (root / "data" / "files" / "file_x.jpg").write_bytes(b"\xff\xd8fake")


def _run(root: Path):
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--data-dir", str(root / "data"),
         "--db", str(root / "data" / "edu-agent.db")],
        capture_output=True, text=True, timeout=120, cwd=str(_REPO))


def test_migrates_counts_and_keeps_originals(tmp_path):
    _write_source(tmp_path, count=3)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "迁移 6 条 / 跳过 1 条" in result.stdout  # 3 会话 + 3 本体;坏文件隔离
    assert "[对账] 全部一致" in result.stdout
    assert "会话源 3 ↔ 库 3" in result.stdout
    assert "本体源 3 ↔ 库 3" in result.stdout
    # 原件保留:源 JSON 一个不少(含坏文件),图片本体不动
    assert len(list((tmp_path / "data" / "conversations").glob("*.json"))) == 4
    assert len(list((tmp_path / "data" / "sessions").glob("*.json"))) == 3
    assert (tmp_path / "data" / "files" / "file_x.jpg").exists()
    # 恢复对象逐字段相等(含 Summary 重建)
    db = SqliteStore(tmp_path / "data" / "edu-agent.db")
    assert db.get("conv_0") == FileConversationStore(
        tmp_path / "data" / "conversations").get("conv_0")
    assert db.load_all() == FileSessionStore(tmp_path / "data" / "sessions").load_all()


def test_idempotent_rerun_is_noop(tmp_path):
    _write_source(tmp_path, count=2)
    first = _run(tmp_path)
    assert first.returncode == 0, first.stdout
    with sqlite3.connect(tmp_path / "data" / "edu-agent.db") as conn:
        before = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    second = _run(tmp_path)
    assert second.returncode == 0, second.stdout
    assert "已迁移过,幂等退出" in second.stdout  # user_version 门
    with sqlite3.connect(tmp_path / "data" / "edu-agent.db") as conn:
        after = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    assert before == after == 4  # 2 会话 + 2 本体,重跑不增不重


def test_runtime_service_writes_then_migration_still_gated(tmp_path):
    """服务先跑(建 schema,不碰 user_version)→ 迁移照常执行;迁移后再跑即幂等。"""
    db = SqliteStore(tmp_path / "data" / "edu-agent.db")
    db.create(Conversation(conversation_id="conv_runtime", question_id="q",
                           attempt_id="a", skill_session_id="skill_r"), "idem-r")
    db.close()
    _write_source(tmp_path, count=1)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "迁移 2 条" in result.stdout
    # 运行期写入的行仍在(迁移用 upsert,不删既有数据)
    assert SqliteStore(tmp_path / "data" / "edu-agent.db").get("conv_runtime") is not None
