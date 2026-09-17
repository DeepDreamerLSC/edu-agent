# ⑦门第四跑 gate-04-v2:机器面首次全绿(2026-09-17,#310 跑批)

candidate(epoch-2 best,nr 靶向族平台模板):

> 请复讲:先说核心思路,再写出第一步的具体算式或操作,最后给出明确结论。
> 请用完整句子描述步骤与结果,以便确认掌握。

内核 = #314/#315/#318 全修;切片 = **v2 终冻面**(--slice v2);11 案 ×2。

## 判定:确定性 checks PASS(22/22) + Lane M PASS(11/11)

- **健康位 5/5 全中**(两跑均达期望):C26 mi 2/2、C46 sm 2/2、C25 sm_ge 1/1
  (#318 有界文案回位实证)、C21 leak false/false、C36 leak false/false
  (新·慈善转述正向位首跑即中);
- **已知限位 6/6 无新增退化**(判定鲁棒;非逐行一致):C40/编造51/C17/C24/C11
  候选读数与终冻基线一致;C15 终冻基线自身抖动 (2,0)、候选 (2,2) 落于基线包络
  (lane_m 取基线 run1=严格端,delta=0;取 run2 亦 pass,delta 阈 −2 仅负向触发)
  ——不作强于证据的一致性断言;
- 泄露网 22/22:三轮修复(stability_age 双面清零)保持。

## 对照四跑曲线

| 跑 | 切片 | checks | Lane M | 阻塞 |
|---|---|---|---|---|
| gate-01(r24) | v1 | FAIL 20/22 | fail 10/11 | stability_age 泄露 + C35 污染位 |
| gate-02(nets-best) | v1 | FAIL 20/22 | fail 10/11 | 同签名(内核层定位) |
| gate-03(修复1/3) | v1 | **PASS 22/22** | fail 8/11 | C17/C25 话姿 + C35 |
| **gate-04(全修+v2)** | **v2 终冻** | **PASS 22/22** | **PASS 11/11** | — |

## 剩余:candidate-green 的另一半 = Lane H(教师盲评)

盲包 12 文件(pack/,A/B 随机,解盲映射在包外 mapping.json)+ 教师使用
说明在 pack/README.md。**盲包已重建(2026-09-17,PM-RULING#6②)**:两臂
同纪元——候选臂 = gate-04 全修内核转录 × baseline 臂 = 默认模板重跑转录
(`teacher-gate-slice-v2/baseline-transcripts/`),不再使用 v1 纪元冻结
messages(P1-① 修复,首版包见 git 历史 7994a17);A/B 随机随重建重掷,
mapping.json 以重建版为准。两臂各取 run1(两跑读数全平,保守跑规则退化
为 run1)。双绿才 promotion——教师线亲读 11 案(#284 教师策略),
产出 pairwise(A worse/B worse/same + 证据)后解盲比对。

## 账目

gate 台账:gate-04 22 案次(候选×11×2)+ baseline 重跑 22 案次(默认模板
×11×2,PM-RULING#6②,实耗 142 calls)。主体段优化器余量 534 calls 不动
(独立复算:checkpoint 计数器 main-01=96 + main-02=182,812−96−182=534 ✓)。
