# 调优轮对照(vs 基线 R1×R2,#34 容差口径:分差≤1 单值判/≥2 区间判)

口径:**P(gate 冻结 wiring)** —— `build_cases` 11 场景;hint 注入:2/11 场景带 `answer_status="correct"`(small_lecturer_dialogue_stability_20_stability_word_problem、small_lecturer_teaching_context_shadow_pilot_20_stability_word_problem),其余 9 场景不带(unknown → 首问无提示)。

剧本截断(实发学生轮/剧本学生轮;⚠ = `ready_to_confirm` 提前判停,余轮不再发——KernelSubject 判停语义):

| 场景 | 学生轮(实发/剧本) |
|---|---|
| small_lecturer_dialogue_scenarios_equation_complete_reasoning | 2/2 |
| small_lecturer_dialogue_stability_20_stability_chicken_rabbit | 4/4 |
| small_lecturer_dialogue_stability_20_stability_equation_subtract | 4/4 |
| small_lecturer_dialogue_stability_20_stability_fraction_addition | 4/4 |
| small_lecturer_dialogue_stability_20_stability_triangle_area | 4/4 |
| small_lecturer_dialogue_stability_20_stability_word_problem | 4/4 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_chicken_rabbit | 4/4 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_equation_subtract | 4/4 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_fraction_addition | 4/4 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_triangle_area | 4/4 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_word_problem | 4/4 |

逐维均分(0-2):首问质量 0.91 | 追问引导 1.82 | 年级适配 2.00 | 节奏 1.18 | 总结与掌握 1.00 | 终止行为 1.00
护栏模式:**无答案** —— 评测侧 KernelSubject 只传题面/年级/answer_status,**不传参考答案**;生产侧带答案。本报告的代喂/泄露类读数出自无答案护栏,不等于生产读数。

| 场景 | R1 | R2 | 本轮 | 判定 |
|---|---:|---:|---:|---|
| small_lecturer_dialogue_scenarios_equation_complete_reasoning | 8 | 8 | 7 | 低于基线 |
| small_lecturer_dialogue_stability_20_stability_chicken_rabbit | 6 | 9 | 7 | 不劣(噪声主导) |
| small_lecturer_dialogue_stability_20_stability_equation_subtract | 7 | 7 | 8 | 达标 |
| small_lecturer_dialogue_stability_20_stability_fraction_addition | 3 | 4 | 8 | 达标 |
| small_lecturer_dialogue_stability_20_stability_triangle_area | 3 | 3 | 6 | 达标 |
| small_lecturer_dialogue_stability_20_stability_word_problem | 11 | 5 | 11 | 不劣(噪声主导) |
| small_lecturer_teaching_context_shadow_pilot_20_stability_chicken_rabbit | 5 | 5 | 7 | 达标 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_equation_subtract | 4 | 4 | 8 | 达标 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_fraction_addition | 3 | 4 | 8 | 达标 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_triangle_area | 2 | 3 | 6 | 达标 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_word_problem | 11 | 8 | 11 | 不劣(噪声主导) |

逐维均分:见 judge-scores.json;对两轮均值差:+2.32

## json_first_pass(01 §6 结构化输出合规率)

M2 门 98%: ✅ 当前 **99.8%** (856/858 产出了结果)

| role | responded | ok | rate | breakdown |
|---|---:|---:|---:|---|
| judge | 205 | 205 | 100.0% | ok=205 |
| tutor | 653 | 651 | 99.7% | ok=651, truncated=2 |
| **合计** | **858** | **856** | **99.8%** | |

> **不合规明细**(在合规分母内,计入未通过):
> · truncated (role=tutor, session=20260910T021359Z-tutor)
> · truncated (role=tutor, session=20260910T112727Z-tutor)

| model | responded | ok | rate |
|---|---:|---:|---:|
| mlx_27b | 205 | 205 | 100.0% |
| qwen3_vl_8b | 653 | 651 | 99.7% |

