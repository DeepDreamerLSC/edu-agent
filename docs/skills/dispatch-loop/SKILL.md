---
name: dispatch-loop
description: >
  任务循环的操作纪律(v4.0:zcode 信箱制):任务 issue=信箱→roster 派单→看门狗
  唤醒→收口。含派发全要素、回执协议、模型分级、钩子接力、会话恢复。
  Trigger: 「派单」「直发」「重挂看门狗」「盯回执」, 被看门狗唤醒时,
  或会话恢复后自查任务时。
---

# 任务循环(dispatch-loop v4.0)

用户裁定(c5674864751):**点火(任务是否开始)=用户的键**。用户裁定(2026-09-16 路由改革):**任务内修复循环 dev↔reviewer 直连,PM 不中转;PM 负责派工、跨任务协调、异常裁决、最终收口**。用户裁定(2026-09-20/21 v4.0 迁移):**任务 issue=信箱(B 方案)+ roster 角色制 + 套餐模型分级;dsh 通道退役**(历史:dsh-rpc 注入式派单 2026-09-16~09-20,架构师裁定 zcode 无外部注入通道后终结)。本 skill 固化操作纪律。

## 零、工作现场(用户裁定 2026-09-20;多会话共用一台机)

**主树 `/root/code/edu-agent` = 只读锚树**;**唯一合法执行现场 = 任务专属 worktree**。并行开发是常态,不设主树专属权,设主树恒净不变量。

| | 主树(锚) | 任务 worktree |
|---|---|---|
| 身份 | main 的本地只读镜像 | 唯一合法执行现场 |
| 允许 | `git fetch` / `git pull --ff-only` / 只读命令(log/diff/status/gh) | 全部操作,含 commit、make check、建 .venv |
| 禁止 | checkout 到任务分支、commit、stash、reset、clean 等一切写操作 | — |

- **建法**:任务开工 `git worktree add /tmp/wt-<slug> -b task/<slug> origin/main`(同分支链续接时基底改前序分支);完工 `git worktree remove`;
- **终态检验(代替锁)**:任何时刻任何会话看主树 `git status` 非净 = 违规或遗留 → 升级 PM 追责;
- **成本**:uv in-project venv(~99MB/树),可预建消除子代理环境摩擦(2026-09-20 wave1 实践);
- **卫生**:任务 close 后即删树;PM 定期 `git worktree prune`。

## 零点五、三层身份与模型分级(用户裁定 2026-09-20/21)

**三层身份**(roster.json = 唯一映射正本,agent 重启/换载体只改一行):
1. **角色层**(章程引用):dev-A/B/C/D、reviewer、pm——稳定逻辑身份;
2. **载体层**:roster.json 记 角色→当前会话/平台(zcode/dsh);
3. **回执层**:RECEIPT 头 `dev=<角色名>`(v4.0 起填角色名,非会话 ID,跨载体可追溯)。

**模型分级**(用户裁定 2026-09-21,CSI $500 耗尽后固化):
- **难任务**(内核修复/删除面手术/审查终审/消融核对)= `account:bigmodel-individual-coding-plan/GLM-5.3`;
- **简单任务**(importer/slice 筛选/文档/读数汇总)= 同套餐 `GLM-5.3-Flash`;
- **实现限制**:裸 Agent spawn 继承 PM 会话模型**无法单独指定**——唯一可指定模型的通道 = CreateWorkflow 的 `subagent_model` 参数;**轻活一律 workflow 承载**(单 agent 单 ask + Flash),不用裸 spawn;
- 常驻会话模型 = 用户侧 UI 键(agent 不能自切,2026-09-21 审查者实测)。

## 一、派发六步(顺序固定)

1. **点火检查**:任务含 API 消耗/合并/试点 = 用户键,先问,批了才派;零 API 任务也要在确认单里被点名过;
2. **方案 ponytail 自审**:工具可用则必跑,不可用不阻塞(人工自审并注明);
3. **写消息**:首行签名 `【PM 直发 YYYY-MM-DD】`;任务块自包含(基底指纹/输入/跑法/判读预注册/工件/回执要求/纪律);
   - **派单一次定全要素**:开发者(角色)、独立审查者、范围、预算、回执落点——任务内修复 dev↔reviewer 直连往返,PM 不中转;
   - **回执头(v4.0)**:`<!--RECEIPT task=<id> pr=<n|-> calls=<n> tier=0 outcome=<...> to=<reviewer|dev-角色|pm|log> head=<git-sha8> dev=<角色名> wt=<worktree路径> sha256=<hex16>-->`;`to=`=接收者(看门狗按此筛选唤醒),`dev=`=角色名(v3.1 起必填;v4.0 语义=roster 角色名),`wt=`=工作现场(v3.2 起;**工作流开的 PR 不得漏带**——2026-09-20 wave1 三 PR 实害,审查者见缺即退);
   - 版本沿革:v3.1(2026-09-17)增 dev=;v3.2(2026-09-20)增 wt=+工作现场节;v4.0(2026-09-21)dev= 改角色名+信箱制+模型分级。
