# Phase C 双标盲审 pack(24/24,固定 hash 序 = cert C24 封存序)

## 盲法规则(guide v1.1 §4 铁律;#448 三段式编排,用户 2026-09-26 点火)
- **只看**:sessions/01–24 的 transcript 轮表 + post-turn obs 表 + 运行注记;
- **不看、不打听**:现有自动评测的一切结果(评分与依据、确定性判定、无进展诊断、任何既有报告或历史评测材料)、**另一位 reviewer 的标注**;
- **两位 reviewer 必须是真实且相互独立的人类**:AI 只装配材料/做机械核验,不计入 human agreement;
- **顺序固定**:hash 序(即本 INDEX 序 01–24),不跳选、不先看后面的;
- 判不了 → 如实填 unsure;不得通过查自动评测结果或与对方讨论来消除 unsure;
- 全部 24 份标注锁定后,执行链才揭示既有自动评测结果做比较;此前任何接触都构成污染,必须主动声明。

## 判据与材料
- 唯一判据:本包 `phase-c-annotation-guide-v1.1.md`(冻结稿,冻结 sha 1c667d46…;校验口径 `head -n -1 <guide> | sha256sum`);
- 每 session 材料含 §6 标注表单副本(Session 编号已填,Reviewer/日期自填);
- 新形态只记 out_of_taxonomy_observation(七族之外只记录,不进 yes gate,不改族定义)。

## 构造性注记(pack 级)
- 本批 24 案场景**未携带 answer_spec**(0/24):依赖「无 spec→fail-closed」的完成/状态发现(答对却 needs_review、verified_complete=False、ready_to_confirm 不终结等)属构造性现象,按 guide §5 标 fixture-limited / non-attributable,不算七族 failure、不进 headline;
- 与 spec 无关的跨轮问题(重复未知化、事实改写、归因错误、支持失配等)照常标注。

## 清单(hash 序 = cert C24 封存序)
01. `small_lecturer_teaching_context_shadow_pilot_20_stability_age`
02. `small_lecturer_teaching_context_shadow_pilot_20_stability_probability`
03. `small_lecturer_teaching_context_shadow_pilot_20_stability_angles`
04. `small_lecturer_math_gold_b2_rope_unit_app_alternative_method`
05. `small_lecturer_math_gold_b2_unit_rate_misconception_repair`
06. `small_lecturer_math_gold_b2_rope_unit_app_misconception_repair`
07. `small_lecturer_math_gold_b2_rope_unit_app_complete_reasoning`
08. `small_lecturer_teaching_context_shadow_pilot_20_stability_unit_conversion`
09. `small_lecturer_teaching_context_shadow_pilot_20_stability_division_remainder`
10. `small_lecturer_target_mode_v3_regressions_target_v3_understood_image_not_vision_failure`
11. `small_lecturer_teaching_context_shadow_pilot_20_stability_ratio`
12. `small_lecturer_math_gold_b2_circle_area_alternative_method`
13. `small_lecturer_math_gold_b2_unit_rate_support_boundary`
14. `small_lecturer_math_gold_b2_heldout_rope_unit_app_support_boundary`
15. `small_lecturer_teaching_context_shadow_pilot_20_stability_word_problem`
16. `small_lecturer_target_mode_v3_regressions_target_v3_coordinate_first_question_alignment`
17. `small_lecturer_math_gold_b2_fraction_multiplication_alternative_method`
18. `small_lecturer_math_gold_b2_circle_area_support_boundary`
19. `small_lecturer_teaching_context_shadow_pilot_20_stability_decimal_multiply`
20. `small_lecturer_math_gold_b2_heldout_fraction_multiplication_misconception_repair`
21. `small_lecturer_math_gold_b2_unit_rate_complete_reasoning`
22. `small_lecturer_math_gold_b2_circle_area_support_boundary_hard_pressure`
23. `small_lecturer_teaching_context_shadow_pilot_20_stability_triangle_area`
24. `small_lecturer_teaching_context_shadow_pilot_20_stability_equation_parentheses`
