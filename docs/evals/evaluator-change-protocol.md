# Evaluator Change Protocol v1 — 评测器变更治理(#537 M5-D)

授权:#537 Architect Gate(2026-10-05)——把 M5 验证出的 evaluator-change 安全边界
冻结为长期协议。**目标不是让 Judge 更聪明,而是限制 Judge 能改什么。**

适用面:任何 **rubric / judge prompt / scorer / grader model / scoring topology /
dimension ownership** 变更。Product(小讲师 agent)改动不在本协议面内。

## 一、四问协议(任何 evaluator change 进实验前必答)

| # | 问题 | 机械落点(不依赖「prompt 里写不要变」) |
|---|---|---|
| ① | **哪些 dimension 有权变化?** | packet `change_scope.requested_dims` ⊆ Dimension Ownership Registry 的 allowed(mutable)集;**未声明 = 无 change right**。validator 对照 `edu_agent/evals/rubrics/dimension-ownership.yaml` 重算 registry sha 比对,漂移即拒 |
| ② | **哪些 dimension 必须保持?** | locked 面由 baseline anchor + 机械断言保证:packet `anchored_comparison` 逐案逐字段 `anchored == baseline` 锁定值(`scripts/anchored_calibration.py` 冻结/组装不变量,validator 复核);locked 集必须恰为 registry locked 集 |
| ③ | **如何证明没有 masking?** | challenge/tension flags:`flags.jsonl` 实际行集 == anchored-arm 检测器发散案集 == packet 申报集(三方相等,零静默);**locked 张力只能路由新 calibration cycle,不能被 candidate 值静默吸收;verdict 变好本身不算成功证据**(validator 只披露 verdict movements,不作成功判据)。负保护:old=fail 案必须全部申报且与冻结 old 臂 verdict 三方一致 |
| ④ | **如何获得 promotion?** | frozen evidence identity(全工件 sha256 链)+ baseline/candidate Scoring Identity + anchored comparison + negative protection set + human review + **human promotion key**。机器验证只到「结构完备」,批准位只在人手里 |

四问的机器载体 = **promotion packet** + **确定性 validator** + **CI 完备性卡口**
(下 §三),人裁步骤在 §四 Calibration Cycle 流程。

## 二、四条长期边界(#537 Architect Gate 原文)

1. **Validator ≠ Approver**——`scripts/validate_promotion_packet.py` 只验 packet
   完备性与身份一致性;packet 的 `human_promotion.decision` 在机器验证面**恒为
   null**,非空即拒。validator 全部输出不存在 approved 字样,唯一肯定结论是
   `structurally complete, awaiting human key`。不存在任何自动 promotion 路径。
2. **Registry change 是 meta-change**——改 dimension ownership 本身必须开新
   calibration cycle,不允许在 candidate PR 里顺手解锁维度。validator 重算
   registry sha256 与 packet 冻结值比对,漂移即拒;`anchored_calibration.py` 的
   baseline 装载同样核对 registry 链(改 locked 维没另开 cycle 即拒)。
3. **Evidence 不随尺改写**——ruler/scorer/model 变化优先 **same-evidence
   re-score**(冻结 judge 行零调用复用,历史先例:M5 全系);packet v1 的
   `execution_identity.product_rerun` schema 上恒为 0。只有 Measurement Contract
   真缺 evidence 才允许新采集,且不走在本 packet 面内。
4. **Scoring Identity ≠ Execution Identity**——换尺/换 grader 不触发 Product
   rerun。packet 分别落 `baseline_scoring_identity` / `candidate_scoring_identity`
   (ruler sha / SCHEMA sha / verdict 规则 / judge 面)与 `execution_identity`。

## 三、Promotion packet(机器可读变更申请)

- **Schema**:`docs/evals/promotion-packet.schema.json`(JSON Schema 2020-12;
  packet v1 = `evaluator-promotion-packet/1`)。
- **示例**:`tests/evals/fixtures/promotion-replay/m5-b2/packet.json`——M5-B2
  PASS 资产的合规重放件(见 §六)。
- **Validator**(确定性、零模型调用):

