---
name: dispatch-loop
description: >
  任务内直连循环的操作纪律:派单→看门狗→唤醒核验→重挂。含 dsh 会话 API
  派发、issue 看门狗、点火键检查、会话恢复重挂。Trigger: 「派单」「直发」
  「重挂看门狗」「盯回执」, 被看门狗唤醒时, 或会话恢复后自查任务时。
---

# 任务内直连循环(dispatch-loop)

用户裁定(c5674864751):**点火(任务是否开始)=用户的键;任务内循环(PM→dev→review→dev)=PM 直连驱动**。本 skill 固化操作纪律。

## 一、派发六步(顺序固定)

1. **点火检查**:任务含 API 消耗/合并/试点 = 用户键,先问(`ask_user_question`),批了才派;零 API 任务也要在「下一波确认单」里被点名确认过;
2. **方案 ponytail 自审**(默认执行):派单前对方案跑一次 `ponytail-review`——与 AGENTS.md 同档:工具可用则必跑,**不可用不阻塞**(按最小修改原则人工自审并注明);发现的问题先修再派;
3. **写消息**:首行签名 `【PM <session-id> 直发 YYYY-MM-DD】`;任务块自包含(基底指纹/输入/跑法/判读预注册/工件/回执要求/纪律);按「先快后长」排序逐条发;
   - **末行摘要**:`【摘要】sha256=<hex16>`(对本行之前全文计算,追加在末行)——防「消息在途损坏/截断」;
   - **回执要求写进派单**:回执首行加机器可读头 `<!--RECEIPT task=<id> pr=<n|-> calls=<n> tier=<flash|pro|0> outcome=<...> sha256=<hex16>-->`(渲染不可见),并回显派单摘要值;
4. **发送**:`python3 "$HOME/calibration-private/dsh-rpc.py" send <会话ID子串> queue "$(cat 消息文件)"`;
   - **坑1**:会话 id 带 `session-` 前缀,用子串匹配(脚本已改);
   - **坑2**:`steer` 会打断对方在跑轮,默认 `queue`(等本轮完自动接下一条);
   - **坑3**:目标会话 run 状态先查 `dsh-rpc.py list`,确认存在;
   - **路由规则(用户裁定 2026-09-16)**:开发任务**默认轮转**——优先派空闲开发者
     (D=e4244967 / A=aacf38e4 / B=788011ea / C=e547e307),不逮一个薅;
     仅当新任务与前序任务**同文件/同分支链**时允许同一开发者连续承接
     (如 P1→P2 同动 kernel_subject.py);审查固定走 659c6ae9;
5. **留痕**:①#253(或对应 issue)落派单记录(派给谁/内容摘要/用户批准范围);②消息逐字存入 `calibration-private/dispatch-ledger/`(命名 `YYYYMMDD-<目标>-<slug>.txt`),manifest.tsv 记 sha256/留痕评论号/状态——**#265 教训:派单原文必须可核,不留 /tmp**;
6. **挂看门狗**:`bash` 工具 `run_in_background` 跑 `issue-watch.sh`(见下),**勿用 nohup**(不会唤醒);派单的回执 issue 不在 watch-list 里就往 `issue-watch.issues` 加一行(运行中的狗下轮自动纳入,免杀狗)。

## 二、看门狗

脚本与 SKILL.md 同仓(`docs/skills/dispatch-loop/`),运行时状态在 `calibration-private/`:
- `issue-watch.sh`:状态文件 `issue-watch.state` 记每 issue 的 last_comment_id——**免手填阈值**(旧版手填是事故源);watch-list `issue-watch.issues` **每轮重读**(增删被盯 issue 免杀狗);gh 失败计数(连续 20 轮退出码 2,不吞错误);8h 超时退出码 1;**本轮收集全部新评论后**退出码 0 才唤醒(一条唤醒覆盖多 issue 多条评论,不漏后续回执);
- `d-state-watch.sh <会话子串>`(缺省 D):只读盯 running 标志,idle ≥4min 报警(回合截断检测);审查者或任何干活会话都可盯;
- 脚本内路径用 `$HOME/calibration-private/`(不硬编码绝对根路径);状态文件名只在脚本里定义一处;
- 已知噪声:PM 自己的留痕评论也触发唤醒——可接受,便宜;
- **重挂 = 直接再跑一次脚本**(自动读状态),禁止手动改阈值。

## 三、唤醒侧协议(被看门狗叫醒后)

