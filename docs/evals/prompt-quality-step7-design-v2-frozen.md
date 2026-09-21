# Kernel 收口期步骤 7:Prompt/Model quality 实验预注册 v2(冻结版)

状态:**预注册冻结**(2026-09-21,架构师总裁定三项裁定收编;v1 草案经裁定升级,跑前冻结跑后不改)。
前置:收口期 kernel correctness 闭环已合(#383-386+#389:learner-state ownership / failure atomicity / trusted ladder / ablation teardown)。
定位:架构师执行序列最后一项——在更薄、更可信的 Kernel 上,解决模型自身的教学行为问题。

## 一、问题定义(不变)

三靶:**evidence reuse**(学生已给实质答案仍重新采集)/ **latest-turn grounding**(回应不锚定学生最新表述)/ **no-progress**(连续轮无实质推进)。模型层残留——Prompt 已含规格但未稳定执行,故实验面是执行强度/表述形态,非新增规则(§11 禁同义句堆叠)。

## 二、实验单元与样本集(v2 修订:编译制)

**单元**:一段完整教学对话(kernel 跑通至收束/评估窗截止)。
**对照组**:main 现行 prompt(收口后 Thin Kernel 之上)。
**实验组**:prompt 改造件(见三,仅 A/B 两方向)。

**样本集三层**(分层报告不合并均分):
- **自产真实回归 cases**:444a/2c85/700m 剧本重放面;
- **外部可执行 scenario(编译制,架构师裁定决策二)**:SocraticMATH 学生轮是**素材不是天然剧本**——机械顺序 replay 构成 counterfactual mismatch(学生在原教师动作条件下的行为被嫁接到我们的 tutor 后)。正确流程:**筛选 → 编译 → A/B**:
  - 筛选层(在跑):两形态候选案例,逐条标注 student 轮上下文依赖度;
  - 编译层(新增协议):弱依赖轮直接保留为真实 student utterance;强依赖轮要么弃案、要么截断到稳定段、要么人工编入现有 steps/branches 场景格式;**禁止 LLM 改写、不建 simulator**;真人 tutor 轮只作来源上下文/judge 参照,**不进被测 tutor transcript**;
  - 规模:**每形态 10-20 条可编译 scenario,宁少勿滥**(少而可信 > 多而失真——有系统失真的样本不增统计力只增噪声)。

## 三、候选方向(v2 修订:C 转 DEFERRED)

- **A 执行强度注入**:系统提示的"已完成视为完成"规则处,要求导师每轮先内部确认"学生最新消息是否已含新证据/已答内容"再选动作(思维链式自查);
- **B 承认位强化**:R2 暖度线的承认位温度分级向"正确答案承认"扩展——学生答案正确时先承认再深化(700m 第 4 轮「但」字的反面);
- ~~C 问句预算~~ **DEFERRED(架构师裁定)**:本质是教学行为的新确定性状态约束,纯 prompt 不可靠实现;当前证据不足以获得进入 Kernel 的存在权(不重演"真实问题→新机制→新状态→Kernel 再变厚")。**正式触发器(五条全满足才重开)**:A/B 完成后 no-progress 仍未达预注册目标 + 主要失败已非 close-loop bug + Prompt A/B 无法稳定降低 + 真实案例证明"追问过量"仍是独立 failure family +(#252 触发器制同源)。重开时先问"最小 deterministic invariant 是什么"——可能是 hard circuit breaker 而非教学型问句预算。

## 四、测量(判读预注册,不变+状态链)

| 指标 | 定义 | pass 线 |
|---|---|---|
| evidence-reuse 犯率 | 形态1 scenario 中学生给出实质答案后导师仍重问/质疑的轮占比 | baseline 对比下降,配对符号检验 p<0.05 |
| grounding 犯率 | 导师轮与学生最新轮无语义衔接的占比 | 同上 |
| no-progress 率 | 评估窗内无实质推进轮序列出现率 | 不劣化(硬线) |
| 收束面 | completed 率/轮数 | 不劣化(硬线) |
| 安全面 | answer_leak/stuck 语义 | 零回退(硬线,回归电池守) |
| 语气面 | R2 五面判读 + blind human delta | 不差于 baseline(人审协议复用) |

**状态链(严格区分,架构师裁定决策三)**:
```
行为实验 PASS → 获得正式 Candidate 资格 → Criterion 1 正式 93 面评分
→ 达到 T_new → Criterion 1 PASS → 部署/pilot
```
六指标只证明"已知病灶修改方向有效且无主要回归",**不等于**整体 93 面达标——后者是正式 scoring surface 的职责。

## 五、真候选资格(deployment identity,架构师裁定新增)

触发 Criterion 1 须同时满足:
```
步骤7行为门全绿
+ human blind review 不差
+ deterministic safety regression 绿
+ 本轮 Kernel correctness 闭环已合并 ✓(#383-386/#389)
+ 无 A/B/C runtime ablation ✓(#389)
+ 无 eval-only product behavior override(跑前核验)
+ Prompt/Kernel/Model config 已冻结
+ Harness 测的就是准备上线的同一 artifact(Eval/Prod same source)
```
**部署语义**:internal staging/production-form build 在判分前允许且推荐(合并+清 eval-only+生成 deployment-form+freeze SHA/config/model/prompt);**学生可见部署/pilot 在 Criterion 1 PASS 之后**(promotion gate 非 post-deployment audit;判据 2 试点是另一出口判据,#255 分立)。

## 六、FAIL 分诊纪律(架构师裁定)

Criterion 1 未达 T_new:**不自动进入"prompt 调到 10.2652 为止"**——先看失败集中在哪(failure 分诊),否则重蹈 target chasing → Judge chasing。**Criterion 1 是验收尺,不是 optimizer objective**。

## 七、最终路线(冻结)

```
当前 Kernel correctness 修复完成 ✓(已合)
        ↓ 冻结产品基线
Prompt A/B(不做 C)
        ↓
自产真实回归 cases + 外部可执行 scenario(编译制)
        ↓
六项预注册指标 + blind human delta
        ↓ 全部绿色
Freeze Candidate(SHA+Prompt+Model+Config)
        ↓
Criterion 1 正式 93 面(T_new=10.2652)
   PASS → 质量出口成立 → 部署/判据2 pilot
   FAIL → failure 分诊(不自动追分)
```

## 八、预算与点火

- 估算:样本 ~30-40 案 × 2 臂 × ~4 轮 ≈ 240-320 tutor calls + judge ~80;Criterion 1 ~400 calls(预注册在案,单独点火);
- 点火键:用户(A/B 跑面点火;Criterion 1 判分点火);
- 承载:工作流(judge panel 形态,wave1 骨架;存档 `prompt-quality-step7`)。

## 裁定记录

- v1→v2 变更:决策一(C 转 DEFERRED+触发器)/决策二(编译制否决机械 replay)/决策三(全绿=候选冻结+正式判分,部署后置);架构师总裁定全文存会话记录,要点见本文件对应节。
