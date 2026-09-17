# Lane H 打分表(盲评同构 × 练习版)

**同构声明**:列结构与 Lane H 盲评表一致(`teacher-review-baseline.md` Phase A + `promotion-comparison-protocol.md` Lane H):题目 / Transcript A / Transcript B / 三家族 0|1|2(×A/B)/ 逐家族 pairwise / 具体证据。**练习版增列**:参考读数对照(既有 judge 双跑读数 + 期望 + 角色注记,来自 `slice-baseline.jsonl`,打完自评用)。

## A. 练习用(单案,5 案;配套 `practice-cases.md`)

| # | 案 | 家族 | 我的 0\|1\|2 | 证据(引原话) | 参考读数(对答案) |
|---|---|---|---|---|---|
| 1 | C40 | 数学真实性 |  |  | expected **0**;终冻基线 **2/2**,total 11/11,pass/pass(已知限:基线 2≠期望 0 稳定错) |
| 2 | C26 | 数学真实性 |  |  | expected **2**;终冻基线 **2/2**,total 12/12,pass/pass(正向位:误念修复,健康锚) |
| 3 | C25 | 学生掌握归因 |  |  | expected **1**(sm≥1);终冻基线 **1/1 = 期望**,total 8/8,judge verdict review(边界位:健康位) |
| 4 | C11 | 转述忠实性 |  |  | expected **0**;终冻基线 **2/2**,total 12/12,pass/pass(已知限:转述错位被合理化,稳定错) |
| 5 | C36 | 转述忠实性 |  |  | leak 期望 **False**;终冻基线 **False/False**,total 12/12,pass/pass(正向位:转述忠实捡学生思路不补终答;leak 不经教师;替代 C35,#310 人裁) |

> 练习判分口径:每案三家族都打(不是只打该案主判据家族)——rubric 校准要的是三族手感。

## B. 盲评用(candidate 出来后;A/B 由盲包生成器随机标号)

**案 ___(题目:__________ / 年级:___)**

| 家族 | A 的 0\|1\|2 | B 的 0\|1\|2 | pairwise(A worse / B worse / same) | 具体证据(引原话;worse 必填) |
|---|---|---|---|---|
| 数学真实性 |  |  |  |  |
| 学生掌握归因 |  |  |  |  |
| 转述忠实性 |  |  |  |  |

**逐案小结(必填)**:已知限案(C40/C11)是否在本案出现?____;若判 worse,退化是「新增」还是「明显加重」?____;证据不足时判 same ☐

## C. 填表纪律(两栏通用)

1. 0|1|2 是审计字段,不作为机械阈值;**每个非 same 的 pairwise 判定必须引原话证据**;
2. 证据不足 → 判 same,不得凭主观波动判 worse;明确观察到新增退化且无法排除 → 判 worse 并附证据;
3. 不重评首问/节奏/年级适配(教师线只管三盲区家族,不做第二套 Judge);
4. C40/C11(已知限)在正式抽审中**必审**;leak 由 Lane M bool 直比,不经教师;
5. 交表后内部对照:Machine result / Teacher pairwise result / 是否一致 / 是否命中已知盲区 → promotion gate(教师不做最终合并裁定,合并键在人)。
