#!/bin/bash
# issue-watch.sh — 多 issue 新评论看门狗(watch-list 文件驱动,每轮重读,免杀狗增删)
# 用法: issue-watch.sh [issue号...]   缺省读 issue-watch.issues(无文件则 253 263)
# 退出码: 0=有新评论(打印) / 1=8h超时 / 2=gh连续失败20轮(auth/网络)
# 状态: issue-watch.state(每行 issue号=last_comment_id)
# watch-list: issue-watch.issues(每行一个 issue 号)——派单到哪个 issue 回执,
#   就往里加一行,运行中的狗下轮自动纳入;无需杀狗。
# 唤醒后重挂 = 直接再跑;自己在被盯 issue 发评论后先同步 state 防自触发。
# 脚本与 SKILL.md 同仓(docs/skills/dispatch-loop/);状态文件在私有工作区。
STATE="$HOME/calibration-private/issue-watch.state"
LIST="$HOME/calibration-private/issue-watch.issues"
REPO=DeepDreamerLSC/edu-agent
FAIL=0
for round in $(seq 1 320); do  # 8h @ 90s
  if [ $# -gt 0 ]; then ISSUES=("$@");
  elif [ -f "$LIST" ]; then mapfile -t ISSUES < "$LIST";
  else ISSUES=(253 263); fi
  found=0
  for is in "${ISSUES[@]}"; do
    [ -z "$is" ] && continue
    last=$(grep "^$is=" "$STATE" 2>/dev/null | cut -d= -f2); last=${last:-0}
    if ! out=$(gh api "repos/$REPO/issues/$is/comments?per_page=100" \
        --jq "[.[] | select((.id|tonumber) > $last)] | max_by(.id) | if . then (.id|tostring) + \"║\" + (.body[:240] | gsub(\"\\n\"; \" \")) else \"\" end" 2>/dev/null); then
      FAIL=$((FAIL+1))
      if [ "$FAIL" -ge 20 ]; then echo "issue#$is: gh 连续失败 $FAIL 轮,退出待查(auth/网络)"; exit 2; fi
      continue
    fi
    FAIL=0
    if [ -n "$out" ]; then
      cid=${out%%║*}
      if grep -q "^$is=" "$STATE" 2>/dev/null; then
        sed -i "s/^$is=.*/$is=$cid/" "$STATE"
      else
        echo "$is=$cid" >> "$STATE"
      fi
      echo "issue#$is 新评论 c$cid:"
      echo "${out#*║}"
      found=1
    fi
  done
  [ "$found" -eq 1 ] && exit 0
  sleep 90
done
echo "8h 超时,无新回执"; exit 1