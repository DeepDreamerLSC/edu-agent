#!/bin/bash
# d-state-watch.sh — 只读盯指定会话 running 标志(盯谁传谁,缺省 D)
# 用法: d-state-watch.sh [会话ID子串]   缺省 e4244967
# 触发:连续 2 轮(≥4min) idle 且非 API 故障 → 疑似回合中断,报告退出
# 不触发:run=True 重置;API 故障(输出空)跳过不计
# 脚本与 SKILL.md 同仓(docs/skills/dispatch-loop/);dsh-rpc.py 在私有工作区。
SID=${1:-e4244967}
IDLE=0
for i in $(seq 1 240); do  # 8h @ 120s
  ST=$(python3 "$HOME/calibration-private/dsh-rpc.py" list 2>/dev/null | grep "$SID")
  if [ -z "$ST" ]; then
    :  # API/鉴权故障,不算 idle,跳过本轮
  elif echo "$ST" | grep -q "run=True"; then
    IDLE=0
  else
    IDLE=$((IDLE+1))
    if [ "$IDLE" -ge 2 ]; then
      echo "⚠ 会话 $SID idle ≥4min——若对应 issue 无新回执,疑似回合被截断(消息已消费无产出)"
      echo "处置:核回执在否;缺则向其 queue「继续」,或按用户指示改派空闲会话(A/B/C)"
      exit 0
    fi
  fi
  sleep 120
done
echo "8h 超时,$SID 仍在跑"