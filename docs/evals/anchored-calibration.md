# Baseline Anchored Dimension Isolation v0.1 — 生产 calibration primitive

授权:#535 comment 5981592681(Architect 2026-10-04)——「primitive 接入生产 calibration
流程」;**不批** anchored 替换生产默认 ruler。工具 `scripts/anchored_calibration.py`,
登记资产 `edu_agent/evals/rubrics/dimension-ownership.yaml`,合同测试
`tests/evals/test_anchored_calibration.py`(确定性,零真实模型调用)。

## 是什么

候选 ruler 实验的**锚定校验面**:candidate 实验只被允许活评三个维度,其余五个判分
字段(三维 + 两个硬门)机械取自 baseline 冻结值,verdict 用生产 `verdict_from_scores`
重算(阈值不动)。效果 = 候选改动的影响被限制在登记为 mutable 的维度内,**结构性
不可能**通过暗中拉动 locked 维来「改善」分数(masking 防护的机械化)。

```
anchored final = { locked 五维 = baseline 机械取值(本 cycle immutable,零重判) }
               ∪ { allowed 三维 = candidate 活评(生产 judge_transcript 面) }
               → 生产 verdict_from_scores 重算(阈值不动)
```

## Calibration Cycle 流程

```
┌────────────────┐   ┌─────────────────────┐   ┌──────────────────────┐   ┌──────────────────┐
│ baseline ruler │ → │ candidate experiment │ → │ anchored validation  │ → │ human promotion  │
│ (生产默认判分)  │   │ (新 ruler/合同假设)   │   │ (本工具,唯一接入点)  │   │ (人裁,Change     │
│                │   │                       │   │ locked 维锁 baseline │   │  Approval)      │
└────────────────┘   └─────────────────────┘   └──────────┬───────────┘   └──────────────────┘
         冻结 judge 行(baseline.json + sidecar sha)      │ flags.jsonl:locked 张力
                                                          ↓ → 路由新 calibration cycle(不静默)
```

一个 cycle 的操作序:

```bash
# 1) 冻结 baseline(零模型调用;输入 = 冻结 judge 行 JSONL)
uv run python scripts/anchored_calibration.py --freeze-baseline \
  --cycle-id <cycle> --judge-rows <frozen-judge-rows.jsonl> --out-dir <dir>

# 2) 锚定活评(生产 judge 面;预算闸 fail-closed,默认 32)
uv run python scripts/anchored_calibration.py --run-anchored \
  --cycle-id <cycle> --cases <live-cases.jsonl> --out-dir <dir> [--budget 32]
```

工件(默认 `var/anchored/<cycle-id>/`):`baseline.json` + `baseline.json.sha256`
(sidecar)、`anchored-arm.jsonl`(逐案 locked/allowed/anchored/verdict delta/
challenge_detector)、`flags.jsonl`(张力披露,空也落盘)、`anchored-summary.json`。
退出码:0 = 过闸;非零 = fail-closed(schema/immutable/sidecar sha/registry 链/预算/
组装不变量任一不过,半轮不落盘)。

## Dimension Ownership Registry

`edu_agent/evals/rubrics/dimension-ownership.yaml`(约束来源:#535 comment 5981592681):

| 字段 | owner | mutable | 语义 |
|---|---|---|---|
| first_question / socratic_followup / grade_fit | baseline | false | 锁定维:本 cycle 取 baseline 冻结值 |
| pacing / summary_mastery / termination | calibration_candidate | true | 活评维:candidate 实验可动 |
| answer_leaked / math_integrity | baseline | false | 硬门字段(verdict 直接入参),必须锁定 |

工具读 registry 驱动锁定集(不硬编码;覆盖集必须恰为生产判分面);`--freeze-baseline`
把 registry sha256 链进 baseline,`--run-anchored` 装载时核对——registry 漂移即拒。

## 三治理约束(#535 裁定原文)

1. **Anchored 非默认 ruler**——只活在 Calibration Cycle 内;工具必须显式
   `--cycle-id` 才运行,无任何生产调用方,不改现行 judge/rubrics 生产语义;
2. **Dimension Ownership Registry**——上表;**改 locked 维须另开 calibration
   cycle**(registry 变更 = 治理级改动,须人批);
3. **Change Right ≠ Change Approval**——生产 ruler change right ≠ 批准替换;后续任何
   candidate 仍需 frozen evidence + anchored comparison + human review + negative
   protection set 才可能获 promotion。

## 与 EF-001 / #536 的关系(M5 证据链)

M5 三轮失败定因了「prompt topology 本身造成确定性漂移」(EF-001,#536):同一对话在
不同 judge 输入拓扑下 locked 维取值漂移。M5-B2 以维度隔离破局——**承认拓扑会漂,就
把不允许漂的维度锚死在 baseline**——17 案 frozen evidence 上 PASS(locked 不变量
17/17,challenge 张力 7/17 全部走 flag 通道披露而非静默吸收)。本工具是 M5-B2 实验
资产(/tmp/m5b2,只读参考)的生产化复刻:judge 活评复用产线面,判分语义零改动。
后续 M5-D(Evaluation Change Governance)将把本 primitive 组合进 evaluator change
protocol。

## 红线速查

- anchored 不是任何生产默认路径;不替换 v3.3 默认 ruler(#535 不批)。
- 冻结面零模型调用;活评走生产 judge 面(温度/Schema/rubric 产线默认)。
- baseline 篡改(sidecar sha 不符)→ 非零退出;flag(locked 张力)→ 如实披露、
  路由新 calibration cycle,不改用 probe 值、不静默、不失败。
