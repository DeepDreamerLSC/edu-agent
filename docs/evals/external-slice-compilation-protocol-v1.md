# 外部 slice 编译协议 v1(经理 v2:候选案例 → 可执行 scenario)

状态:草案(2026-09-21,PM 拟;依据架构师总裁定决策二+步骤7预注册 v2 §二)。跑前冻结。
输入:`external_slices/socraticmath_v1.json`(36 条候选,带 context_dependency 标注,#394 已合)。
输出:可执行 scenario 集,与自产回归 cases 同接口进 A/B。

## 一、目标格式(全部现成,零新基建)

Runner(`kernel_subject.py run_case`)已支持两种剧本,**同一案例可混用(steps 前缀+线性尾)**:

- **线性 v1**(`small_lecturer_dialogue_scenario/v1`):`student_turns` 固定序列,不看导师说什么照发——**适合弱依赖轮**;
- **分支 v2**(`dialogue_scenarios/v2`):`steps[].branches`,每步按**导师上一句的文本特征**(`assistant_contains_any/all` 子串命中,声明序首个命中,兜底 fallback)选学生回应——**适合强依赖轮**:`select_branch` 纯文本路由,确定性可复算(#178 跟随器既有语义)。

## 二、编译规则(逐级,按 context_dependency 分派)

**R1 全弱依赖案例 → 线性 v1**:student_turns = 原学生轮序列(原文照录,只允许截断不允许改写);question/problem 取 slice 的 problem 面。

**R2 强依赖在中后段 → 截断成稳定前缀**:保留首个强依赖轮之前的弱依赖序列,判读面注明截断位置与舍弃轮数。

**R3 强依赖需保留(形态核心,如"学生纠正导师"的纠正轮)→ 编入 v2 分支**:
- `branch.student_response` = **该真实学生轮原文**;
- `branch.when.assistant_contains_any`(或 all)= 从**原对话中被回应的那句 tutor 轮**机械提取特征子串(数字/关键名词/问句核心词;脚本提取候选,人工确认 3-5 个);语义 = "我们的导师若也说了类似的话,学生给出这个真实回应"——**路由到原文生条件,不制造 counterfactual**;
- 同步一条 `fallback` 分支(该步唯一):fallback 的 student_response 用该案例**另一条弱依赖真实轮**或前一步的语义保持变体;若两者皆无 → 该案例降级 R4;
- 判读标注:分支命中走"真实回应",fallback 走"降级回应",A/B 两臂的路由分布差异作为实验报告的一部分(公平性证据)。

**R4 弃案**:强依赖贯穿全篇且特征子串无法生成可靠路由(过于泛化/多义)→ 弃,记录原因入产物头部。

**全局禁止**:LLM 改写学生轮文本(只允许原文或截断);建 simulator;把真人 tutor 轮放进被测 transcript。

## 三、工序与人工确认

1. **初稿(可子代理,套餐 Flash 承载)**:脚本从 reference_dialogue 机械提取每强依赖轮的分支特征候选;按 R1-R4 出编译初稿+逐条处置理由;
2. **人工确认(PM 或用户抽验)**:每条分支特征的人工核(3-5 子串是否真能路由);**每形态至少 3 条全通读**;
3. **验收(确定性)**:产物过 `scenario_corpus` validator;抽 3 条 mock-gateway dry-run 验证路由命中与 fallback 行为;与 slice 候选的对账(36 = 编译 + 截断 + 弃,逐条有去向)。

## 四、规模预期(预注册 §二的口径)

- 形态1(20 条候选):预期编译 12-18 条可执行;
- 形态2(16 条,强形态仅 5-6):预期 5-10 条可执行;
- 合计 ~20±,宁少勿滥(R4 从严)。

## 五、产物

`edu_agent/evals/datasets/external_slices/socraticmath_executable_v1.json`(v1/v2 混合集,头部:编译规则版本/逐条处置记录/弃案原因/fallback 语义说明);PR 三字段照模板,需求来源=eval(#382 步骤7+架构师裁定决策二)。

## 裁定链

架构师决策二原文要点:「学生轮是素材不是天然剧本;弱依赖直接保留,强依赖弃/截/人工编入现有 steps/branches;不要让模型改写;10-20 条真正 executable > 50 条失真回放」。本协议 R1-R4 为其操作化。
