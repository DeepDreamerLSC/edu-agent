# 泄露网 V1 锚/终答测试面备料(#333 裁定 c5717512971;PM 88ccdbcabde5da82)

零模型零 calls;只读数据集与既有工件,未跑 runner。三件套:
`classification.jsonl`(105 案分类)+ `seeds-anchor-v1.json`(Q5 第一层 A-D 种子)+
`coverage-inventory.md`(现有锁面);测试骨架 = `tests/teaching/test_anchor_reveal_v1.py`
(全 skip,实现 PR 激活)。

## 一、案面分类(静态可判面)

**提取口径**(复用 `numeric.py::_question_numbers`:ASCII 整数/小数,分数按两数):
- answer 数字集:canonical 字段 = pilot_20 `question.answer` / enriched12 `reference_answer.value`;
- 题面数字集:question 文本;
- **steps 各级 value 数字集:数据集不落盘**——session.steps 是运行期产物(runtime plan 经
  solver 校验后入会话;数据集 `steps` 字段是模拟器剧本分支,非数值解步;corpus 转录亦不
  序列化 steps)。**故裁定 A 类(可分锚)/B 类(单步碰撞)静态不可判,属运行期判定**——
  V1 七条件(anchor 非空 / ∩answer_pool=∅ / 当前级 / hint_level>0 / ≠ready_to_confirm /
  telling 路径 / stuck)本身就是运行期分类器,92/93 硬门按运行期口径实施即可。

**分类标签**:S=单数字终答(静态面齐)/ C=多部件(≥2 数字,全部件按终答保护)/
N=无静态答案源(标人工复核)。

| 池 | n | S | C | N | flags |
|---|---|---|---|---|---|
| gold_candidates | 60 | 0 | 0 | **60** | answer_absent_static(答案只在运行期 plan/终答轮) |
| gold_b2 | 13 | 0 | 0 | **13** | 同上 |
| pilot_20 | 20 | 16 | 4 | 0 | 2 answer⊆question;1 answer_pool_empty(纯文字答案);4 multi_part |
| enriched12 | 12 | 8 | 4 | 0 | 3 answer⊆question;1 answer_pool_empty;4 multi_part |
| 合计 | **105** | 24 | 8 | 73 | — |

**关键读数**:
1. **C 类 8 案**(多部件全保护面):enriched12 的 `understanding_04`(直径6,半径3)、
   `stuck_03`(两对分数)、`understanding_01`(第5列第4行)等;pilot 的鸡兔(鸡3,兔5)、
   比率(甲14,乙21)、余数(8组,余5)等——这些案的 answer_pool=全部数字,V1 Q1
   「不造答案 ontology、保守全保护」在提取口径下天然成立。
2. **answer⊆question 5 案**(答案唯一数字是题面数,如 x=6 的 6):`_answer_focus_numbers`
   空集回全集 fail-closed;V1 锚条件里 answer_pool 取**全量** `_answer_numbers`
   (漂移池口径)不受影响——实现 PR 勿误用 focus 口径做锚减法。
3. **answer_pool_empty 2 案**(纯文字答案:下粗上细/红球可能性更大):数字面无从泄露,
   但 ∩∅ 恒过 → 种子 F 案固化「保守不给数字锚」的安全读法(实现 PR 裁定采纳与否)。
4. **N 类 73 案**:gold 两件无静态答案字段(题库答案不落盘,judge 语义判分无需)——
   这 73 案的 answer_pool 只能运行期取(`_known_answer`:question.answer 优先/steps
   末值兜底)或未来补 canonical answer 字段;硬门(92/93 泄漏=0)按运行期口径不受阻。

## 二、viability 4 案种子(Q5 第一层)

`seeds-anchor-v1.json` 7 种子:A 锚-合法(chicken_rabbit,中间值 10)+
B×2 锚-非法(stuck_02/answerhit_01,单步 value=终答)+ C(support guiding_focus 零锚)
+ D(ready_to_confirm 禁)+ M(understanding_04 多部件重叠仍不给)+ F(答案不可判定
fail-closed)。steps 为**合成 plan 步**(运行期产物,已逐条标注 synthetic);
答案/题面为数据集 canonical 原文。

## 三、现有锁面与骨架

- 不能破的最小集:`coverage-inventory.md`(soften 三路径/阶梯不变量/终答两路径锁/
  known_answer 同源/numeric.py 零改动);
- 预期断言草案(Q5 第二层四条 + 第一层参数化):`tests/teaching/test_anchor_reveal_v1.py`
  ——**全 skip**,实现 PR 删 skip 即进回归网;硬门(92/93 泄漏=0)与 viability 重放
  (应过过/应拦拦)留实现 PR(裁定执行序 3/5)。
