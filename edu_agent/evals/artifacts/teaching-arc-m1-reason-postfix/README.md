# M1 · reason 字段修复后基线复测(#157 评审响应)

## 是什么

#157 评审(审查者 + PM 复核)确认两条**不属 reason 字段**的根因——卡壳信号漏判
(「我还不知道/我不会/不明白」误走模型路径)与数字守卫末值洗白(steps 无条件
白名单含末值=答案)——修复落在 #158(7bf0f4b)。本目录在**修复后基线**上重测
reason 字段的净效应,并按裁定补 **P 口径(判门/夜评)各一帧**(此前 reason 只在
F/R 口径测过,prompting.py 指令影响所有 tutor 调用,判门口径从未测过)。

- **before** = 7bf0f4b(main + #158 两修复,无 reason)
- **after** = 8dfa8a5(task/w4-reason-field 叠栈于 #158,含 reason 终版措辞)
- F 口径 = #143 冻结口径原样(11 场景 × 2 重复 = 22 份);P 口径 =
  `tuning_round.build_cases` 11 场景(gate 冻结 wiring:仅 word_problem 注入
  answer_status=correct),judge 27B 单遍——与夜评同源。
- 同 judge(mlx_27b,temperature=0,盲判)、同 tutor(qwen3_vl_8b)、
  同 models.yaml(sha256 六帧一致 `3feca1b4…`,见各 manifest.json)。

## 目录

| 目录 | 口径 | 内容 | sha |
|---|---|---|---|
| `before-run1/` `before-run2/` | F | 修复后基线(无 reason)两跑 | 7bf0f4b |
| `after-run1/` `after-run2/` | F | 修复后基线 + reason 两跑 | 8dfa8a5 |
| `P-baseline/` | P | 修复后基线(无 reason)夜评帧 | 7bf0f4b |
| `P-after/` | P | 修复后基线 + reason 夜评帧 | 8dfa8a5 |

F 每目录:`F/M/`(cases.jsonl + collect + judge-cases + judge-scores)+
`metrics.json` + `feeding-corpus.jsonl` + `manifest.json`。P 每目录:
`collect/` + `judge-scores.json` + `comparison.md` + `manifest.json`
(nightly 预检溯源)。

## F 口径四帧总表(22 份/帧)

| 帧 | 首问合规 | 代喂(judge) | 答案数字真泄露 |
|---|---|---|---|
| before-run1 | 22/22 | 0.364 (8/22) | **0 行** |
| before-run2 | 22/22 | 0.364 (8/22) | **0 行** |
| after-run1 | 22/22 | 0.455 (10/22) | **0 行**(4 行 = 学生已说答案的收尾确认,见下) |
| after-run2 | 22/22 | 0.182 (4/22) | **0 行** |

**与前六帧(修复前基线)的关键差异**:

1. **第 1 轮全演示泄露消失,且是确定性消失**。前六帧 after 两跑的 rabbit 第 1 轮
   「我还不知道怎么同时算两种动物。」全部误走模型路径并整题演示(逐字复现);
   本四帧(rabbit 4 case × 4 帧 = 16 次)该轮 guard_events 全部 `branch=reveal`
   ——确定性阶梯揭示,只给首级中间值(「假设全是鸡,算出总脚数」),不给终答。
   路由修复把「该走确定性阶梯的轮次」从模型路径收回,泄露与方差双来源关闭。
2. **真泄露 = 0(四帧)**。after-run1 的 4 行 answer_number 命中经逐轮复核为
   fraction_addition 第 4 轮:学生先自己说出「八分之七」(答案),导师做确认式
   收尾(「6+1=7,分母都是8,所以确实是八分之七」)。学生已说 → 学生历史合法
   来源;该轮 7/8 未进违例池(ready 态答案池并入,#156 判停闸对「学生已说答案」
   正确放行)。属弧线允许的收尾确认,非 tutor 发起的泄露。判定规则更新:
   真泄露 = 教师说出/替算出**学生尚未给出**的参考答案数字。
3. **代喂(judge)在噪声带内,方向不定**:before 两跑恒 0.364;after 两跑
   0.455/0.182(同代码跨帧差 0.27)。前六帧测得的「0.182 减半、两跑复现」在
   修复后基线上**不再成立**——n=2 的复现落在轮转噪声带内,不足以宣称减半。
   此为对前六帧结论第 2 条的诚实修正(前六帧第 4 条「泄露场景轮换」同理)。
4. 首问合规 22/22 四帧不回归(硬约束保持)。

## P 口径(判门/夜评)对照

| 场景(短名) | R1×R2 基线 | 053133f 晨帧(main) | P-baseline(#158 修复) | P-after(修复+reason) |
|---|---|---:|---:|---:|
| scenarios equation_complete | 8,8 | 12 | 12 | 7 |
| dialogue chicken_rabbit | 6,9 | 8 | 5 | 7 |
| dialogue equation_subtract | 7,7 | 12 | 12 | 8 |
| dialogue fraction_addition | 3,4 | 10 | 9 | 8 |
| dialogue triangle_area | 3,3 | 10 | 8 | 6 |
| dialogue word_problem | 11,5 | 4 | 11 | 11 |
| tc chicken_rabbit | 5,5 | 8 | 5 | 7 |
| tc equation_subtract | 4,4 | 12 | 12 | 8 |
| tc fraction_addition | 3,4 | 10 | 9 | 8 |
| tc triangle_area | 2,3 | 10 | 9 | 6 |
| tc word_problem | 11,8 | 4 | 11 | 11 |
| **合计(对 R1×R2 均值差)** | | 110(+3.50) | 103(+3.77) | 87(+2.32) |

六维均分(0-2,P-baseline → P-after):首问 1.27→0.91 | 追问引导 1.82→1.82 |
年级适配 2.00→2.00 | 节奏 1.36→1.18 | 总结与掌握 1.45→1.00 | 终止 1.45→1.00。

**读数(逐维归因,transcript 定性核实过)**:

- **升**:chicken_rabbit 两格 +2(5→7):t1 卡壳轮确定性揭示 + 追问/节奏改善
  ——路由修复在判门口径同样兑现。
- **降(集中在「学生已会/顺推」场景)**:equation 系三格(12→7/8/8)掉分维度
  一致(首问/节奏/总结/终止);triangle 两格(8/9→6)是**引导问句复读循环**
  (「你猜猜,为什么三角形面积要除以2?」第 3、4 轮逐字重复,收尾不收束)——
  reason 的引导计划在同一问点上打转,无 reason 帧对应轮次措辞更多样。
- **门不破**:json_first_pass M2 门(≥98%):P-baseline 100%(293/293)、
  P-after 窗口 99.8%(858 份中 2 份 truncated 均为历史会话,非本帧)。
  场景级「低于基线」格三帧各现 1-2 格且格位轮换(晨帧 word_problem×2、
  P-baseline chicken、P-after equation_complete)——夜评口径本就
  「不 gate 判达标,只看逐题六维分与 pass 数的日间轨迹」。
- **单帧声明**:P 口径场景分单帧抖动大(word_problem 同线 4↔11 摆动),
  本两帧是**判门帧的前置证据**,不是判门结论;reason 对 M2 gate 的净影响
  需夜评多帧轨迹裁定。系统性信号(六维均值全降、复读机制)值得在判门前
  用夜评轨迹复核。

## 结论(#157 净效应,修复后基线)

1. **「泄露前移到第 1 轮」不再归因于 reason**:该模式由卡壳路由缺口承载,
   修复后四帧 F 口径真泄露 0,卡壳轮确定性走 reveal(16/16)。
2. **F 口径(reason 净效应)**:泄露 0、首问 22/22 保持;代喂在轮转噪声带内
   (0.182-0.455),无稳定方向——前六帧的「代喂减半」结论撤回,改为
   「噪声带内、无显著效应」。
3. **P 口径(前置证据)**:总分 87 vs 103(fix-only)/110(晨帧 main);
   掉分机制 = 引导问句复读 + 收尾弱化,收益 = 卡壳场景改善;M2 结构门不破。
4. **措辞不再迭代**:裁定条件「重测后泄露仍前移到第 1 轮」未触发(真泄露 0),
   硬约束(首问 22/22)四帧保持。

## 复现

F:在被测帧工作树跑 `arc_eval_fix112_frames.py --frame {before,after}
--calibers F --out <dir>` → `arc_eval_judge.py --out <dir>/<frame>` →
`arc_eval_metrics.py --out <dir>/<frame>`(工具不入库;模型经 Mac
8301/8303,SSH 隧道)。P:`scripts/tuning_round.py --nightly --out var/tuning/<name>`。
