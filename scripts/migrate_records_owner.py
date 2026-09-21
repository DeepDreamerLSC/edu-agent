#!/usr/bin/env python3
"""一次性迁移:records 表补 owner 列 + 幂等唯一索引换复合(06 设计稿 §2.2 第 1/4 条)。

- **幂等**:`PRAGMA user_version` 作迁移标记(1→2;migrate_json_to_sqlite.py 用 0→1,
  本脚本接续 1→2;runtime SqliteStore 不碰 user_version,惯例同前)。已是 2 再跑 =
  立即退出,结果不变;不引入迁移框架。
- **ALTER ADD COLUMN owner TEXT NOT NULL DEFAULT ''**:存量行全部落 owner=''
  = 前归属纪元(06 §2.2 第 5 条:归属信息本就不存在,不回填、不限制访问)。
- **索引切换(06 §4.2 唯一既有表结构变更)**:旧全局唯一索引
  `uq_records_idempotency ON records(idempotency_key)` 必须与新复合索引
  `uq_records_idempotency ON records(owner, idempotency_key)` 同批切换——旧名同义
  重建(CREATE INDEX IF NOT EXISTS 对同名索引静默跳过,须先 DROP),存量库才真正
  换成复合命名空间,防「一边复合一边全局」的裂脑。
- **新库直达**:SqliteStore._SCHEMA 已带 owner 列与复合索引,全新部署无需本脚本
  (user_version=0 时若 records 表已存在即视为 M3 建过库,照常迁移)。
- **对账**:打印列存在性/索引清单/行数对照,迁移后逐项核验。

用法:uv run python scripts/migrate_records_owner.py [--db data/edu-agent.db]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

OWNER_VERSION = 2  # 0/1 = 未迁移(0=从未跑过 json 迁移的新库,1=已跑过)


def has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def index_columns(conn: sqlite3.Connection, name: str) -> list[str]:
    return [row[2] for row in conn.execute(f"PRAGMA index_info({name})")]


def migrate(db_path: Path) -> int:
    if not db_path.is_file():
        print(f"[迁移] 库不存在,新库由 _SCHEMA 直建 owner 列,无需迁移:{db_path}")
        return 0
    with sqlite3.connect(db_path) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= OWNER_VERSION:
            print(f"[迁移] user_version={version},已是 owner 纪元,幂等退出")
            return 0
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "records" not in tables:
            print("[迁移] 无 records 表(空库/新库),标记 user_version 后退出")
            conn.execute(f"PRAGMA user_version={OWNER_VERSION}")
            return 0
        before = conn.execute(
            "SELECT COUNT(*) FROM records WHERE kind='conversation'").fetchone()[0]

        if not has_column(conn, "records", "owner"):
            conn.execute("ALTER TABLE records ADD COLUMN owner TEXT NOT NULL DEFAULT ''")
        # 索引同批切换:DROP 旧全局唯一 → 建复合唯一(06 §4.2)。旧名同义重建,
        # CREATE IF NOT EXISTS 对同名旧索引会静默跳过,必须先 DROP。
        conn.execute("DROP INDEX IF EXISTS uq_records_idempotency")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_records_idempotency"
            " ON records(owner, idempotency_key)"
            " WHERE kind='conversation' AND idempotency_key IS NOT NULL"
            " AND idempotency_key != ''")
        conn.execute(f"PRAGMA user_version={OWNER_VERSION}")
        conn.commit()

        # 对账:owner 列存在、复合索引列序 (owner, idempotency_key)、行数不变
        assert has_column(conn, "records", "owner"), "owner 列未建成"
        columns = index_columns(conn, "uq_records_idempotency")
        assert columns == ["owner", "idempotency_key"], f"复合索引列序异常:{columns}"
        after = conn.execute(
            "SELECT COUNT(*) FROM records WHERE kind='conversation'").fetchone()[0]
        legacy = conn.execute(
            "SELECT COUNT(*) FROM records WHERE kind='conversation' AND owner=''").fetchone()[0]
        assert before == after, f"行数变化:{before} → {after}"
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    print(f"[迁移] records 补 owner 列 + 幂等索引换复合 完成:会话行 {after}"
          f"(其中前归属纪元 owner='' {legacy} 行,不限制访问);user_version={version}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=Path("data/edu-agent.db"))
    return migrate(parser.parse_args().db)


if __name__ == "__main__":
    sys.exit(main())
