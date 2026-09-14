# judge v2 · 52 案验收 rescore(#253 点火件,2026-09-14)

**验收判定:未过 —— 门 17/20,3 案不符(C25/C46/C51),原始输出原样报回,未修、未重试、未跑 93 案全量**(派单纪律:任何一案不符即停)。

- 判卷依据:`/root/calibration-private/expectation表.csv`(52 行,期望值列冻结)+ README §3 取数表
- 判分器:judge rubric v2(PR #260,main `3a650e5`);judge 模型 mlx_27b(8301,Qwen3.5-27B-4bit),单遍 primary,temperature=0
- **judger_sha256 = `a567948cecd5e40bbdbf7429bb3d4801ec0759e1518622cf1a146e27b2dbad52`(新指纹首次落位)** = main `3a650e5` 的 checks.py+judge.py 哈希;本工件跑批 HEAD 即 `3a650e5`(manifest.identity 为证),判分器与 main 逐字一致
- 输入:49 案 = corpus-round-v2 存档轨迹(collect `cases-20260914T032228Z-bda5`)× 题面(cases.jsonl);C15 = 挑战案 JSON;编造51 = fix112 `…__r1.json`;构造52 = README §2 落 `/tmp/constructed_52.json`。judge-cases.jsonl = 52 案实际输入全文(可复算地基)

## 验收门:20 案逐字段比对(14 硬期望 + 6 已核 PM 抽验)

| 案 | 段 | 字段 | 期望 | 实际 | 判定 | 推导 verdict |
|---|---|---|---|---|---|---|
| C02 | P2 | summary_mastery | ≥1 | 1 | ✓ | — |
| C06 | P1 | answer_leaked | false | false | ✓ | — |
| C12 | P1 | answer_leaked | false | false | ✓ | — |
| C14 | P1 | answer_leaked | false | false | ✓ | — |
| C15 | P3 | math_integrity | 0 | 0 | ✓ | fail ✓ |
| C17 | P2 | summary_mastery | 2 | 2 | ✓ | — |
| C20 | P3 | math_integrity | 0 | 0 | ✓ | fail ✓ |
| C24 | P2 | summary_mastery | 0 | 0 | ✓ | — |
| **C25** | **P2** | **summary_mastery** | **≥1** | **0** | **✗** | —(verdict=review) |
| C26 | P3 | math_integrity | 2 | 2 | ✓ | — |
| C31 | P1 | answer_leaked | false | false | ✓ | — |
| C35 | P1 | answer_leaked | true | true | ✓ | fail ✓ |
| C37 | P1 | answer_leaked | false | false | ✓ | — |
| C39 | P3 | math_integrity | 0 | 0 | ✓ | fail ✓ |
| C41 | P3 | math_integrity | 2 | 2 | ✓ | — |
| C43 | P1 | answer_leaked | true | true | ✓ | fail ✓ |
| C45 | P3 | math_integrity | 2 | 2 | ✓ | — |
| **C46** | **P2** | **summary_mastery** | **1** | **2** | **✗** | —(verdict=pass) |
| **C51** | **P3** | **math_integrity** | **0** | **2** | **✗** | fail ✓(经 answer_leaked=true 否决,非把关) |
| C52 | P1(构造) | answer_leaked | true | true | ✓ | fail ✓ |

## 3 案不符 · 原始输出(原样,不修)

**C25** `distance_speed_alternative_method`(期望 summary_mastery≥1:总结框「关键转折是把2.5小时拆成2小时和0.5小时,分别计算再相加」实质总结在,不得无依据判 0):

- 六维:first_question=2, socratic_followup=1, grade_fit=2, pacing=1, **summary_mastery=0**, termination=1;total=7 → verdict=review
- summary_mastery 证据(judge 原文):「仍需注意的是,每小时60千米这个速度要始终用在每段计算里,不能漏掉单位换算。」——judge 以「注意事项」作总结证据,未引用总结框;P2 新注「注意事项不能替代学生实际学习证据」被读成「注意事项即全部总结」
- answer_leaked=false,math_integrity=2

**C46** `stability_age`(已核 PM 抽验期望 summary_mastery=1:总结框把导师轮3引入的除法判断记为学生本人关键证据=误归因;学生真实独立贡献仅轮5验证步):

- 六维全 2(12/12)→ verdict=pass;**summary_mastery=2**
- summary_mastery 证据(judge 原文):「你通过理解'3倍'关系,正确判断要用除法,把36平均分成3份得到12,还验证了12×3=36,这一步完全正确!」——judge 按总结框面值记「有据掌握判断」,未穿透归因(除法判断出自导师轮3)
- answer_leaked=false,math_integrity=2;旧 judge 同为 12/12 pass(该维无变化)

**C51 编造51** `stability_fraction_addition__r1`(硬期望 math_integrity=0:导师「八分之一变成十二分之一」= 1/8≠1/12,自造改变解题结果的错误分母换算,补丁 0 档锚点「编造了错误的分母运算」):

- 六维:2,1,2,1,0,0;total=6;**math_integrity=2**;**answer_leaked=true** → verdict=fail(经否决路径)
- math_integrity 证据(judge 原文):「你把四分之三化成八分之六,这个转换是对的!因为四分之三等于八分之六…」——judge 抓住了正确的 3/4→6/8 换算,未引「变成十二分之一」编造句
- 边界注记(README §4):编造51 answer_leaked 本就「未钉死、只观察」——本跑该字段输出 true(导师轮4「八分之六加八分之一,等于八分之七」先于学生陈述 7/8,但学生前句已给等价未约分表达式),不判门;**门字段是 math_integrity,不符**

## 诊断面(非门,只报告)

- **audit verdict 一致率 29/50(58.0%)**(audit 过/待议/不及格 ↔ pass/review/fail):
  - audit=过(33 案)→ pass 18 / review 14 / fail 1
  - audit=待议(10 案)→ review 4 / fail 6
  - audit=不及格(7 案)→ fail 7(全部命中)
- **否决命中(answer_leaked=true)7 案**:C15 挑战案、C52 构造案、C20 `fraction_multiplication_alternative`、C21 `distance_speed_support_boundary`、C35、C43、编造51。其中 C35/C43/C52 为硬期望 ✓;C15/C20 与 README §4 边界备注的预期 false 相左(两案门字段均另过:math_integrity=0 ✓)——judge 对「格数分解/错误值不属终答泄露」的等价性读法偏严,备查
- **把关命中(math_integrity=0)5 案**:C15、C20、C39(三硬期望 ✓)+ C06 `equation_addition_complete`、C19 `parentheses_equation_alternative`。C06 audit=过,被新门压到 fail = 新判据的增量效应;C19 audit=不及格,把关方向与其一致(非门字段,报告备查)
- **summary_mastery=0 共 21 案**(P2 重写后该维显著收紧;C24=0 ✓ 防过矫正锚点本身成立,但 C25 误伤同向)——P2 的 0 档判定把「注意事项/模板句」当总结证据的读法是 C25 不符的直接原因

## 复算

```bash
# 重判(52 案,零 tutor 调用;judge 单遍 mlx_27b,需 8301 端点可达):
uv run python scripts/rescore_judge.py \
  --archive edu_agent/evals/artifacts/corpus-round-v2/collect/cases-20260914T032228Z-bda5 edu_agent/evals/artifacts/corpus-round-v2/cases.jsonl \
  --archive edu_agent/evals/artifacts/teaching-arc-fix112/after/F/M/collect/cases-20260910T063653Z-c9ae edu_agent/evals/artifacts/teaching-arc-fix112/after/F/M/cases.jsonl \
  --extra-case /root/calibration-private/C15挑战案例.json \
  --extra-case /tmp/constructed_52.json \
  --only <52 案清单(自 expectation表.csv case_id 列)> \
  --old-scores edu_agent/evals/artifacts/corpus-round-v2/collect/cases-20260914T032228Z-bda5/judge-scores.jsonl \
  --out <新目录>
# 判卷(门表 + 诊断):期望值冻结自 expectation表.csv,判卷脚本逻辑见本 README 表格
```

温度 0 但生成非确定端点偶有抖动;重跑个别案分数可能微动(稳定性口径属 #32 双评面,本跑未做)。52 案 judge 输入全文在 `judge-cases.jsonl`,逐案输出在 `judge-scores.jsonl` 与 `collect/judge-cases-20260914T151541Z-dfec/results/`(runner 台账),旧 judge 对照在 `comparison.jsonl`(编造51 无旧分,旧管线为盲判哈希 id 不同源)。
