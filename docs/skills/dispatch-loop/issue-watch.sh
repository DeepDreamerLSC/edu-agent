#!/bin/bash
# issue-watch.sh — 多 issue 新评论看门狗(全量有序+to=筛选+分页)
# 用法: issue-watch.sh [issue号...]   缺省读 issue-watch.issues(无文件则 253 263)
# 退出码: 0=有 to=pm/无头 新评论(唤醒) / 1=8h超时 / 2=gh连续失败20轮
# 状态: issue-watch.state(每行 issue号=last_comment_id)
# watch-list: issue-watch.issues(每行一个 issue 号)——运行中增删免杀狗
# 唤醒纪律: 按 to= 字段筛选——to=pm 或无 to= 才叫醒 PM;to=reviewer/dev/log 只记不叫
set -o pipefail  # gh|python 管道:gh 失败(exit 1)必须传播,否则 FAIL 永不计数
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
    # 分页取全(>100 评论翻页;判据=原始页条数,非过滤后条数)
    while true; do
      if [ -n "$ISSUE_WATCH_FIXTURE" ] && [ -f "$ISSUE_WATCH_FIXTURE/$is.page${page}.json" ]; then
        # 测试模式:从 fixture 文件读(每页一个 JSON 数组);raw_n 同判据(原始页条数)
        raw_n=$(python3 -c "import json; print(len(json.load(open('$ISSUE_WATCH_FIXTURE/$is.page${page}.json'))))" 2>/dev/null || echo 0)
        out=$(python3 -c "
import json, sys
data = json.load(open('$ISSUE_WATCH_FIXTURE/$is.page${page}.json'))
for c in data:
    if int(c['id']) > $last:
        body_escaped = json.dumps(c['body'])[1:-1]  # JSON 转义,换行变 \\n
        sys.stdout.write(str(c['id']) + '\t' + body_escaped + '\n')
" 2>/dev/null) || out=""
      elif ! raw=$(gh api "repos/$REPO/issues/$is/comments?per_page=100&page=$page" 2>/dev/null); then
        FAIL=$((FAIL+1))
        if [ "$FAIL" -ge 20 ]; then echo "issue#$is: gh 连续失败 $FAIL 轮,退出待查(auth/网络)"; exit 2; fi
        break
      else
        FAIL=0
        # 翻页判据=原始页条数(非过滤后)——总评论>100 时第 1 页过滤后可为 0 条,
        # 但新评论全在第 2+ 页(2026-09-19 #333 114 条盲区事故的根因)
        raw_n=$(printf '%s' "$raw" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)
        out=$(printf '%s' "$raw" | python3 -c "
import json, sys
for c in json.load(sys.stdin):
    if int(c['id']) > $last:
        print(str(c['id']) + '\t' + json.dumps(c['body'])[1:-1])
" 2>/dev/null)
      fi
      # 累积本页新评论(TSV: id\tbody_escaped;空页跳过——空串经 <<< 仍产生一个空行)
      if [ -n "$out" ]; then
        while IFS=$'\t' read -r cid body_escaped; do
          new_ids+=("$cid")
          new_bodies+=("$body_escaped")
        done <<< "$out"
      fi
      # 检查原始页是否满页(需翻页;按 raw_n 而非过滤条数)
      [ "$raw_n" -lt 100 ] && break
      page=$((page+1))
    done
    # 全量有序输出(按 id 序,已保证)
    if [ "${#new_ids[@]}" -gt 0 ]; then
      max_id=0
      for i in "${!new_ids[@]}"; do
        cid=${new_ids[$i]}
        body_escaped=${new_bodies[$i]}
        body=$(python3 -c "import json,sys; print(json.loads('\"' + sys.argv[1] + '\"'))" "$body_escaped")
        echo "issue#$is 新评论 c$cid:"
        echo "${body:0:2000}"  # 大幅截断(2000字,非240)
        [ "$cid" -gt "$max_id" ] && max_id=$cid
        # 解析 to= 字段(精确抽字段值,非行内首次匹配)
        to=$(python3 -c "
import re, sys
body = sys.argv[1]
m = re.search(r'<!--RECEIPT\s+([^>]*?)-->', body)
if m:
    fields = m.group(1)
    to_m = re.search(r'\bto=(\w+)', fields)
    if to_m:
        print(to_m.group(1))
    else:
        print('')  # 无 to= 旧头
else:
    print('')  # 非回执
" "$body")
        if [ "$to" = "reviewer" ] || [ "$to" = "dev" ] || [ "$to" = "log" ]; then
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
