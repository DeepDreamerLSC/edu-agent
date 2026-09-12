#!/usr/bin/env python3
"""一次性迁移:data/{conversations,sessions}/ 的 JSON → SQLite(M3 DB 存储)。

- **幂等**:`PRAGMA user_version` 作迁移标记(0→1;runtime SqliteStore 不碰它,
  schema 归 CREATE IF NOT EXISTS)。已迁移(≥1)再跑 = 立即退出,结果不变;
  不引入迁移框架。
- **原件保留**:只读 JSON,绝不删除/改名;人确认后再人工清理。
- **对账**:打印 迁移/跳过/失败 条数,并逐条核对(源 JSON 在库中有行,且恢复
  对象逐字段相等),库内总行数与源条数对照。
- 跳过 = 单文件损坏(JSON 解析失败/形状不符,与文件版扫描同语义,不炸全部)
  或存量数据撞唯一键(重复幂等键/skill_session——UNIQUE 已下沉 DDL);其余
  SQLite 写入错误 = 失败(fail-closed,立即中止非零退出——产品数据不许半迁)。
- data/files/ 是二进制图片本体,无元数据 JSON 可迁(元数据由服务运行时写
  files 表),对账时按 0 条说明。

用法:uv run python scripts/migrate_json_to_sqlite.py [--data-dir data] [--db data/edu-agent.db]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from edu_agent.store import SqliteStore
from edu_agent.store.conversations import conversation_restore
from edu_agent.store.learner_sessions import restore_session


def _load_json_files(directory: Path) -> list[tuple[Path, dict]]:
    """目录内 *.json 逐个解析;损坏的打印并计为跳过(隔离,不中止)。

    为何不复用 FileSessionStore.load_all()(留痕,防后人当漏项重提):对账要
    "逐文件"的跳过计数与源路径,load_all 只回对象列表;为一次性脚本(跑完
    user_version=1 封门)改它的签名不值——见 PR #196 审查的否决记录。"""
    loaded, skipped = [], 0
    if not directory.is_dir():
        return loaded, skipped
    for path in sorted(directory.glob("*.json")):
        try:
            loaded.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, OSError) as error:
            print(f"[迁移] 跳过损坏文件:{path}({type(error).__name__})")
            skipped += 1
    return loaded, skipped


def migrate(data_dir: Path, db_path: Path) -> int:
    store = SqliteStore(db_path)
    with sqlite3.connect(db_path) as marker:  # user_version 只归本脚本管
        version = marker.execute("PRAGMA user_version").fetchone()[0]
    if version >= 1:
        print(f"[迁移] user_version={version},已迁移过,幂等退出(库:{db_path})")
        return 0

    conversations, conv_skipped = _load_json_files(data_dir / "conversations")
    sessions, sess_skipped = _load_json_files(data_dir / "sessions")

    migrated = duplicates = 0
    for _, data in conversations:  # 失败 = 写入错误,fail-closed 中止
        try:
            conversation, idempotency_key = conversation_restore(data)
        except (TypeError, KeyError) as error:
            print(f"[迁移] 跳过形状不符的会话:{data.get('conversation_id')}"
                  f"({type(error).__name__})")
            conv_skipped += 1
            continue
        existing = store.find_by_idempotency(idempotency_key) if idempotency_key else None
        if existing is not None and existing.conversation_id != conversation.conversation_id:
            print(f"[迁移] 跳过重复幂等键:{idempotency_key}"
                  f"(已有 {existing.conversation_id})")
            duplicates += 1
            continue
        try:
            store.create(conversation, idempotency_key)
        except sqlite3.IntegrityError:
            # UNIQUE 已下沉 DDL(idempotency/skill_session):存量源数据撞唯一键
            # (如重复 skill_session)计为跳过,不炸半迁——数据冲突不是基础设施故障。
            print(f"[迁移] 跳过唯一键冲突:{conversation.conversation_id}")
            duplicates += 1
            continue
        migrated += 1

    for _, data in sessions:
        try:
            session = restore_session(data)
        except (TypeError, KeyError) as error:
            print(f"[迁移] 跳过形状不符的本体:{data.get('session_id')}"
                  f"({type(error).__name__})")
            sess_skipped += 1
            continue
        store.save(session)
        migrated += 1

    print(f"[迁移] 迁移 {migrated} 条 / 跳过 {conv_skipped + sess_skipped} 条"
          f"(损坏或形状不符)+ 重复幂等键 {duplicates} 条 / 失败 0 条")
    _reconcile(store, conversations, sessions, data_dir)
    with sqlite3.connect(db_path) as marker:
        marker.execute("PRAGMA user_version=1")
        marker.commit()
    return 0


def _reconcile(store: SqliteStore, conversations: list, sessions: list,
               data_dir: Path) -> None:
    """逐条核对:每个源 JSON 在库中有行且**恢复对象逐字段相等**(经 restore 补
    additive 默认值后比较——裸 JSON 比较会把"旧文件缺新字段"误报成不一致)。"""
    mismatches = 0
    for path, data in conversations:
        expected, _ = conversation_restore(data)
        actual = store.get(str(data.get("conversation_id") or ""))
        if actual != expected:
            print(f"[对账] 不一致会话:{path.name}")
            mismatches += 1
    for path, data in sessions:
        if store.load(str(data.get("session_id") or "")) != restore_session(data):
            print(f"[对账] 不一致本体:{path.name}")
            mismatches += 1
    files_dir = data_dir / "files"
    file_note = (f"{len(list(files_dir.glob('*')))} 个二进制图片本体(不入库,元数据由服务运行时写 files 表)"
                 if files_dir.is_dir() else "目录不存在")
    counts = {}
    with sqlite3.connect(store.path) as conn:
        for kind in ("conversation", "session"):
            counts[kind] = conn.execute(
                "SELECT COUNT(*) FROM records WHERE kind=?", (kind,)).fetchone()[0]
        counts["files"] = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    print(f"[对账] 会话源 {len(conversations)} ↔ 库 {counts['conversation']};"
          f"本体源 {len(sessions)} ↔ 库 {counts['session']};"
          f"文件元数据 0 ↔ 库 {counts['files']}(源:{file_note})")
    print(f"[对账] {'全部一致' if mismatches == 0 else f'{mismatches} 条不一致!'}")
    if mismatches:
        sys.exit(4)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default="data", type=Path,
                        help="既有 JSON 数据目录(默认 data;只读不动)")
    parser.add_argument("--db", default="data/edu-agent.db", type=Path,
                        help="目标 SQLite 库(默认 data/edu-agent.db)")
    args = parser.parse_args()
    return migrate(args.data_dir, args.db)


if __name__ == "__main__":
    sys.exit(main())
