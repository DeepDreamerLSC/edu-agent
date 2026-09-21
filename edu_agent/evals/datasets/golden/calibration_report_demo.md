# 标定一致率报告(judge × 人分)

> 演示样例(机器面):judge A(judge分数表,旧 judge A)× judge B(预打分v2 去评注列)。
> 双盲口径(PM 裁定):人分原始 CSV 属私有面不进仓,本目录只放机器面演示;
> 真实人分一致率在本地跑同一命令:`scripts/calibration_report.py --judge <judge-scores.jsonl> --human <人分CSV>`。
> 49 案(C15 旧 judge 未跑、C51/C52 构造面不在两表内)。数字是旧口径 A/B 分歧的史实,只作用法演示。

- 配对:49 案(judge 49 × 人分 50,交集配对)

| 维度 | 一致率 | 加权κ(二次) |
|---|---|---|
| 首问(first_question) | 46/49 = 94% | 0.00 |
| 引导追问(socratic_followup) | 22/49 = 45% | 0.15 |
| 年级适配(grade_fit) | 44/49 = 90% | 0.00 |
| 节奏(pacing) | 13/49 = 27% | 0.13 |
| 总结掌握(summary_mastery) | 29/49 = 59% | 0.58 |
| 收尾时机(termination) | 16/49 = 33% | 0.36 |

- 六维加权κ均值:0.20
- verdict 翻转:30 例:C01, C02, C03, C05, C06, C07, C09, C12, C13, C14, C16, C18, C19, C21, C22, C23, C24, C25, C26, C31, C33, C35, C37, C38, C40, C41, C44, C45, C48, C49

口径:双盲(教师材料不带 judge 分数);人分 CSV 属私有面,本报告只落聚合面,不带评注原文。
