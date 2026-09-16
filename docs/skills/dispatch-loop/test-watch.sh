#!/bin/bash
# test-watch.sh — issue-watch.sh / d-state-watch.sh 验收测试(零 API,纯 fixture)
# 跑法: bash docs/skills/dispatch-loop/test-watch.sh
# 期望输出: 5 PASS(三模拟/to= 三态/分页/d-state),0 FAIL
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$SCRIPT_DIR/issue-watch.sh"
D_SCRIPT="$SCRIPT_DIR/d-state-watch.sh"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
export HOME="$WORK/fakehome"
mkdir -p "$WORK/fakehome/calibration-private"
STATE="$WORK/fakehome/calibration-private/issue-watch.state"
D_STATE="$WORK/fakehome/calibration-private/d-state-watch.state"
FIX="$WORK/fixtures"
mkdir -p "$FIX"

pass=0; fail=0
ok() { echo "PASS: $1"; pass=$((pass+1)); }
no() { echo "FAIL: $1"; fail=$((fail+1)); }

# === 测试 1: 三模拟评论全量有序输出(>240 字 bodies 不截断) ===
cat > "$FIX/253.page1.json" <<'JSON'
[
  {"id": 1001, "body": "COMMENT-ONE: 这是一条很长的模拟评论,用于验证 issue-watch.sh 在三评论同波场景下是否全量输出而不被 max_by 吞掉,超过二百四十字也不会截断。AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"},
  {"id": 1002, "body": "COMMENT-TWO: 第二条模拟评论,同样很长,验证全量有序。BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"},
  {"id": 1003, "body": "COMMENT-THREE: 第三条,to=pm。<!--RECEIPT task=demo pr=999 calls=0 tier=0 outcome=demo to=pm sha256=deadbeef12345678-->"}
]
JSON
echo "253=1000" > "$STATE"
out=$(ISSUE_WATCH_FIXTURE="$FIX" ISSUE_WATCH_ROUNDS=1 bash "$SCRIPT" 253)
echo "$out" | grep -q "COMMENT-ONE" && \
echo "$out" | grep -q "COMMENT-TWO" && \
echo "$out" | grep -q "COMMENT-THREE" && \
echo "$out" | grep -c "c100[123]" | grep -q "^3$" && \
[ "$(echo "$out" | grep "COMMENT-ONE" | wc -c)" -gt 240 ] \
  && ok "三模拟评论全量有序+大幅截断(>240字)" \
  || no "三模拟评论全量有序"

# 游标推进验证
grep -q "^253=1003$" "$STATE" && ok "游标推进到最大 id(1003)" || no "游标推进"

# === 测试 2: to= 过滤三态 ===
# 2a: to=log 不唤醒(exit 1 = 超时,因为 1 轮内没 to=pm/无头)
cat > "$FIX/301.page1.json" <<'JSON'
[{"id": 2001, "body": "reviewer log <!--RECEIPT task=x pr=1 calls=0 tier=0 to=log sha256=abc-->"}]
JSON
echo "301=2000" > "$STATE"
rc=0; ISSUE_WATCH_FIXTURE="$FIX" ISSUE_WATCH_ROUNDS=1 bash "$SCRIPT" 301 > /dev/null 2>&1; rc=$?
[ "$rc" -eq 1 ] && ok "to=log 不唤醒(exit 1 超时)" || no "to=log 应不唤醒(实际 rc=$rc)"

# 2b: to=pm 唤醒(exit 0)
cat > "$FIX/302.page1.json" <<'JSON'
[{"id": 2002, "body": "pm target <!--RECEIPT task=x pr=1 calls=0 tier=0 to=pm sha256=abc-->"}]
JSON
echo "302=2001" > "$STATE"
rc=0; ISSUE_WATCH_FIXTURE="$FIX" ISSUE_WATCH_ROUNDS=1 bash "$SCRIPT" 302 > /dev/null 2>&1; rc=$?
[ "$rc" -eq 0 ] && ok "to=pm 唤醒(exit 0)" || no "to=pm 应唤醒(实际 rc=$rc)"

# 2c: 无 to= 旧头保守唤醒(exit 0)
cat > "$FIX/303.page1.json" <<'JSON'
[{"id": 2003, "body": "旧回执头 <!--RECEIPT task=x pr=1 calls=0 tier=0 sha256=abc-->"}]
JSON
echo "303=2002" > "$STATE"
rc=0; ISSUE_WATCH_FIXTURE="$FIX" ISSUE_WATCH_ROUNDS=1 bash "$SCRIPT" 303 > /dev/null 2>&1; rc=$?
[ "$rc" -eq 0 ] && ok "无 to= 旧头保守唤醒(exit 0)" || no "无 to= 应保守唤醒(实际 rc=$rc)"

# === 测试 3: 分页(>100 评论翻页取全) ===
# 造 page1(100 条) + page2(17 条) = 117 条
python3 -c "
import json
p1 = [{'id': 3000+i, 'body': f'page1-{i}'} for i in range(100)]
p2 = [{'id': 3100+i, 'body': f'page2-{i}'} for i in range(17)]
json.dump(p1, open('$FIX/400.page1.json', 'w'))
json.dump(p2, open('$FIX/400.page2.json', 'w'))
"
echo "400=2999" > "$STATE"
out=$(ISSUE_WATCH_FIXTURE="$FIX" ISSUE_WATCH_ROUNDS=1 bash "$SCRIPT" 400)
count=$(echo "$out" | grep -c "^issue#400 新评论 c3[01]")
[ "$count" -eq 117 ] && ok "分页取全 117 条(100+17)" || no "分页应 117 条(实际 $count)"
grep -q "^400=3116$" "$STATE" && ok "分页游标推进到最大 id(3116)" || no "分页游标"

# === 测试 4: d-state 正常完成场景零误报 ===
echo "sess123=1726000000=555=4" > "$D_STATE"  # grace=4min → 2 轮触发阈值
echo "555=9000" > "$STATE"  # issue#555 last seen comment id = 9000
echo "session-sess123 run=False" > "$WORK/fixture-list.txt"
echo "9001" > "$WORK/fixture-list.txt.receipt"  # 新回执 id=9001 > 9000
out=$(D_STATE_WATCH_FIXTURE="$WORK/fixture-list.txt" D_STATE_WATCH_ROUNDS=5 \
      bash "$D_SCRIPT" sess123 --grace 4)
echo "$out" | grep -q "正常完成" && ok "d-state 正常完成零误报" || no "d-state 应识别正常完成"

# === 测试 5: d-state 无回执场景(真正 idle)报警 ===
echo "sess456=1726000000=556=4" > "$D_STATE"
echo "556=9000" > "$STATE"
echo "session-sess456 run=False" > "$WORK/fixture-list2.txt"
echo "9000" > "$WORK/fixture-list2.txt.receipt"  # 无新回执(id=9000 不 > last=9000)
out=$(D_STATE_WATCH_FIXTURE="$WORK/fixture-list2.txt" D_STATE_WATCH_ROUNDS=5 \
      bash "$D_SCRIPT" sess456 --grace 4)
echo "$out" | grep -q "疑似回合截断" && ok "d-state 无回执场景报警" || no "d-state 应在无回执时报警"

echo ""
echo "===== 结果: $pass PASS / $fail FAIL ====="
[ "$fail" -eq 0 ] && exit 0 || exit 1
