#!/bin/bash
# 备份校验(M3 DB 存储):sha256 侧车 + SQLite integrity_check + 行数打印。
# 用法:verify-db-backup.sh [备份文件];不带参数时取本地备份目录里最新的一个。
# 照老仓库 verify-postgres-backup.sh 的 shasum -a 256 --check 那一套,加库级校验。
set -euo pipefail

DIR="${OSS_BACKUP_DIR:-$HOME/edu-agent-backups}"
SQLITE3_BIN="${SQLITE3_BIN:-sqlite3}"
F="${1:-}"

if [ -z "$F" ]; then
  F="$(ls -t "$DIR"/edu-agent-*.db 2>/dev/null | head -1 || true)"
  [ -n "$F" ] || { echo "[verify-db-backup] $DIR 下没有备份" >&2; exit 2; }
fi
[ -f "$F" ] || { echo "[verify-db-backup] 文件不存在:$F" >&2; exit 2; }
[ -f "$F.sha256" ] || { echo "[verify-db-backup] 缺侧车:$F.sha256" >&2; exit 2; }

(cd "$(dirname "$F")" && shasum -a 256 --check "$(basename "$F").sha256")
CHECK="$("$SQLITE3_BIN" "$F" 'PRAGMA integrity_check;')"
[ "$CHECK" = "ok" ] || { echo "[verify-db-backup] integrity_check:$CHECK" >&2; exit 3; }
echo "[verify-db-backup] integrity_check: ok"
echo "[verify-db-backup] 行数: conversations=$("$SQLITE3_BIN" "$F" "SELECT COUNT(*) FROM records WHERE kind='conversation'")" \
  "sessions=$("$SQLITE3_BIN" "$F" "SELECT COUNT(*) FROM records WHERE kind='session'")" \
  "files=$("$SQLITE3_BIN" "$F" 'SELECT COUNT(*) FROM files')"
