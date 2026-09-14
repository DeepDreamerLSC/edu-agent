# corpus-round-v2 工件口径(#178;首个全量走判分器溯源指纹的轮次)

跑在 main `2c43754`(#248 合入点:训练集 120 teacher_confirmed)。复算命令:

```bash
sh scripts/corpus_round.sh \
  --corpus edu_agent/evals/datasets/small_lecturer_math_gold_candidates.json \
  --corpus edu_agent/evals/datasets/small_lecturer_math_gold_b2.json \
  --corpus edu_agent/evals/datasets/small_lecturer_teaching_context_shadow_pilot_20.json \
  --out edu_agent/evals/artifacts/corpus-round-v2 \
  --diff-from edu_agent/evals/artifacts/math-gold-v1/collect/cases-20260913T134402Z-3b59 \
  --concurrency 2
```

## 口径边界

- **批跑面 93 ≠ 训练集 120**(#248 审 P3 双口径):27 条 legacy 不在面——
  `small_lecturer_dialogue_scenarios.json` 3 条(v1 schema,corpus loader 不收)、
  `small_lecturer_shadow_scenarios_24.json` 24 条(v3 且无剧本,模拟器消费面)。
  门口径(raw=120)按 #238 裁定计;本工件实际覆盖 = loadable 93。
- **judger_sha256 = `440395a900bfdd09828c75ff8ffe211c8b80b0c9a5a6512eb90a2e882e6ed446`**:
  首个带判分器指纹的轮次;对照基线 math-gold-v1 无指纹 → report 自动注
  「基线无溯源」(#238 §5 首轮基线欠账,自本轮起每轮可断点比对)。
- cases.jsonl sha256 = `a26f7b725cf215b77a0b26f041d481b6b9e3da73e42e9966d6d964a8eb142e62`。
- **跨轮判定注意**:金标两件(gold 60 / b2 13)checks=无声明(只声明
  ready_to_record)⇒ diff 判定恒绿,跨轮信号要看 final_state 与 judge;
  pilot-20 带 checks,`rectangle_perimeter` 的「新增红」实为**跨 pilot 轮持续红**
  (corpus-round-v1 365c 同红;diff 基线 math-gold-v1 无 pilot 行,故记新增)。
- 成本:**调用数 514**(v1 同口径:start 93 + 学生轮 202 + finish 67 + 重生成 60
  + judge 92;另有 16 轮 schema 修复复检可见于 guard_events(v1 口径归上界)、
  网关内部重试 1-2 次/失败条不可见 ⇒ 上界 ≈ 532);墙钟 ~37 分钟(并发 2);
  1 条内容类失败(`fraction_addition_support_boundary`,schema_violation——
  与 v1 首轮的 content 失败同 case,台账 failures.jsonl 在案)。

## 三问读数(派单读数面;详细表在 report.md)

**a) b2 新 13 条首批**:completed 9 / needs_review 4;judge 3 pass / 1 review /
9 fail,均值 6.8/12(金标 60 均值 7.1,分轨序与 v1 一致:修复弧最高、边界弧最低)。
**硬压力轨**:三连「不会」压力全走确定性揭示阶梯(hint 1→2→3,模型轮 0),
`answer_leaked=False`——终答 50.24 全程未出现,**压力下不塌不泄,设计意图守住**;
needs_review 为弧线未走完的设计值;judge 3/12(pacing/summary/termination 低分
即「未完成教学弧」的直接后果,非泄漏)。

**b) pilot-20 促升后 vs 旧轮(corpus-round-v1 365c,2026-09-12)**:
final_state 19/20 completed 两轮一致(rectangle_perimeter 两轮均 needs_review,
持续红第 6+ 次复现);judge 总分 12/20 逐字持平,8 条变动(±1–2 四条,±3–4 三条,
离群两条:average 5→9 升、decimal_multiply 12→5 降);verdict 一致 14/20。
变动带与分诊结论(c5657191064:同输入异采样 → 生成面波动 3 分级)一致——
促升(金标落字段)不改剧本与装配,读数漂移归生成面。

**c) 分诊发现(讲题冒出题面外数字)复现率**:数值来源闸工件读数——
**71/278 模型轮(25.5%)首过产出题面外数字,涉及 40/93 case(43%)**;
共 96 个数字实例(answer 源 58 + hallucinated 源 38),**全部 gate=blocked** 进
修复漏斗(60 次重生成:泄漏族 50 + feeds_method regenerate 型 10),落到学生面的
文本经漏斗保证。注意边界:分诊 §3.2 的**语义重排族**(换分子/分母自造条件、
数字全在允许集内)本闸按构造不可见——该族的复现率不可由此测得,属已知盲区。

软化路径脚注(#241 行 4 首次生产读数):cut=1(pilot `equation_parentheses`
揭示 hint 同分句收回)/ mask=0 / dropped=0。
