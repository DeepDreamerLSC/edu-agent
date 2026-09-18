# no-progress 盲对材料(M3 人审;teacher-delta-review 模式)

**随机 A/B 分配+种子记录**:mapping.json(seed=20260919,臂→盲标),
**盲审完成前不得启封**;启封后注记:护栏张力天花板说明与三层定性见
`../real-case-v1/README.md`(盲审材料保持干净,PM 令③)。

## 对构成(4 对,转录全部复用已跑件,零新 calls)

| 对 | 案 | baseline | candidate |
|---|---|---|---|
| 1 | 真实案·等边三角形方位(6a61aa32) | 生产提取原案(9 轮) | M1 replay(10 轮) |
| 2-4 | 控制案三形态(复核/重引导/追依据) | **待 PM 裁**(baseline 无已跑件:M2 只跑了 candidate) | controls-v1 replay |

## 判读线(PM 冻结)

- 失败案(对 1):**candidate 须判 better**
- 3 控制案:**不得 worse**

## 呈审面

每对两份 `pair-N-A/B.txt`(纯学生/导师轮次转录,无臂信息无判读提示);
人审对每对选「哪边更好或平」;M3 判完→启封 mapping→终版回执(#333,
含 M1-M4 全链结论)。
