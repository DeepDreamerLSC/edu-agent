# 步骤 7 可应答性复核(Dev A / D2)——Dev B WP3 剧本(13 条)

**依据**:#130 SOP「可应答性检查:执行者扮演 tutor 逐轮接话,每轮能被通用 scaffold 接住(剧本不依赖特定导师措辞)」。
**被审**:`edu_agent/evals/datasets/small_lecturer_image_teaching_v1.json`(w8 tip `8a7499e`,13 candidate)。
**前提**:WP2 透传 `question["image"]`,即 tutor 在评测中**有图**;故"需回图"类发言可被接住,判据是**不依赖特定导师措辞**。

## 结论:13/13 条每轮均可被通用 scaffold 接住,但有 4 处需 Dev B 修订

| 场景 | turns | 每轮可接住? | 复核意见 |
|---|---|---|---|
| 01 text_position | 3 | ✅ | 错答→自纠→正解,通用 Socratic 可接。 |
| 03 text_position | 4 | ✅(有瑕疵) | **数字不一致**:turn2「往北800米」取自题(5)「向东600米再向北800米」,但 turn2 上下文是(3)「以东1400米再往北600米」。请改 turn2 为「600米」或明确指(5)。 |
| 04 text_position | 3 | ✅(有争议) | **图读争议**:turn1 用 A(1,5)B(1,2)C(5,2)D(3,5)(B 的读法),我仲裁为 A(1,5)D(4,5)B(1,3)C(4,3)。剧本 premise 用了未定稿坐标→待图读定稿后同步。 |
| 05 text_position | 3 | ✅ | 用了 75°(与图一致);但 **B 转录漏了 75°/40°**(见仲裁 idx5),剧本是对的、转录待补。 |
| 06 fraction_formula | 3 | ✅ | 「涂3个」→「12÷4×3=9」自纠,可接。 |
| 09 fraction_formula | 3 | ✅(有争议) | 用了「剩下3/8→倒出5/8→C」;量杯刻度读法**未定稿**(仲裁 idx9:我 3/8 vs B 本次 3/5),premise 待定。 |
| 14 application_table | 3 | ✅ | 逐图验 a×b=1,可接。 |
| 20 circle_geometry | 3 | ✅(有争议) | turn1 用「4cm」、turn2「那条线是半径还是直径」需 tutor 描述图;图尺寸**未定稿**(仲裁 idx20),premise 待定。 |
| 23 percentage_multi_part | 3 | ✅ | 49% 相对性→自纠,可接。 |
| 26 visual_statistics_open | 3 | ✅ | turn3 卡住→reveal 可接。 |
| 27 visual_statistics_open | 3 | ✅(有争议) | turn3「哪条先陡后平」需 tutor 指图;**B 转录把 A/C/D 描述成一样**(仲裁 idx27),选项不可区分→premise 待定。 |
| 29 visual_statistics_open | 3 | ✅(有争议) | turn1「行驶了20分钟」= **我的旧答案**;仲裁 idx29 判 B 图读更准(止约18分)。剧本 premise 待定。 |
| 30 visual_statistics_open | 3 | ✅ | turn3「点阵看不清」→reveal 可接。 |

## 三弧分布(与 B 自检一致)
`ready_to_record` 6(01/06/09/14/23/29)、`needed_reveal` 3(04/20/27)、`not_ready` 4(03/05/26/30)。符合 s9「三弧都用上,比例 WP3 设计自由」。

## 需 Dev B 修订的 4 处(按优先级)
1. **#03 turn2 数字**(600 vs 800)——硬瑕疵,直接改。
2. **#04 turn1 坐标 / #29 turn1 分钟数 / #09 量杯 / #20 尺寸 / #27 选项**——均**依赖未定稿的图读**。这些是 required 视觉题,premise 必须用**图是源的终版图读**;待视觉通道恢复后我出终版,Dev B 同步剧本。

## 给 Dev B 的答复(它点名要的 3 条精确答案)
`#3`(坐标网格读格)、`#20`(看圆读刻度)、`#27`(注水折线)的精确图读**当前被阻塞**:`read_image` 报 `model deepseek-v4.1-flash-expires does not declare image input`(视觉模型被切回文本模型)。需切回多模态模型后我出终版;在此之前这 3 条 `reference_answer` 仍是「需读格/待图读/需读折线」,不满足硬规范 3。
