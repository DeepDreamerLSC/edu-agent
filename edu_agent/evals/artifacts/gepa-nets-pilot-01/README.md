# GEPA nets-in-loop 试点 01(#310 试点段,2026-09-17,PM-RULING#4 批 300 calls)

initial = r24 模板(⑦门被拒候选,--initial-template-file);two-knobs + nr 靶向
编辑器(本地 judge 后端);Net A 泄露网在 loop 内。

## 读数(2 代即停等审)

| 代 | 父代(mean/nr/num/hard) | 变体 | leak_net | 判定 |
|---|---|---|---|---|
| 初始 | 8.25 / .0 / 0 / **.5**(前缀 16 案批) | — | — | — |
| 0 | 8.25/.0/0/.5 | **10.5/.25/0/0** | 0 | Pareto 拒(nr 维纠缠)但成 best(父代 hard .5 被 clean 过滤出局) |
| 1 | 10.5 | noop(编辑器原样返回) | 0 | — |

预算:48/300(未触硬限);wall 232s。

## 三问验收(#310 任务书)

1. **否决生效**:逻辑级 ✓(单元钉:四维全优+泄露违例 → accepted=False 且不注册
   分数,checkpoint best 不被占据);**现场未触发**——两代抽样批 0 违例
   (stability_age 类案未入批),避让证明缺席;
2. **编辑器避让**:未获证明(无 leak_net 失败帧,编辑器无从避让);
3. **曲线不发散**:r0 变体 10.5/.25/0/**hard 0** 为全程最强净向量;但 nr 维纠缠
   再现——父代 hard .5 机械压低 nr(.0),变体 hard 归零后 nr 显性化(.25),
   dominates 拒绝。hard 与 nr 在 verdict 语义上互斥(fail 案不计 review),
   四维独立 Pareto 对此盲。

## 新发现(记档,供主体段设计)

- **前缀批偏差**:_restore_or_seed 初始评估用 train_cases[:16](文件序前缀,
  非随机)——本跑父代 hard .5 的极端读数疑与此有关;主体段应改
  sample_batch(seed=0) 与代间批同分布;
- **nr/hard 纠缠**:verdict 互斥使 hard 高的批 nr 虚低,Pareto 四维独立假设
  失真;主体段候选对策:nr 分母改「非 hard 案」或并入失败帧归因。

## 下一步

停等审(2 代纪律)。主体段(≤812 calls)批复前提:上两发现的处置裁定。
