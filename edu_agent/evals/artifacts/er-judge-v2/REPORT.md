# ER judge v2——evidence-reuse 判分器语义边界窄修(裁令④,2026-09-22)

需求来源:eval(#382 裁令④ + 教训 A3:ER judge v2 语义边界窄修;规格 =
er-judge-v2-analysis 三件:四案×7臂 drill / 20 轨迹 dev 全对照 / 54 池 holdout 抽样)。
纪律:非 redesign,边界条件修正;judge 框架不动(#382);v1 ER 段判据族照录只读对照。

## 正本落点决策

ER 判分在 r3 时只存在于判读员工件脚本 `runs/scripts/unified_six_metrics_r3.py`
的 ER 段——**untracked**(runs/ 不进库,随 r3 封存不动)。查 `edu_agent/evals/`
正本判分面:`judge.py` 是 93 面 rubric 模型判分、`checks.py` 是回归 check 注册表
(`possible_no_progress_cycle` 是 no-progress 机械代理,不是 ER),均无 evidence-reuse
对应面。故 v2 以**本目录 tracked 工件**落库为正本(er_judge_v2.py),工件脚本
`unified_six_metrics_r3.py` 不改不进库;r3 复算用 `calibrate.py replay` 的 v1 照录
逻辑做只读对照。仓内判分资产化 = 本目录 + `tests/evals/test_er_judge_v2.py` 回归电池。

## 七点窄修(v1 → v2 对照)

| # | 裁令④条款 | v1(词面族) | v2 |
|---|---|---|---|
| FP-1 | 问理由/验证/解释 ≠ 当未知 | `怎么想到/检查一下/验证一下/再算/再想` 在 doubt 词表内,问理由即命中 | 问理由族/问验证族/空话族移出 doubt;doubt 拆质疑性(但/可是/你确定/肯定对)与确认性(是不是/一样吗/…)两列 |
| FP-2 | 无指向「是不是」不触发 | `是不是`+问号即 doubt,不问宾语 | whether 型问句须过点 1 指向门:问句数字 ⊆ 学生上轮数字 + 数字局部上下文锚定(或 ≥4 字公共 CJK 子串);问新对象/新计算不算 |
| FP-3 | ACK 结构化 | 19 词偶然否决(`成立/棒/清楚/关键` 等泛词) | 显式承认结构(`是对的/完全正确/没错/思路完全对` 等述谓式)+ 尾标签问句(对吧?)豁免;**承认不豁免指向性整句重问**(675:B-old RETIRE 证据) |
| FN-1 | 非数字终答可构成 evidence | 答案无 ASCII 数字 → 全案不进分母(675 双屏障盲区) | 字母终答须断言语境(答案是A/选A);文字结论(易变形)作字符串键;含运算符答案(12:4=6:2、x-21=35)须关系骨架进 said |
| FN-2 | repro 案进适用域 | 仅 form1 案进分母(repro 案 v1 不评) | 无 form 标注但有答案的案(cross-stitch/ball-bounce/incident)按 form1 同形处理;数值答案 form2 案维持排除 |
| FN-3 | 真重复不被偶然 ACK 豁免 | `成立` 偶然 ACK 否决 + stray 数字一票否决(866 双漏) | 问句重复(子句级相似度 >0.85,回看 3 导师轮)→ no-progress 族必计;stray 否决收紧为「导师轮明确纠正该 stray 数字」 |
| 概念分离 | ER vs no-progress 分族 | ER 段混含重复复读(相似度族并列) | ER=把已给目标信息当未知(指向性重问);no-progress=无增量重复推进(问句重复);重复命中优先落 no-progress 族,不与 ER 混计 |

另:分母去污染——纯数字答案剥枚举段(因数列表)与换算段(单位换算事实)后判定
said(3565 t1「1平方分米等于100平方厘米」不立 said)。

## 四道验收(判分器对规格件)

1. **dev 复现(硬门)**:20 轨迹(10 曝光盘案 × r3 双臂)逐轮 v2 标注与
   dev-calibration.json `v2_turns` **完全一致:轨迹 20/20,逐轮 27/27,
   ER/NP/denominator 计数零差异**(dev-calibration.json)。
2. **drill 四案×7臂**:55 分母轮 v1_hit/v2_er/v2_np/理由与 drill.json 零差异
   (drill.json)。
3. **holdout 对判**(16 未曝光案 r3 双臂,54 池确定性抽样 20 turn;抽样与
   holdout-sampling.json 逐位复现):任务口径 12 turn(7 signal + 5 quiet)
   **9/12**;全 20 turn **17/20**;安静轮零误报(12 个 gold-legal 安静轮全部
   judge=legal)。3 处不一致经诊断为 **v2 规格盲区而非实现走样**(sha 冻结在案、
   dev/drill 零差异排除走样),如实记录不硬凑,见下节。
4. **r3 诊断 replay**(26 案双臂,FAIL 不翻案):旧尺子 6 个词面命中
   (baseline 3 + candidate 3)**全部**被 v2 改判 legal——即 r3 的 ER 词面信号
   100% 是 FP(问理由/问验证/分母污染);v2 补现旧尺子盲区:真 ER 1 轮
   (675-b-t3,最纯样本)+ no-progress 9 轮(b=7/c=2,含 incident-700m 与
   cross-stitch 死循环形态)。r3 结论不变:r3 的 ER 面证据本就不支撑翻案,
   新尺子只说明旧尺子错在哪(r3-diagnostic-replay.json)。

## holdout 3 处不一致 = v2 边界(如实记录)

1. `incident-700m-replay/b/t5`:gold=np,judge=er。导师口头承认(数字很准)后
   第 3 次要求同一推导——措辞已换(「能再讲讲你是怎么算出下降6/5℃的吗」vs
   t1「能说说你是怎么从海拔700米推算出」),子句相似度 <0.85 不触发 np,落
   ER(但+指向)。**盲区:换措辞重复(语义重复)超出词面相似度窗。**
2. `incident-700m-replay/c/t4`:gold=np,judge=legal。数数脚手架问第 3 次,
   增量仅为措辞具体化(几个100米→□个100米)。gold 标注自己已记为边界案
   (单轮增量观=legal,窗口无推进观=np)。**盲区同上:近似重复的窗口判定。**
3. `socraticmath_train_223/c/t3`:gold=legal,judge=np。「这和**长方形**有什么
   不同」vs t2「这和**正方形**有什么不同」子句相似度 0.900>0.85 触发 np,但
   对比对象已换(2 字替换)。**盲区:词面相似对宾语替换不敏感。**

三处共同指向同一族边界(问句重复检测的词面相似度判据),是 ⑤ confirmation
prereg 之外 judge 侧的已知局限;修它们需要语义级重复判定,超出窄修范围
(裁令④:语义边界修正非 redesign),留档不硬凑。

## provenance 链

- holdout 标注时冻结 sha16=`43ef6f0649bf1571`(gold_labels_holdout.json
  provenance 字段;标注未运行 judge 输出对照);
- 入库版 sha16=`f520faae98842e6d`:为过 ruff 复杂度关(02 §2.1)机械抽取
  `_repeat_reason` 助手 + 补 provenance 文档行,判据语义零改动;
- 四道验收输出在两版间**逐字节一致**(dev 对规格件逐轮全同)。
- ⑤ prereg 起草时应以入库版 sha 为 judge 冻结锚。

## 复现

数据源 = 既有 r3/ablation 结果工件(只读,零 tutor calls):

```
python3 edu_agent/evals/artifacts/er-judge-v2/calibrate.py drill  --out drill.json
python3 edu_agent/evals/artifacts/er-judge-v2/calibrate.py dev    --out dev-calibration.json
python3 edu_agent/evals/artifacts/er-judge-v2/calibrate.py sample --out holdout-sampling.json
python3 edu_agent/evals/artifacts/er-judge-v2/calibrate.py holdout --out holdout-agreement.json
python3 edu_agent/evals/artifacts/er-judge-v2/calibrate.py replay --out r3-diagnostic-replay.json
# --runs-root 默认 /tmp/wt-step7-ab(r3/ablation 工件树)
```

仓内护栏:`tests/evals/test_er_judge_v2.py`(七点回归电池,真实案文最小复现)。


## 数据源与归档落点(P3-nano 修法一,#412 审查 5755351702)

`calibrate.py` 各子命令消费的数据源不在本目录,在 **r3/ablation 运行时工件树 `/tmp/wt-step7-ab/`**:
- `runs/candidate/cases.jsonl`、`runs/{baseline,candidate}/results/*.json`(r3 双臂 26 案轨迹)
- `runs/ablation-*/results/*.json`(五臂 ablation 8 案)
- `edu_agent/evals/datasets/external_slices/socraticmath_executable_v1.json`(经由 runs_root 相对路径)

该 /tmp 树为临时工件:树在时可逐字节重产(#411 审查亲验);树失后需重放跑面(r3 工程链在
calibration-private/step7-* 档案可复现)。**仓内不归档原始轨迹**(生产数据隔离+体积纪律);
判分器正本(er_judge_v2.py)与 gold labels 入仓即可复用——未来新跑面传 --runs-root 指向新树。
