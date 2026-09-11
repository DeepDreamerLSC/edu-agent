# WS4 第 1 条 · 守卫替换粒度与收束轮误判(M2 遗留缺陷)评测报告

> 依据:#165 WS4 第 1 条 + #152 follow-up(#164 的已知代价);缺陷登记于 #152(15:46 评论)。
> 工件:`edu_agent/evals/artifacts/ws4-guard-granularity/`(before/after 两帧 P 口径 + crush-repro)。
> 基线:`4232fda`(post-#164 main);改动:① 处置粒度 ② 陈述判据(见 §1)。

## 0. 口径自述

- **P 口径帧**(`scripts/tuning_round.py --out`,11 场景 = 夜评同口径 P(gate 冻结 wiring),
  tutor=qwen3_vl_8b、judge=mlx_27b 本机;两帧同晚先后跑,判据/基线一字未改。
- **无答案护栏**:评测侧 KernelSubject 只传题面/年级/answer_status(与夜评同);
  模型 `start()` 自规划的 steps 即 `_known_answer` 的阶梯末级兜底来源。
- **needs_review 判据**:`finish()` 在非 `ready_to_confirm` 态返回 needs_review;
  该状态与「未完成」在 judge 的 termination/pacing 维度直接扣分。

## 1. 两项改动

**① 处置粒度(不再整轮换模板)**。命中未说出的方法词时,原实现一律
`safe_text = _ELICIT_TEMPLATE` + 强制 `ready_to_confirm=False`——连本轮引导/确认语义一起丢掉。
现改为 `_repair_feeds_method()` 三级处置:
1. **重生成**(既有 `_regenerate` + 新 `_FEEDS_METHOD_CRITIQUE`:保留本轮作用、只是不点名);
2. **确定性脱敏**(`_mask_hit_tokens`:只把命中词换「这种方法」,学生已说的词保持点名);
3. 模板兜底(理论上不可达:词表无互为子串项)。
埋点新增 `mode`(regenerated / masked / template)与既有 `{guard, rule_ids, original, regenerated}`
并存;`regenerated=True` 的两种处置**不再连坐 `session.stuck`**(修好 ≠ 硬降级)。

**② 末轮例外:学生已陈述终答的轮次不推向 needs_review**。两条同源修正:
- `_answer_focus_numbers()`:「是否已陈述」判据用**答案数字 − 题面已给数字**的结论数字;
  实测(`8 - 5 = 3` 型阶梯末级)答案数字含题面给定的 8,学生收束轮永不复述 → 判据恒 False。
  兜底:剔完为空则退回原集(fail-closed)。
- 命中代喂时**仅当学生尚未陈述终答**才强制 `ready_to_confirm=False`。
- 分工说明:`_drift_sources` 的**漂移池**仍用全量 `_answer_numbers`(凡能泄露答案的数字都算),
  两者口径不同、各有依据,已在注释里写清。

## 2. 帧证据:P 口径 11 场景 A/B

| 场景 | R1 | R2 | before(main) | after(本 PR) | 判定 |
|---|---:|---:|---:|---:|---|
| equation_complete_reasoning | 8 | 8 | 12 | 12 | 达标 |
| chicken_rabbit(dialogue) | 6 | 9 | 8 | 8 | 不劣 |
| equation_subtract | 7 | 7 | 12 | 12 | 达标 |
| fraction_addition | 3 | 4 | 11 | 11 | 达标 |
| triangle_area | 3 | 3 | 7 | 7 | 达标 |
| word_problem | 11 | 5 | 11 | 11 | 不劣 |
| T:chicken_rabbit | 5 | 5 | 8 | 8 | 达标 |
| T:equation_subtract | 4 | 4 | 12 | 12 | 达标 |
| T:fraction_addition | 3 | 4 | 11 | 11 | 达标 |
| T:triangle_area | 2 | 3 | 7 | 7 | 达标 |
| T:word_problem | 11 | 8 | 11 | 11 | 不劣 |

- **逐场景零变化**(分数逐项相同;均值差两帧同为 +4.41;json 一次通过率两帧 100%)。
- **验收「chicken_rabbit 的 needs_review 消失」✓**:

| 帧 | final_state 普查 | 守卫命中 |
|---|---|---|
| before | chicken_rabbit **×2 = needs_review**;其余 completed | `premature_confirm` ×2(chicken_rabbit)+ `answer_leak` ×2(triangle) |
| after | **全部 completed**(chicken_rabbit 也 completed) | `premature_confirm` **×0**;`answer_leak` ×2 不变 |

命中原句(before):学生末轮「所以兔有10除以2等于5只,鸡有3只,检查5乘4加3乘2等于26。」→
模型确认「你算得完全对!5只兔和3只鸡…」→ 闸误触发 → 换成「…那我们来检查一下…」→ 剧本耗尽 →
needs_review。after:同句确认**原文放行**、`ready_to_confirm` 保持 → completed。

## 3. 帧证据:压分复现(#152 config ③ 的机制隔离)

见 `crush-repro/README.md`(含注入文本与运行方式)。**同一配置**两棵树对照:

| 树 | final_state | 总分 | 六维 |
|---|---|---:|---|
| before(main) | **needs_review** | **5** | 1/2/2/0/0/0 |
| after(本 PR) | **completed** | **12** | 2/2/2/2/2/2 |

**验收「原被压到 3 分的场景回到 ≥12」✓**(#152 记 3 分,本配置隔离守卫后 main 5 分 → 修复后 12 分)。
更重的注入(强制每步点名、同一 system 提示两棵树同注入)另测一次:main 1 分/needs_review →
本 PR 10 分/completed,收束轮走 `mode=masked`(「你用**这种方法**…真棒!」)——该配置自身污染
首问/总结(#152 因 B),故不作达标口径,只作**脱敏路径**佐证。

## 4. 专测(断言即规格;+5 net,2 条重命名,**无删除**)

- `test_gate_allows_confirm_when_student_stated_conclusion_numbers`(题面数字不计入)
- `test_finish_completes_instead_of_needs_review_after_stated_answer`(验收口径)
- `test_gate_still_blocks_when_student_only_restates_given_numbers`(反向保护:只说题面数字仍拦)
- `test_method_feed_hit_regenerates_and_records_event`(路径 + `mode` 埋点 + 不落 stuck)
- `test_method_feed_hit_masks_only_unsaid_tokens`(脱敏只隐未说词、已说词保点名)
- `test_feeds_hit_keeps_confirm_when_student_stated_answer`(末轮例外)
- 重命名:`test_method_feed_swap_records_original_event` → `..._regenerates_and_records_event`;
  `test_reply_replaces_method_feed_with_elicit_and_keeps_open` → `test_reply_repairs_method_feed_and_keeps_open`

## 5. 复现命令

```bash
# before 帧(post-#164 main=4232fda 检出的工作树里):
.venv/bin/python scripts/tuning_round.py --out <分支树>/edu_agent/evals/artifacts/ws4-guard-granularity/before
# after 帧(本 PR 分支工作树里):
.venv/bin/python scripts/tuning_round.py --out edu_agent/evals/artifacts/ws4-guard-granularity/after
# 压分复现:按 crush-repro/README.md 在两棵树各注入一行(逐轮提示)、跑同一个 equation 场景 + judge
```

## 6. 边界与未做

- **未改**:判据/基线/数据集/`baselines/`/夜评口径一字未动;`scripts/*.py` 零改动
  (只运行既有工具);P 帧与夜评可比。
- **测试比**:1.27 → 1.28(本 PR 净增测试多于代码;`#97` 的「先精简再翻闸」不受影响)。
- **本单不含**(顺次在 WS4 其他条目):揭示路径软化(#165 第 2 条)、逐轮列入夜评(#146 M2)、
  提示阶梯 #107(#146 M3)、弧线 adherence 采集不评判(#146 登记)。
- **词面边界仍在**:学生「找公分母」/教师「通分」这类词面差异按词面判仍拦(派单红线:不放宽判定),
  逐条定性见 #161 报告 §2。
