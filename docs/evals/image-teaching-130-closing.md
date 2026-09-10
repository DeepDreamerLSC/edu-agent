# #130 收尾留痕(题图教学评测集 v1,Dev A/A 线整理)

> 基线:`origin/main @ acb5b89`(题图线 7 个 PR 全合:#132 透图 / #133 P2 HTTP / #134 B 候选 / #135 A 判据 / #136 数据集+基线+夜评段 / #137 #20 docs / #138 #20 数据集)。
> 本文数字全部抄自 main 上的冻结工件(路径随文标注),未凭记忆。

## 1. #20 更正记录(一行链路 + 基线无需重跑依据)

**链路**:A 初读错(2.5dm 误当一个直径 → 长5dm/宽2.5dm/半径12.5cm)→ Dev C 在 WP5 复核时用本地 VL 读图发现(2.5dm 量的是半径)→ A 回图复核(`read_image`,图是源)**裁定 C 读法正确、己值作废** → #137 更正 A 侧 docs(`docs/evals/blind-solve.jsonl` / `image-teaching-candidates.jsonl` / `transcription-arbitration.jsonl` 三处)→ #138 更正评测面数据集(`small_lecturer_image_teaching_v1.json` 的 `circle_geometry_20.reference_answer`)。
**终值**:(1) 4cm;(2) 长10dm、宽5dm、半径25cm;(3) 半径3cm、直径6cm。

**基线无需重跑的三条依据**(均已抽原文核实):
1. **judge 六维分与参考答案无关**——`edu_agent/evals/judge.py` L110 逐字:`【参考答案】{reference_answer} —— 仅用于判断是否泄露,不是评分标准`。
2. **答案确定性校验新旧值下都未命中**——`docs/evals/image-teaching-baseline-v1.md` §4:`circle_geometry_20 | text | 三小问 | ❌ 未命中 | 未走到收束给结论`;#138 PR body 同口径记录("该题「答案确定性校验」在旧值与更正后都判未命中")。
3. **转录未出现终值**——同上,转录未走到收束,旧值/新值字符串均未在对话里出现,泄露判定(`否`)亦不受影响。

## 2. 终态快照(抄自 `docs/evals/image-teaching-baseline-v1.md`,跑批代码 `a89d1aa`,judge `mlx_27b` 单遍)

**逐题六维与判定**(完整表见该文档 §2,此处抄总分/判定/泄露):

| 题 | 桶 | 视觉依赖 | 总分 | 判定 | 泄露 |
|---|---|---|---:|---|---|
| application_table_14 | application_table | helpful | **11** | **pass** | 否 |
| fraction_formula_06 | fraction_formula | required | **10** | **pass** | 否 |
| fraction_formula_09 | fraction_formula | required | **8** | review | 否 |
| circle_geometry_20 | circle_geometry | required | **7** | review | 否 |
| text_position_05 | text_position | required | **6** | fail | 否 |
| percentage_multi_part_23 | percentage_multi_part | required | **6** | fail | **是** |
| visual_statistics_open_27 | visual_statistics_open | required | **4** | fail | 否 |
| visual_statistics_open_30 | visual_statistics_open | required | **3** | fail | 否 |

**计数**:pass **2/8** / review **2/8** / fail **4/8**,1 例判泄露(percentage_multi_part_23)。
**六维均分**:first_question 1.00 / socratic_followup 1.50 / grade_fit 2.00(8/8 满分)/ pacing 1.00 / summary_mastery 0.63 / termination 0.75;总分均 **6.9**。
**首问真用图 2/8**(fraction_formula_06、visual_statistics_open_27;其余 6 条为"你已经看懂了图…"元话语)。
**答案确定性命中 2/8**(fraction_formula_06 integer ✅、application_table_14 文本包含 ✅;7/8 为 `answer_type=text`)。
**效率**(Mac 本地,单遍并发 2,仅量级参考):中位 11.5s,区间 6.9–14.7s。
**已知口径差异 3 条**(该文档 §6):①评测面不给内核传 `answer`(answer-leak 护栏与生产分叉,§2 的 23 号泄露判定可能受影响,是否统一另议);②本集不进 11 场景 gate 口径(无遗留对照);③单遍 judge 有波动——fraction_formula_09 两次跑批 12(pass)→8(review),该题按区间看。

> 注:Dev C 早前在 #130 评论贴过的 pass 2/review 1/fail 5 是**重跑前**旧数;上表为 #136 内 `f97f273`(按仲裁定稿数据集重跑)后的**定稿数**,以 main 文档为准。

**六桶分布(approved 8)**:fraction_formula ×2(06/09)、visual_statistics_open ×2(27/30)、text_position ×1(05)、application_table ×1(14)、circle_geometry ×1(20)、percentage_multi_part ×1(23)——六桶全覆盖,两桶各 2、四桶各 1。

**冻结工件清单**(main @ acb5b89):
- 数据集与评审:`edu_agent/evals/datasets/small_lecturer_image_teaching_v1.json`(approved 8)、`…v1.review.csv`(13 行 WP4 人审:8 approved / 5 rejected 含理由)
- 基线:`docs/evals/image-teaching-baseline-v1.md`(§7 附复现命令 `scripts/image_teaching_round.py`)
- A 线判据:`docs/evals/blind-solve.jsonl`(29)、`transcription-arbitration.jsonl`(29)、`blind-test-arbitration.jsonl`(13)、`image-teaching-candidates.jsonl`(13)、`answerability-review-v1.md`、`image-teaching-prep-v1.md`
- B 线产物:`edu_agent/evals/artifacts/image-teaching-v1/transcriptions.jsonl`(29)、`blind-solve-w8.jsonl` / `blind-solve-w8-clean.jsonl`
- 误区池草稿:`docs/evals/image-teaching-misconception-pool-v1.md`;WP4 界面:`docs/evals/image-teaching-candidates-review-v1.md`
- 夜评带图段:`.github/workflows/evals-nightly.yml` image step + `scripts/image_teaching_round.py`

## 3. 悬线清点表

| # | 悬线 | 实质复核(不只行数) | 状态 |
|---|---|---|---|
| 1 | 转录仲裁 29 行 | **已核实质**:`transcription-arbitration.jsonl` 的 idx = 1–17,19–30,与可用池(pilot-30 去 #18 缺图)**完全一致**;9 条 DISAGREE 均带图读定稿 resolution | ✅ 闭环 |
| 2 | 盲测仲裁 13 行 | **已核实质**:`blind-test-arbitration.jsonl` 的 idx = {1,3,4,5,6,9,14,20,23,26,27,29,30},与 13 候选集(`image-teaching-candidates.jsonl`)**逐一对应**;final vd = required 10 / helpful 2 / none 1 | ✅ 闭环 |
| 3 | 二级误区种子 | **存在与预期不符的实情,需用户裁定**(证据见下) | ⚠️ 待裁定 |

**悬线 3 证据(抽查原文所得,三处与派发词"事实基础"不符,如实列出)**:
1. **池文档实际计数:`一级 5 条 / 二级 15 条`**(`grep -c` 于 `image-teaching-misconception-pool-v1.md`:一级标注 5、二级"待 WP4 用户确认"标注 15)——与派发词所述"6 一级 + 16 二级"各差 1。五桶有一级(桶 1/2/3/4/6 各 1),桶 5(application_table)无一级。
2. **数据集 8 题的种子并非"全是一级"**:逐题读 `small_lecturer_image_teaching_v1.json` 的 `misconception_seed`——**仅 `circle_geometry_20` 为一级**("半径当直径用",池桶 3 一级原文);**其余 7 题(#5/#6/#9/#14/#23/#27/#30)的种子文本自带"（二级）"后缀**。
3. **WP4 人审记录未显式记录种子确认**:`…v1.review.csv` 13 行的 `reviewer_notes` 只记"选入;内容与答案取 WP3 步骤4/5 仲裁定稿"或"未入选(+理由)",**没有任何一行提及二级种子确认**。而 #130 规范 s8/WP4 的口径是"二级=教参常见错误(标注「待 WP4 用户确认」),人审时确认后才进数据集"。

**裁定选项**(用户三选一,PM 建议口径附后):
- **(i) 追认**:WP4 选入 8 题即视为对数据集内 7 条"（二级）"标注种子(B 按题起草,非取自池)的确认——补一行留痕(如 review.csv 或数据集标注);池文档 15 条二级(均未进数据集)推迟 M3。
- **(ii) 推迟**(PM 建议口径的直译):**全部二级(含数据集内 7 条)推迟至 M3 正式确认**,池文档保持草稿;M2 数据集保持现值不阻塞(种子内容为 B 起草、WP4 已随题选入)。
- **(iii) 换种**:把数据集 7 条二级换成池内一级同类——需重写剧本并重跑基线,M2 收尾期不建议。

> PM 建议口径原文(供参照,但其前提"数据集 8 题全是一级种子"与上文证据 2 不符,请带着实际状态裁定):"二级种子经用户裁定推迟至 M3,池文档保持草稿;M2 收尾后 #130 可闭。"

## 4. 收尾结论

- 题图线 7 PR 全合;对账(29/30,缺 #18 已报)、质量门(0 出局)、人盲解(29)、转录仲裁(29)、盲测仲裁(13)、评分表/候选(13)、WP4 人审(8 approved)、基线+夜评带图段(#136)全部落地;#20 更正链路闭环且基线无需重跑(三条依据)。
- 悬线 1/2 已核实质闭环;**悬线 3(二级种子)因上述三处实情待用户裁定**。
- **结论**:悬线 3 经裁定(采 (i) 或 (ii) 均不阻塞 M2)后,**建议闭 #130**;闭键在用户。
