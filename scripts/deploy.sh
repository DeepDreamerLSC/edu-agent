#!/bin/bash
# 应用部署(04 §2.1):一条命令两分钟内;ENV 只有 local|test,只差一个 .env.<ENV>。
# 每步幂等:拉代码/uv sync 天然增量,重启/健康轮询/smoke 可重复——失败重跑本脚本
# 即断点续跑(已完成步骤廉价重放)。部署目标 origin/main(04 §3.5);本 checkout
# 是专用部署目录,reset --hard 丢弃被跟踪文件的本地改动(.env.* 与 var/ 不受影响)。
# DEPLOY_REF 仅限本地自验候选分支,ENV=test 的正式部署一律用默认 main。
# 被部署的服务**只有一个**:合作方对话服务(含 /healthz,端口 8300,04 §2.1)。
set -eEuo pipefail   # -E:函数内失败也要触发 ERR trap → 失败同样写台账(finish failed)

ENV_NAME="" DRY_RUN=0 APP_PORT=8300 APP_LABEL=com.edu-agent.partner-api \
  REF="${DEPLOY_REF:-main}"
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
  local result="$1" now deploy_id duration_ms
  now=$(date +%s)
  duration_ms=$(( (now - START) * 1000 ))
  deploy_id=$(date -u -r "$now" +%Y%m%dT%H%M%SZ)
  mkdir -p var
  printf '{"deploy_id":"%s","sha":"%s","env":"%s","duration_ms":%s,"result":"%s"}\n' \
    "$deploy_id" "$(git rev-parse --short HEAD)" "$ENV_NAME" "$duration_ms" "$result" >> var/deploy.jsonl
}
trap 'finish failed' ERR

step_fetch() {
  git fetch --quiet origin "$REF"
  git checkout --quiet --detach "origin/$REF"
  git reset --hard --quiet "origin/$REF"
  # 本脚本就在这个 checkout 里:reset 会换掉自己的文件,而 bash 是按偏移增量读脚本的
  # → 新旧混用(2026-09-11 实测:旧的 APP_LABEL 去读已被新代码删掉的 plist)。更新完
  # 代码换一份跑,保证全程按同一版本执行;重跑幂等(拉取/同步/重启均可廉价重放)。
  [ -n "${DEPLOY_REEXEC:-}" ] || exec env DEPLOY_REEXEC=1 "$0" --env "$ENV_NAME"
}
step_sync() { uv sync --frozen; }
step_restart() {  # bootout 异步:等卸载完成再 bootstrap,否则撞 "5: Input/output error"
  # 模板随 APP_LABEL 走:同一环境一个服务(04 §2.1)。__ENV_NAME__ 只传环境名,
  # 凭据仍在部署目录的 .env.<ENV>,由启动器读(launchd 不继承 shell 环境)。
  sed -e "s|__DEPLOY_ROOT__|$ROOT|" -e "s|__ENV_NAME__|$ENV_NAME|" \
    "deploy/launchd/$APP_LABEL.plist" > "$HOME/Library/LaunchAgents/$APP_LABEL.plist"
  launchctl bootout "gui/$(id -u)/$APP_LABEL" >/dev/null 2>&1 || true
  local i
  for i in $(seq 1 20); do
    launchctl print "gui/$(id -u)/$APP_LABEL" >/dev/null 2>&1 || break
    sleep 0.5
  done
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
if [ "$DRY_RUN" = 1 ]; then  # dry-run 不是部署:不写台账(04 §2.1 台账只记真实部署)
  say "dry-run 完成,未执行任何步骤、未写台账"
  exit 0
fi
finish ok
say "完成,用时 $(( $(date +%s) - START ))s"
