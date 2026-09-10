# M1 · reason 规划字段 before/after 工件(#146,05 §5)

> **修复后基线复测**:本目录六帧跑于**修复前**基线(#157 评审确认其中第 1 轮
> 全演示泄露由卡壳路由缺口与允许集洗白两条根因承载,非 reason 字段)。
> 修复后(#158)基线的净效应复测与 P 口径(判门)帧见
> `teaching-arc-m1-reason-postfix/`——真泄露 0、代喂结论修正为噪声带内。

## 是什么

`TUTOR_TURN_SCHEMA` 增加 `reason` 规划字段(声明在 `reply` 之前 + required)的
before/after 评测工件。口径 F(#143 冻结口径原样:11 场景 × 2 重复 = 22 份
transcript)、臂 = post-#148 main(弧线已合入;b5b9c77),评测帧工具与 #112 同源
(`arc_eval_fix112_frames/judge/metrics.py`,评测分支工具,不入库)。

- **before** = b5b9c77(post-#148 main,无 reason)
- **after-run1/run2** = e632eb4(终版指令:作用域限定 + 「用提问让他自己算」)
- **after-v1-unconditional** = 9a684c8(迭代 1:无条件指令——数据保留供决策)
- **after-v2-prohibition** = e6fb27f(迭代 2:作用域 + 禁令「不替学生算出最终结果」)

同 judge(mlx_27b,temperature=0,盲判:case id 匿名、不含臂/分支/commit)、
同 tutor(qwen3_vl_8b)、同 models.yaml(sha256 见各 manifest.json)。

## 目录

| 目录 | 内容 | sha |
|---|---|---|
| `before-run1/` | before 首跑 | b5b9c77 |
| `before-run2/` | before 重跑(控制组:同代码零改动) | b5b9c77 |
| `after-run1/` | 终版 after 首跑 | e632eb4* |
| `after-run2/` | 终版 after 复现 | e632eb4* |
| `after-v1-unconditional/` | 指令迭代 1 | 9a684c8 |
| `after-v2-prohibition/` | 指令迭代 2 | e6fb27f* |

*after 帧跑批于 e632eb4/e6fb27f;分支历史随后重写(仅剔除误入的评测脚本),
同内容对应终分支 043568a/cfce131——kernel.py/prompting.py 逐字一致,manifest
里的 git_sha 为跑批时点原值。

每目录:`F/M/`(cases.jsonl + collect + judge-cases + judge-scores)+
`metrics.json` + `feeding-corpus.jsonl` + `manifest.json`(帧/模型/差异核对)。

## 结果总表(口径 F,22 份/帧)

| 帧 | 首问合规 | 复讲达成 | 代喂(judge) | 答案数字真泄露 |
|---|---|---|---|---|
| before-run1 | 22/22 | 0/22 | **0.364** (8/22) | 4 case(rabbit,第3轮替走最后一步) |
| before-run2 | 22/22 | 4/22 | **0.364** (8/22) | **0 case** |
| after-v1 | 17/22 ⚠️ | 9/22 | 0.364 (8/22) | 4 case(area,第3轮替算终答) |
| after-v2 | 18/22 ⚠️ | 7/22 | 0.455 (10/22) | 4 case(area,首问「是30平方厘米吗?」猜答) |
| after-run1 | 22/22 | 4/22 | **0.182** (4/22) | 4 case(rabbit,第1轮全演示「8-5=3只」) |
| after-run2 | 22/22 | 4/22 | **0.182** (4/22) | 4 case(rabbit,同上,逐字复现) |

判定说明:
- **代喂(judge)**:盲判四指标之 feeding.fed;before 两跑恒 0.364,终版 after 两跑恒
  0.182——**减半,复现稳定**。这是 reason 字段唯一稳定可复现的正向效应。
- **答案数字真泄露**:确定性扫描 answer_number 命中,人工逐句复核后剔除记法伪影
  (addition 场景:教师用阿拉伯记法 3/4、6/8 复述题目分数,参考答案 7/8 的分母 8
  被扫描器误计;学生用中文「八分之七」,扫描器不识别——教师行为本身是合规教学,
  答案数字 7 未泄露)。真泄露 = 教师说出/替算出学生尚未给出的参考答案数字。
- **泄露基线本身不稳定**:before 同代码两跑 = 4 case → 0 case。单跑 A/B 的
  「泄露场景轮换」(rabbit↔area)在噪声带内,不能归因;但**终版 after 的 rabbit
  全演示泄露逐字复现于两跑**(「剩下的就是鸡:8-5=3只」),是该指令措辞的系统性
  副作用(模型把「用提问让他自己算」执行为「演示计算再让学生验证」)。

## 结论(相对 05 §6 目标)

1. **违规强命中(答案数字) 5 → 0-1:未达成。** 泄露 case 数四帧恒 4/22(v1/v2/v3
   各 4),基线噪声带 0-4;reason 字段不减少答案数字泄露,只改变泄露落在哪个场景、
   以何种模式出现(验证式/替算式/猜答式/全演示式)。
2. **代喂率(judge)不升:超额达成。** 0.364 → 0.182(两跑复现),方法名词代喂与
   答案代喂的合并 judge 判定减半。
3. **首问合规**:终版 22/22 不回归(迭代 1 的无条件指令曾致 5/22 开场漂移为复讲
   指令;作用域限定修复)。
4. **成本**:tutor 输出 tokens p50 77-80 → 109-116(+~38%,reason 句约 30-40 tok)。
   单次调用总时延在共享 Mac 上噪声带 1772-4400ms(同代码两跑),无法据此归因;
   权威数字以 PR CI benchmark 门(tutor.ttft 86ms 宽松门 / e2e p50 835ms ±10%)为准。

## 顺序证明(验证 a)

真实 tutor 调用截获 TUTOR_TURN_SCHEMA 原始输出 4 次,字段序全部
`['reason', 'reply', 'ready_to_confirm', 'cited_numbers']`——schema 经
json.dumps 进 prompt,声明序即生成序;transcript 只落学生可见文本(turn.text),
reason 不落盘、不进 judge 输入(盲判 judge-cases 可核)。

## 工具与复现

帧/judge/metrics 脚本与 #112 同源(task/arc-eval 历史 84d6886),评测分支工具
不入库。复现:在被测帧工作树跑 `arc_eval_fix112_frames.py --frame {before,after}
--calibers F --out <dir>` → `arc_eval_judge.py --out <dir>/<frame>` →
`arc_eval_metrics.py --out <dir>/<frame>`(模型经 Mac 8301/8303,需 SSH 隧道)。
