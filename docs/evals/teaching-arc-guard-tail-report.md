# 护栏尾单两件(③ 代喂接 student_evidence / ④ 补词)评测报告

> 任务来源:#157 PM 复核(裁定 1)+ #148 §5 实测 + #146 登记;派单 2026-09-10,同日按评审意见 rebase 瘦身、评测转 nightly。
> **范围变更**:原派单三件中的 ①(允许集末值边界)与 #158 重复且取法相反(#158 按值剥离
> `steps − _answer_numbers`,优于派单草图的按位置 `steps[:-1]`——题库 16/10 阶梯答案 3/5
> 时按位置会误伤末级中间值),已随 rebase 撤出;①② 现均经 #157/#158 合入 main。
> 本 PR 只留 ③④(检测层,main 仍空缺),单变量 = post-#157 main(`61eb75a`,内容等价
> 于 main 头 `7b75a670`)+ ③④ 两处改动。

## 0. 口径与效度自述(读报告不读代码)

- **证据版本(r1)**:post-#156 main(`5236c8e`)× ①③④ 的两帧(68 transcript × 2,同晚同
  配置,manifest 自证帧身份),工件随 force-push 留存于 **PR #161 时间线(`7c7984b`)**。
  对 ③ 的有效性:撤出的 ① 只动 `_drift_sources` 数字允许集,**不触碰 feeds_method 路径**
  (词表/命中/替换逻辑零交集),故 r1 的误伤数据对 ③ 成立;**误伤 4→0(逐句口径)已经评审
  独立复算吻合**(逐事件口径 3→0,两口径见下)。
- **计数双口径**:逐事件 = feeds_method 替换事件数(guard_events);逐句 = 被换下的 tutor
  原句条数(同一句在两重复各计一次时,逐句≥逐事件)。r1:before 逐句 4 / 逐事件 3;
  after 两口径均 0。
- **指标口径**:四指标 = #143 冻结判据(judge 盲评 + 本地阈值算术),一字未改;误伤/真代喂
  = 从 `guard_events`(feeds_method 事件)按「命中词是否已被学生(截至当轮,含当轮)说出」
  逐条分类,脚本化重算(§4)。
- **护栏模式**:无答案(评测侧 KernelSubject 不传参考答案,与夜评同口径)。
- **后续(r2,转 nightly)**:post-#157 main 单变量重测由 nightly 承担(评审决定,2026-09-10),
  复现命令与观察点在 §4——r1 的 ① 混合实验形态不再重跑。

## 1. ③ `_feeds_method` 接 `student_evidence`

**改动**:`_feeds_method(text)` → `_feeds_method_hits(text, student_evidence)`:仅「学生尚未
说出」的方法词才算代喂;`student_evidence` 复用 `_GuardContext` 既有字段(含当轮学生消息,
与泄露护栏同源,零新增模型调用、零新增埋点类型)。判定不放宽、词表不删;埋点 `rule_ids`
精确到未说词。

