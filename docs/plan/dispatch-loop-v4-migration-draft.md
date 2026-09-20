# dispatch-loop v4.0 草案 —— dsh → zcode 迁移(B 方案:GitHub 信箱 + cron 分发)

状态:草案(2026-09-20,PM 拟)。待用户裁定后落 SKILL.md 正本(走 PR)。
前置裁定:用户已定 B 方案(独立 zcode 会话 + GitHub 信箱 + cron 分发,非 PM 中心化子代理);
用户已初始化 zcode 侧 agent(开发者 B = sess_1188d1ad、审查者 = sess_d2ae44fb,均已活跃)。
关联:PR #380(工作现场节,v3.2)——本草案叠加其上,不冲突。

## 一、迁移不改的(原则:内容协议与承载工具解耦)

| 层 | 不动理由 |
|---|---|
| GitHub 回执协议(RECEIPT 头、to=/dev=/wt=/sha256) | 纯内容协议,与承载工具零耦合 |
| 共享账本(board.json / dispatch-ledger / review-dispatched / issue-watch.issues) | 在 ~/calibration-private/,不绑 dsh |
| issue-watch.sh 轮询内核(gh api + to= 解析 + 游标) | 只认 GitHub,不知 dsh 存在 |
| 角色章程(pm.md / reviewer.md)权责边界 | 只需换措辞里的会话指称 |
| 监视禁令、点火键、审查独立性、直连循环语义 | 迁移不碰价值观层 |

## 二、核心架构:任务 issue 信箱 + 唤醒 + 分发(T1 修订,用户裁定 2026-09-20)

```
PM 派单 ──建/复用──▶ 任务 issue(每个任务一条线 = 该任务的信箱)
                         │
PM cron(*/15)───────────┤ 读 watch-list 增量(游标+to= 解析,复用 issue-watch 内核)
                         │
    ┌────────────────────┼────────────────┐
    ▼                    ▼                ▼
 to=pm               to=reviewer       to=dev-*
(处理/呈报用户)      (审查者 */5 自取)  (该 dev */5 自取;
                                        to=log 只记不动)
```

**信箱模型(用户裁定 T1,推翻初稿的固定信箱)**:任务 issue = 该任务的信箱。派单/回执/修改单/审查结论落对应任务 issue 或 PR 评论,不设全局固定 issue。理由:每任务一条线直观可追;复用 SKILL.md 第七节生命周期门(创建四问/WIP≤5/死亡门),信箱自带流控;board.json 的 task.issue 字段本就是线索正本。#381 降格为迁移协调 anchor(上岗/公告/双栈状态)。

**与 dsh 版的本质差异**:dsh 是「推」(PM 直接注入对方会话队列);zcode 版是「拉」(消息落 GitHub,各角色按 cron 节奏自取)。GitHub 本来就是持久账本,信箱化只是把「叫醒服务」从 dsh 换成 cron/轮询。

## 三、角色与 agent 解耦(本草案的骨架)

**现状问题**:SKILL.md 路由规则硬编码 5 个 dsh 会话 ID(D=e4244967/A=aacf38e4/B=788011ea/C=e547e307/审查=659c6ae9);board.json 37 处会话 ID 引用。agent 死亡/重启/换工具,章程就得改。

**v4.0 做法:三层身份,只认角色名,不认会话 ID**

1. **角色层(章程引用的)**:`dev-D / dev-A / dev-B / dev-C / reviewer`——稳定的逻辑身份,写进 SKILL.md 路由规则;
2. **载体层(运行时可换的)**:`roster.json`(calibration-private,与 board.json 同级)维护 `角色名 → 当前载体` 映射:
   ```json
   {
     "dev-B":  {"platform": "zcode", "session": "sess_1188d1ad", "note": "2026-09-20 由 dsh 788011ea 迁入"},
     "reviewer": {"platform": "zcode", "session": "sess_d2ae44fb", "note": "2026-09-20 由 dsh 659c6ae9 迁入"},
     "dev-D":  {"platform": "dsh", "session": "e4244967", "status": "退役中"}
   }
   ```
   agent 重启/更换只改 roster.json 一行,章程与 board 不动;
3. **回执层(自报家门,已有)**:RECEIPT 头 `dev=` 字段从「dsh 会话 ID」改为「角色名」(如 `dev=dev-B`)——共用 GitHub 账号下区分提交者的机制不变,但标识变成稳定角色名,日志可跨载体追溯。

