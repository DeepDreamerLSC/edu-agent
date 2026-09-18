# 现有测试盘点:V1 改动不能破的既有断言(#333 备料任务 3)

范围:`_soften_step_text` / `_reveal_stuck_hint` / `_answer_focus_numbers` 及相邻
(`_next_step`/`_support_move`/`_known_answer`)。V1 实现是在 `_reveal_stuck_hint` 内
**加**锚(裁定:七条件全过才给),以下锁面全部必须原样保持。

## tests/teaching/test_kernel_restate.py(揭示/复讲主线,15+ 锁)

| 锁面 | 测试 | V1 约束 |
|---|---|---|
| elicit 请复讲(零模型,guard `{branch: elicit, hint_level: 0, turn}`) | `test_answer_hit_elicits_restatement_without_model` 等 5 件 | 不动 elicit 面 |
| ready_to_confirm 禁 elicit | `test_confirm_state_blocks_elicit` | V1 D 条件同源,不得放宽 |
| 阶梯推进 + 互异(`hint_level` 1/2,文本不连 repeat) | `test_repeat_fallback_advances_ladder` 等 2 件 | 锚不得改变推进语义 |
| **cut/mask 动作化 9 形态**(分句边界收回/序数形态拦截#185/导出值拦截#185/answer_masked/multi_hit_masked/裸数字丢弃/披露框架丢弃) | `_reveal_after_repeat` parametrize | V1 锚是**加字段**,不得绕过 soften:带锚文本仍须过动作化 |
| `_answer_focus_numbers` 口径(答案−题面;题面数放行;steps 末值兜底) | `test_reveal_keeps_question_numbers_when_answer_falls_back_to_steps_value` | anchor=step−answer_pool 与 focus 口径**两回事**,不得混用改动 |
| soften 路径埋点(cut/mask 可分,#241 行4) | `test_reveal_soften_path_tagged_in_guard_events` | V1 additive 键不得破坏既有键 |
| 整步弃用可辨识(`dropped: true` + NEEDS_REVIEW) | `test_dropped_reveal_step_is_flagged_in_guard_events` | 弃用轮无锚 |
| 防复读背板走阶梯(泄露兜底/代喂兜底 → reveal) | 2 件背板测试 | 背板路径同受 V1 七条件约束 |
| 代喂处置粒度(regenerated/masked 埋点) | `test_method_feed_hit_*` | 模型路径零例外不涉 |

## tests/teaching/test_kernel_invariants.py(终答不变量,硬锁)

- **终答文本只出现在 bottom-out / finish 两条路径**(VERDICT#6);确认/赞许轮不引述终答值。
  **V1 的锚是第三个合法披露点,实现 PR 必须同步改写该不变量注释与断言**(裁定授权),
  但 bottom-out/finish 语义不变。

## tests/teaching/test_answer_leak_guardrails.py(泄露网判定口径,13+ 锁)

- grounded/unverified 披露分界、已陈述值可复述、已知条件可指、复合方向不算句级泄露
  ——**答案泄露判定基线 `_known_answer`**(question.answer 优先,steps 末值兜底)是
  V1 answer_pool 的同源基线:不得单独改一处。

## tests/teaching/test_leak_gate_numeric.py(numeric.py 纯函数)

- `_question_numbers`/`_spoken_numbers`/`_answer_focus_numbers` 行为(含 fail-closed
  空集回全集)。裁定 Q7:**不改 numeric.py 归因**——V1 全部落 kernel 侧。

## 汇总:V1 实现的「不能破」最小集

1. soften 三路径(cut/mask/none)语义与埋点键;2. 阶梯推进与 bottom-out/finish 不变量;
3. elicit/support 触发判据与埋点形状;4. `_known_answer` 三处同源基线;5. numeric.py 零改动;
6. 防复读背板路径。新增面 = reveal 事件 additive 键(`anchor_numbers`)+ 七条件闸。