**验收(r1,post-#156 基线)**:

| 量 | before | after | 说明 |
|---|---|---|---|
| 误伤·逐句 | **4** | **0** | 全部 R/fraction:学生 S5 复讲「先通分…」,教师复述定名被整条换成请讲引导 |
| 误伤·逐事件 | 3 | 0 | 同源数据逐事件口径 |
| 真代喂(存在未说词) | 9 | 10 | 拦截保留;增量来自会话样本差,非放宽 |
| 合规定名可见性 | R·method_name 语料 10 → **14** | ③ 放行的「先通分」类确认句原文流过、成为语料行(before 被换下不可见)——③ 在语料层的直接可见效果 |
| 四指标 | F 逐项相同;R rs +1(恰消 before 两重复分歧);无重生成级联 | P 双向翻转有 judge 证据(「教师未明确要求复讲」),after P 0 次 feeds 替换,属会话路径差 |

**专测**(随 PR):学生已说「通分」→ 原文放行;混合命中(已说「通分」+ 未说「假设法」)
→ 只记未说词 `rule_ids=["假设法"]`;④ 词触发。

**残余命中逐条定性(r1 after,10 次全部「底乘高」)**:

| # | 口径/场景 | 学生已说 | 教师句 | 定性 |
|---|---|---|---|---|
| 1-6 | L/triangle | 「我还是觉得面积就是60平方厘米」(卡在错答) | 「这其实是底乘高的结果,但三角形面积确实要除以2」 | **真代喂(规则内)**:学生卡壳,教师先行点名方法——弧线要求他先讲 |
| 7-10 | R/triangle | S5 已完整复讲「两个三角形拼成底10高6的平行四边形…再除以2等于30」 | 「那平行四边形面积是底乘高,也就是10×6=60」 | **词面不同档**:内容已讲、术语未名(拼平行四边形=底×高的实质)——按词面判仍拦(判定不放宽,派单红线);实质是否属「讲完可定名」,属词表/语义层后续裁定,本单不动 |

before 的 P·假设法 4 次同属词面不同档(学生「可以先假设8只全是鸡」做而未名),r1 after 样本
未复现,登记备查。

## 2. ④ 补词「面积公式」

**改动**:`_METHOD_TOKENS` 增补一个词(14→15);不动 `OPEN_SCHEMA`、不整体对齐两套词表、
不加事后脱敏(#148 §6.1 实测 1/4 破损)。**证据**:#148 §5 该词从阶梯揭示句原样漏出(实测
依据);专测 `test_area_formula_token_swapped`(学生未说 → 换请讲引导 + 埋点含「面积公式」)
锁定行为;r1 批跑样本未出现该词(漏出句是当次模型路径产物)——词已在网内,由专测锁定。

## 3. 明确不做(派单红线,全部保持)

② 卡壳词表(出处见 §5);不动评测协议/数据集/judge 判据/`baselines/`/P-F-R;不动首问措辞;
不读 `minimum_student_turns`;无模型自报字段;无解析脱敏;③ 判定不放宽、词表不删。

## 4. r2(nightly)复现命令与观察点

```bash
# r2 before 帧(post-#157 main=61eb75a 检出的工作树里;--base-sha 显式给 61eb75a,
# 否则若本地 origin/main 陈旧会把 kernel_diff 算错):
.venv/bin/python scripts/arc_eval_fix112_frames.py --frame before --calibers F,R,L,P \
    --base-sha 61eb75a --out edu_agent/evals/artifacts/teaching-arc-guard-tail-r2
# r2 after 帧(本 PR 合入后的 main 工作树里):
.venv/bin/python scripts/arc_eval_fix112_frames.py --frame after --calibers F,R,L,P \
    --base-sha 61eb75a --out edu_agent/evals/artifacts/teaching-arc-guard-tail-r2
# 判分 + 汇总(两帧各一次,任一工作树,只读工件):
.venv/bin/python scripts/arc_eval_judge.py   --out …/teaching-arc-guard-tail-r2/before
.venv/bin/python scripts/arc_eval_judge.py   --out …/teaching-arc-guard-tail-r2/after
.venv/bin/python scripts/arc_eval_metrics.py --out …/teaching-arc-guard-tail-r2/before
.venv/bin/python scripts/arc_eval_metrics.py --out …/teaching-arc-guard-tail-r2/after
```

误伤/真代喂分类口径:遍历 `<帧>/<口径>/M/collect/*/results/*.json` 的
`transcript.guard_events`(feeds_method 事件),`rule_ids` 逐词对照「截至当轮(含当轮)学生
消息」——全部已说 = 误伤,存在未说 = 真代喂(逐事件口径);再数被换下的 tutor 原句条数
(逐句口径)。(零手拼,全部可离线重算。)

**r2 观察点**:① 误伤两口径维持 0、真代喂拦截保留;② R·method_name 语料含「先通分」类
确认句(合规定名可见);③ `answer_number` 确定性面(P·首问)逐字不变——注意 r1 里 L 口径
16 行终答复述语料是 ① 洞的形态(已由 #158 修复接管),r2 两帧的对应变化属 #158 域归因;
④ 无重生成级联(四指标 F 逐项对照)。

## 5. 附:「② 卡壳词表缓议」裁定出处

#146 评论(PM 记录,DeepDreamerLSC,2026-09-10T12:15:13Z)《护栏/路由尾单瘦身 + ② 卡壳
词表经用户裁定推迟》第二节:推迟理由三条(无出口绑定 / 修好后更多轮次改走确定性阶梯、会在
判门帧前扰动测量 / 真正价值场景在 M4 对抗评测)+ 触发条件三条(M4 开工 / 判门帧夜评再现
同轮跨 run 分叉 / 出现未路由阶梯的泄露实例)。该裁定此后已被 #158 按 #157 评审「发现 2」
实修(词表 + 「我不会(?!吧)」负向断言 + 7 条对抗样例含 r1 rabbit t1 原句)并合入 main
取代——即 ② 不再缓议。
