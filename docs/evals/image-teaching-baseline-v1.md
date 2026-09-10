# 题图教学评测集 v1 基线(#130 WP5)

**用途**:M3 调优的基线参考。本集测的是**看图教学能力**(不是看图解题)——11 场景 gate 段全是纯文本,
本段补上「题图 → 首问 → 多轮」的带图能力口径。

## 1. 跑批口径

| 项 | 值 |
|---|---|
| 数据集 | `edu_agent/evals/datasets/small_lecturer_image_teaching_v1.json`(approved 8 条,用户 WP4 人审选定;内容与答案取 WP3 步骤 4/5 仲裁定稿) |
| 代码 | `a89d1aa` |
| 被测对象 | `KernelSubject`(内核三函数,tutor = `qwen3_vl_8b`,VL 主选) |
| Judge | `mlx_27b`(Qwen3.5-27B-4bit,**单遍 primary**,同 11 场景口径) |
| 运行位置 | **Mac 本地**(runner 宿主),非隧道 |
| 命令 | `python scripts/image_teaching_round.py --dataset … --out var/…` |

**结论:pass 2/8**(`application_table_14` 11 分、`fraction_formula_06` 10 分),review 2/8,fail 4/8,1 例判泄露。

## 2. 逐题六维 judge 分

| 题 | 桶 | 视觉依赖 | first_question | socratic_followup | grade_fit | pacing | summary_mastery | termination | 总分 | 判定 | 泄露 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `application_table_14` | application_table | helpful | 1 | 2 | 2 | 2 | 2 | 2 | **11** | **pass** | 否 |
| `fraction_formula_06` | fraction_formula | required | 1 | 2 | 2 | 2 | 1 | 2 | **10** | **pass** | 否 |
| `fraction_formula_09` | fraction_formula | required | 1 | 2 | 2 | 1 | 1 | 1 | **8** | review | 否 |
| `circle_geometry_20` | circle_geometry | required | 2 | 2 | 2 | 1 | 0 | 0 | **7** | review | 否 |
| `text_position_05` | text_position | required | 2 | 1 | 2 | 1 | 0 | 0 | **6** | fail | 否 |
| `percentage_multi_part_23` | percentage_multi_part | required | 0 | 1 | 2 | 1 | 1 | 1 | **6** | fail | **是** |
| `visual_statistics_open_27` | visual_statistics_open | required | 1 | 1 | 2 | 0 | 0 | 0 | **4** | fail | 否 |
| `visual_statistics_open_30` | visual_statistics_open | required | 0 | 1 | 2 | 0 | 0 | 0 | **3** | fail | 否 |
| **均分** | | | **1.00** | **1.50** | **2.00** | **1.00** | **0.63** | **0.75** | **6.9** | | |

**结构性观察**:

- `grade_fit` 8/8 满分(2.00)——年级口吻稳;**没有一题因年级不适掉分**。
- `summary_mastery`(0.63)与 `termination`(0.75)是最弱两维:4 题以 `needs_review` 收尾,
  小结退化成兜底句「这一题的学习证据还不够,我们继续……」。**2 题达标恰是 `completed` 收尾的两题**。
- `first_question` 均分 1.00(8 条里 3 条得 0/1 分以下),带图首问普遍偏弱(见 §3)。
- **1 例判泄露**(`percentage_multi_part_23`)——唯一 `answer_leaked=true` 的题。

## 3. 首问是否真用图(逐题人工判读,引转录对照)

判据:首问是否引用了**只能从图里得到**的信息(转录文本已给的数字不算用图)。逐题对照题面转录:

| 题 | 首问原文 | 该信息来自 | 真用图 |
|---|---|---|---|
| `fraction_formula_06` | 「**你数对了圆片总数是 12 个**,下一步我们来算 3/4 是多少…」 | 转录只说「如右图,将这些圆片的 3/4 涂上蓝色…」,**12 个只能数图** | ✅ |
| `visual_statistics_open_27` | 「你已经看懂了**水位变化的三个阶段**,还有没有不懂的地方?」 | 折线段数只能读图(转录无曲线信息) | ✅ |
| `fraction_formula_09` | 「你已经看懂图了,现在来选一选,哪个选项是倒出的水量?」 | 选项在转录里已有;泛问,未引剩余分率 | ✗ |
| `circle_geometry_20` | 「你已经看懂了这道题的图和要求,还有没有不懂的地方?」 | 泛问,未引任何标注值 | ✗ |
| `text_position_05` | 「你已经看懂题图了吗?想先从哪个小问开始?」 | 泛问,未引方位角 | ✗ |
| `percentage_multi_part_23` | 「你已经看懂了两个问题的核心,还有没有不懂的地方?」 | 泛问 | ✗ |
| `application_table_14` | 「你已经看完了所有选项,现在告诉我,你认为哪一个是正确的?」 | 选项描述在转录里;泛问 | ✗ |
| `visual_statistics_open_30` | 「你已经看懂了三角形数和五边形数的规律,还有没有不懂的地方?」 | 名称在转录里;「规律」未落到点阵值 | ✗ |

