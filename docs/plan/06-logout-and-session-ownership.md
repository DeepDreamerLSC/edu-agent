# 06 真登出与会话归属(设计稿)

状态:**设计稿待审**(2026-09-18;#241-8 存量拆单,来源 #106;零代码——本稿供用户+架构师审,人批后开实现单)。

读法:第 1 节现状盘点(全部结论来自 2026-09-18 main 代码,文内带 文件:行号,文末附验证命令);第 2 节登出语义三问;第 3 节试点场景最小改动面;第 4 节风险与边界;第 5 节落地顺序与验收清单。

## 1. 现状盘点(读代码)

### 1.1 认证流:两条登录通道,一种无状态令牌

| 通道 | 入口 | 令牌 payload | TTL |
|---|---|---|---|
| 合作方 PKCE | `POST /api/openapi/v1/auth/native-codes`(断言 JWT+PKCE,API Key+幂等键)→ `POST /api/auth/native/token`(一次性授权码 90s) | `user_id/tenant_id/role/exp/jti`(identity.py:239-241) | 2h(`TOKEN_TTL_S=7200`) |
| 演示账密 | `POST /api/auth/login`(DEMO_ACCOUNT/DEMO_PASSWORD 环境变量) | `account/role/exp`——**无 jti、无 user_id**(identity.py:125-126) | 2h |

令牌 = 无状态 HMAC:`edu_native_<b64url(payload)>.<b64url(hmac-sha256)>`(identity.py:98-101)。每个对话面/文件面请求经 `_authorized()`(server.py:143-153)→ `verify_token()`:重算签名常数时间比对 + `exp` 检查(identity.py:250-268)——**不查任何服务端状态,无吊销面**。`EDU_AUTH_ENFORCE=0` 可熔断跳过验签(联调应急,默认强制)。

### 1.2 登出现状:假登出(#106 定性)

`POST /api/auth/logout` 恒返回 `{"ok": true}`(server.py:137-140),不读 token、不落状态、不吊销——路由注释原话:「token 为无状态 HMAC,不做吊销名单(最小实现,目标指示)」。后果:**登出后旧 token 在 2h 内仍可调用全部接口**。

**合同缺口**:partner-sso.md §7.1 时序图与第 3/4 条明文「学生主动退出、切换账号或**共享设备换人**时,App 立即调用退出接口」「EduAgent 撤销当前登录会话,后续请求必须重新完成登录流程」——与实现不符(该差距已在 partner-sso.md 头部注记自认 v1 不做;试点共享设备场景把记录债变成实缺陷)。

### 1.3 会话归属模型:不绑任何人

- `Conversation` 数据类 = conversation_id/question_id/attempt_id/skill_session_id/session_version/state/first_question/summary/extras(sessions.py:17-27)——**无 user/owner 字段**;
- SQLite `records` 表 = id/kind/idempotency_key/skill_session_id/kernel_session_id/payload(sqlite.py:50-58)——**无 owner 列**;`files` 表同(file_id/payload);内核侧 LearnerSession 按 session_id 键存,同无归属;
- 服务端访问控制 = **仅令牌有效性**:`send/status/refresh` 一律按路径 ID 直取会话(service.py:448/648/406),从不与令牌身份关联。任何一枚有效 token + 拿到(或从共享设备残留读出)会话 ID,即可:refresh 读首问、status 读状态、**send 冒充续聊**(向他人会话写入学生轮并读回复——回复上下文含对方学生内容);
- ID 形态 `conv_{uuid4.hex[:12]}`(48bit,service.py:350)——盲猜不现实;现实向量 = 共享设备上「上一学生 App 残留的会话 ID/幂等键」。归属过滤 = 纵深防御 + 合同兑现,不是唯一屏障;
- 演示页 `/chat`:token 只存 JS 变量(chat.html:90),刷新即失——本地不留痕是巧合非设计。

### 1.4 幂等键归属:全局命名空间

- open 幂等键全局:`find_by_idempotency(key)` 不分人(sessions.py:35-38;SQLite 唯一索引 `uq_records_idempotency` 全局,sqlite.py:63-66)——**学生 B 重放学生 A 的幂等键,open 幂等路径直接返回 A 的会话**(service.py:301-306);
- 学生轮 `message_idempotency_key` 同为全局缓存键(service.py:458-463);
- 登录面 `Idempotency-Key`(native-codes)在 IdentityService 全局 dict(identity.py:163)——该面属合作方服务器侧(指纹绑定、单合作方),试点无跨人风险,**不动**。

## 2. 设计:登出语义三问

### 2.1 Q1 服务端作废,还是保留只清本地?→ **服务端作废(jti 吊销名单)**

判据:试点 = 共享设备轮用,§7.1「换人立即撤销」是合同义务;只清本地挡不住残留 token 的 2h 窗口。#241-8 行注「无状态 HMAC 吊销」即此义。

**最小实现**:

1. `verify_token` 在签名/exp 通过后查吊销名单:payload 的 `jti` 命中 → False(identity.py:264-266 已 json.loads 出 payload,增一次 set 成员查询,零新增解析);
2. 吊销名单 = **内存 set(锁保护,照 `_code_lock` 模式 identity.py:164)+ SQLite 表 `revoked_tokens(jti TEXT PRIMARY KEY, exp INTEGER)` 落盘**。`build_server` 已注入 `db`(server.py:514-521,healthz 探针同通道):启动时全量加载进内存,**热路径每请求只碰内存,不碰 SQLite**;
3. logout 写序:**先落 SQLite(失败 → 500,不假报 ok——宁可不吊销也不谎报成功),后加内存 set**(内存 add 无失败路径);
4. **演示通道 payload 补 jti**(identity.py:125-126 加 `uuid.uuid4().hex`)——否则演示 token 无法吊销;
5. logout 路由读 `Authorization` 头 → 验签 → 吊销 → `{"ok": true}`。**缺头/验签失败也返回 200 ok:true(幂等空操作)**——客户端视角「登出总是成功」,零破坏;
6. 过期自动清理:`DELETE FROM revoked_tokens WHERE exp < now`,logout 写入时顺手清 + 启动时清一次。表只存登出事件,量级 = 每学生每日个位数,常驻几十行——**吊销状态最长寿命 = token 剩余 TTL,不积累**。

**不做**(YAGNI;合同 v1 明确不支持项):有状态会话对象、refresh_token、网页 Cookie SSO、多合作方、管理端吊销他人 token、登出广播/踢下线。

### 2.2 Q2 共享设备归属隔离的最小实现 → owner 字段 + 请求身份下传 + 越权 404

1. `Conversation` 增 `owner: str = ""`;`records` 表增列 `owner TEXT NOT NULL DEFAULT ''`(新库进 `_SCHEMA`;存量库走一次性迁移脚本 ALTER——PRAGMA user_version 归迁移脚本管,sqlite.py:28-30 同惯例);
2. server 层把「谁在请求」下传:`_authorized()` 从返回 bool 改为返回验签后的 payload(或 None);open/send/status/refresh 调用点带 `owner=payload.user_id`(演示通道 owner=account);
3. service 层过滤:会话的 `owner` 非空且 ≠ 当前请求者 → **404「会话不存在」**(不回 403:不向他人泄露会话存在性——共享设备好奇者探测 ID 一无所获;正常流里合作方 App 不会拿别人的 ID,404 不伤调试);
4. **幂等键改复合归属 `(owner, idempotency_key)`**:全局唯一索引 `uq_records_idempotency` 替换为 `(owner, idempotency_key)` 复合唯一索引——不同学生用同名键各开各的会话;内存版 `_by_idempotency` 同步改复合键;
5. 兼容口径:存量行 `owner=''` = 「前归属纪元」,不限制访问(归属信息本就不存在,不回填;试点若全新库部署则无此档);
6. files 面(上传/读取)同模式可复制,但**不入本单最小面**:file_id 是 open 前的一次性中间件,不构成会话内容面;列为实现单可选项。

### 2.3 Q3 过期自动清理

- 吊销名单:按 exp 自动清理(2.1 第 6 条);
- 会话/文件**数据**保留策略:不在本单。试点周期短(数周)、SQLite 单文件,数据清理是运维件不是安全件;试点后若需要,另拆单(如按 created_at 归档),不在安全件里夹带。

## 3. 试点场景对齐(教室 ~10–50 学生轮用设备)

### 3.1 轮换时序(学生 A 下机 → 学生 B 上机)

```
A 结束:App 调 POST /api/auth/logout(带 A 的 token)
        → 服务端吊销 jti(内存+SQLite),返回 ok:true
        → App 丢弃本地 token/会话列表(客户端义务,合同 §7.1 已约定)
B 上机:App 走 PKCE 静默登录拿 B 的 token
        → A 残留 token 再用:      401(吊销命中)
        → A 残留 conversation_id + B 的 token:404(归属过滤)
        → B 重放 A 的幂等键:      新开 B 自己的会话(复合键)
```

### 3.2 最小改动面(实现单按此开)

| 面 | 文件 | 改动 |
|---|---|---|
| 吊销名单 | `identity.py` | `revoked` set+锁;`revoke(token)`;`verify_token` 增查;demo payload 补 jti |
| logout 路由 | `server.py:137-140` | 读头 → revoke → ok:true(空操作幂等) |
| 身份下传 | `server.py` `_authorized`/`_dispatch`/`do_GET`/`do_PUT` | bool → payload;调用点带 owner |
| 归属过滤 | `service.py` open/send/status/refresh | owner 参数 + 不匹配 404 |
| 存储 | `sessions.py`/`sqlite.py` | Conversation.owner;records.owner 列;复合唯一索引;`revoked_tokens` 表 |
| 合同文档 | `partner-sso.md` | 头部 v1 注记改为「logout 即吊销」;§7.1 时序图落实 |
| 演示页(可选) | `static/chat.html` | 登出按钮(fetch logout + 清 TOKEN) |

预估量级 ~100–150 行含测试,分两个 PR(§5)。

### 3.3 明确不做(YAGNI)

用户/账号系统与角色管理(花名册 = EXTERNAL_STUDENT_MAP 环境变量,加行即扩容);多租户隔离(tenant_id 已在 token,单合作方 v1);设备注册/绑定;「登出所有设备」;会话列表管理 API;本地存储加密;服务端主动踢线。

## 4. 风险与边界

### 4.1 登出后 SSE 行为:无长连可断

`_stream`(server.py:226-246)是**缓冲一次性响应**:先算完整回复,再拼全部 SSE 帧、带 Content-Length 一次写回——不存在长连接。语义:登出瞬间的在途请求正常完成;**下一个请求 401**。无需断连机制,零改动。

### 4.2 幂等重放键的归属

复合键是本设计唯一的既有表结构变更,风险在**索引切换**:旧全局唯一索引 `uq_records_idempotency` 必须与新复合索引同批切换,存量库走迁移脚本;内存/SQLite 双实现同步改,防「一边复合一边全局」的裂脑。登录面 Idempotency-Key 保持全局不动(1.4)。

### 4.3 与既有件无冲突声明

- **#263 listen backlog(已修,CLOSED)**:吊销查询是 O(1) 内存 set 成员判断,不新增连接/线程/队列,与 burst 连接修复正交;
- **#222 extras.guard_events 导出**:吊销是新表;owner 是新增列,旧读写路径默认值兜底,records 既有列语义零变化;
- **#31 原子落盘惯例**:吊销写穿走 SQLite 同连接,无新文件、无新后台任务(不自建租约/心跳/清理 worker——启动+写时顺手清即够);
- **EDU_AUTH_ENFORCE=0**:熔断语义不变——跳过验签 = 跳过吊销检查(联调专用,生产默认强制)。

### 4.4 其他边界

- **重启语义**:HMAC token 本就跨重启有效(只依赖密钥)——吊销名单落 SQLite 后同样跨重启,**重启不再复活已登出 token**(这是选 SQLite 而非纯内存的原因);
- **时钟**:exp 与清理均用 `int(time.time())`,与现有一致,不引入新时钟源;
- **性能**:每请求增一次内存 set 查询;logout 增一次 SQLite 写。教室 50 人量级无感;
- **审计**:登出事件天然留痕于 `revoked_tokens`(jti+exp),配合访问日志可回答「何时登出」;不建独立审计表。

## 5. 落地顺序与验收(供实现单引用)

**PR-1 吊销面**(独立可合,单闭 #106):identity 吊销名单 + logout 路由 + demo jti + partner-sso 文档更新。
验收:登出后旧 token 全接口 401;双次登出均 200;无 token 登出 200;重启后吊销仍生效;`EDU_AUTH_ENFORCE=0` 语义不变;make check 绿。

**PR-2 归属面**(依赖 PR-1 的身份下传):owner 列/字段 + 复合幂等键 + 404 过滤 + 迁移脚本。
验收:跨 owner 读/写/续聊全 404;同 owner 全正常;不同 owner 同幂等键各开各会话;存量 `owner=''` 行可续;内存/SQLite 双实现行为一致;make check 绿。

——本稿零代码;实现单凭人批后的本稿开工,PR 只开不合,合并键在人。

## 附:现状盘点验证命令(审查者可跑)

```bash
sed -n '137,140p' edu_agent/api/server.py                 # 假登出路由(注释原话)
sed -n '250,268p' edu_agent/api/identity.py               # verify_token:重算+exp,无吊销
sed -n '17,27p'   edu_agent/store/sessions.py             # Conversation 无 owner 字段
sed -n '50,66p'   edu_agent/store/sqlite.py               # records 表无 owner 列;全局唯一索引
sed -n '301,306p' edu_agent/api/service.py                # 幂等键全局:同键返回既有会话
sed -n '226,246p' edu_agent/api/server.py                 # SSE = 缓冲一次性响应
sed -n '7,10p'    docs/partner/partner-sso.md             # v1 不做吊销的自认注记
grep -n "共享设备" docs/partner/partner-sso.md            # §7.1 合同义务
```
