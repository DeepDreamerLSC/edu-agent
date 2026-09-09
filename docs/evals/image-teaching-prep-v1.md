# 题图评测集 v1 评分表(image-teaching-prep-v1)

**状态**:`visual_inspection_pending`(Dev A 视觉通道待解锁后填)
**依赖**:#130 规范(含 p1-p8/s1-s9)、#34 裁决链、WP1-WP5 工作包。
**数据基线**:`pilot-30.jsonl`(30 条 ↔ 257 张对账,29/30 命中,缺 #18 已报)

## 1. 对账结果(步骤 1,已完成)

- 30 条 ↔ 257 张 sha256 逐条匹配,29/30 命中。
- **缺图**:idx 18,circle_geometry,`4-1圆的认识`,qid `6a62f678184f723b3592b93f`,sha `ae0f4ec5f123b1ba3c81a6254a7cd9de131bc50bbcd4961847a5bf6e9d8a7eaf`。已评论 [#130 #5603934633](https://github.com/DeepDreamerLSC/edu-agent/issues/130#issuecomment-5603934633)。
- 六桶分布:各 5 条(均匀)。

## 2. 硬门 ① 结果(免视觉预筛)

硬门 ① 四子项(复用 reliability 失败模式):
- (a) 非整页截图 ✅ 全通过(最大 1187×266 / 37KB,远低于 1500px 或 400KB 阈值)。
- (b) 长宽比可归一化 → 11 张 ratio>8 标 `normalize`,其余 `-`。
- (c) 文字可读 ⏳ 待目检。
- (d) 无裸 LaTeX ⏳ 待目检。

| idx | bucket(中) | bucket | qid | 尺寸 | ratio | 字节 | 归一化 | 整页 | 文字可读 | 无裸 LaTeX | 硬门 ① 总判 |
|---:|---|---|---|---|---:|---:|:---:|:---:|:---:|:---:|:---:|
| 1 | 坐标定位 | text_position | `6a61a8dabd46…` | 888×28 | 31.7 | 11258 | Y | - | ⏳ | ⏳ | ⏳ |
| 2 | 坐标定位 | text_position | `6a61a8e5bd46…` | 856×62 | 13.8 | 15736 | Y | - | ⏳ | ⏳ | ⏳ |
| 3 | 坐标定位 | text_position | `6a61a907bd46…` | 748×452 | 1.7 | 60297 | - | - | ⏳ | ⏳ | ⏳ |
| 4 | 坐标定位 | text_position | `6a61a927bd46…` | 1183×198 | 6.0 | 34139 | - | - | ⏳ | ⏳ | ⏳ |
| 5 | 坐标定位 | text_position | `6a69586fb0ff…` | 341×349 | 1.0 | 25186 | - | - | ⏳ | ⏳ | ⏳ |
| 6 | 分数公式 | fraction_formula | `6a695a01b0ff…` | 423×153 | 2.8 | 13029 | - | - | ⏳ | ⏳ | ⏳ |
| 7 | 分数公式 | fraction_formula | `6a61b319f0e2…` | 718×52 | 13.8 | 9629 | Y | - | ⏳ | ⏳ | ⏳ |
| 8 | 分数公式 | fraction_formula | `6a61b33cf0e2…` | 419×86 | 4.9 | 7008 | - | - | ⏳ | ⏳ | ⏳ |
| 9 | 分数公式 | fraction_formula | `6a61b366bd46…` | 813×192 | 4.2 | 21599 | - | - | ⏳ | ⏳ | ⏳ |
| 10 | 分数公式 | fraction_formula | `6a695a176c23…` | 307×211 | 1.5 | 10296 | - | - | ⏳ | ⏳ | ⏳ |
| 11 | 应用表格 | application_table | `6a62c9a999bf…` | 877×51 | 17.2 | 12336 | Y | - | ⏳ | ⏳ | ⏳ |
| 12 | 应用表格 | application_table | `6a62c9b499bf…` | 473×51 | 9.3 | 4650 | Y | - | ⏳ | ⏳ | ⏳ |
| 13 | 应用表格 | application_table | `6a699cc32ef3…` | 468×146 | 3.2 | 13521 | - | - | ⏳ | ⏳ | ⏳ |
| 14 | 应用表格 | application_table | `6a62ca0099bf…` | 527×163 | 3.2 | 21091 | - | - | ⏳ | ⏳ | ⏳ |
| 15 | 应用表格 | application_table | `6a62ca0999bf…` | 409×50 | 8.2 | 7040 | Y | - | ⏳ | ⏳ | ⏳ |
| 16 | 圆几何 | circle_geometry | `6a62f66a184f…` | 463×28 | 16.5 | 7593 | Y | - | ⏳ | ⏳ | ⏳ |
| 17 | 圆几何 | circle_geometry | `6a62f66f184f…` | 330×28 | 11.8 | 5771 | Y | - | ⏳ | ⏳ | ⏳ |
| 18 | 圆几何 | circle_geometry | `6a62f678184f…` | 892×28 | 31.9 | MISSING | Y | - | ⏳ | ⏳ | ⏳ |
| 19 | 圆几何 | circle_geometry | `6a62f68399bf…` | 859×97 | 8.9 | 23018 | Y | - | ⏳ | ⏳ | ⏳ |
| 20 | 圆几何 | circle_geometry | `6a69e0d72ef3…` | 582×221 | 2.6 | 31413 | - | - | ⏳ | ⏳ | ⏳ |
| 21 | 百分数 | percentage_multi_part | `6a63152599bf…` | 1101×220 | 5.0 | 35734 | - | - | ⏳ | ⏳ | ⏳ |
| 22 | 百分数 | percentage_multi_part | `6a63156999bf…` | 645×194 | 3.3 | 27890 | - | - | ⏳ | ⏳ | ⏳ |
| 23 | 百分数 | percentage_multi_part | `6a69e6862ef3…` | 655×356 | 1.8 | 44449 | - | - | ⏳ | ⏳ | ⏳ |
| 24 | 百分数 | percentage_multi_part | `6a6955706c23…` | 538×39 | 13.8 | 5161 | Y | - | ⏳ | ⏳ | ⏳ |
| 25 | 百分数 | percentage_multi_part | `6a6955936c23…` | 393×72 | 5.5 | 7044 | - | - | ⏳ | ⏳ | ⏳ |
| 26 | 图形统计开放 | visual_statistics_open | `6a69e8892ef3…` | 571×338 | 1.7 | 42496 | - | - | ⏳ | ⏳ | ⏳ |
| 27 | 图形统计开放 | visual_statistics_open | `6a69e89d2ef3…` | 1187×266 | 4.5 | 37882 | - | - | ⏳ | ⏳ | ⏳ |
| 28 | 图形统计开放 | visual_statistics_open | `6a631f21184f…` | 922×128 | 7.2 | 19065 | - | - | ⏳ | ⏳ | ⏳ |
| 29 | 图形统计开放 | visual_statistics_open | `6a631f3d184f…` | 1045×231 | 4.5 | 34592 | - | - | ⏳ | ⏳ | ⏳ |
| 30 | 图形统计开放 | visual_statistics_open | `6a631f46184f…` | 374×654 | 1.7 | 30432 | - | - | ⏳ | ⏳ | ⏳ |

## 3. 三维评分(⏳ 待目检后填)

排序制三维:视觉依赖度(`required`>`helpful`>`none`,权重最高)→ 对话承载力(误区咬得住+解路拆得开,s4)→ 答案确定性(数值型>文本型)。

| idx | bucket | visual_dep | 对话承载力 | 答案确定性 | 三维总分 |
|---:|---|---|---|---|---:|
| 1 | text_position | ⏳ | ⏳ | ⏳ | ⏳ |
| 2 | text_position | ⏳ | ⏳ | ⏳ | ⏳ |
| 3 | text_position | ⏳ | ⏳ | ⏳ | ⏳ |
| 4 | text_position | ⏳ | ⏳ | ⏳ | ⏳ |
| 5 | text_position | ⏳ | ⏳ | ⏳ | ⏳ |
| 6 | fraction_formula | ⏳ | ⏳ | ⏳ | ⏳ |
| 7 | fraction_formula | ⏳ | ⏳ | ⏳ | ⏳ |
| 8 | fraction_formula | ⏳ | ⏳ | ⏳ | ⏳ |
| 9 | fraction_formula | ⏳ | ⏳ | ⏳ | ⏳ |
| 10 | fraction_formula | ⏳ | ⏳ | ⏳ | ⏳ |
| 11 | application_table | ⏳ | ⏳ | ⏳ | ⏳ |
| 12 | application_table | ⏳ | ⏳ | ⏳ | ⏳ |
| 13 | application_table | ⏳ | ⏳ | ⏳ | ⏳ |
| 14 | application_table | ⏳ | ⏳ | ⏳ | ⏳ |
| 15 | application_table | ⏳ | ⏳ | ⏳ | ⏳ |
| 16 | circle_geometry | ⏳ | ⏳ | ⏳ | ⏳ |
| 17 | circle_geometry | ⏳ | ⏳ | ⏳ | ⏳ |
| 18 | circle_geometry | ⏳ | ⏳ | ⏳ | ⏳ |
| 19 | circle_geometry | ⏳ | ⏳ | ⏳ | ⏳ |
| 20 | circle_geometry | ⏳ | ⏳ | ⏳ | ⏳ |
| 21 | percentage_multi_part | ⏳ | ⏳ | ⏳ | ⏳ |
| 22 | percentage_multi_part | ⏳ | ⏳ | ⏳ | ⏳ |
| 23 | percentage_multi_part | ⏳ | ⏳ | ⏳ | ⏳ |
| 24 | percentage_multi_part | ⏳ | ⏳ | ⏳ | ⏳ |
| 25 | percentage_multi_part | ⏳ | ⏳ | ⏳ | ⏳ |
| 26 | visual_statistics_open | ⏳ | ⏳ | ⏳ | ⏳ |
| 27 | visual_statistics_open | ⏳ | ⏳ | ⏳ | ⏳ |
| 28 | visual_statistics_open | ⏳ | ⏳ | ⏳ | ⏳ |
| 29 | visual_statistics_open | ⏳ | ⏳ | ⏳ | ⏳ |
| 30 | visual_statistics_open | ⏳ | ⏳ | ⏳ | ⏳ |

## 4. 选出建议(程序约束 ⏳)

- 目标:12-15 题。桶覆盖贪心 / 集级难度目标 2 易·4 中·2 难(难题从 `visual_statistics_open` 出) / 正向对照 ≥ 1。
- 元原则:反循环,不选当前模型会做的题(评测集优化诊断力,不优化通过率)。
- 选出:待目检 + 盲测 + 三维分齐后定。

## 5. 后续动作(待视觉解锁)

1. 逐张目检 → 填硬门 ① (c)/(d) 列。
2. 人盲解 → 落 `blind-solve.jsonl`(schema 见 §6)。
3. Dev B VL 转录到位后 → 转录仲裁。
4. Dev B deepseek 盲测到位后 → 失败模式仲裁。
5. 三维评分 + 选出 + 剧本起草。

## 6. blind-solve.jsonl schema(v1)

```jsonc
// 每条过门候选(29 条,除缺图 #18 与目检出局)各一条
{
  "schema_version": "small_lecturer_image_blind_solve/v1",
  "solved_at": "2026-09-09T<ISO8601>",
  "solves": [{
    "idx": 1,                    // pilot-30 序号
    "question_id": "...",
    "bucket": "text_position",
    "image_sha256": "...",
    "image_file": "pqfile_xxx.jpg",
    "qgate_pass": true,          // 本表 §2 硬门 ① 总判
    "qgate_reason": "非整页/归一化后文字可读/无裸LaTeX",
    "transcription": "从图逐字抄录(图是源,与 B 的 VL 转录分开,待仲裁对齐)",
    "reference_answer": {"value": "62.8", "answer_type": "decimal_1", "unit": "米"},
    "solution_steps": ["步骤 1:…","步骤 2:…","步骤 3:…"],
    "visual_dependency_prelim": "required|helpful|none",
    "misconception_seed_prelim": "桶内误区池候选(待 WP4 人确认)",
    "difficulty_prelim": "easy|medium|hard",
    "dialogue_capacity_prelim": "high|medium|low"
  }]
}
```

**时序纪律**:本文件由 Dev A 在 Dev B 跑 deepseek 对照之前落盘,防锚定(#130 SOP s2)。