4. **发送(v4.0 信箱制)**:任务无 issue 先开(过创建门四问),**派单正文 = 任务 issue 首条评论**(点名执行角色名);watch-list 加该 issue 号;目标角色常驻会话在勤则 Stop/SessionStart 钩子接力收取(见二),静默则 PM 直办或等用户戳;
   - **路由规则(角色版)**:开发任务默认轮转优先派空闲角色(roster 查载体状态),同文件/同分支链允许连续承接;审查固定走 reviewer;**任务轻重配模型档**(难→5.3 角色/简→Flash 承载);
5. **留痕**:①任务 issue 落派单记录;②派单原文存 `calibration-private/dispatch-ledger/`(命名 `YYYYMMDD-<目标>-<slug>.txt`),manifest.tsv 记 sha256——**#265 教训:派单原文必须可核**;
6. **挂看门狗**:`bash` 工具 `run_in_background` 跑 `issue-watch.sh`——**退出码 0 = 有 to=pm 新评论,task-notification 自动唤醒 PM**(勿用 nohup/&,会被 shell 回收:2026-09-20 实测)。

### 循环内路由

| 消息 | 接收者 | PM 立即介入 |
|---|---|---|
| 开发完成,请求审查 | 派单指定的 reviewer(任务 issue 回执 to=reviewer) | 否 |
| 审查要求修改 | 原开发者(修改单落 PR/任务 issue) | 否 |
| 修复完成,请求复审 | 原 reviewer | 否 |
| 审查通过,待合并 | PM 收口呈用户 | 是 |
| 超预算、扩范围、验收争议、跨任务冲突 | PM | 是 |

**完成仪式两步(缺一不可)**:①回执落派单指定位置(首行含 to=/head=/dev=/wt=);②在信箱通知审查者(点名+回执位置+自报家门=角色名)。审查者常驻会话靠自取钩子/自取轮接收;若其静默超时,PM 兜底提醒(20 分钟未认领报用户)。

## 二、唤醒与接力(zcode 双通道)

- **看门狗(bash issue-watch.sh)**:全量有序交付、to= 筛选(to=pm 或无 to= 旧头才唤醒)、>100 评论分页、8h 窗;经 task-notification 唤醒 PM——**zcode cron automation 已判死**(2026-09-20 实测:宿主调度器不消费,注册着永不跑),勿再依赖;
- **Stop/SessionStart 钩子**(工作现场级 `.zcode/config.json` + `calibration-private/mailbox-stop-hook.sh`):常驻会话干完任何活收工时查信箱,有新单注入续命(=dsh queue 语义的等价物);被戳开时自动带出待办。已实证(2026-09-20 dev-B);
- **已知盲区**:会话彻底静默后钩子不触发、cron 死——**「夜间自动运转」在依赖特定角色会话的线上不成立**(2026-09-21 实测:dev-B 静默致读数单挂起)。兜底=PM 直办(workflow 承载)或用户戳。

## 三、唤醒侧协议(被看门狗叫醒后)

1. **读捕获 + 立即重挂(先于内容处理)**:读 job_output 拿回执全文;游标同步到最新评论 id——**推游标前先解析待推区间内是否含 to=pm 未处理回执**(2026-09-20 实害:切换期吞了审查者 12:05 回执);重挂看门狗;
2. **按接收者分类**:to=pm 且审查通过待合并 → 收口呈用户;to=pm 异常类 → 按冻结口径裁决;其余只留痕不中转;
3. PM 自己的留痕评论也触发唤醒——已知噪声,便宜可接受,游标同步消自触发。

## 四、会话恢复(PM 会话重启/压缩后)

