# judge v3.2 定稿 · 52 案验收 rescore(#253,2026-09-15)

## **硬门 20/20 全过**(判卷口径冻结于 [#253 c5674758872](https://github.com/DeepDreamerLSC/edu-agent/issues/253#issuecomment-5674758872),跑前锚定,跑后未改)

- 基底:main@`fd1c706`(#265 已合);分支 `task/253-v32-rescore-52`;**judger_sha256 = `af93e5645086f6f02c0fcd303550adedf5a4004b3d8f69359999d481df85d3a8`**(checks.py+judge.py @ 分支头,跑前断言 MATCH,即 #265 定稿指纹)
- 输入 = `judge-v2-rescore-52/judge-cases.jsonl` 存档**逐字复用**(52 案,只动判据版本 v2→v3.2 定稿,隔离输入变量)
- 引擎:`judge_independent` → deepseek-chat 配置,**实际服务档位 deepseek-flash**(GET /v1/models 实录:服务列表 = deepseek-flash/deepseek-v4-pro,配置名不在列表;72 调用响应 model 字段全部 `deepseek-flash`)——送达证明见 api-facts.jsonl 首行 + 逐调用行
- **调用计数:72 = 门 20×2 + 诊断 32×1,零 route-1 修复,零失败案**(守卫上限 80 未触)
- 判卷协议(冻结):门案**两跑均达期望才计过**;mi/leak 两跑不一致 → 保守端计 fail(fail-closed);verdict 机械推导阈值不动;**六维 total 报告口径 = acceptance aggregation policy(门案两跑均值),非「模型真实分数」**

## 门 20 案逐案判读(对照 c5674758872 冻结快照)

| 案 | 判据 | 期望 | run1 | run2 | 两跑一致 | 判定 | v2(17/20 轮) |
|---|---|---|---|---|---|---|---|
| C02 | sm≥1 | 1 | 1 | 1 | ✓ | **过** | 过 |
| C06 | leaked | false | false | false | ✓ | **过** | 过 |
| C12 | leaked | false | false | false | ✓ | **过** | 过 |
| C14 | leaked | false | false | false | ✓ | **过** | 过 |
| C15 | mi | 0 | 0 | 0 | ✓ | **过** | 过 |
| C17 | sm | 2 | 2 | 2 | ✓ | **过** | 过 |
| C20 | mi | 0 | 0 | 0 | ✓ | **过** | 过 |
| C24 | sm | 0 | 0 | 0 | ✓ | **过** | 过 |
| C25 | sm≥1 | 1 | 1 | 1 | ✓ | **过** | **败(v2 sm=0)→ 翻正** |
| C26 | mi | 2 | 2 | 2 | ✓ | **过** | 过 |
| C31 | leaked | false | false | false | ✓ | **过** | 过 |
| C35 | leaked | true | true | true | ✓ | **过** | 过 |
| C37 | leaked | false | false | false | ✓ | **过** | 过 |
| C39 | mi | 0 | 0 | 0 | ✓ | **过** | 过 |
| C41 | mi | 2 | 2 | 2 | ✓ | **过** | 过 |
| C43 | leaked | true | true | true | ✓ | **过** | 过 |
| C45 | mi | 2 | 2 | 2 | ✓ | **过** | 过 |
| C46 | sm | 2(外评重裁) | 2 | 2 | ✓ | **过** | 败(旧期望 1,v2 实测 sm=2)→ 期望重裁后过 |
| 编造51 | mi | 0 | 0 | 0 | ✓ | **过** | **败(v2 mi=2)→ 翻正** |
| 构造52 | leaked | true | true | true | ✓ | **过** | 过 |

## 两跑翻转清单(门 20 案;全字段对照见 run1-vs-run2.jsonl)

- **mi 翻转:0/20;leak 翻转:0/20;verdict 翻转:0/20**(fail-closed 条款未触发)
- 六维单维 ±1 漂移:**3/20**——C20 grade_fit(1→2)、C43 socratic_followup(1→0)、C45 termination(1→2);三案门判据均非六维面,不受影响
- evidence 自由文本:20/20 两跑不同(措辞差异,判据字段全部同判)
- 对照 v3.2 因子鉴定轮(B/B 1/7 leak 翻转):本批 72 调用关键字段零翻转——稳定性面显著优于先导(单批观测,非结论)

## 与 v2 17/20 差异表(v2 读数取 judge-v2-rescore-52/judge-scores.jsonl)

| 案 | v2 | v3.2 定稿 | 差异归因 |
|---|---|---|---|
| C25 | sm=0(败) | **sm=1 ×2(过)** | 文本修:件 2 参与度判据(方法总结在、学生证据/掌握判断缺 → 1 档,两跑证据同判) |
| C46 | sm=2(旧期望 1 下败) | sm=2 ×2(重裁期望 2 下过) | 期望重裁(c5673905941):非代码翻正;两跑均引真实学生轮(轮5「应该把36平均分成3份,用36除以3」/轮7「小华是12岁,12乘3等于36,符合题意」) |
| 编造51 | mi=2(败) | **mi=0 ×2(过)** | 文本修:枚举程序+基底锚点;两跑枚举均含「八分之一变成十二分之一」标错并独立验算(「应为二十四分之三」) |
| 其余 17 | 过 | 过 | 判据字段全部维持 |

## 诊断 32 案(×1,无门判据,仅供诊断)

verdict 分布:pass 16 / review 13 / fail 3;math_integrity:2×31 + 1×1;answer_leaked 全 false;零失败案。逐案原始输出 = judge-scores-diag.jsonl(与 v2 对照可复用 comparison 思路,本轮未设诊断门,不另做一致性统计——先导已量化的抖动/盲区面见 judge-v3.2-factorial/README)。

## 复算

```bash
# 需 DEEPSEEK_API_KEY;输入 = judge-v2-rescore-52/judge-cases.jsonl(存档逐字复用);
# 门案清单 = 本 README 冻结快照 20 案;驱动逻辑:judge_independent 角色 ×
# max_tokens 900 / temperature 0 / 单调用,门 ×2 + 诊断 ×1;判卷协议 = c5674758872。
# 逐调用台账(含响应 model 字段)= api-facts.jsonl;两跑字段对照 = run1-vs-run2.jsonl。
```

按纪律:先跑完再判卷(已守);门绿 → 后续件(指纹冻结/93 案)等 PM 点火;工件落分支,**PR 只开不合**。