**真用图 2/8**(`fraction_formula_06`、`visual_statistics_open_27`)。**6/8 是「你已经看懂了图…还有没有不懂的地方」这类元话语**——
模型知道有图,但首问没有把图的信息接进教学。这正是 M3 要调的点:`visual_dependency=required`
的 7 条里,只有 2 条首问真的用了图。

> 注:`fraction_formula_06` 的判读**依赖 WP3 步骤 4 的转录定稿**——旧转录带「(图:3×4=12个圆)」旁注,
> 12 个属文本可得;去掉旁注后 12 个只能数图,该题才成为真正的带图题。

## 4. 答案确定性校验(answer_type 自动比对)

| 题 | answer_type | 参考答案 | 自动比对 | 说明 |
|---|---|---|---|---|
| `fraction_formula_06` | **integer** | `9` | ✅ 命中 | 唯一可数值自动判的题 |
| `application_table_14` | text | `C` | ✅ 命中 | 文本包含 |
| `fraction_formula_09` | text | `C(800×5/8)` | ❌ 未命中 | 未走到收束给结论 |
| `circle_geometry_20` | text | 三小问 | ❌ 未命中 | 同上 |
| `percentage_multi_part_23` | text | 两问 | ❌ 未命中 | 且判泄露 |
| `text_position_05` | text | 四空方位 | ❌ 未命中 | 同上 |
| `visual_statistics_open_27` | text | `A` | ❌ 未命中 | 未走到收束 |
| `visual_statistics_open_30` | text | 数+通项 | ❌ 未命中 | 同上 |

**命中 2/8**。⚠️ 口径提醒:8 条里 **7 条 `answer_type=text`**,只有 1 条 `integer`——
真正「确定性」的自动比对只对 1 条成立,其余是文本包含(提示性)。想把这个指标做实,M3 扩集时
应提高 `integer`/`fraction`/`decimal_*` 题的比例(本集选 8 时已提示过这一点)。

## 5. 效率(Mac 本地采集)

| 题 | 端到端 total_ms |
|---|---:|
| `fraction_formula_06` | 6 882 |
| `fraction_formula_09` | 8 793 |
| `text_position_05` | 10 609 |
| `visual_statistics_open_30` | 11 372 |
| `visual_statistics_open_27` | 11 504 |
| `circle_geometry_20` | 12 045 |
| `percentage_multi_part_23` | 12 906 |
| `application_table_14` | 14 653 |

中位 11.5 s,区间 6.9–14.7 s。同机同服务采集(非隧道),但**单遍、并发 2**,只作量级参考,不作门限。

## 6. 已知口径差异(不藏)

1. **评测面不给内核传 `answer`**:`KernelSubject.run_case` 只传 `{text, image}`,生产
   (`api/service.py` ← 题源)传 `{text, answer, analysis, knowledge_points}`。内核 answer-leak
   护栏因此在评测里拿不到答案,规则与生产不同(带 answer 命中 `grounded_answer_disclosure` 并重生成;
   不带则 `unverified_source_value_disclosure` 放行)。本集与 11 场景保持同口径,**未**单方面改;
   是否统一另议(已报 #130)。§2 的 `percentage_multi_part_23` 泄露判定可能受此影响。
2. 本集**不进 11 场景 gate 口径**(无遗留对照),夜评只作日间轨迹记录,不判达标。
3. 单遍 judge + 温度 0 仍有模型侧波动:`fraction_formula_09` 在两次跑批间从 12(pass)掉到 8(review),
   该题结论请按区间看,不要当精确值。

## 7. 复现

```bash
# Mac 本地(runner 宿主),非隧道
python scripts/image_teaching_round.py \
  --dataset edu_agent/evals/datasets/small_lecturer_image_teaching_v1.json \
  --out var/image-teaching/baseline-v1
# 产物:comparison.md / judge-scores.json / judge-cases.jsonl / cases.jsonl / collect/
```
