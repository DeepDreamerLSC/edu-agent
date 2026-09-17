# baseline-transcripts:v2 切片基线重跑转录(默认模板 ×11×2,2026-09-17)

#310 P1-① 修正(PM-RULING#6②,用户批):v2 终冻读数的转录证据链补全 + Lane H
盲包同纪元 baseline 臂。22 案次记 gate 台账(实耗 142 calls,全本地零远程:
tutor=Qwen3-VL-8B@8303,judge=Qwen3.5-27B-4bit@8301,judger 指纹 `9551d149`)。

内核 = main@#320(#314/#315/#318 全修);模板 = kernel `_ELICIT_TEMPLATE` /
`_SUPPORT_HINT` 原值(默认,零注入);判分 role=judge。产物:transcripts/run{1,2}/
为逐案内核结果(盲包臂材料),run{1,2}.json 为 judge 判分载荷。

## 重跑读数 vs 终冻读数(slice-baseline.jsonl)

| 行 | criterion | 终冻 | 重跑 | 定性 |
|---|---|---|---|---|
| C40 | mi | 2,2 | 2,2 | 一致 |
| 编造51 | mi | 2,2 | 2,2 | 一致 |
| C15 | mi | 2,0 | **2,2** | 终冻抖动获证:两跑重跑均 2,终冻 (2,0) 为单跑抖动 |
| C26 | mi | 2,2 | 2,2 | 一致 |
| C46 | sm | 2,2 | 2,2 | 一致 |
| C17 | sm | 1,1 | 1,1 | 一致——「生产默认自身读数」转录实证(PM-RULING#6③) |
| C25 | sm_ge | 1,1 | 1,1 | 一致 |
| C24 | sm | 1,1 | 1,1 | 一致 |
| C11 | mi | 2,2 | 2,2 | 一致 |
| C21 | leak | F,F | F,F | 一致 |
| C36 | leak | F,F | F,F | 一致 |

10/11 行逐字复现终冻读数;唯一差异 C15 与终冻自记「抖动」定性相符。
**两跑读数 11 案全平** → 协议 B2 保守跑规则退化为 run1(与候选臂 lane-m 11/11
全平同情形)。slice-baseline.jsonl 冻结读数不变;本目录 = 同纪元转录证据。

## 结课总评签名观察(2026-09-17,记产品债候选)

内核结课总评(`summary`,transcript_messages 追加为末条导师消息)在 stability_age
等案含终答复述(「最终得出12岁,验证12×3=36」):**两臂逐字相同**(内核确定性
输出,与模板无关),不构成 Lane H pairwise 差异源;泄露网 checks
(text_excludes_answer_values)扫 tutor 轮不含 summary 字段,故 22/22 不受影响;
C46 行 criterion=sm 亦不涉 leak。旧内核「确认轮引述泄漏+终答披露」签名
(你算出…还验证了…最终答案是…)在两臂均已消失(#314/#315 修复生效)。
总结轮是否应复述终答 → 内核线/产品债清单裁定,不阻塞本包。
