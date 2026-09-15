# judge v3.2 定稿 · 93 案 ×2 rescore → B_new(#253,2026-09-15)

**全部数字口径 = acceptance aggregation policy(两跑平均),非「模型真实分数」。**

## 头表

| 量 | 值 |
|---|---|
| **B_new**(92 案均值,逐案 total=(r1+r2)/2) | **9.5217** |
| run1 独立均值 | 9.5652 |
| run2 独立均值 | 9.4783 |
| **T_new** = B_new + 0.30×(12−B_new)(机械式) | **10.2652** |
| math_integrity 两跑不一致 | **0/92** |
| answer_leaked 两跑不一致 | **1/92**(`stability_triangle_area`,true↔false) |
| 逐案 \|r1−r2\| 分布 | 0:81 案 / 1:7 案 / 2:3 案 / 3:1 案(最大差 3) |
| 调用计数 | **184 = 92×2,零 route-1 修复,零截断,零失败案**(守卫 200 未触) |
| 指纹 | `af93e5645086f6f02c0fcd303550adedf5a4004b3d8f69359999d481df85d3a8`(main 基底断言 MATCH = c5675065011 冻结值) |
| 引擎送达 | GET /v1/models(服务列表 deepseek-flash/deepseek-v4-pro)+ **184 行响应 model 全显 `deepseek-flash`** |

## 输入构成(判卷前已落存档可点验:input-provenance.json / case-sources.jsonl / 首 commit)

- 目标 93 = corpus-round-v2/cases.jsonl(#238/#257 manifest 全集);**可判 92 = 存档逐字 49(judge-v2-rescore-52,输入隔离)+ 同构新建 43**(_archive_cases 配方:corpus-round-v2 collect transcript × cases.jsonl 题面;**往返校验:49 交集案重建与存档逐字段 0 不一致**——同构性机器证明);
- **1 案不可判(原样上报)**:`fraction_addition_support_boundary`——corpus-round-v2 源跑即 content 失败(tutor 侧 GatewayError schema_violation,attempt 1,failures.jsonl 2026-09-14T03:23:27 原样行),全仓无 transcript(corpus-round-v1 未跑此案);**派单 93×2=186 修正为 92×2=184**,若需补足该案须先修 tutor 侧源跑(另单);
- 派单面「52 案已存档逐字复用」的精确口径:52 存档中 **49** 为 manifest 成员(逐字复用);另 3 案(编造51/构造52/challenge_coordinate_swap)为 judge 线特构探针案,非 manifest 成员,不入本批(如需纳入请更正派单)。

## 抖动噪声实测(r1 vs r2,同输入同参数独立调用)

- **81/92 案 total 两跑完全同值**;±1 者 7 案;±2 者 3 案;±3 者 1 案(逐案差值见 per-case-aggregation.jsonl)
- 六维逐维两跑翻转案数:first_question 0 / socratic_followup 2 / grade_fit 1 / pacing 6 / summary_mastery 4 / termination 3
- verdict 分布:run1 pass 45 / review 38 / fail 9;run2 pass 44 / review 41 / fail 7
- **math_integrity 两跑 0 翻转**(92/92 同判)——与 52 案门跑一致(mi 面在该引擎上稳定);answer_leaked 仅 1 案翻转(与因子鉴定轮 B/B 观测到的 leak 抖动同量级)

## 判读注记

- B_new 与首轮 judge 均值 6.0(#238 §2 ④,corpus-round-v1 裸题面口径)**不可比**:v1 无 reference_answer + 判据 v1;本批 = v3.2 定稿判据 + 全量 reference_answer 口径;
- T_new 为派单给定的机械换算式(B_new + 0.30×(12−B_new)),无独立测量含义,不表述为模型真实分数;
- leak 翻转案(stability_triangle_area)按预注册口径单列不入任何门;mi/leak 不一致清单全量 = 本 README 头表(0+1)。

## 复算

```bash
# 需 DEEPSEEK_API_KEY;输入 = 本目录 judge-cases.jsonl(92 案存档,判卷前已推);
# 跑法 = judge_independent 角色两遍(role=judge_independent→deepseek-flash,temp=0,
# max_tokens 900);聚合 = per-case (r1+r2)/2 → 均值 B_new;T_new 机械式;
# 全部口径注记以本 README 为准(预注册聚合,c5675…派单)。
```

按纪律:不重试不修参数、失败案原样上报(本批零失败);工件落分支,**PR 只开不合**。
