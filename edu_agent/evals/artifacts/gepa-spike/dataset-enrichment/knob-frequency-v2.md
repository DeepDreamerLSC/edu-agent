# #256 路线 a:elicit 数据集富化——v2 案例集与信号验证(零模型调用)

**任务**:PM 直发 2026-09-17(`sha256=5c3f5b958923f8de`);用户已裁路线 v2=(a) 富化数据集——「先补足 understanding/stuck/completion 等真实触发分布,再继续 GEPA」。本工件 = 12 新案 + 匹配器逐轮验证记录 + 频次表。**零模型调用、零 LLM API;不写新实验**。

## 交付物

| 文件 | 说明 |
|---|---|
| `edu_agent/evals/datasets/small_lecturer_image_teaching_v2_enriched12.json` | 新案例集(12 案;**v1 文件零改动**,新文件机械方案 = 同 schema_version `small_lecturer_image_teaching/v1`,同一 loader/harness 可直接消费) |
| `edu_agent/api/static/bank/synthetic_v2_*.png` ×12 | 合成示意图(文件名前缀与真实题图池明确区分;治理②:零真实学生数据、零真实题库内容) |
| 本目录 `generate_images.py` | 图片生成器(stdlib 手写 PNG 编码,无 Pillow/无新依赖;确定性——无随机无时间戳,重跑字节一致,sha256 对账恒成立) |
| 本目录 `matches.json` | 匹配器在 v2 上的原始输出(逐案逐轮命中) |
| `edu_agent/evals/artifacts/gepa-spike/knob-frequency/analyze.py` | 匹配器(入仓口径)扩展:`--s1` 数据集覆盖参数 + answer-hit 核验(见下);**v1 默认跑复核零漂移** |

## 设计(跑前冻结口径的落法)

1. **词形 = kernel 既有信号函数的真实触发形态**(频次表 S1/S2 匹配口径,不自造同义新词):understanding = 「懂了/明白了/会了/没问题…」(L111 正则形态);stuck = 「太难了/没思路/还是不会/看不懂/有点不会/猜不出/想不出」(L119 八形态表);completion = 「算出来了/做完了…」(L137 实录集)。写完用入仓匹配器逐轮验证 ✓(下表)。
2. **信号模式建模自 S2 证据**(knob-frequency 工件):S2 真实转录中三族信号**零出现**——elicit 全走答案命中路径(末轮陈述结论数字,鸡兔同笼案 t4/t5);故 understanding/stuck 的位置模式取 S1 在库先例(信号位于中后段、进展或消化之后)与 kernel 测试基线词形;答案命中族照 S2 模式(纠错后末轮报结论数字)。**合成内容,不抄 S2/v1 文本**。
3. **难度带同档**:六年级、3 轮、v1 既有 bucket 词表(text_position/visual_statistics_open/fraction_formula/application_table/circle_geometry/percentage_multi_part)、expected.outcome 三值分布、visual_dependency=required。
4. **v1 复现性优先**:v1 数据集/工件/加载路径零改动;`to_cases` 增 1 行 `answer_status` 透传(additive;v1 无此字段默认空串,行为零漂移,测试钉)。

## 验收矩阵(匹配器重跑,逐轮记录见 `matches.json`)

| 信号族 | 目标 | 实测(12 案) | 案与触发轮 |
|---|---|---|---|
| understanding(→elicit 复讲) | ≥4 | **4** ✓ | understanding_01~04,各 t[2](消化后) |
| stuck(→卡壳支持族) | ≥4 | **4** ✓ | stuck_01 t[0,1](全局性双形态);stuck_02/03/04 t[1](进展后) |
| completion/answer-hit(→采集追问/答案命中+判停) | ≥4 | **4** ✓ | answercollect_01/02:completion 信号 t[1] 且结论数字未陈述(→`answer_collect` 分支);answerhit_01/02:结论数字 t[1] 命中(→`_student_hits_known_answer` 分支) |

- answer-hit 判定用 **kernel 一手判据**(`_question_numbers`/`_hits_numbers`):结论数字集 = `question.answer` 数字 − 题面数字(focus:answercollect_01 {10}、_02 {4}、answerhit_01 {4}、_02 {144});collection 案确认 **0 命中**(数字确未陈述)、hit 案各 1 轮命中 ✓。
- `question.answer` 与 `reference_answer.value` 一致性机检:**0 分叉**。
- 复现清单原式(understanding 命中案数)在 v2 上 = 4(v1 上 = 0——正是本单要补的分布)。

## 运行时使能事实(如实申明,供探针单使用)

- `answer_status=incorrect` 已随 v2 案入数据并经 `to_cases` 透传(本 PR 新增 1 行 + 2 测试)→ KernelSubject 会设 `learner.answer_status`(答案命中/采集追问分支的数据侧前提)✓;
- 答案命中分支在**运行时**还需内核看到答案数字(`_known_answer` = `question.answer` 优先)——v2 的 C 族已把 `answer` 写入 `question` dict,但 `_question_payload` 仅在 `feed_answer=True`(显式测量断点,#178 条件变更登记)时才喂——**该开关属未来探针单的点火面,本单未动**;
- 判停闸证据(C 族 hit 案的「已陈述结论数字」形态)同理:闸判据 `_student_stated_answer` 运行时依赖同上。
- **互补件互引**(PM 2026-09-17 裁定两层并存):`small_lecturer_signal_enrichment_v2.json`(signal_enrichment/v2 schema,纯文本题面,信号检测语料,tests/teaching 消费;其 description 侧互引见 PR #330)≠ 本件(image_teaching/v1 schema,图片题教学场景,评测线 harness/to_cases 消费面)。

## 来源与身份

- 基线:main `358f72a`(#304 合并后);kernel 信号函数/numeric 判据 sha256 见 `matches.json` 所引代码(本仓 main);v1 数据集 sha256 `1256d23df69afdc4…`(零改动);
- 图片:12 张合成示意图,`generate_images.py` 重跑可复现(确定性编码);bank 目录新增文件名前缀 `synthetic_v2_`;
- 治理②:无真实学生数据;案例文本为合成教学内容,信号词形来自 kernel 代码与测试基线(仓内一手),未抄任何转录内容。

## 复现

```bash
# 1. 图片(重跑字节一致,数据集 sha 对账)
.venv/bin/python edu_agent/evals/artifacts/gepa-spike/dataset-enrichment/generate_images.py
# 2. loader 校验 + 匹配器重跑(三族各 ≥4)
.venv/bin/python -c "from edu_agent.evals.image_teaching import load_scenarios; load_scenarios('edu_agent/evals/datasets/small_lecturer_image_teaching_v2_enriched12.json'); print('loader OK')"
.venv/bin/python edu_agent/evals/artifacts/gepa-spike/knob-frequency/analyze.py \
    --s1 edu_agent/evals/datasets/small_lecturer_image_teaching_v2_enriched12.json \
    --out edu_agent/evals/artifacts/gepa-spike/dataset-enrichment/matches.json
```
