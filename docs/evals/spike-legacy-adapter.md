# Spike 结论:老系统合作方流程接口实测行为清单(M1 阶段 1)

日期:2026-09-07 · 环境:edu-test.chiraliumai.cn(测试部署)· 驱动:capacity 租户学生 session(50 个文件化账号)· 适配器雏形:PR #37

范围与前提:00 §8.2 阶段 1;题号歧义走 capacity 租户唯一发布题(issue #3 workaround);/health 503(评审链路 model worker 缺失)在 spike 范围内接受红,记录在案;tutor 链路实测可用。全程对老环境只做 HTTP 调用,零写入;凭据只走环境变量。

## 1. 端点行为清单(实测)

| 环节 | 端点 | 实测行为 | 延迟(单发) |
|---|---|---|---|
| 登录 | `POST /api/auth/login` {account,password,remember:false} | 200,Bearer access_token;响应 `expires_in` 实测为 null,TTL 由服务端常量决定(8h,remember 30d);无 refresh-token 端点,续期=重登录 | 1.1 s |
| 题目查询 | `GET /api/prepared-questions/{qid}` | 200;qid=partner_question_id;409 `PREPARED_QUESTION_ID_AMBIGUOUS` 当同题号多源发布(test_school 5 题,capacity 租户无此问题) | <0.3 s |
| 开会话 | `POST /api/prepared-questions/{qid}/open` {idempotency_key} | 200:conversation/skill_session/attempt/session_version/first_question_ready=true,首问在 conversation.messages 尾部 | 6.0–6.9 s(新 attempt);0.5–0.7 s(幂等重开/恢复) |
| 刷新 | `POST /api/conversations/{cid}/skill-sessions/{ssid}/refresh` | 200:交互信封(state/kind/session_version) | 0.54–0.59 s |
| 回合(流式) | `POST /api/conversations/{cid}/messages/stream` | SSE 见 §3;done 帧含完整 assistant_message(metadata.interaction 带 state+session_version) | 6.2–7.3 s(并发 2 时 11.5–13 s) |
| 回合(同步) | `POST .../messages` | 同 body 同语义;幂等重放(同 client_turn_id+idempotency_key)→ 200 且同一 assistant message_id,不重复入列 | 同上 |

消息 body 契约:`{content, skill_id:"small_lecturer_coaching", input:{skill_session_id, expected_session_version[, interaction_action, values]}, client_turn_id, idempotency_key}`。interaction_action ∈ activate / submit_inputs / cancel / restart(评测驱动普通回合不带 action)。

## 2. 超时与重试语义(实测)

- **幂等键**:open 同 idempotency_key 重发 → 同一 attempt_id/conversation,`restored=true`,快路径(0.5 s);messages 同键重放 → 同一 assistant message_id。评测驱动全链路带幂等键是安全的。
- **session_version(与 00 §4.2 预设不同)**:普通对话回合携带陈旧 expected_session_version 实测**被宽容**(HTTP 200,服务端按当前版本推进,last-write-wins),不返回 409。409 家族的实测/合同边界:
  - `SKILL_SESSION_NOT_FOUND`(409):指定的 skill_session_id 不存在(实测);
  - `SKILL_SESSION_STALE`(409,合同):指定会话已不是当前前台会话;
  - `SKILL_SESSION_CONFLICT`(409,合同):录制资源绑定版本冲突;同会话内切换题目包。
  - 结论:适配器按信封 session_version 推进即可,不必为 409 做版本回读;评测并发写同一会话是被宽容的,但应避免(数据歧义)。
- **token 失效**:坏/过期 token → 401;重登录后原请求成功(实测)。真实 TTL 8h(代码常量),过夜跑单轮(≤数小时)内一次登录即可,但按 401→重登录→重试一次实现(适配器已内置,流式路径同,幂等键保证重发安全)。
- **流式中断**:客户端在 delta 后断开 → 服务端不锁会话;新幂等键重试立即正常(实测 9.5 s 正常回合)。中断回合的助手消息是否落库未定论(GET conversation 的 messages 提取口径待核),重试路径无影响。

## 3. 流式帧格式

`event: <name>\ndata: {json}\n\n`,事件序:`start → status(×1-2) → interaction → delta(×n) → done | error`。

- `delta`:{delta: 文本片, model_call_id};**安全分片流**:完整生成+门禁后才分片下发,实测 TTFT≈端到端(每回合 delta 仅 2–3 片)。评测的 TTFT 口径按端到端记录,与 01 §5 gateway 口径不同源。
- `done`:完整 ConversationMessageCreateResponse(assistant_message.metadata.interaction 为状态权威)。
- `error`:{code, message, status_code, retryable, agent_run_id};retryable=true 的模型类失败可重试,适配器按 EnvironmentFailure 上抛交 runner 分类。

## 4. 会话生命周期

- Attempt 粒度 = (学生, 题目):**粘性**。同一学生重开同题(即使新幂等键)→ 恢复既有 attempt(restored=true);开另一道题 → 新 attempt/新 conversation,二者可并存。
- **评测跑批含义**:复用学生会污染 attempt 历史;基线夜跑应每场景取池中独立学生(capacity 池 50 个),或经 `values.attempt_action="restart"`(老评测运行时的做法,未在 spike 实测)。
- 终态:交互信封 state ∈ collecting_inputs(教学中)→ completed / failed / cancelled / incomplete;教学回合数较长(六年级题实测 5–7 回合仍在 collecting_inputs,每回合 7–10 s 真实推理),confirm(confirmation 信封)按合同以普通消息应答,短程实测未触及——留给阶段 2 用数据集场景驱动验证。
- 登录态 8h;native SSO 链路测试环境关闭(issue #3),学生 session 路线为 M1 唯一路径。

## 5. 实测安全并发(2 起步)

2 个独立学生并发全流程(开+1 回合):全部成功;延迟劣化明显——open 5.8/10.7 s(单发 ~6.5 s),回合 11.5/13.0 s(单发 6.5–7.3 s),墙钟 24.8 s 对串行 ~28 s,吞吐增益边际。**建议**:基线夜跑从并发 2 起步,以晨间摘要的 p95 与环境失败率实测定参;上调前先看老系统 tutor 链路(单进程推理服务)的容量。每个并发 worker 用独立学生账号与独立 httpx.Client。

## 6. 移交与留桩

- [ ] attempt 复用策略(fresh 学生池 / restart action)——M1 阶段 2 接 runner 时定
- [ ] confirmation 信封应答词表——阶段 2 场景驱动实测
- [ ] GET conversation 的 messages 分页/口径——中断回合落库语义复核
- [ ] test_school 题号歧义与 /health 503——环境侧并行事项(issue #3/#34)
- 实测数字已回填看板 #34:全流程单对话 42–56 s(含 5 回合);安全并发 2 可用(延迟 +60–80%)
