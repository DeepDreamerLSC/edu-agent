# 题图评测集 v1 评分表(image-teaching-prep-v1)

**状态**:`visual_inspection_done` + `blind_solve_done`(待步骤 4/5 Dev B 转录仲裁+盲测后定选出)
**依赖**:#130 规范(含 p1-p8/s1-s9)、#34 裁决链、WP1-WP5 工作包。
**数据基线**:`pilot-30.jsonl`(30 条 ↔ 257 张对账,29/30 命中,缺 #18 已报)。
> Dev A(视觉线 w7)目检 + 人盲解 → `docs/evals/blind-solve.jsonl`(29 条,已先于 Dev B deepseek 落盘,防锚定)。

## 1. 对账(已完成)

- 30 条 ↔ 257 张 sha256 逐条匹配,**29/30 命中**。
- **缺图**:idx 18,circle_geometry,`4-1圆的认识`,qid `6a62f678184f723b3592b93f`,sha `ae0f4ec5f123b1ba3c81a6254a7cd9de131bc50bbcd4961847a5bf6e9d8a7eaf`。[#130 #5603934633](https://github.com/DeepDreamerLSC/edu-agent/issues/130#issuecomment-5603934633)
- 六桶分布:各 5 条(均匀;circle_geometry 因缺图存 4 条)。

## 2. 硬门 ① 质量门(已完成,0 出局)

四子项:非整页截图 / 长宽比可归一化 / 文字可读 / 无裸 LaTeX。**全部 29 条通过**(无整页截图;11 张 ratio>8 标归一化;29 张文字均清晰可读;无裸 LaTeX)。

| idx | bucket(中) | qid | 尺寸 | ratio | 归一化 | 文字可读 | 无裸LaTeX | 硬门① |
|---:|---|---|---:|---:|:---:|:---:|:---:|:---:|
| 1 | 坐标定位 | `6a61a8dabd46…` | 888×28 | 31.7 | Y | Y | Y | 通过 |
| 2 | 坐标定位 | `6a61a8e5bd46…` | 856×62 | 13.8 | Y | Y | Y | 通过 |
| 3 | 坐标定位 | `6a61a907bd46…` | 748×452 | 1.7 | - | Y | Y | 通过 |
| 4 | 坐标定位 | `6a61a927bd46…` | 1183×198 | 6.0 | - | Y | Y | 通过 |
| 5 | 坐标定位 | `6a69586fb0ff…` | 341×349 | 1.0 | - | Y | Y | 通过 |
| 6 | 分数公式 | `6a695a01b0ff…` | 423×153 | 2.8 | - | Y | Y | 通过 |
| 7 | 分数公式 | `6a61b319f0e2…` | 718×52 | 13.8 | Y | Y | Y | 通过 |
| 8 | 分数公式 | `6a61b33cf0e2…` | 419×86 | 4.9 | - | Y | Y | 通过 |
| 9 | 分数公式 | `6a61b366bd46…` | 813×192 | 4.2 | - | Y | Y | 通过 |
| 10 | 分数公式 | `6a695a176c23…` | 307×211 | 1.5 | - | Y | Y | 通过 |
| 11 | 应用表格 | `6a62c9a999bf…` | 877×51 | 17.2 | Y | Y | Y | 通过 |
| 12 | 应用表格 | `6a62c9b499bf…` | 473×51 | 9.3 | Y | Y | Y | 通过 |
| 13 | 应用表格 | `6a699cc32ef3…` | 468×146 | 3.2 | - | Y | Y | 通过 |
| 14 | 应用表格 | `6a62ca0099bf…` | 527×163 | 3.2 | - | Y | Y | 通过 |
| 15 | 应用表格 | `6a62ca0999bf…` | 409×50 | 8.2 | Y | Y | Y | 通过 |
| 16 | 圆几何 | `6a62f66a184f…` | 463×28 | 16.5 | Y | Y | Y | 通过 |
| 17 | 圆几何 | `6a62f66f184f…` | 330×28 | 11.8 | Y | Y | Y | 通过 |
| 18 | 圆几何 | `6a62f678184f…` | 缺图 | — | — | — | — | 缺图 |
| 19 | 圆几何 | `6a62f68399bf…` | 859×97 | 8.9 | Y | Y | Y | 通过 |
| 20 | 圆几何 | `6a69e0d72ef3…` | 582×221 | 2.6 | - | Y | Y | 通过 |
| 21 | 百分数 | `6a63152599bf…` | 1101×220 | 5.0 | - | Y | Y | 通过 |
| 22 | 百分数 | `6a63156999bf…` | 645×194 | 3.3 | - | Y | Y | 通过 |
| 23 | 百分数 | `6a69e6862ef3…` | 655×356 | 1.8 | - | Y | Y | 通过 |
| 24 | 百分数 | `6a6955706c23…` | 538×39 | 13.8 | Y | Y | Y | 通过 |
| 25 | 百分数 | `6a6955936c23…` | 393×72 | 5.5 | - | Y | Y | 通过 |
| 26 | 图形统计开放 | `6a69e8892ef3…` | 571×338 | 1.7 | - | Y | Y | 通过 |
| 27 | 图形统计开放 | `6a69e89d2ef3…` | 1187×266 | 4.5 | - | Y | Y | 通过 |
| 28 | 图形统计开放 | `6a631f21184f…` | 922×128 | 7.2 | - | Y | Y | 通过 |
| 29 | 图形统计开放 | `6a631f3d184f…` | 1045×231 | 4.5 | - | Y | Y | 通过 |
| 30 | 图形统计开放 | `6a631f46184f…` | 374×654 | 0.6 | - | Y | Y | 通过 |

## 3. 盲解记录(已完成 → blind-solve.jsonl)

29 条过门候选逐题从图求解,transcription(图是源)+ reference_answer + solution_steps + visual_dependency_prelim + misconception_seed_prelim + difficulty_prelim + note 全写于 `docs/evals/blind-solve.jsonl`。

## 4. 三维预评(⏳ 待步骤 4/5 后定稿)

排序制三维(视觉依赖度权重最高 → 对话承载力 → 答案确定性)。下表为 Dev A 预评(`required`>`helpful`>`none`;对话承载力 `high`>`medium`>`low`;答案确定性 数值型>文本型)。

| idx | bucket | visual_dep | 对话承载力 | 答案确定性 | 难度 |
|---:|---|---|---|---|---:|
| 1 | text_position | none | low | text | easy |
| 2 | text_position | none | low | text | easy |
| 3 | text_position | required | high | text | medium |
| 4 | text_position | required | medium | text | medium |
| 5 | text_position | required | medium | text | medium |
| 6 | fraction_formula | required | low | integer | easy |
| 7 | fraction_formula | none | low | decimal_1 | easy |
| 8 | fraction_formula | none | medium | text | medium |
| 9 | fraction_formula | required | medium | text | medium |
| 10 | fraction_formula | none | low | fraction | easy |
| 11 | application_table | none | medium | fraction | medium |
| 12 | application_table | none | medium | fraction | medium |
| 13 | application_table | none | medium | text | medium |
| 14 | application_table | helpful | medium | text | medium |
| 15 | application_table | none | medium | integer | hard |
| 16 | circle_geometry | none | low | integer | easy |
| 17 | circle_geometry | none | low | integer | easy |
| 19 | circle_geometry | none | medium | text | medium |
| 20 | circle_geometry | required | high | text | hard |
| 21 | percentage_multi_part | helpful | medium | text | medium |
| 22 | percentage_multi_part | none | medium | text | medium |
| 23 | percentage_multi_part | helpful | high | text | hard |
| 24 | percentage_multi_part | none | medium | text | medium |
| 25 | percentage_multi_part | none | low | text | easy |
| 26 | visual_statistics_open | required | high | text | hard |
| 27 | visual_statistics_open | required | high | text | hard |
| 28 | visual_statistics_open | helpful | medium | integer | medium |
| 29 | visual_statistics_open | required | medium | text | medium |
| 30 | visual_statistics_open | required | high | text | hard |

## 5. 选出建议(⏳ 待步骤 4/5 + Dev B 剧本)

- **程序约束**:桶覆盖贪心(空桶第一题 > 已覆盖桶第三题)/ 集级难度目标 2 易·4 中·2 难 / 正向对照 ≥1。
- **元原则**:反循环——不选当前模型会做的题(评测集优化诊断力,不优化通过率)。
- **待定**:转录仲裁(图是源)对出 29 条转录 → 盲测失败模式仲裁(required/helpful/none 定稿) → 据此筛 12-15 题。

## 6. 时序与产物

- `blind-solve.jsonl` 已先于 Dev B deepseek 落盘(防锚定,#130 SOP s2)。
- 无应用码改动;仅 docs/evals 产物。

## 5b. 初选建议(初步,待步骤 4/5 + Dev B 剧本复核)

按 SOP 挑选侧(硬门全过 → 三维排序 → 程序约束 → 反循环元原则)。以下为 Dev A 初步建议的 **13 条候选池**,含 6 桶全覆盖 + 正向对照 ≥1,供 WP4 人审砍 8。

**候选(桶覆盖贪心 + required 优先 + 反循环)**:`#3 #5 #4`(text_position 坐标)、`#9 #6`(fraction_formula 分数)、`#14`(application_table 图形)、`#20`(circle_geometry 读刻度)、`#23`(percentage 百分数相对性,含误区种子)、`#26 #27 #29 #30`(visual_statistics_open,开放/规律/图读)。

**校验指标**:
- 桶覆盖:6 桶全覆盖(text_position ×4 / fraction ×2 / application ×1 / circle ×1 / percentage ×1 / statistics ×4)。
- `visual_dependency=required` 数:10(#3 #4 #5 #6 #9 #20 #26 #27 #29 #30)≥ 6/8。
- 难度分布(候选池):easy 2(#1 #6)/ medium 5(#3 #4 #5 #9 #14 #29)/ hard 5(#20 #23 #26 #27 #30)。
- 正向对照 ≥1:`#1`(纯文字有序数对,当前模型易过)→ 链路 sanity check(反循环:不做主选,只作对照)。
- 反循环:主选 required + 高对话承载力(#23 #26 #27 #30)避开"模型自然会做"的纯文字单答案题。

> ⚠️ 本建议基于 Dev A 盲解预评(`visual_dependency_prelim`/`difficulty_prelim`)。**待步骤 4(转录仲裁,图是源)+ 步骤 5(Dev B 仅凭转录求解的失败模式仲裁 → required/helpful/none 定稿)+ 步骤 7(可应答性复核)后定稿**,届时据此选 8 提交 WP4 人审。


## 7. 全链定稿(步骤 1-7 已完成)

- 步骤1 对账:29/30(缺#18已报) · 步骤2 质量门:0出局 · 步骤3 人盲解:29条。
- 步骤4 转录仲裁:29条全量(18一致/9分歧/2附注),7+1条图读定稿(#3/#4/#5/#9/#20/#24/#27/#29)。
- 步骤5 盲测失败模式仲裁:13候选 final `visual_dependency` = **required 10 / helpful 2 / none 1**(≥6/8)。
- 方法学裁定:`question.text` 逐字化(图注→`figure_note`),`vd=required` 站得住。
- 步骤7 可应答性复核:13/13 可接住,4处修订建议(已贴 Dev B PR #134)。
- 13 条候选池(桶全覆盖)供 WP4 人审砍 8:required ≥6/8、难度 spread、正向对照 #1。
