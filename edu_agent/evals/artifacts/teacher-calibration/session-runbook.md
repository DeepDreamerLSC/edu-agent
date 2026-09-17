# 教师会执行手册(session-runbook)

**目的**:让 Lane H 盲评会「即发即开」——主持人(AM/PM 代)按本单执行,不临场决策。
**本单只做执行编排**;判读规则/协议已冻结(`teacher-review-baseline.md` Phase A、
`promotion-comparison-protocol.md` Lane H、`teacher-promotion-gate-v1.md` 第 3 步),
会中**不改任何规则**。配套件:同目录 `teacher-onboarding.md` / `practice-cases.md` /
`scoring-template.md`(校准包 #328)。

---

## 0. 角色与物料总览

| 角色 | 谁承担 | 职责 |
|---|---|---|
| 教师(T1…Tn) | 用户确认到位的教师 | 打分 + pairwise 定性 + 证据;不做任何裁决 |
| 主持人 | AM/PM 代 | 发料/计时/回收/数字化;**不解盲、不裁分歧** |
| 程序侧(Phase B) | AM/PM 代(会后) | 解盲映射、Lane H 判定汇总、与 Lane M 合流 |

**盲评纪律一句话**:教师全程只接触 `pack/` 内随机标号的 A/B transcript 与空白 B 表;
`mapping.json`(解盲钥匙)与参考读数**永不进教师手**(练习段参考读数仅在打完自评时开放)。

---

## 1. 议程单(含时间预估;总时长 ≈ 2.5–3h,可拆两场)

| 段 | 时长 | 内容 | 材料 |
|---|---|---|---|
| ① 会前自学 | ≈10min(可提前) | 读 `teacher-onboarding.md` 一页纸:三家族 0\|1\|2 锚点 + 打分表用法 + pairwise 规则 | onboarding |
| ② 校准段 | **30–40min** | 5 练习案(C40/C26/C25/C11/C36)独立打分 → 打完**才**翻参考读数对答案,重点看分叉点 | `practice-cases.md` + `scoring-template.md` A 表 |
| ③ 盲评段 | **80–100min**(11 案 × 6–10min) | 逐案 A/B pairwise(见 §3 节奏建议) | `gate-04-v2/pack/*.md` + `scoring-template.md` B 表(每案一张) |
| ④ debrief | ≈15min | 三问(见 §4) | 无 |

**节奏建议(盲评段)**:每案 6–10min——A 打三家族(2–3min)→ B 打三家族(2–3min)
→ 逐家族 pairwise + 证据(2–3min);已知限案(C40/C11)允许 +2min;第 6 案后休息 5min。
**不催案**:宁可超时,不可压缩证据栏——`worse` 无证据按冻结规则判 `same`(防假红),
而仓促填证据会制造假红。

---

## 2. 物料核对清单(会前逐项打勾,主持人执行)

**教师手包(仅这些)**:
- [ ] `teacher-onboarding.md` ×1(会前发或自学)
- [ ] `practice-cases.md` ×1(校准段;参考读数区叮嘱「打完才翻」)
- [ ] `scoring-template.md` ×1(A 练习表 + B 空白表模板;盲评段按 B 表每案复印 1 张)
- [ ] 盲包 11 案:`edu_agent/evals/artifacts/gate-04-v2/pack/*.md`(随机标号 A/B)——
      发前抽查:**包内无 baseline/candidate 字样、无分数、无 mapping 线索**
- [ ] 计时器 ×1;空白草稿纸

**主持人/程序侧持有(教师不可见)**:
- [ ] `gate-04-v2/mapping.json`(解盲钥匙;仓内属程序面,**不随教师物料发放**)
- [ ] 判读钥匙(练习案参考读数 = `practice-cases.md` 各案末 + `slice-baseline.jsonl`;
      盲评段主持人也不向教师提及任何机器读数,防锚定)
- [ ] 回收信封/场外归档目录(见 §5)

**版本核对**:
- [ ] 校准包与盲包为同源版本(本 runbook 基于 #328 分支 `artifacts/teacher-calibration`
      @ ffaef75;gate-04-v2 = ⑦门第四跑,机器面 checks **22/22** + Lane M **11/11** 已绿)
- [ ] `practice-cases.md` 打印件含参考读数区(C36 案注明「替代 C35,#310 人裁」)

---

## 3. 盲评段执行程序(逐案循环)

1. 主持人发本案 B 表 + `pack/` 对应案(教师报当前序号,主持人翻页发,防跳读);
2. 教师独立填:三家族 × A/B 各 0\|1\|2 → 逐家族 pairwise(`A worse`/`B worse`/`same`)
   → 具体证据(引原话;**worse 必填**,新增或明显加重退化);
3. 教师在表头记**开始/结束时间**(§5 每案耗时);
4. 主持人即收即点数,当场确认 11 案 × 教师数齐,缺即补;
5. 全程不讨论、不互相看表;疑问记 debrief,会中不裁。

**记录口径(只定留痕,判读规则零改动)**:

- **教师间分歧**:各教师表格**分开保留**(T1/T2… 编号),不平均、不现场对表、
  不裁决;分歧案在回收清单上标「分歧」(哪案哪家族哪侧不同),留待 Phase B
  程序侧按既有协议处理——教师侧结论以**每人一份**原始记录为准;
- **abstain(教师主动声明无法评)**:pairwise 栏记 `abstain` + 一句原因;
  `abstain` 是**记录态**,不折算 same/worse/better(与冻结规则「证据不足判 same」
  是两回事——那是评了但证据不够);该案标「缺教师信号」,是否补评由程序侧按
  fail-closed 纪律另定(本单不裁);
- **每案耗时**:表头起止时间,会后仅用于节奏复盘与后续场次排期,
  **不作质量门**(慢≠错,快≠对)。

---

## 4. debrief(≈15min;只收过程反馈,不改规则)

三问,逐人口头+记录:
1. 哪些案你最不确定?卡点是什么(家族定义?证据找法?A/B 都像?)?
2. 与练习段参考读数的分叉点(C40/C11 机器稳定 2、期望 0),你的判感如何?
3. 流程负担:每案时长/表格结构/材料顺序,哪里可减?

Debrief 记录**同 §5 场外归档**;产出只用于下场会编排,不回灌判读规则。

---

## 5. 收集程序(回收 → 数字化 → 归档;治理②口径)

**治理铁律**:真实教师数据(身份、笔迹、原始表、debrief 原话)**不进本公开仓**
(治理②);入仓的只有**摘要级判定计数**(每案三态 + abstain 数,无教师可识别信息)。

1. **回收**:散会当场清点(11 案 × 教师数),信封密封,主持人保管;
2. **数字化**:主持人事后(建议 24h 内)把 B 表转录为私密结构化文件
   (字段 = B 表列:案/A 三家族分/B 三家族分/逐家族 pairwise/证据/耗时;
   教师以 T1/T2… 编号,**不记真名**),存 `calibration-private/teacher-calib/<date>/`
   (场外);
3. **自查**(数字化后、交程序侧前):每案分数非空、pairwise 三态合法、
   `worse` 行证据非空、abstain 行有原因;缺项标出交主持人补录;
4. **归档**:原始纸质/扫描件同目录存档;场外目录清单(日期/教师数/案数)
   可写进回执,文件本体不入仓;
5. **移交**:数字化文件交程序侧(= 主持人)做 Phase B 解盲与 Lane H 汇总。

---

## 6. 双绿判定衔接(引用既有协议,零新规则)

**本会只产出 Lane H 的教师侧原始信号;合流判定全部在程序侧按已冻结协议执行**:

```
盲评会(本单)→ 教师原始表(场外)→ 数字化自查 → Phase B 解盲(mapping.json)
                                        ↓
                    Lane H 判定:逐家族 pairwise ≠ worse(且 worse 无证据→same)
                    [promotion-comparison-protocol.md Lane H 规则]
                                        ↓
      Lane M(gate-04-v2,已绿):checks 22/22 + Lane M 11/11(lane-m-result.json gate=pass)
                                        ↓
              family green = 机器回归 none AND 教师 pairwise ≠ worse  → 双绿
              [teacher-promotion-gate-v1.md 第 3 步 + promotion-comparison-protocol.md Final]
                                        ↓
                        双绿 → promotion(#293 主线 flow:held-out + checks + 人抽审)
```

- Lane M 侧**无需教师参与**:`gate-04-v2/lane-m-result.json`(gate=pass,11/11)与
  `checks.json`(22/22)已是入仓工件,教师会不触碰、不重算;
- 已知限案(C40/C11)教师独立判断 = 盲区最终裁定面(机器分只记录变化、不据此 fail);
- 已知限 delta≤−2 的「待复核」解除:需 Lane H 明确 same/better 理由(冻结规则,
  教师按 B 表正常填写即覆盖);
- 合流结果(每案三态计数 + family green 与否)由程序侧写入回执/工件,**不含原始教师数据**。

---

## 附:执行检查点速查(主持人卡片)

会前 → §2 清单全勾 | 段间 → 收齐清点、abstain/分歧即时标注 | 散会 → §5 当场清点密封 |
会后 24h → 数字化 + 自查 + 移交 | Phase B → 解盲 + 合流 + 回执(摘要级)
