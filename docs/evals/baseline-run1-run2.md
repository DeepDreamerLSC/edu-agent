# M1 基线报告:老系统 Run 1 × Run 2(阶段 4,M1 出口件)

日期:2026-09-07 · 被测对象:老系统(适配器经合作方流程接口驱动)· judge:Qwen3.5-27B-4bit(mlx,8301)经 gateway · 数据:runner/评分落盘文件(`.mimosa/baseline-runs/`),数字未手拼 · 看板:#34

## 1. 覆盖面(如实声明)

- **11 场景 / 3 数据集**(small_lecturer_dialogue_scenarios 1、dialogue_stability_20 5、teaching_context_shadow_pilot_20 5;均为线性脚本可驱动场景)。
- 盲区(沿 A 线盘点口径,见 #34):adaptive_pilot 8 场景需模拟器驱动;stability_* 题号 15 个未发布;shadow_scenarios_24 / one_call_fast_path_21 / target_mode_v3 等场景题干不在已发布题库;图片题批次(pujia)无文字脚本。**追平门的"全部 21 数据集"尚未覆盖,本基线是可驱动面的全量。**
- 环境前置:题号歧义与快照/渠道/链条三层债由 PM 修复(2026-09-07,#34);评分与收集错峰,8301 单角色喂给。

## 2. 效率与稳定性汇总(两轮,同条件:日间静默窗口、并发 2、fresh 学生池、定参 #41)

| 指标 | Run 1 | Run 2 | 方差 |
|---|---|---|---|
| 完成率 | 11/11(100%) | 11/11(100%) | 0 |
| 环境失败 / 内容失败 | 0 / 0 | 0 / 0 | — |
| 总时长 | 470.1s | 453.4s | **−3.5%** |
| 单场景 p50 / p95 | 81.1s / 119.8s | 80.8s / 112.6s | **−0.3% / −6.0%** |
| 回合 p50 / p95(n=32) | 15.7s / 22.5s | 17.1s / 21.6s | **+9.1% / −4.1%** |
| token 续期 | 未触发(≪8h TTL) | 未触发 | — |

收集侧全部指标方差 <10%(回合 p50 +9.1% 最高,未超)。

## 3. 教学指标逐场景(judge 六维总分,0-12;双评均已完成)

| 场景 | R1 verdict | R1 总分 | R2 verdict | R2 总分 | 分差 |
|---|---|---:|---|---:|---:|
| dialogue_scenarios:equation_complete_reasoning | review | 8 | review | 8 | 0 |
| stability_20:chicken_rabbit | fail | 6 | review | 9 | 3 |
| stability_20:equation_subtract | review | 7 | review | 7 | 0 |
| stability_20:fraction_addition | fail | 3 | fail | 4 | 1 |
| stability_20:triangle_area | fail | 3 | fail | 3 | 0 |
| stability_20:word_problem | pass | 11 | fail | 5 | **6** |
| teaching_context:chicken_rabbit | fail | 5 | fail | 5 | 0 |
| teaching_context:equation_subtract | fail | 4 | fail | 4 | 0 |
| teaching_context:fraction_addition | fail | 3 | fail | 4 | 1 |
| teaching_context:triangle_area | fail | 2 | fail | 3 | 1 |
| teaching_context:word_problem | pass | 11 | review | 8 | **3** |

- 两轮总分均 5.73 / 5.45(−4.9%)。verdict 分布(R1/R2):pass 1/1,review 3/3,fail 7/7——**老系统基线在可驱动场景上以 fail 为主**,薄弱维:socratic_followup(均 0.64/0.55)、pacing(0.64/0.45)、summary_mastery(0.36/0.27)、termination(0.55/0.36)。
- 逐维均分(R1):first_question 1.82、grade_fit 1.73(强项:首问不泄露、年级表达);R2 同序一致(first_question 1.82、grade_fit 2.0)。

## 4. judge 稳定性档案(第二页:跨轮分差分布)

| 层 | 口径 | 结果 |
|---|---|---|
| 同轮双评(27B 评两次) | Run1 11 case:最大分差 1、均值 0.18、verdict 翻转 0;Run2:最大 1、均值 0.09、翻转 0 | **极稳** |
| 跨轮同 case(两次独立生成的对话各评) | 11 case:分差 max 6、mean 1.36;**3/11 case 总分差 >10%**(12 分制 1.2);verdict 翻转 2(pass↔fail、fail↔review) | **显著** |
| 独立性保险(DeepSeek 平行,10% 抽样=2) | 带符号平均分差(27B−DeepSeek):R1 −1.5(非同向)、R2 −2.0(同向) | 样本小,趋势待扩样 |

判读:同轮双评极稳说明 judge 本身可复现;跨轮大分差的主导项是**对话生成非确定性**(同场景两轮对话内容不同,word_problem 两轮分差 6 即生成差异放大)。追平门容差设计输入:逐场景对照应以**同一对话的评分**为配对单位(双评口径,σ≈0.13),跨轮对话生成的方差不应计入门容差——留人定追平门对照口径。

## 5. judge 模型披露(#32)

- 主选/双评:Qwen3.5-27B-4bit(mlx-lm server,127.0.0.1:8301),`judge_model` 随每条评分落盘。
- 独立通道:deepseek-chat(10% 抽样 2 case);系统性偏向判定与切回留人批,不自行切回。

## 6. M1 出口对照(00 §8.2 阶段 4)

- [x] 基线报告入库(本 PR)
- [x] 两轮复跑方差对照(§2/§4)
- [x] 失败分类与晨间摘要实战(Run 1/2 均零失败;补跑路径在阶段 2/中断实录已验证)
- [ ] 追平门对照口径(同对话配对 vs 跨轮)——留人定(§4 判读)
- [ ] 覆盖面扩展(模拟器场景/stability_* 发布/图片题)——数据侧决策,留人
