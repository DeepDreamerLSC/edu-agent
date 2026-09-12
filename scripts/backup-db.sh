#!/bin/bash
# SQLite 备份(M3 DB 存储):一致性快照 + 本地滚动 + 上传 OSS。
# 设计要点(照老仓库 backup-postgres.sh 先例):
# - VACUUM INTO 出一致性快照(禁止直接 cp 带 WAL 的 .db——会拷出半截状态);
# - integrity_check + 关键表行数 live↔snap 对账,不过不发布;
# - .sha256 侧车;.tmp 写好后原子改名(发布即完整);
# - 本地滚动:find -mtime +N 连同 .sha256 一起删(远程不删,交给 bucket 生命周期);
# - ossutil 强制 HTTPS endpoint(备份包含用户对话内容,不能明文过网);
#   凭据单源 ~/.config/edu-agent/oss.env,运行时写进 mktemp 出来的 0600 配置,
#   trap 退出即删——密钥不进命令行参数(ps 可见)、不进日志。
set -euo pipefail

OSS_ENV_FILE="${OSS_ENV_FILE:-$HOME/.config/edu-agent/oss.env}"
DB="${EDU_DB_PATH:-data/edu-agent.db}"
DIR="${OSS_BACKUP_DIR:-$HOME/edu-agent-backups}"
RETENTION="${OSS_BACKUP_RETENTION_DAYS:-7}"
ENV_TAG="${EDU_ENV:-test}"
OSSUTIL_BIN="${OSSUTIL_BIN:-$HOME/.local/bin/ossutil}"
SQLITE3_BIN="${SQLITE3_BIN:-sqlite3}"

fail() { echo "[backup-db] $*" >&2; exit 3; }

[ -f "$OSS_ENV_FILE" ] || fail "凭据文件不存在:$OSS_ENV_FILE"
set -a; . "$OSS_ENV_FILE"; set +a
for key in OSS_BUCKET OSS_ENDPOINT OSS_BACKUP_PREFIX OSS_ACCESS_KEY_ID OSS_ACCESS_KEY_SECRET; do
  # ${!key} 是本脚本首处 bash 专属语法(dash 下 Bad substitution):#!/bin/bash 从此承重,勿换 sh
  value="${!key:-}"  # 间接展开(等同旧 eval 写法,无二次求值);:- 必须保留,set -u 下缺键走空串兜底
  [ -n "$value" ] || fail "oss.env 缺键:$key"
done
case "$OSS_ENDPOINT" in
  https://*) ;;
  *) fail "OSS_ENDPOINT 必须是 https:// 开头(备份含用户对话,禁止明文过网):$OSS_ENDPOINT";;
esac
case "$DIR" in /*) ;; *) fail "备份目录必须绝对路径(老仓库先例:prod 不许相对路径):$DIR";;
esac
[ -f "$DB" ] || fail "库不存在:$DB"
[ -x "$OSSUTIL_BIN" ] || fail "ossutil 不存在:$OSSUTIL_BIN"

mkdir -p "$DIR"
chmod 700 "$DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="edu-agent-$STAMP.db"
TMP="$DIR/$NAME.tmp"

# 1) 一致性快照(单事务副本;失败即中止,不留半截)
"$SQLITE3_BIN" "$DB" "VACUUM INTO '$TMP'"

# 2) 完整性 + 关键表行数对账(records 分 kind 计数,files 计数)
[ "$("$SQLITE3_BIN" "$TMP" 'PRAGMA integrity_check;')" = "ok" ] || { rm -f "$TMP"; fail "快照 integrity_check 未通过"; }
for check in \
  "SELECT COUNT(*) FROM records WHERE kind='conversation'" \
  "SELECT COUNT(*) FROM records WHERE kind='session'" \
  "SELECT COUNT(*) FROM files"; do
  live="$("$SQLITE3_BIN" "$DB" "$check")"
  snap="$("$SQLITE3_BIN" "$TMP" "$check")"
  [ "$live" = "$snap" ] || { rm -f "$TMP"; fail "行数不一致($check):live=$live snap=$snap"; }
done

# 3) sha256 侧车(侧车内写最终文件名)+ 原子改名:发布即"库+校验"成对完整
HASH="$(cd "$DIR" && shasum -a 256 "$NAME.tmp" | awk '{print $1}')"
echo "$HASH  $NAME" > "$TMP.sha256"
mv "$TMP" "$DIR/$NAME"
mv "$TMP.sha256" "$DIR/$NAME.sha256"

# 4) 本地滚动(连同侧车;远程保留交给 bucket 生命周期 7+30 天,本脚本不删远程)
find "$DIR" -type f \( -name 'edu-agent-*.db' -o -name 'edu-agent-*.db.sha256' \) \
  -mtime "+$RETENTION" -delete

# 5) 上传 OSS(HTTPS;凭据只进 0600 临时配置文件,trap 删除)
CFG="$(mktemp)"
chmod 600 "$CFG"
trap 'rm -f "$CFG"' EXIT
printf 'language=EN\n[Credentials]\naccessKeyID=%s\naccessKeySecret=%s\n' \
  "$OSS_ACCESS_KEY_ID" "$OSS_ACCESS_KEY_SECRET" > "$CFG"
REMOTE="oss://$OSS_BUCKET/$OSS_BACKUP_PREFIX/$ENV_TAG/$STAMP"
"$OSSUTIL_BIN" -c "$CFG" -e "$OSS_ENDPOINT" cp "$DIR/$NAME" "$REMOTE/$NAME"
"$OSSUTIL_BIN" -c "$CFG" -e "$OSS_ENDPOINT" cp "$DIR/$NAME.sha256" "$REMOTE/$NAME.sha256"
echo "[backup-db] 完成:$DIR/$NAME → $REMOTE/(本地保留 ${RETENTION} 天)"