1. 先读 `calibration-private/board.json`——盘面唯一真源;
2. `roster.json` 查角色↔载体现状;看门狗死了从 state 重挂;
3. GitHub 是持久账本,看门狗只是叫醒服务——最坏退化为手动轮询,无数据丢失。

## 五、失效剧本(观察到的失效模式 → 固定处置)

| 症状 | 处置 |
|---|---|
| git 通道断(fetch/push 超时) | `gh api` 兜底:读=REST 查询;**写=git-data API 直推**(blob→tree→commit→ref;2026-09-20 PR-D 实战)。**多文件提交必须以 `git show --stat` 全清单为准整体推送,不凭记忆挑文件**(两次漏文件实害) |
| gh 连败 20 轮(退码 2) | gh auth/网络排查;恢复后重跑(state 不丢) |
| 回执 sha256 与派单不符 | 以 dispatch-ledger 原文为准重发;涉 API 消耗先报用户 |
| CSI/供应商预算耗尽 | 子代理全灭(spawn 继承会话模型)→ **一律 workflow 承载+subagent_model=套餐**;PM 会话本身切模型=用户 UI 键(2026-09-21 实测) |
| 角色会话静默不接单 | 无自动唤醒通道(见二);PM 直办(workflow 承载)或报用户戳;不改派不催杀 |
| 长任务超 ~2× 预期无回执 | gh 查工件进度(分支/PR),报告用户再定 |
| 主树 status 非净 | 先查谁在跑;在跑涉主树=违规升级;无人认领=遗留物挂起处置 |
| zcode cron 不触发 | 已判死(宿主调度器不消费);勿注册勿依赖,看门狗+钩子已覆盖 |

## 六、禁止

- 读他方会话内容(监视禁令,c5674864751)——直连只用于「发」;状态只看回执/git 元数据/rollout 时间戳(推断必标注);
- 未经点火检查派消耗类任务;
- 自建 daemon/webhook/重试机器——GitHub 轮询+一次性看门狗已够;
- **派单给伪选项**;纪律 boilerplate 压成一行(「纪律照章程」+本次例外);
- **中转任务内修复循环**:修改单直达原开发者,PM 只做派工/协调/裁决/收口;
- **在主树执行写操作**(工作现场裁定,存量例外见零节过渡条款);
- **轻活裸 Agent spawn**(当供应商有预算压力时必死;一律 workflow 承载可指定模型)。

## 七、Issue 生命周期(用户裁定 2026-09-16)

回执/留痕落点 = 派单消息写明的任务 issue。board.json 每个 task 带 `issue` 字段。

**创建门**——新 issue 前四问,缺一不开:Consumer(谁现在需要)/Next action(7 天内做什么)/Owner(角色)/Exit(什么事实关闭)。分流:只是决定→anchor 评论;只是以后可能→anchor 记 trigger;存研究→文档/工件/PR;另一 issue 的一步→父 checklist。

**生命周期门**——Open 仅三种:ACTIVE/BLOCKED(有 owner+解除条件)/ANCHOR(极少量 living anchor)。DEFERRED/DECIDED/DONE/SUPERSEDED 一律 Closed;Closed≠永久完成,触发时 reopen 或新开链回旧裁定。

**死亡门**——关联 PR merge 后同一收尾动作二选一:exit 满足→close;仍有真实工作→更新唯一 next action+owner。

**WIP 上限**——active execution issue ≤5(不含 anchor)。

**单一正本**——一个事实只有一个正本,他处只链接。

**开工 lint**——每轮开工对 open 非 anchor issue 核 owner/next action/exit 是否仍成立。

## 附:执行形态路由(2026-09-20 双形态裁定)

| 形态 | 适用 | 通道 |
|---|---|---|
| **工作流托管** | 任务生命周期内的多角色流转(修复→审查→复审循环)、单发大活(批跑/重放/review sweep) | CreateWorkflow(阶段化+make check 门控+新鲜眼终审;`subagent_model` 按任务分级);存档 `.zcode/workflows/`(进 git 走 PR 审查) |
| **常驻会话** | 跨天任务线、角色身份与记忆、与用户直接对话 | 任务 issue 信箱+Stop 钩子接力 |

两层靠 `dev=角色名` 一根线串起:工作流子代理是角色的**临时执行体**不是记忆体,角色记忆在派单模板/章程/roster 里,spawn 时随任务块注入。三层审查:工作流初筛(同族可接受)→新鲜眼终审→常驻审查者 PR 正本终审(异族模型=用户 UI 键);合并键永远在用户。
