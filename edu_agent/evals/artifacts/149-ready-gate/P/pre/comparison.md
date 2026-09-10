# 调优轮对照(vs 基线 R1×R2,#34 容差口径:分差≤1 单值判/≥2 区间判)

| 场景 | R1 | R2 | 本轮 | 判定 |
|---|---:|---:|---:|---|
| small_lecturer_dialogue_scenarios_equation_complete_reasoning | 8 | 8 | 12 | 达标 |
| small_lecturer_dialogue_stability_20_stability_chicken_rabbit | 6 | 9 | 8 | 不劣(噪声主导) |
| small_lecturer_dialogue_stability_20_stability_equation_subtract | 7 | 7 | 12 | 达标 |
| small_lecturer_dialogue_stability_20_stability_fraction_addition | 3 | 4 | 12 | 达标 |
| small_lecturer_dialogue_stability_20_stability_triangle_area | 3 | 3 | 10 | 达标 |
| small_lecturer_dialogue_stability_20_stability_word_problem | 11 | 5 | 5 | 不劣(噪声主导) |
| small_lecturer_teaching_context_shadow_pilot_20_stability_chicken_rabbit | 5 | 5 | 8 | 达标 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_equation_subtract | 4 | 4 | 12 | 达标 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_fraction_addition | 3 | 4 | 12 | 达标 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_triangle_area | 2 | 3 | 10 | 达标 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_word_problem | 11 | 8 | 5 | 低于基线 |

逐维均分:见 judge-scores.json;对两轮均值差:+4.05

## json_first_pass(01 §6 结构化输出合规率)

M2 门 98%: ✅ 当前 **100.0%** (57/57 产出了结果)

| role | responded | ok | rate | breakdown |
|---|---:|---:|---:|---|
| judge | 9 | 9 | 100.0% | ok=9 |
| tutor | 48 | 48 | 100.0% | ok=48 |
| **合计** | **57** | **57** | **100.0%** | |

| model | responded | ok | rate |
|---|---:|---:|---:|
| mlx_27b | 9 | 9 | 100.0% |
| qwen3_vl_8b | 48 | 48 | 100.0% |