**交付物增加一件**:每个 zcode agent 会话首次上岗时读 `roster.json` 确认自己的角色名,之后的回执/自报家门全用角色名。

## 四、逐件变更清单

| # | 件 | 变更 | 深度 |
|---|---|---|---|
| 1 | 信令通道 | `dsh-rpc.py send` 退役;派单 = GitHub issue 评论(gh pr comment / gh issue comment),消息体 = 现派单模板原样(签名行+摘要行不变) | 重 |
| 2 | 看门狗唤醒层 | bash 后台 issue-watch.sh → **zcode CronCreate**(`*/15 * * * *`,prompt=「读游标增量→按 to= 分发→to=pm 处理」);「勿用 nohup」「重挂先于内容」两族坑消失 | 重 |
| 3 | d-state-watch.sh | 退役(zcode 无 running 标志可查);其职责并入 cron:回执 issue 超时无新评论 → 提醒 PM「仍欠回执且超约定时间」(脚本注释里本就预告的方向) | 重 |
| 4 | SKILL.md 派发六步 | 第 3 步「发送」改写:queue/steer 概念删除(拉模式下无「打断在跑轮」问题,steer 禁令随之消亡);坑 1/2/3 重写;路由规则改角色名 | 中 |
| 5 | roster.json(新) | 角色名→载体映射,agent 上岗首读 | 新增 |
| 6 | board.json | 37 处会话 ID → 角色名(一次性重写,历史条目原样保留旧 ID 加注) | 轻 |
| 7 | progress-html/SKILL.md | `cp 到 ~/.dsh/skills/` → zcode 技能装载路径 | 轻 |
| 8 | pm.md / reviewer.md | 措辞:「会话」→「agent 会话(见 roster.json)」;监视禁令的指向物更新 | 轻 |
| 9 | dsh-rpc.py | 归档至 calibration-private/archive/(不删,双栈期 dsh 侧开发者还在用) | 轻 |

## 五、双栈过渡(不能一刀切)

1. **T0(裁定日)**:roster.json 建立;B/审查者已在 zcode 侧活跃 → 标记 zcode 载体;D/A/C 仍在 dsh → 保持 dsh 载体;
2. **双栈期**:派单按 roster.json 的 platform 字段选通道——zcode 载体走 GitHub 信箱(自己轮询),dsh 载体仍走 dsh-rpc 推送;看门狗两端并存(cron 盯 zcode 侧,issue-watch.sh 盯 dsh 侧——两者都是读 GitHub,无冲突);
3. **逐个迁移**:每个 agent 迁移 = roster.json 改一行 + 一次上岗验证(回执走通即可);
4. **退役**:全部角色 zcode 化后,SKILL.md 落 v4.0 正本(一次 PR),dsh-rpc.py 归档,issue-watch.sh 的 PM 唤醒职责移交 cron。

## 六、开放问题(裁定记录 2026-09-20)

1. **cron 的宿主会话**:**已裁:挂 PM 会话**(CronCreate 持久于 workspace,PM 会话重启不丢);
2. **开发者自取节奏**:**已裁:A 选项,各角色会话内自建 */5 自取 cron**(每会话限一条 cron,须各角色自行创建;PM 分发器带 20 分钟未认领兜底报告);
3. **queue 语义的损失**:拉模式下自然消失(消息=issue 评论,永不丢,晚读无害)——按简化接受,无需裁定;
4. **审查者没有看门狗**:**已裁:审查者也挂 */5 自取 cron**,v3.x「不 queue 它就不知道」的坑消失。

**追加裁定(T1)**:信箱=任务 issue,非固定 issue——每任务一条线,复用生命周期门;#381 为迁移 anchor。

## 七、风险与缓解

- **风险**:cron 挂的会话如果模型侧改动(如 skill 失效),看门狗静默死亡 → **缓解**:cron 每次跑本身就是心跳,GetWorkflowRun/运行记录可查;另留 issue-watch.sh 兜底一条(低频,*/60);
- **风险**:GitHub 信箱让消息从「私队列」变「公开评论」→ **缓解**:派单内容本来就要留痕 issue,这不是新暴露;但注意 dispatch-ledger 仍为逐字正本(现状不变);
- **风险**:roster.json 单点 → **缓解**:它在 calibration-private 与 board.json 同域,同备份策略。