```bash
uv run python scripts/validate_promotion_packet.py <packet.json> \
  [--registry edu_agent/evals/rubrics/dimension-ownership.yaml]
```

  退出码 0 = `structurally complete, awaiting human key`(唯一肯定输出);
  1 = fail-closed,逐条列 FAIL。缺 frozen evidence / identity / negative
  protection / human 位任一项即 FAIL(#537 Exit 2)。
- **CI 完备性卡口**(`scripts/pr_gates.py` 第六门,#537 M5-D 授权的最小面):
  PR 触碰 `edu_agent/evals/rubrics/`(rubric 量具)或 judge 面
  (`edu_agent/evals/judge.py`、`edu_agent/evals/s2_judge.py` 判分执行面)而
  PR body 缺 `promotion-packet:` 行(指向合规 packet)→ pr-gates 失败并打
  `evaluator-change` 标签(亮到合并时刻,同 structural/calibration 门)。
  该门只查「packet 引用存在」,不验内容——内容验证走 validator,批准走人;
  门规则来自 main(issue #24:被审分支不能携带自己的门)。

## 四、Calibration Cycle 流程

```
┌──────────┐   ┌──────────────┐   ┌────────────────────┐   ┌──────────────┐   ┌───────────────┐
│ L2 Finding│ → │ Calibration  │ → │ freeze baseline    │ → │ anchored     │ → │ promotion     │
│ (判分疑点) │   │ Hypothesis   │   │ (anchored_calibration│ validation    │   │ packet +      │
│           │   │ + change right│  │  --freeze-baseline) │ (run-anchored │   │ human key     │
│           │   │ (四问①声明)  │   │ locked 五维冻结     │  allowed 三维) │   │ (人裁,§二-1) │
└──────────┘   └──────────────┘   └────────────────────┘   └────────────────┘   └───────────────┘
                                         │ flags.jsonl:locked 张力 → 路由新 cycle(不静默)
                                         ↓ registry 变更?→ meta-change → 重开 cycle(§二-2)
```

操作正本见 [docs/evals/anchored-calibration.md](anchored-calibration.md)(#535
primitive:冻结/活评/组装/flag 通道工件与退出码)。本协议在其上只加一层:**cycle
收口时必须组装 promotion packet 并过 validator**,然后才进入人裁。Change Right ≠
Change Approval(#535 约束三)在本协议下机械化——packet 结构完备也不构成批准。

## 五、锚链:#535 → #536 → #537

- **#535 M5-A**(2026-10-03,FAIL):Measurement Contract enrichment——B 案归因
  翻转 10/10 但 A 失保护(application_table 被 socratic 1→2 联动抬成 review);
  **富集过宽**。教训→四问②③:locked 面不能靠边界条款,要机械锚定。
- **#535 M5-A'**(2026-10-04,FAIL):维度隔离仍失守,3 案 socratic_followup
  locked 漂移(projection guard FAIL)→ 升级条款:**当前 ruler 架构不适合局部
  修正,需重新设计 scoring decomposition**。
- **#535 M5-B**(2026-10-04,FAIL→#536 EF-001):decomposed topology 在相同
  evidence、相同语义指令下 **7/17 locked 维确定性漂移**(socratic×5、
  math_integrity×2;temp-0 逐字节稳定排除噪声)——EF-001「Holistic Ruler
  Topology Drift」(#536 登记)。教训→四问①的 registry 与 §二-2:topology 是
  ownership 问题,不是文案问题。
- **#535 M5-B2**(2026-10-04,PASS):Baseline Anchored Dimension Isolation——
  locked 五维 = baseline 机械取值,allowed 三维活评;locked 不变量 17/17,
  challenge 张力 7/17 全走 flag 通道(不静默)。→ 生产化 primitive
  (#535 comment 5981592681 裁定,PR #538)。
- **#537 M5-D**(本协议):组合上述资产为治理层。**M5-C(self-consistency)
  仍 PARKED。**

## 六、历史重放验收(#537 Exit 5)

`tests/evals/fixtures/promotion-replay/`(冻结重放语料,零模型调用;重建口径
见目录 README)对四个历史实验重放 validator:

| corpus | 历史判定 | validator 判定 | 拒因 |
|---|---|---|---|
| `m5-a`(contextual candidate) | FAIL(富集过宽·A 失保护) | FAIL | locked 漂移 6 处(probability socratic/grade_fit/math_integrity、application_table/open_27/circle_area socratic 1→2) |
| `m5-ap`(v2 维度隔离) | FAIL(隔离失守) | FAIL | locked 漂移 3 处(application_table/open_27/circle_area socratic_followup) |
| `m5-b`(decomposed topology) | FAIL(EF-001) | FAIL | locked 漂移 7 处 **+ 7 案检测器发散零 flag(静默吸收)** + 申报不实 |
| `m5-b2`(anchored validation) | PASS | `structurally complete, awaiting human key` | ——(locked 不变量 17/17;7 案张力全披露;4 案 verdict movement 经 allowed 维,如实披露不作成功证据) |

即 #537 Exit 5 的两条:**正确拒绝曾经的 overreach candidate;接受结构完整的
anchored validation packet**。合同测试 `tests/evals/test_promotion_packet.py`
固化以上判定(含 human 位非空→拒、registry 漂移→拒、evidence 篡改→拒)。

## 七、红线速查

- validator 不拥有 promotion authority;任何输出不含 approved;`decision` 位
  只由人在 promotion 步骤填写。
- M5-D 不改生产 rubric / judge prompt / grader model;**不自动切换默认 ruler**
  (协议完成 ≠ 任一 candidate 获生产批准;anchored 非默认路径,#535 约束一)。
- 不为过协议门放宽 #490 identity 或 anchored invariants(#537 禁止项)。
- registry / 本 schema / 本文档 / validator / 卡口均为治理级改动(触碰即过
  structural + evaluator-change 卡口,须人批)。
