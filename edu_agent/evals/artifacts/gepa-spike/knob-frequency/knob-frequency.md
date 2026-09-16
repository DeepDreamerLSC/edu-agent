# #256 旋钮频次分析(零模型调用)

**任务**:PM 直发 2026-09-17(`sha256=ee6c92c56f561fa1`)——哪些确定性模板在本仓证据面上真的触发过,为路线键 v2 备裁定弹药。**只交事实表:不写新实验、不改判读、不选杠杆**。

**匹配口径**(审查者复现清单同款,#256 评论 5697507803):信号判定一律 import kernel 既有信号函数(`_student_signals_understanding` / `_student_signals_stuck` / `_student_signals_completion`),**不自造正则**;轮级触发以 `guard_events` 埋点为权威(`branch=elicit/support/reveal/answer_collect`、`guard=premature_confirm` 及泄漏族);匹配器 = `analyze.py`(本目录,零调用,逐案逐轮原始命中见 `matches.json`)。

## 数据面(四层,先说清一件事)

**派单假设「round-00/01.json 含逐案逐轮转录」与工件实况不符**(review-303 P1-① 已裁事实):配对工件只含分数/判定,无转录。因此配对运行层(下表 S3)只能提供 hit 验证与 Δ 概览,「模板是否注入」的转录级证据由 S4(全转录空转扫描)承担。本分析据实扩展证据面:加入 main 上**唯一成套真实转录**(S2)做实证对照——否则全部旋钮都只能标「推断」。

| 层 | 来源 | 身份 |
|---|---|---|
| S1 数据集 | `edu_agent/evals/datasets/small_lecturer_image_teaching_v1.json`(8 案×3 轮 student_turns) | main `f9d80af`,sha256 `1256d23df69afdc4…` |
| S2 转录 | `edu_agent/evals/artifacts/149-ready-gate/**/results/*.json`(F 44 + P 44 + R 40 = **128 件 / 638 轮**真实运行转录,guard_events 完整) | main `f9d80af` |
| S3 配对 | `gepa-spike/paired-experiment/round-00\|01.json + paired-report.json` | `task/256-paired-experiment` @ `a0142577`(26dab44a 后工件零改动,已核 diff=0) |
| S4 探针 | `gepa-spike/structural-probe/round-00.json`(逐案首问 + 全转录空转扫描 idle 判定) | `probe/structural-variant` @ `74c87e6d`(6c68289) |
| 代码基准 | `edu_agent/agents/small_lecturer/kernel.py` | main `f9d80af`,sha256 `d1c0612bdaf7cf57…`(行号以此为据;#302 合并后较派单所引 L810-828 有位移) |

## 频次表(逐旋钮;S1=案数,S2=案/轮,S3/S4 见注)

| 旋钮(调用点) | 触发条件(代码路径) | S1 elicit 8 案 | S2 149 转录 | 判定 |
|---|---|---|---|---|
| **elicit 复讲** `_ask_restatement`(L688;理解信号路径) | `_student_signals_understanding`(L111)于 reply L812 | **0/8 案,0 轮** | **10 场景/20 运行件,54 轮** | **此数据集不可达**(双源一致,见下) |
| elicit 复讲(答案命中路径) | `_student_hits_known_answer`(L148,仅 `answer_status=incorrect`)reply L824 | 不可达:8/8 案无 incorrect 字段 | (并入上行合计) | 不可达(弧线前提缺失) |
| **support 拆小问句** `_stuck_hint`(L187 guiding_focus) | `_student_signals_stuck`(L119)于 reply L816;埋点 `branch=support` | **1/8 案**(`image_v1_visual_statistics_open_30` turn[2]「选做那题太难了,我连点阵怎么摆的都看不清。」) | 0 案/0 轮 | 数据面触发信号成立 = **唯一可达候选**;运行时是否真触发依赖会话状态(move 选择)→ **推断,非转录实证** |
| **reveal 揭示阶梯** `_reveal_stuck_hint`(L329) | stuck telling / 复读降级 / 护栏兜底;埋点 `branch=reveal` | 1/8 案有 stuck 信号(潜在入口) | **1 场景/2 运行件,2 轮**(fraction_addition r1/r2) | 同上;S2 实证其在真实对话可触发 |
| **answer_collect 采集追问** `_ask_final_answer`(L695) | incorrect + `_student_signals_completion`(L137)+ 未述答案 + 会话首次,reply L830-840;埋点 `branch=answer_collect` | **0/8 案**(completion 0/8;incorrect 前提缺失) | 0 案/0 轮 | **不可达**(双前提全缺) |
| **判停闸重写** `_gate_premature_confirm`(L760) | 模型 ready + 答案有数字 + 学生未述;fail-open 无数字不闸;埋点 `guard=premature_confirm` | 依赖模型 ready,不可静态判定;P 口径评测不喂答案 → fail-open → **推断不可达** | **4 场景/8 运行件,16 轮** | elicit 线不可达(评测口径);真实对话线活跃 |
| **泄漏/代喂护栏族**(`_repair_feeds_method` L791 等;`_record_event` L480) | 模型输出含未授方法词/终答;soften cut/mask、dropped、mode=regenerated/masked/template、value_disclosure | 依赖模型输出,不可静态判定 | **6 场景/16 运行件,38 轮** | elicit 线未观测触发(配对运行 idle);真实对话线活跃 |
| **finish 零调用模板** `_structured_summary` | 确认态 + correct + 无卡点 | 依赖模型 ready,不可静态判定 | **8 运行件**(旧文案「是你自己讲下来的」) | 真实对话线触发过 |
| **finish needs_review**(`NEEDS_REVIEW_TEXT` L368;#302 起另有 `FINISH_EVIDENCE_TEXT` L371) | 未达确认态 finish | 依赖模型 ready | **42 运行件**(全部 NEEDS_REVIEW_TEXT 形态;无 bottom-out 前缀案) | 真实对话线高频 |

S3 注:round-00/01 `template_hit_validation` 均 `hit_count=0/8、samples=[]`——该验证**结构性失效**(P1-①:`first_question` 全仓无产出方),0/8 不能当「模板未注入」的证据;Δ 概览:round-00 7/8 案 Δ=0,**round-01 8/8 案全零**(见 `matches.json`)。
S4 注:**idle 8/8 案、首问 parent≡variant 8/8、变体模板文本出现 0/8**——全转录空转扫描的转录级证据:配对运行中变体模板从未改变任何一轮输出。

## 结论(事实,非杠杆选择)

**此数据集(elicit 8 案)上:可达旋钮 = 卡壳支持族(support/reveal),依据 1/8 案存在真实 stuck 信号(唯一有数据面触发条件的旋钮);其余全部 0 触发或前提缺失**:

1. **elicit 复讲不可达,双源互证**:数据集侧 0/8 案理解信号(审查者复现清单原式复算 = 0,与 review-probe-rerun 回执「8/8 案零理解信号」一致)+ 运行侧 S4 全转录空转扫描 idle 8/8、首问 8/8 全同、模板文本 0 出现。两独立证据源指向同一事实:**注入点不触发**,而非「模板注入了但 judge 无感」。
2. **answer_collect 不可达**:0/8 完成表达信号,且 8/8 案无 `answer_status=incorrect`(分支仅 incorrect 弧线);S2 的 128 件转录亦 0 触发。
3. **判停闸/泄漏族/finish 三路**:S1 数据集层不可静态判定(依赖模型行为);在 S2 真实转录上全部活跃(闸 4 场景/16 轮、泄漏 6 场景/38 轮、finish 50 运行件;elicit 复讲 10 场景/54 轮)——**旋钮不是死码,是 elicit 数据集缺触发信号**。

口径边界:matchers 的信号函数与埋点键均为 kernel 内既有一手定义;「推断,非转录实证」已逐行标注(判停闸 P 口径、support 运行时 move 选择、泄漏族模型输出依赖、S1 层 finish 各路)。

## 复现

```bash
# S3/S4 源件按上表分支抽取到任意目录后:
.venv/bin/python edu_agent/evals/artifacts/gepa-spike/knob-frequency/analyze.py \
    --paired <S3 目录> --probe <S4 目录>
# S1/S2 直读本仓(main f9d80af);零模型调用;输出 matches.json + stdout 汇总
```
