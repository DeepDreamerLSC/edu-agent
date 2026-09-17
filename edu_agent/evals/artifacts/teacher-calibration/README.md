# 教师校准练习包(#293 教师线锚点;Lane H 解冻前置件)

**任务**:PM 直发 2026-09-17(`sha256=364a47d7601fcc2a`)。教师上场(用户 09-17 确认)前先打已知答案的案对齐 rubric,再进 Lane H 盲评。**零模型调用、零 LLM API;未新跑未重判**。

## 文件

| 文件 | 内容 |
|---|---|
| `teacher-onboarding.md` | 教师上手一页纸:三家族 0\|1\|2 判分锚点 + 打分表用法 + Lane H pairwise 规则练习版说明(「A worse/B worse/same + 证据」「证据不足判 same」「C40/C11 必审」「leak 不经教师」「两跑不一致保守端计 fail」) |
| `practice-cases.md` | 练习案 5 案:题目 + 逐字转录 + 教师打分区 + **参考读数区**(打完自评) |
| `scoring-template.md` | 打分表模板:与 Lane H 盲评表同构 + 练习版参考读数对照列;含盲评用空白表与填表纪律 |

## 选材与覆盖(全部已付费已评分的入仓数据;只读)

来源 = **现行冻结面** `artifacts/teacher-gate-slice-v2/`(`slice-cases.jsonl` 转录逐字 + `slice-baseline.jsonl` 参考读数逐字;#323 终冻读数 = 修复后内核 × 默认模板新纪元实测,双跑)。v1 `teacher-gate-slice/` 已整体留档,不作选材面。切片文件零改动(盲包生成器与 gate_slice 是 #323 修复域,本单未触碰)。

| 练习案 | 家族 | 判据 | 期望 | 终冻基线(双跑) | 角色 |
|---|---|---|---|---|---|
| C40 | 数学真实性 | mi | 0 | **2/2**(total 11/11,pass/pass) | **已知限**(规则命题被计算命题吸收;基线 2≠期望 0,稳定错) |
| C26 | 数学真实性 | mi | 2 | 2/2(total 12/12,pass/pass) | 正向位(误念修复;健康锚) |
| C25 | 归因 | sm_ge | 1 | **1/1 = 期望**(total 8/8,judge verdict review) | 边界位(方法总结在/学生证据缺;健康位) |
| C11 | 转述忠实性 | mi | 0 | **2/2**(total 12/12,pass/pass) | **已知限**(转述错位被合理化;稳定错) |
| C36 | 转述忠实性 | leak | False | False/False(total 12/12,pass/pass) | 正向位(转述忠实:捡学生思路推进不补终答;leak 不经教师,词感校准) |

三家族各 ≥1 ✓;两种已知限(盲评必审案)+ 边界位 + 健康锚 + 家族 3 正向位。**C36 替代 v1 的 C35**(#310 人裁:C35「正向位(终答泄露检出)」定性为 test-role contamination——judge 校准正样本被误用作产品健康位;处置 = 切片 v2,PR #319/#320)。

## 使用顺序

1. `teacher-onboarding.md`(一页纸,约 10 分钟);
2. `practice-cases.md` 逐案独立打分(三家族 0\|1\|2 + 引原话证据);
3. 打完翻各案「参考读数」对答案——重点看与机器的**分叉点**(C40/C11:机器稳定 2 分、期望 0 分——教师若同样给 2,即复现了盲区;C25:机器 1 分=期望,体会 1 的边界形态);
4. `scoring-template.md` B 表 = 盲评真实结构,后续 candidate 盲评直接复用。

## 边界

- 零模型调用零 LLM API;只读入仓工件,治理②合规;不动盲包生成器/gate_slice;参考读数**程序提取**(slice-baseline.jsonl 终冻 + gate-04-v2/run{1,2}.json 双源对拍一致),不新跑不重判;

**防复发对拍命令**(审查者可复跑;当前 main 的 #323 终冻件):

```bash
.venv/bin/python -c "import json;bl={r['label']:r for r in map(json.loads,open('edu_agent/evals/artifacts/teacher-gate-slice-v2/slice-baseline.jsonl'))};runs={i:json.load(open(f'edu_agent/evals/artifacts/gate-04-v2/run{i}.json')) for i in (1,2)};[print(l,bl[l]['expected'],bl[l]['baseline'],'| run1',runs[1][bl[l]['case_id']]['total'],runs[1][bl[l]['case_id']]['verdict'],'| run2',runs[2][bl[l]['case_id']]['total'],runs[2][bl[l]['case_id']]['verdict']) for l in ('C40','C26','C25','C11','C36')]"
```
- agent 只开 PR 不合并;纯 artifacts 新增,四类结构路径零触碰。