1. **读回执 + 立即重挂看门狗(不分拆,先做这条再处理内容)**:
   - 读 `job_output` 拿到回执全文(评论号点验);
   - 把 `issue-watch.state` 里该 issue 的 id 同步到最新评论 id(避免新狗自触发);
   - 用 bash `run_in_background` 重挂 `issue-watch.sh`(第二节);
   —— **看门狗退出是唤醒信号,不是终点;重挂必须在同一轮内先完成**,否则下一波回执漏接(教训:曾因把重挂拖到列表末尾而漏过 #285 回执);
2. **按冻结口径核验**(判卷/判读标准在派单或 #253 冻结评论里,跑后不改);
3. 裁定:收编/驳回/追问——追问可直发(循环内);
4. 留痕裁定于对应 issue;
5. **审查自动派发**:回执关联的 OPEN PR 若未派过审查 → 打包一单派审查者
   (659c6ae9,queue 模式):标准审查提示词(只验证不产码/复现清单/Q0 抽验
   必做/可合不可合+理由);已派记录入 `calibration-private/review-dispatched.txt`
   防重;审查属任务内循环(dev→review→dev),零 API,无需点火;合并键仍在人;
   —— 后续自己在被盯 issue 发评论后,再同步一次 `issue-watch.state` 到该评论 id(避免自触发);
6. **点火级/红灯才报用户**(候选升级、基线落定、门红诊断);其余自动消化。

## 四、会话恢复(我的会话重启/压缩后)

1. **先读 `calibration-private/board.json`**——PM 盘面唯一真源(任务/状态/待按键/预算/文件索引),不依赖记忆;
2. `job_list` 查看门狗是否还活;死了 → issue-watch.sh 从 state 重挂,d-state-watch.sh 带会话子串重挂(状态不丢);
3. 对方会话可能已把回执落 GitHub——GitHub 是持久账本,看门狗只是叫醒服务,**最坏退化为手动轮询,无数据丢失**;
4. 恢复后把 board.json 的 `updated` 刷新,任务状态对齐现状。

## 五、失效剧本(观察到的失效模式 → 固定处置)

| 症状 | 处置 |
|---|---|
| 看门狗退码 2(gh 连败 20 轮) | gh auth/网络排查;期间人工 `gh api` 兜底;恢复后直接重跑 issue-watch.sh(state 不丢) |
| d-state-watch 报 idle≥4min 无回执 | 核对应 issue 回执在否:在=误报,重挂;缺=回合疑似截断,向其 queue「继续」,或按用户指示改派空闲会话 |
| 回执 sha256 与派单不符 | 消息可能在途损坏:以 dispatch-ledger 原文为准重发该单;涉 API 消耗的先报用户 |
| 长任务超 ~2× 预期无回执 | `dsh-rpc.py list` 查活 + 工件目录查进度(分支/PR),报告用户再定——不催不杀,只报事实 |
| 我的会话重启/压缩 | 见第四节;board.json 是真源 |
| dsh 升级后 session API 疑似失效 | 先 `dsh-rpc.py probe`(空内容,零副作用)验通道,再真派——逆向 API 无契约保证 |
| git 通道断(fetch 超时) | `gh api` 兜底读远端真值(既有做法) |

## 六、禁止

- 读他方会话内容(监视禁令,c5674864751)——直连只用于「发」;
- 未经点火检查派消耗类任务;
- `steer` 打断对方在跑轮(除非用户明示);
- 自建 daemon/webhook/重试机器——GitHub 轮询 + 一次性看门狗已够,复杂度预算花在刀刃上;
- **派单给伪选项**:编号选项必须是接收者可执行的;禁止项放纪律段一句带过,不给编号(避免假决策);
- **纪律 boilerplate 重复**:接收者有 AGENTS.md,纪律条款不重抄;压成"纪律照章程"一行,仅列本次例外。

## 七、Issue 路由(粗粒度任务)

派单时留痕到对应 issue,不再默认 #253。

| 任务 | Issue |
|---|---|
| 人审标定集(judge 外部有效性) | #253 |
| GEPA 执行序(①②③ 三键) | #284 |
| ⑦ 门(教师 promotion gate) | #285 |
| RM 试金石(T1 候选对) | #286 |
| PM 运营日志(派发/收编/会话切换) | #287 |

**规则**:
- 派单时根据任务性质选择对应 issue
- board.json 每个 task 加 `issue` 字段指向对应 issue
- 看门狗盯所有 7 个 issue(253/263/254/284/285/286/287)
