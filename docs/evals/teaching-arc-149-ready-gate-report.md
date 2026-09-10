# #149 判停闸 + 护栏答案基线 —— before/after 帧报告

来源:issue #149(PM 方案,马尾辫自审后)。工件:`edu_agent/evals/artifacts/149-ready-gate/`。
一句话:把「判停」的权威从**模型自报**移回**确定性验证层** —— `ready_to_confirm` 只作建议。

## 1. 改动(三件,边界见 §6)

| # | 改动 | 落点 |
|---|---|---|
| ① | **判停闸**:模型置 `ready_to_confirm` 后,须经确定性校验「学生历史里已出现命中已知答案的数字集」才判停;否则闸下 + 重写。判据抽核 `_hits_answer_numbers`,与 #112 触发**共用一套**(无第二套判据);fail-open:答案取不到数字时不闸。 | `kernel.py` `_gate_premature_confirm` / `_answer_numbers` / `_student_stated_answer` |
| ② | **护栏答案基线统一走 `_known_answer`**(answer 优先、steps 末值兜底);`soft_no_answer` 同源判定。此前直接读 `question["answer"]` → 评测侧只传题面时永远「无答案模式」。 | `kernel.py` `_GuardContext.answer_reference` / `_guard_check` / `_guard_output` |
| ③ | **闸后处置走既有 `_regenerate`**(judge→refiner 的 refiner):一句重写指令重调 tutor;失败落既有阶梯兜底 + `stuck`。不新增学生可见模板、不删词、不做解析脱敏。 | `kernel.py` `_PREMATURE_CONFIRM_CRITIQUE` |

测试:+5 例(`tests/teaching/test_kernel_ready_gate.py`);2 例既有构造按新不变量改写(见 §5)。

## 2. 帧口径(可比性)

