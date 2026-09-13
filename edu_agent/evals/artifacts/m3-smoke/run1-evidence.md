# M3 合同冒烟 run1 证据(#221 裁定 6:合作方真路径 + 真内核真模型)

## 口径

- **时间**:2026-09-13(联调窗口前);**树** = 本 PR(`feat/221-m3-smoke` 全部文件,head 见 PR 描述)。
- **被测**:`scripts/serve_partner_api.py` 装配(真内核 small-lecturer + SqliteStore + IdentityService),
  `EDU_QUESTION_SOURCE=seed`(题号 `equation_subtract`,解方程 3x+7=25)。
- **模型(真,非 mock)**:tutor 主选 `qwen3_vl_8b`(Qwen3-VL-8B-GGUF,127.0.0.1:8303),
  备选 `mlx_27b`(Qwen3.5-27B-4bit,127.0.0.1:8301);judge 主选 mlx_27b。
  configs/models.yaml(仓库唯一模型配置,sha256 见 healthz 快照)。
- **第六型 error 帧**用坏网关实例:同一 DB、`EDU_MODELS_YAML` 指向 vision+mlx 全死的
  副本(127.0.0.1:9)——503 路径的黑盒触发,不 mock 代码。
- **断言主体**:`scripts/m3_smoke.py`(黑盒 HTTP,零生产代码 import)。

## 结果:13/13 阶段 PASS(证据 JSON:`run1-result.json`)

login(含 401 错密信封)→ open(idempotency_key)→ 幂等重试(同 key 同会话)→
409 QUESTION_SOURCE_PINNED(同 key 换题 + 信封四键形状)→ refresh(B3 信封)→
messages(expected_session_version 全程响应回读)→ 消息幂等(同 message_idempotency_key
原样返回、version 不前进)→ 409 SKILL_SESSION_CONFLICT(旧版本)→ 422(未知键)→
403(禁交键 answer)→ SSE happy 五型帧序(status→start→interaction→delta→done,
delta 载全文且与 done 一致)→ confirm(completed 分支 + 终态后 409)→
SSE 第六型 error 帧(坏网关 503 → start/error 两帧)。

模型延迟实测:open(首问)1705ms / 学生轮 1071ms / 流式轮 1444ms / confirm 834ms。

## 「App 零改动」验证结论

合同面**零意外形状**:13 阶段全过,服务端行为与 00 §5.2/#48 合同快照一致。
过程中修正的 4 处均为**客户端(冒烟脚本)预设错误**,不是服务端偏差:

1. learner 子键(grade 等)是 open 请求**顶层平铺**字段,不嵌套在 `learner` 下
   (422 错误信封的允许清单可自证);
2. 统一 Open 响应是 §5 嵌套形态 `question.active_session.*`(conversation 是字符串 id);
3. refresh 是 POST(空体),非 GET;
4. SSE status 帧的 session_version = 本轮**完成后**版本(与 done 帧同源,响应构造后一次编码)。

**1 个行为发现(给 runbook/伪流式决策)**:tutor 主备语义真实生效——vision 死端口而
mlx 活着时,open 与流式轮无感降级成功;主备全死才 503。对「App 零改动」是利好
(单模型故障不中断),但意味着流式延迟可能悄悄落到备选模型,TTFT 口径要按主备混合计。

## 复现

```bash
# 主实例(真模型)+ 坏网关实例(共库,vision+mlx 指死端口;sed 出 models_dead.yaml)
DEMO_ACCOUNT=student1 DEMO_PASSWORD=… IDENTITY_TOKEN_HMAC_KEY=… EDU_QUESTION_SOURCE=seed \
EDU_PARTNER_API_PORT=8312 EDU_DB_PATH=/tmp/m3smoke/main.db python scripts/serve_partner_api.py &
EDU_MODELS_YAML=/tmp/m3smoke/models_dead.yaml EDU_PARTNER_API_PORT=8313 (其余同上) … &
python scripts/m3_smoke.py --base-url http://127.0.0.1:8312 \
    --error-base-url http://127.0.0.1:8313 --account student1 --password … \
    --out result.json
```
