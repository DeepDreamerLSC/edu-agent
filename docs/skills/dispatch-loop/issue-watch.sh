#!/bin/bash
# issue-watch.sh — 多 issue 新评论看门狗(全量有序+to=筛选+分页)
# 用法: issue-watch.sh [issue号...]   缺省读 issue-watch.issues(无文件则 253 263)
# 退出码: 0=有 to=pm/无头 新评论(唤醒) / 1=8h超时 / 2=gh连续失败20轮
# 状态: issue-watch.state(每行 issue号=last_comment_id)
# watch-list: issue-watch.issues(每行一个 issue 号)——运行中增删免杀狗
# 唤醒纪律: 按 to= 字段筛选——to=pm 或无 to= 才叫醒 PM;to=reviewer/dev/log 只记不叫
STATE="$HOME/calibration-private/issue-watch.state"
LIST="$HOME/calibration-private/issue-watch.issues"
REPO=DeepDreamerLSC/edu-agent
FAIL=0
MAX_ROUNDS=${ISSUE_WATCH_ROUNDS:-320}  # 默认 320 轮(8h @ 90s);测试可设 1
for round in $(seq 1 "$MAX_ROUNDS"); do
  if [ $# -gt 0 ]; then ISSUES=("$@");
  elif [ -f "$LIST" ]; then mapfile -t ISSUES < "$LIST";
  else ISSUES=(253 263); fi
  wake=0
  for is in "${ISSUES[@]}"; do
    [ -z "$is" ] && continue
    last=$(grep "^$is=" "$STATE" 2>/dev/null | cut -d= -f2); last=${last:-0}
    page=1
    new_ids=()
    new_bodies=()
    # 分页取全(>100 评论翻页)
    while true; do
      if [ -n "$ISSUE_WATCH_FIXTURE" ] && [ -f "$ISSUE_WATCH_FIXTURE/$is.page${page}.json" ]; then
        # 测试模式:从 fixture 文件读(每页一个 JSON 数组)
        out=$(python3 -c "
import json, sys
data = json.load(open('$ISSUE_WATCH_FIXTURE/$is.page${page}.json'))
for c in data:
    if int(c['id']) > $last:
        sys.stdout.write(str(c['id']) + '║' + c['body'] + '\n')
" 2>/dev/null) || out=""
      elif ! out=$(gh api "repos/$REPO/issues/$is/comments?per_page=100&page=$page" \
          --jq ".[] | select((.id|tonumber) > $last) | (.id|tostring) + \"║\" + .body" 2>/dev/null); then
        FAIL=$((FAIL+1))
        if [ "$FAIL" -ge 20 ]; then echo "issue#$is: gh 连续失败 $FAIL 轮,退出待查(auth/网络)"; exit 2; fi
        break
      fi
      FAIL=0
      [ -z "$out" ] && break
      # 累积本页新评论
      while IFS= read -r line; do
        cid=${line%%║*}
        body=${line#*║}
        new_ids+=("$cid")
        new_bodies+=("$body")
      done <<< "$out"
      # 检查是否满页(需翻页)
      count=$(echo "$out" | wc -l)
      [ "$count" -lt 100 ] && break
      page=$((page+1))
    done
    # 全量有序输出(按 id 序,已保证)
    if [ "${#new_ids[@]}" -gt 0 ]; then
      max_id=0
      for i in "${!new_ids[@]}"; do
        cid=${new_ids[$i]}
        body=${new_bodies[$i]}
        echo "issue#$is 新评论 c$cid:"
        echo "${body:0:2000}"  # 大幅截断(2000字,非240)
        [ "$cid" -gt "$max_id" ] && max_id=$cid
        # 解析 to= 字段(旧头无 to= 保守唤醒)
        if echo "$body" | grep -qE '<!--RECEIPT .*to=(reviewer|dev|log)'; then
          : # 非 PM 目标,只记不叫
        else
          wake=1  # to=pm 或无 to= 保守唤醒
        fi
      done
      # 游标推进(全部交付后)
      if grep -q "^$is=" "$STATE" 2>/dev/null; then
        sed -i "s/^$is=.*/$is=$max_id/" "$STATE"
      else
        echo "$is=$max_id" >> "$STATE"
      fi
    fi
  done
  [ "$wake" -eq 1 ] && exit 0
  [ -z "$ISSUE_WATCH_FIXTURE" ] && sleep 90
done
echo "8h 超时,无新回执"; exit 1
