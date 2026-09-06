#!/bin/bash
# 应用部署(04 §2.1):一条命令两分钟内;ENV 只有 local|test,只差一个 .env.<ENV>。
# 每步幂等:拉代码/uv sync 天然增量,重启/健康轮询/smoke 可重复——失败重跑本脚本
# 即断点续跑(已完成步骤廉价重放)。部署目标 origin/main(04 §3.5);本 checkout
# 是专用部署目录,reset --hard 丢弃被跟踪文件的本地改动(.env.* 与 var/ 不受影响)。
# DEPLOY_REF 仅限本地自验候选分支,ENV=test 的正式部署一律用默认 main。
set -euo pipefail

ENV_NAME="" DRY_RUN=0 APP_PORT=8300 APP_LABEL=com.edu-agent.app REF="${DEPLOY_REF:-main}"
while [ $# -gt 0 ]; do
  case "$1" in
    --env) ENV_NAME="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "用法:deploy.sh --env local|test [--dry-run](04 §2.1)"; exit 2 ;;
  esac
done
[ "$ENV_NAME" = "local" ] || [ "$ENV_NAME" = "test" ] || { echo "ENV 只支持 local|test"; exit 2; }

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
START=$(date +%s)
say() { echo "[deploy:$ENV_NAME] $*"; }
finish() {  # 04 §2.1:每次部署写一条 JSONL,成功与失败都记
  local result="$1" ms=$(( ($(date +%s) - START) * 1000 ))
  mkdir -p var
  printf '{"deploy_id":"%s","sha":"%s","env":"%s","duration_ms":%s,"result":"%s"}\n' \
    "$(date -u +%Y%m%dT%H%M%SZ)" "$(git rev-parse --short HEAD)" "$ENV_NAME" "$ms" "$result" >> var/deploy.jsonl
}
trap 'finish failed' ERR

step_fetch() {
  git fetch --quiet origin "$REF"
  git checkout --quiet --detach "origin/$REF"
  git reset --hard --quiet "origin/$REF"
}
step_sync() { uv sync --frozen; }
step_restart() {  # bootout+bootstrap:plist 重读,幂等重启
  sed "s|__DEPLOY_ROOT__|$ROOT|" deploy/launchd/com.edu-agent.app.plist \
    > "$HOME/Library/LaunchAgents/$APP_LABEL.plist"
  launchctl bootout "gui/$(id -u)/$APP_LABEL" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/$APP_LABEL.plist"
}
step_health() {  # 轮询 30s:服务起来且 /healthz 可用
  local i
  for i in $(seq 1 30); do
    curl -fsS "http://127.0.0.1:$APP_PORT/healthz" >/dev/null 2>&1 && break
    sleep 1
  done
  curl -fsS "http://127.0.0.1:$APP_PORT/healthz"
  echo
}
step_smoke() { uv run python scripts/smoke.py; }

run() {  # --dry-run 只打印计划(04 §2.1)
  if [ "$DRY_RUN" = 1 ]; then echo "[dry-run] $1"; else say "$1"; "$2"; fi
}

if [ -f ".env.$ENV_NAME" ] && [ "$DRY_RUN" = 0 ]; then
  set -a; . ".env.$ENV_NAME"; set +a   # 凭据只进环境,不进日志(gitignored)
fi
run "拉代码到 origin/$REF(reset 幂等)" step_fetch
run "uv sync --frozen(增量幂等)" step_sync
run "重启应用服务 launchd/$APP_LABEL" step_restart
run "健康检查 /healthz(轮询 30s)" step_health
run "链路 smoke:3 条固定调用(04 §2.2)" step_smoke
finish ok
say "完成,用时 $(( $(date +%s) - START ))s"
