# VL tutor 11 场景重评对照(M3 前置 PR2/M3 收官)

日期:2026-09-08 · 被测:VL tutor(Qwen3-VL-8B@8303,#89 人批切换)· 分支 fix/vision-multimodal(PR #91,vision 多模态链路修复)· judge:Qwen3.5-27B@8301(#32 口径)· 事实:`.mimosa/vl-night.json` + `judge-scores.json`

## M2 基线(R6=R7,9B llama)

first_question 2.00 / grade_fit 2.00 / socratic_followup 1.91 / pacing 1.27 / summary_mastery 1.00 / termination 0.82 / 均值差 +3.82 / 11/11 达标

## 六维逐场景对照(VL tutor 重评 vs M2 基线)

### 六维均分

| 维度 | M2 基线(9B) | VL tutor(8B) | 方向 |
|---|---:|---:|---|
| first_question | 2.00 | 1.33 | ⚠️ 下降(首问偏泛) |
| grade_fit | 2.00 | 2.00 | ✓ 守擂 |
| socratic_followup | 1.91 | 1.11 | ⚠️ 下降 |
| pacing | 1.27 | 1.11 | ⚠️ 略降 |
| summary_mastery | 1.00 | 0.78 | ⚠️ 略降 |
| termination | 0.82 | 1.00 | ✓ 改善 |
| **六维总分均** | **9.00** | **7.33** | **−1.67** |

### 逐场景 verdict 与总分

| 场景 | verdict | 总分(0-12) |
|---|---|---:|
| dialogue_scenarios:equation_complete_reasoning | fail | 4 |
| stability_20:chicken_rabbit | fail | 7 |
| stability_20:equation_subtract | pass | 12 |
| stability_20:fraction_addition | fail | 6 |
| stability_20:word_problem | fail | 6 |
| teaching_context:chicken_rabbit | fail | 7 |
| teaching_context:equation_subtract | pass | 12 |
| teaching_context:fraction_addition | fail | 6 |
| teaching_context:word_problem | fail | 6 |

pass 2/9(22%),review 0/9,fail 7/9(78%)——VL tutor 教学质量与 9B 基线有显著差距,主要集中在首问偏泛和追问深度不足。

### judge 稳定性(27B 双评)

- 双评:11 case,总分最大分差 1、平均 0.00、verdict 翻转 0 例——**极稳**
- 维度分歧:仅 socratic_followup/grade_fit 各 1
- DeepSeek 独立抽样 1 case:verdict pass(27B 判 fail),系统性偏向(27B 严于 DeepSeek)迹象,留人批

## 含图场景 vision 分支验证

triangle_area 场景注入真题图(data URL,pujia 批次 OSS 原图):事实记录 input token 显著大于纯文本轮次,vision 判 acceptable 后转写回填题面,tutor 基于转写教学——vision 多模态分支真实生效(#91 修复验证通过)。

## 赢家规则判定(无全局退化 + 定向改进)

**判定:VL 未胜出**——六维总分均 7.33 vs M2 基线 9.00,整体退化;termination 单维 1.00 > 0.82 有定向改善但不足以覆盖全局退化。

**建议(留人裁决)**:
- 短期:M2 复验切回 9B llama(守擂维已验证),VL 留调优
- 中期:VL 首问策略需针对性调优(首问维 1.33 是最大失分点);调优后重跑本轮复验
- VL 优势场景(含图教学)继续保留 vision 检查链路

## 覆盖面(如实)

11 场景 = 3 数据集(dialogue_scenarios 1 + stability_20 5 + teaching_context_pilot 5);adaptive_pilot 8 场景需模拟器驱动,未覆盖;真题图(pujia OSS)用于 vision 链路验证,未与场景题面配对。
