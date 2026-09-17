#!/bin/bash
# liveness-watch.sh — GEPA nets run 活性看门狗(#290 契约风格,进程版)
# 用法: liveness-watch.sh <run_dir> <driver_pid> [--stale-min N]
#   缺省 stale 45 分钟(单批 15 案 × ~4 调用 × 20s ≈ 20min;45min 留裕量)
# 契约(照 #290:状态文件 + 轮询 + 只记录不自动重跑):
#   - 驱动每 120s 检查一次 pid;state.json 每次模型调用原子更新(mtime 即心跳)
#   - pid 死 + phase=done        → 记「正常结束」退出 0
#   - pid 死 + phase≠done        → 记「进程死亡@最后 phase」退出 1(只记录,不重跑)
#   - pid 活 + 心跳 stale ≥ 阈值 → 记一次「心跳超时」(去重),继续盯
#   - pid 活 + 心跳新鲜          → 静默
# 输出:run_dir/watchdog.log(append);退出码 0=正常收尾 1=异常 2=轮数耗尽仍在跑
RUN_DIR=${1:?用法: liveness-watch.sh <run_dir> <pid> [--stale-min N]}
PID=${2:?缺 pid}
STALE_MIN=45
[ "$3" = "--stale-min" ] && STALE_MIN=${4:-45}
MAX_ROUNDS=${WATCHDOG_ROUNDS:-180}   # 120s × 180 = 6h 窗口
LOG="$RUN_DIR/watchdog.log"
STALE_S=$((STALE_MIN * 60))
note() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }
phase() { /usr/bin/python3 -c "import json,sys;print(json.load(open('$RUN_DIR/state.json')).get('phase','?'))" 2>/dev/null || echo "?"; }
last_calls() { /usr/bin/python3 -c "import json;print(json.load(open('$RUN_DIR/state.json')).get('calls','?'))" 2>/dev/null || echo "?"; }

for i in $(seq 1 "$MAX_ROUNDS"); do
  if ! kill -0 "$PID" 2>/dev/null; then
    PH=$(phase)
    if [ "$PH" = "done" ]; then
      note "✓ pid=$PID 正常结束(phase=done,calls=$(last_calls))"
      exit 0
    fi
    note "⚠ pid=$PID 进程死亡 @phase=$PH calls=$(last_calls)——只记录不重跑(用户信封纪律)"
    exit 1
  fi
  if [ -f "$RUN_DIR/state.json" ]; then
    AGE=$(( $(date +%s) - $(stat -f %m "$RUN_DIR/state.json" 2>/dev/null || echo 0) ))
    if [ "$AGE" -ge "$STALE_S" ] && [ ! -f "$RUN_DIR/.reported-stale" ]; then
      note "⚠ pid=$PID 活着但心跳超时 ${AGE}s ≥ ${STALE_S}s @phase=$(phase) calls=$(last_calls)"
      touch "$RUN_DIR/.reported-stale"
    fi
  fi
  sleep 120
done
note "pid=$PID 观察窗耗尽($((MAX_ROUNDS * 2))min)仍在跑——交回 agent 处置"
exit 2