| 项 | 值 |
|---|---|
| before | `b5b9c77`(main,#148 已合)kernel sha256 `ef4af3041db6…`,`has_gate=False` |
| after | `38028ba`(本 PR)kernel sha256 `565079a19305…`,`has_gate=True` |
| 输入 | F/R 口径用例 = #148 冻结工件 `teaching-arc-fix112/before101/{F,R}/M/cases.jsonl` **原样**;P 口径 = `scripts/tuning_round.py` 夜评同源 11 场景 |
| 被测对象 | `KernelSubject`(start→reply×N→finish),tutor Qwen3-VL-8B@8303,judge mlx_27b@8301,并发 2,`models.yaml` sha256 `3feca1b4…`(两侧同) |
| 代码隔离 | 两侧各在**独立 git worktree + 独立 venv** 跑(共享检出被并发切换过一次,已弃用其数据) |

帧目录:`P/{pre,post,pre-run2,post-run2}`、`F/{pre,post}`、`R/{pre,post}` —— 每目录含 `cases.jsonl`、`results/`(逐例 transcript)、`summary.json`(含 provenance)、`SOURCE.txt`;P 目录另含 `comparison.md`、`judge-scores.json`。

## 3. 验收三条(逐条给工件出处)

### ① chicken_rabbit:复讲步可达,学生自己说出答案的那一轮出现 → ✅

`F/post` `results/*dialogue_stability_20_stability_chicken_rabbit__r1.json`(逐轮原文):

- 第 3 轮学生「实际比16只多10只,每把一只鸡换成兔会多2只脚。」→ 模型原拟「…那需要换5只兔。我们来验证一下:5只兔有20只脚,3只鸡有6只脚,加起来是26只脚…」并置 `ready_to_confirm`;
- **闸命中**(`guard_events` 有 `{"guard":"premature_confirm","original":"…需要换5只兔。…加起来是26只脚…"}`),该轮学生可见文本被重写为「你刚才说每把一只鸡换成兔会多2只脚,那要补上10只脚,需要换多少只兔呢?」→ 状态 `dialogue`;
- 第 4 轮学生自己说出答案「所以兔有10除以2等于5只,鸡有3只,检查5乘4加3乘2等于26。」→ 确定性复讲引导(`guard_events` 有 `{"branch":"elicit"}`),学生可见文本 = 「很好,你已经懂了。那请你从头讲讲你的思路…」。

before 同例(`F/pre`)第 3 轮即 `ready_to_confirm` 收尾,剧本第 4 轮(复讲内容)永不发生。

### ② 剧本截断计数 → ✅(P 口径 2/4 → 4/4;F/R 提前判停归零)

截断口径:`执行轮数 = transcript 轮数 − 1`;分类器(`/tmp/f149/classify.py` 同逻辑)按「末态是否 `ready_to_confirm` + 学生是否已陈述答案数字集」判读,逐例给结论。

**P 口径(夜评同源,11 场景)** —— word_problem 两个场景(各 4 轮剧本):

| 帧 | dialogue word_problem | shadow word_problem | 闸命中 |
|---|---|---|---|
| `P/pre`(run1) | **2/4** 末态 ready_to_confirm | **2/4** 末态 ready_to_confirm | 0 |
| `P/pre-run2` | **2/4** | **2/4** | 0 |
| `P/post`(run1) | **4/4** ✅ | **4/4** ✅ | 1 / 1 |
| `P/post-run2` | **4/4** ✅ | **4/4** ✅ | 1 / 1 |

**F 口径(22 例 = 11 场景 × 2 重复)**:

| 帧 | 截断 | 其中「提前判停」 |
|---|---|---|
| `F/pre` | 4/22(全部为 chicken_rabbit ×4,3/4,末态 ready_to_confirm,学生未陈述答案) | **4** |
| `F/post` | **0/22** | **0** |

**R 口径(20 例 = 10 incorrect 场景 × 2 重复)**:

| 帧 | 截断 | 其中「提前判停」 | 合法确认(学生已陈述答案后确认) |
|---|---|---|---|
| `R/pre` | 6/20(chicken_rabbit ×2、shadow fraction_addition ×2、shadow triangle_area ×2) | **4**(chicken_rabbit ×2、fraction_addition ×2) | 2 |
| `R/post` | 2/20 | **0** ✅ | 2 |

> R 剩 2 例为 **合法确认**:`R/post` shadow triangle_area 第 4 轮学生说出答案(30)→ 复讲引导;第 5 轮复讲完 → 模型确认。截断分类器给「合法确认」,不是缺陷。

### ③ 零回归红线 → ✅(correct 路径 12/12;R6 绿)

- **correct 路径**:P 口径 `dialogue_scenarios_equation_complete_reasoning`(answer_status=correct)R1/R2 = 8/8 → **before 12 / after 12**(两样本均 12):`P/pre`、`P/post`、`P/pre-run2`、`P/post-run2` 的 `comparison.md` 同一行;
- **合法确认仍放行**:单测 `test_gate_allows_confirm_when_student_stated_answer`;R 口径 2 例真实「学生已陈述→确认」照常通过;
- **R6 确定性套件**:`make check` **599 passed**(含 `tests/teaching/` 175 例:r6 套件 + #112 合同 + 本 PR 新增 5 例)。

## 4. P 口径判定表(before ×2 样本 → after ×2 样本)

| 场景 | R1 | R2 | pre-run1 | pre-run2 | post-run1 | post-run2 |
|---|---:|---:|---:|---:|---:|---:|
| equation_complete_reasoning(**) | 8 | 8 | 12 | 12 | 12 | 12 |
| dialogue chicken_rabbit | 6 | 9 | 8 | 8 | 7 | 7 |
| dialogue equation_subtract | 7 | 7 | 12 | 12 | 12 | 12 |
| dialogue fraction_addition | 3 | 4 | 12 | 10 | 9 | 9 |
| dialogue triangle_area | 3 | 3 | 10 | 10 | 8 | 8 |
| dialogue word_problem | 11 | 5 | 5 | 4 | **11** | **11** |
| shadow chicken_rabbit | 5 | 5 | 8 | 8 | 7 | 7 |
| shadow equation_subtract | 4 | 4 | 12 | 12 | 12 | 12 |
| shadow fraction_addition | 3 | 4 | 12 | 10 | 9 | 9 |
| shadow triangle_area | 2 | 3 | 10 | 10 | 8 | 8 |
| shadow word_problem | 11 | 8 | 5(低于基线) | 4(低于基线) | **11(不劣)** | **11(不劣)** |

(**)correct 路径哨兵。对两轮均值差:pre +4.05 / post +4.05(两侧总分巧合相同,构成不同:word_problem 两行各 +6~+7,另 4 行各 −1~−3。)

**word_problem 五维齐升**(`P/pre-run2 → P/post-run2` judge 逐维):first_question 0→1、socratic_followup 1→2、pacing 0→2、summary_mastery 1→2、termination 0→2,合计 4→11。

## 5. 上报两条(按「不自行归类」纪律,原文引用)

### 上报 1:闸后对话在剧本末轮仍在进行 → judge 的 summary/termination/pacing 维度扣分

P 口径 4 行 −1~−3 的构成(judge 逐维,`P/pre-run2 → P/post-run2`):

| 场景 | 维度变化 | 读法 |
|---|---|---|
| chicken_rabbit(dialogue+shadow) 8→7 | socratic_followup 1→2、`answer_leaked` True→**False**;summary_mastery 1→0、termination 1→0 | 不提前确认了 → 剧本 4 轮走完仍未到合法收尾 → judge 判「无总结/无收束」 |
| triangle_area(×2) 10→8 | pacing 2→1、summary_mastery 2→1 | 同上 |
| fraction_addition(×2) 12/10→9 | pacing 2→1;`answer_leaked` False→**True** | 首问文本两帧不同(见 §7 方差),judge 首问/自评随之变 |

**性质**:这些扣分来自「对话被固定长度剧本截断在弧线中段」,不是教学行为退化 —— 闸的作用正是**不再提前宣布收束**。是否要把评测剧本延长(或把 summary/termination 维度在「剧本耗尽」时豁免),**属口径决策,我不自行归类**,交 PM/C 线裁定。

### 上报 2:跨时间窗的模型输出方差(帧解读必须带上)

同一侧连跑两样本结果稳定(post 侧 11 行逐分相同),但两侧之间**若干首问文本不同**、同一 before 侧 fraction_addition 两样本 12/10 不同。例:

- `P/pre` fraction_addition 首问「你好呀,我们一起看看这道关于分数加法的题,你打算先从哪一步开始算呢?」
- `P/post` 同场景首问「你已经知道怎么把两个分数加在一起了,还有没有不懂的地方?」

两帧首问均**无**护栏事件(排除①②改写),用例与提示词相同(`cases.jsonl` 两侧逐字节相同、`models.yaml` 哈希相同)→ 归因为**并发 2 下服务层批处理相关的跨轮方差**(temperature=0;轮内 r1/r2 两重复 10/10 逐字一致、跨进程单例复跑亦逐字一致,故不是随机噪声而更像时间窗相关)。**结论:所有 before/after 判断以「两侧同窗口连跑的两样本」为准(§3/§4),单轮 ±1~3 分不作为结论。**

## 6. 明确不做(边界)

不动评测协议 / 数据集 / judge 判据 / `baselines/` / P-F-R 口径;不读 `minimum_student_turns`(只作报告信号);不动 `prompting.py` 首问措辞;不引入任何模型自报字段;不做解析脱敏。④「顺序不敏感的数字集包含」**未新增**——#112 判据本身已是数字集包含(orders-insensitive),`test_shared_judge_core_order_insensitive_via_public_path` 复验「兔5只,鸡3只」命中「鸡3只,兔5只」。

## 7. 复现

```bash
# 帧(两侧各自 worktree,避免共享检出被切换)
cd <worktree> && EDU_FACTS_DIR=/tmp/facts ./.venv/bin/python scripts/tuning_round.py --out /tmp/P
./.venv/bin/python /tmp/f149/run_frames.py F /tmp/f149/f_cases.jsonl /tmp/f149/F   # F/R 口径
```
