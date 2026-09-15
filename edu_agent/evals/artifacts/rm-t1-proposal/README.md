# rm-t1-proposal:RM 试金石 T1 候选对(#253,2026-09-16,零模型调用)

任务(PM 7e9b92bc 直发,task=rm-t1-scan):收集「同文错误确认对」备料——探测奖励
模型能否当**能力探测器**(学生自报「懂了」不可信,见 #253 登记的讲题入口无能力闸)。
本目录只备料;MPS 跑不跑 = 用户键,不在本件。

## 文件

- `pairs.jsonl`:9 组候选对(每组 = A/B 两段逐字引文 + 差异说明 + RM 判别力一句);
- `verify_quotes.py`:引文逐字核验(对源文件逐字节比对,机械证明「逐字可定位」,
  口径同 #272 审查)。

复跑核验(零依赖标准库):

```bash
python3 edu_agent/evals/artifacts/rm-t1-proposal/verify_quotes.py
# 期望输出:逐字核验 49/49 轮 ALL MATCH
```

## 源(全部仓内只读,零 API)

| 源 | 用途 |
|---|---|
| `judge-v3.2-rescore-93/judge-cases.jsonl`(92 案)+ `per-case-aggregation.jsonl`(mi 双跑) | A/B 两侧引文与判卷上下文 |
| `teacher-gate-slice/slice-cases.jsonl`(11 案逐字冻结)+ `slice-baseline.jsonl` | 特构案(T1-P03/P08)引文与家族分类 |

## 9 组配对总表

| 对 | 错误类型 | 场景 | A 侧(含错误确认) | B 侧(干净) | A 侧判卷现状 |
|---|---|---|---|---|---|
| T1-P01 | 假规则被吸收 | 3x+7=25 | equation_multiplication_misconception_repair(C40)[1-5] | equation_multiplication_complete_reasoning[1-5] | **mi=2/2 盲区**(已知限) |
| T1-P02 | 归因错位被放过(兼慈善转述) | 1/3+1/6 | fraction_addition_alternative_method(C11)[1-4] | fraction_addition_complete_reasoning[1-4] | **mi=2/2 盲区**(已知限) |
| T1-P03 | 错误等值被认可 | 3/4+1/8 | 编造51(stability_fraction_addition__r1)[4] | 同案 [6](讲师正确转换) | mi=0/0 可判 |
| T1-P04 | 错误等值被认可(中性回声放过) | 2(x+3)=18 | parentheses_equation_alternative_method[3-4] | parentheses_equation_misconception_repair(C26)[1-2] | mi=1/1 部分可判 |
| T1-P05 | 错误等值被认可 | 半径 4 圆面积 | b2_circle_area_misconception_repair[1-2] | b2_circle_area_alternative_method[1-2] | mi=0/0 可判 |
| T1-P06 | 错误等值被认可 | 2/3×6 | b2_fraction_multiplication_alternative_method[1-2] | b2_fraction_multiplication_complete_reasoning[1-3] | mi=0/0 可判 |
| T1-P07 | 假规则被吸收(等价算式伪区分) | 200 元打八折 | percentage_discount_alternative_method[1-3] | percentage_discount_complete_reasoning[1-5] | mi=1/1 部分可判 |
| T1-P08 | 错误等值被认可(坐标互换) | 坐标系 B(2,4) | challenge_coordinate_swap_20260914(C15)[9-10] | 同案 [7-8](正确陈述获确认) | mi=0/0 可判 |
| T1-P09 | 慈善转述 | 60km/h×2.5h | distance_speed_support_boundary(C21)[1-2] | distance_speed_complete_reasoning[1-2] | mi=2/2(归因面无判据) |

错误类型覆盖:错误等值×5 / 假规则×2 / 归因错位×1 / 慈善转述×1(P02 兼归因与慈善,
P09 为纯慈善转述)。

## 配对方法与诚实账

- **配对判定是人工的,引文抽取是机械的**:轮次区间人工选定,引文由脚本从源 JSONL
  按 (case_id, 轮次下标) 抽取,无手抄(生成后 49/49 轮与源逐字节一致,见上复跑命令);
- **同文优先**:7 组跨案同题配对(同题面同位置同话步),2 组同案最小对比(T1-P03
  同话步真假等值、T1-P08 同款确认句式真伪陈述)——同案对已在对内标注;
- **盘过不用的(如实)**:teacher-gate-slice 归因家族四案(C46/C17/C25/C24)全是
  判卷健康位,无「能力错归因被确认」实例,归因错位仅由 P02(C11 错位引语)覆盖;
  C40 同题兄弟案(equation_multiplication alternative/support_boundary)扫描无假规则,
  未入对;C24(零参与位)是证据不足非错误确认,排除;
- **判卷现状供参考**:A 侧两对(P01/P02)是现行判卷 mi=2/2 的已知盲区
  (teacher-gate-slice C40/C11 已知限位)——RM 若能在这些对上分辨,即补当前判据
  盲区;mi 可判的对(P03-P08)可同时做 RM 与判卷的一致性校验。

## PM 裁定入口

逐组裁定:每组三字段(difference/probes 已在 pairs.jsonl;引文按 case_id+轮次回源
核验,或直接跑 verify_quotes.py)。设计权在 PM:组可增删改,工件冻结纪律同
teacher-gate-slice(改案集/基线需人批)。
