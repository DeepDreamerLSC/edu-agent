# corpus checks × 真模型轮次报告(#216)

- 生成:2026-09-14T04:00:52.929119+00:00
- 工件:edu_agent/evals/artifacts/corpus-round-v2
- judger_sha256:440395a900bfdd09828c75ff8ffe211c8b80b0c9a5a6512eb90a2e882e6ed446
- 对照基线:edu_agent/evals/artifacts/math-gold-v1/collect/cases-20260913T134402Z-3b59
- **新增红:1**(绿→红 = 回归信号)
- 基线无溯源(判分器指纹自本轮起,#238 §5 首轮基线欠账)

| case_id | status | final_state | checks | 判定(跨轮) | judge |
|---|---|---|---|---|---|
| small_lecturer_math_gold_b2_circle_area_alternative_method | ok | needs_review | 无声明 | 绿 | total=5 fail 追问=1 |
| small_lecturer_math_gold_b2_circle_area_misconception_repair | ok | needs_review | 无声明 | 绿 | total=6 fail 追问=1 |
| small_lecturer_math_gold_b2_circle_area_support_boundary | ok | completed | 无声明 | 绿 | total=11 pass 追问=1 |
| small_lecturer_math_gold_b2_circle_area_support_boundary_hard_pressure | ok | needs_review | 无声明 | 绿 | total=3 fail 追问=0 |
| small_lecturer_math_gold_b2_fraction_multiplication_alternative_method | ok | completed | 无声明 | 绿 | total=4 fail 追问=0 |
| small_lecturer_math_gold_b2_fraction_multiplication_complete_reasoning | ok | completed | 无声明 | 绿 | total=6 fail 追问=0 |
| small_lecturer_math_gold_b2_fraction_multiplication_support_boundary | ok | needs_review | 无声明 | 绿 | total=4 fail 追问=0 |
| small_lecturer_math_gold_b2_rope_unit_app_alternative_method | ok | completed | 无声明 | 绿 | total=6 fail 追问=0 |
| small_lecturer_math_gold_b2_rope_unit_app_complete_reasoning | ok | completed | 无声明 | 绿 | total=6 fail 追问=1 |
| small_lecturer_math_gold_b2_rope_unit_app_misconception_repair | ok | completed | 无声明 | 绿 | total=12 pass 追问=2 |
| small_lecturer_math_gold_b2_unit_rate_complete_reasoning | ok | completed | 无声明 | 绿 | total=6 fail 追问=0 |
| small_lecturer_math_gold_b2_unit_rate_misconception_repair | ok | completed | 无声明 | 绿 | total=12 pass 追问=2 |
| small_lecturer_math_gold_b2_unit_rate_support_boundary | ok | completed | 无声明 | 绿 | total=8 review 追问=1 |
| small_lecturer_math_gold_candidates_average_score_alternative_method | ok | completed | 无声明 | 绿 | total=4→4 fail 追问=1 |
| small_lecturer_math_gold_candidates_average_score_complete_reasoning | ok | completed | 无声明 | 绿 | total=9→9 review 追问=2 |
| small_lecturer_math_gold_candidates_average_score_misconception_repair | ok | completed | 无声明 | 绿 | total=9→9 review 追问=2 |
| small_lecturer_math_gold_candidates_average_score_support_boundary | ok | needs_review | 无声明 | 绿 | total=3→4 fail 追问=0 |
| small_lecturer_math_gold_candidates_chicken_rabbit_alternative_method | ok | completed | 无声明 | 绿 | total=3→5 fail 追问=0 |
| small_lecturer_math_gold_candidates_chicken_rabbit_complete_reasoning | ok | completed | 无声明 | 绿 | total=12→12 pass 追问=2 |
| small_lecturer_math_gold_candidates_chicken_rabbit_misconception_repair | ok | completed | 无声明 | 绿 | total=10→9 review 追问=2 |
| small_lecturer_math_gold_candidates_chicken_rabbit_support_boundary | ok | needs_review | 无声明 | 绿 | total=4→5 fail 追问=1 |
| small_lecturer_math_gold_candidates_decimal_multiplication_alternative_method | ok | completed | 无声明 | 绿 | total=4→4 fail 追问=0 |
| small_lecturer_math_gold_candidates_decimal_multiplication_complete_reasoning | ok | completed | 无声明 | 绿 | total=12→12 pass 追问=2 |
| small_lecturer_math_gold_candidates_decimal_multiplication_misconception_repair | ok | completed | 无声明 | 绿 | total=12→12 pass 追问=2 |
| small_lecturer_math_gold_candidates_decimal_multiplication_support_boundary | ok | needs_review | 无声明 | 绿 | total=5→5 fail 追问=1 |
| small_lecturer_math_gold_candidates_distance_speed_alternative_method | ok | completed | 无声明 | 绿 | total=6→6 fail 追问=1 |
| small_lecturer_math_gold_candidates_distance_speed_complete_reasoning | ok | completed | 无声明 | 绿 | total=2→10 pass 追问=1 |
| small_lecturer_math_gold_candidates_distance_speed_misconception_repair | ok | completed | 无声明 | 绿 | total=2→9 review 追问=2 |
| small_lecturer_math_gold_candidates_distance_speed_support_boundary | ok | needs_review | 无声明 | 绿 | total=2→3 fail 追问=0 |
| small_lecturer_math_gold_candidates_division_remainder_alternative_method | ok | completed | 无声明 | 绿 | total=5→5 fail 追问=1 |
| small_lecturer_math_gold_candidates_division_remainder_complete_reasoning | ok | needs_review | 无声明 | 绿 | total=4→6 fail 追问=1 |
| small_lecturer_math_gold_candidates_division_remainder_misconception_repair | ok | needs_review | 无声明 | 绿 | total=6→6 fail 追问=1 |
| small_lecturer_math_gold_candidates_division_remainder_support_boundary | ok | needs_review | 无声明 | 绿 | total=4→5 fail 追问=1 |
| small_lecturer_math_gold_candidates_equation_addition_alternative_method | ok | completed | 无声明 | 绿 | total=6→6 fail 追问=1 |
| small_lecturer_math_gold_candidates_equation_addition_complete_reasoning | ok | completed | 无声明 | 绿 | total=6→4 fail 追问=0 |
| small_lecturer_math_gold_candidates_equation_addition_misconception_repair | ok | completed | 无声明 | 绿 | total=4→12 pass 追问=2 |
| small_lecturer_math_gold_candidates_equation_addition_support_boundary | ok | needs_review | 无声明 | 绿 | total=5→5 fail 追问=1 |
| small_lecturer_math_gold_candidates_equation_multiplication_alternative_method | ok | completed | 无声明 | 绿 | total=6→6 fail 追问=1 |
| small_lecturer_math_gold_candidates_equation_multiplication_complete_reasoning | ok | completed | 无声明 | 绿 | total=8→8 review 追问=1 |
| small_lecturer_math_gold_candidates_equation_multiplication_misconception_repair | ok | completed | 无声明 | 绿 | total=8→8 review 追问=1 |
| small_lecturer_math_gold_candidates_equation_multiplication_support_boundary | ok | needs_review | 无声明 | 绿 | total=7→5 fail 追问=1 |
| small_lecturer_math_gold_candidates_fraction_addition_alternative_method | ok | needs_review | 无声明 | 绿 | total=6→5 fail 追问=1 |
| small_lecturer_math_gold_candidates_fraction_addition_complete_reasoning | ok | completed | 无声明 | 绿 | total=8→8 review 追问=1 |
| small_lecturer_math_gold_candidates_fraction_addition_misconception_repair | ok | completed | 无声明 | 绿 | total=9→9 review 追问=2 |
| small_lecturer_math_gold_candidates_fraction_addition_support_boundary | content | - | - | - | - |
| small_lecturer_math_gold_candidates_number_pattern_alternative_method | ok | completed | 无声明 | 绿 | total=3→3 fail 追问=0 |
| small_lecturer_math_gold_candidates_number_pattern_complete_reasoning | ok | completed | 无声明 | 绿 | total=5→6 fail 追问=1 |
| small_lecturer_math_gold_candidates_number_pattern_misconception_repair | ok | completed | 无声明 | 绿 | total=11→11 pass 追问=2 |
| small_lecturer_math_gold_candidates_number_pattern_support_boundary | ok | needs_review | 无声明 | 绿 | total=5→6 fail 追问=1 |
| small_lecturer_math_gold_candidates_parentheses_equation_alternative_method | ok | needs_review | 无声明 | 绿 | total=2→3 fail 追问=0 |
| small_lecturer_math_gold_candidates_parentheses_equation_complete_reasoning | ok | completed | 无声明 | 绿 | total=8→8 review 追问=1 |
| small_lecturer_math_gold_candidates_parentheses_equation_misconception_repair | ok | completed | 无声明 | 绿 | total=7→7 review 追问=1 |
| small_lecturer_math_gold_candidates_parentheses_equation_support_boundary | ok | needs_review | 无声明 | 绿 | total=7→7 review 追问=2 |
| small_lecturer_math_gold_candidates_percentage_discount_alternative_method | ok | completed | 无声明 | 绿 | total=5→3 fail 追问=0 |
| small_lecturer_math_gold_candidates_percentage_discount_complete_reasoning | ok | completed | 无声明 | 绿 | total=5→10 pass 追问=1 |
| small_lecturer_math_gold_candidates_percentage_discount_misconception_repair | ok | completed | 无声明 | 绿 | total=9→9 review 追问=2 |
| small_lecturer_math_gold_candidates_percentage_discount_support_boundary | ok | needs_review | 无声明 | 绿 | total=4→5 fail 追问=1 |
| small_lecturer_math_gold_candidates_ratio_share_alternative_method | ok | completed | 无声明 | 绿 | total=9→11 pass 追问=2 |
| small_lecturer_math_gold_candidates_ratio_share_complete_reasoning | ok | completed | 无声明 | 绿 | total=4→12 pass 追问=2 |
| small_lecturer_math_gold_candidates_ratio_share_misconception_repair | ok | completed | 无声明 | 绿 | total=12→12 pass 追问=2 |
| small_lecturer_math_gold_candidates_ratio_share_support_boundary | ok | needs_review | 无声明 | 绿 | total=4→6 fail 追问=1 |
| small_lecturer_math_gold_candidates_rectangle_perimeter_alternative_method | ok | completed | 无声明 | 绿 | total=3→7 review 追问=1 |
| small_lecturer_math_gold_candidates_rectangle_perimeter_complete_reasoning | ok | completed | 无声明 | 绿 | total=8→8 review 追问=1 |
| small_lecturer_math_gold_candidates_rectangle_perimeter_misconception_repair | ok | completed | 无声明 | 绿 | total=9→9 review 追问=2 |
| small_lecturer_math_gold_candidates_rectangle_perimeter_support_boundary | ok | needs_review | 无声明 | 绿 | total=5→5 fail 追问=1 |
| small_lecturer_math_gold_candidates_simple_probability_alternative_method | ok | completed | 无声明 | 绿 | total=1→6 fail 追问=1 |
| small_lecturer_math_gold_candidates_simple_probability_complete_reasoning | ok | needs_review | 无声明 | 绿 | total=2→3 fail 追问=0 |
| small_lecturer_math_gold_candidates_simple_probability_misconception_repair | ok | needs_review | 无声明 | 绿 | total=1→1 fail 追问=0 |
| small_lecturer_math_gold_candidates_simple_probability_support_boundary | ok | needs_review | 无声明 | 绿 | total=4→5 fail 追问=1 |
| small_lecturer_math_gold_candidates_triangle_area_alternative_method | ok | completed | 无声明 | 绿 | total=12→12 pass 追问=2 |
| small_lecturer_math_gold_candidates_triangle_area_complete_reasoning | ok | completed | 无声明 | 绿 | total=11→11 pass 追问=1 |
| small_lecturer_math_gold_candidates_triangle_area_misconception_repair | ok | completed | 无声明 | 绿 | total=5→12 pass 追问=2 |
| small_lecturer_math_gold_candidates_triangle_area_support_boundary | ok | needs_review | 无声明 | 绿 | total=4→6 fail 追问=1 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_age | ok | completed | 全绿 | 绿 | total=12 pass 追问=2 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_angles | ok | completed | 全绿 | 绿 | total=12 pass 追问=2 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_average | ok | completed | 全绿 | 绿 | total=9 review 追问=1 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_chicken_rabbit | ok | completed | 全绿 | 绿 | total=12 pass 追问=2 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_decimal_multiply | ok | completed | 全绿 | 绿 | total=5 fail 追问=1 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_discount | ok | completed | 全绿 | 绿 | total=12 pass 追问=2 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_division_remainder | ok | completed | 全绿 | 绿 | total=12 pass 追问=2 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_equation_parentheses | ok | completed | 全绿 | 绿 | total=12 pass 追问=2 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_equation_sign | ok | completed | 全绿 | 绿 | total=12 pass 追问=2 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_equation_subtract | ok | completed | 全绿 | 绿 | total=12 pass 追问=2 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_fraction_addition | ok | completed | 全绿 | 绿 | total=10 pass 追问=2 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_order_operations | ok | completed | 全绿 | 绿 | total=12 pass 追问=2 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_probability | ok | completed | 全绿 | 绿 | total=12 pass 追问=2 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_ratio | ok | completed | 全绿 | 绿 | total=12 pass 追问=2 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_rectangle_perimeter | ok | needs_review | finish_status:final_state 期望 completed,实际 needs_review | 新增红 | total=5 fail 追问=1 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_sequence | ok | completed | 全绿 | 绿 | total=12 pass 追问=2 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_speed | ok | completed | 全绿 | 绿 | total=9 review 追问=2 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_triangle_area | ok | completed | 全绿 | 绿 | total=8 fail 追问=1 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_unit_conversion | ok | completed | 全绿 | 绿 | total=12 pass 追问=2 |
| small_lecturer_teaching_context_shadow_pilot_20_stability_word_problem | ok | completed | 全绿 | 绿 | total=9 review 追问=1 |

- 软化路径命中(#241 行 4):cut=1(同分句边界收回) / mask=0(兜底改写「几」) / dropped=0(整步弃用)