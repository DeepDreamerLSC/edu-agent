#!/bin/bash
# d-state-watch.sh — 盯会话 running + 结合任务状态(正常完成不报警)
# 用法: d-state-watch.sh [会话ID子串] [--grace <min>]   缺省 e4244967,grace 10min
# 状态: d-state-watch.state(每行 会话ID=派发时戳=预期回执issue=grace_min)
# 触发: idle ≥ grace 且 预期回执 issue 无新评论(仍欠回执) → 疑似截断
# 不触发: run=True;idle<grace;已有回执(正常完成)
STATE="$HOME/calibration-private/d-state-watch.state"
SID=${1:-e4244967}
GRACE=10
[ "$2" = "--grace" ] && GRACE=${3:-10}
IDLE=0
MAX_ROUNDS=${D_STATE_WATCH_ROUNDS:-240}  # 默认 240 轮(8h @ 120s);测试可设 1-5
# 读状态文件(派发时戳/预期issue/grace)
dispatched_at=$(grep "^$SID=" "$STATE" 2>/dev/null | cut -d= -f2)
expected_issue=$(grep "^$SID=" "$STATE" 2>/dev/null | cut -d= -f3)
state_grace=$(grep "^$SID=" "$STATE" 2>/dev/null | cut -d= -f4)
[ -n "$state_grace" ] && GRACE=$state_grace
for i in $(seq 1 "$MAX_ROUNDS"); do
  if [ -n "$D_STATE_WATCH_FIXTURE" ]; then
    ST=$(cat "$D_STATE_WATCH_FIXTURE" 2>/dev/null)
  else
    ST=$(python3 "$HOME/calibration-private/dsh-rpc.py" list 2>/dev/null | grep "$SID")
  fi
  if [ -z "$ST" ]; then
    :  # API/鉴权故障,跳过
  elif echo "$ST" | grep -q "run=True"; then
    IDLE=0
  else
    IDLE=$((IDLE+1))
    if [ "$IDLE" -ge "$((GRACE/2))" ]; then  # grace/2 轮(grace_min/2min_per_round)
      # 检查预期回执 issue 是否有新评论(正常完成场景)
      if [ -n "$expected_issue" ]; then
        last=$(grep "^$expected_issue=" "$HOME/calibration-private/issue-watch.state" 2>/dev/null | cut -d= -f2)
        last=${last:-0}
        latest_id=""
        if [ -n "$D_STATE_WATCH_FIXTURE" ] && [ -f "${D_STATE_WATCH_FIXTURE}.receipt" ]; then
          latest_id=$(cat "${D_STATE_WATCH_FIXTURE}.receipt")
        else
          latest_id=$(gh api "repos/DeepDreamerLSC/edu-agent/issues/$expected_issue/comments?per_page=1" \
              --jq ".[0].id" 2>/dev/null)
        fi
        if [ -n "$latest_id" ] && echo "$latest_id" | grep -qE "^[0-9]+$" && [ "$latest_id" -gt "$last" ]; then
          echo "✓ 会话 $SID idle ≥${GRACE}min,但 issue#$expected_issue 有新回执——正常完成"
          exit 0
        fi
      fi
      echo "⚠ 会话 $SID idle ≥${GRACE}min 且无新回执——疑似回合截断"
      echo "处置:核回执在否;缺则向其 queue「继续」,或改派空闲会话"
      exit 0
    fi
  fi
  [ -n "$D_STATE_WATCH_FIXTURE" ] && sleep 0 || sleep 120
done
echo "8h 超时,$SID 仍在跑"
