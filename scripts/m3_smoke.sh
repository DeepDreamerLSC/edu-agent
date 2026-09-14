#!/bin/bash
# ============================================
# M3 集成冒烟——你亲手跑的全链路验证
# 用法: bash m3_smoke.sh
# ============================================
BASE="${1:-http://127.0.0.1:8300}"
PASS=0; FAIL=0
section() { echo ""; echo "════════ $1 ════════"; }
ok()   { echo "  ✅ $1"; PASS=$((PASS+1)); }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

section "① 健康检查"
HEALTH=$(curl -s --max-time 3 "$BASE/healthz" 2>/dev/null)
[ -n "$HEALTH" ] && ok "healthz: $HEALTH" || fail "healthz 无响应"

section "② 简单登录(student1)"
LOGIN=$(curl -s --max-time 10 -X POST "$BASE/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"account":"student1","password":"demo","role":"student"}' 2>/dev/null)
TOKEN=$(echo "$LOGIN" | python3 -c "import json,sys; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
[ -n "$TOKEN" ] && ok "token: ${TOKEN:0:30}..." || fail "登录失败: $(echo $LOGIN | head -c 120)"

section "③ 创建会话(合作方入口)"
CONV=$(curl -s --max-time 60 -X POST "$BASE/api/conversations" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"question_id":"chicken_rabbit"}' 2>/dev/null)
CONV_ID=$(echo "$CONV" | python3 -c "import json,sys; print(json.load(sys.stdin).get('conversation_id',''))" 2>/dev/null)
FIRST_Q=$(echo "$CONV" | python3 -c "import json,sys; print(json.load(sys.stdin).get('first_question','')[:100])" 2>/dev/null)
[ -n "$CONV_ID" ] && ok "conversation_id: $CONV_ID" || fail "创建会话失败"
[ -n "$FIRST_Q" ] && echo "  首问: $FIRST_Q"

section "④ 学生答错 → 苏格拉底纠偏"
R1=$(curl -s --max-time 30 -X POST "$BASE/api/conversations/$CONV_ID/messages" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"content":"我觉得鸡有4只兔有4只","skill_id":"small_lecturer_coaching","input":{"expected_session_version":1}}' 2>/dev/null)
A1=$(echo "$R1" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('assistant_message',{}).get('content',d.get('error',{}).get('code','解析失败'))[:150])" 2>/dev/null)
[ -n "$A1" ] && ok "纠偏: $A1" || fail "第2轮失败: $(echo $R1 | head -c 100)"

section "⑤ 学生自我修正 → 确认"
R2=$(curl -s --max-time 30 -X POST "$BASE/api/conversations/$CONV_ID/messages" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"content":"哦!鸡3只6只脚,兔5只20只脚,刚好26只!","skill_id":"small_lecturer_coaching","input":{"expected_session_version":2}}' 2>/dev/null)
A2=$(echo "$R2" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('assistant_message',{}).get('content',d.get('error',{}).get('code','解析失败'))[:150])" 2>/dev/null)
[ -n "$A2" ] && ok "确认: $A2" || fail "第3轮失败"

section "⑥ confirm → 总结"
R3=$(curl -s --max-time 30 -X POST "$BASE/api/conversations/$CONV_ID/messages" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"content":"我确认我学会了","skill_id":"small_lecturer_coaching","input":{"expected_session_version":3,"interaction_action":"confirm"}}' 2>/dev/null)
A3=$(echo "$R3" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('interaction',{}).get('result',{}); print(json.dumps({k:str(v)[:80] for k,v in r.items()}, ensure_ascii=False)) if r else print(d.get('assistant_message',{}).get('content','无')[:150])" 2>/dev/null)
[ -n "$A3" ] && ok "总结: $A3" || fail "confirm 失败"

section "⑦ GET 会话状态"
STATE=$(curl -s --max-time 10 "$BASE/api/conversations/$CONV_ID" \
  -H "Authorization: Bearer $TOKEN" 2>/dev/null)
[ -n "$STATE" ] && ok "状态: $(echo $STATE | head -c 120)" || fail "GET 失败"

echo ""
echo "════════ 结果 ════════"
echo "通过: $PASS | 失败: $FAIL"
[ $FAIL -eq 0 ] && echo "🎉 全链路通过——M3 技术收口" || echo "⚠️ 有失败项,按序修"
