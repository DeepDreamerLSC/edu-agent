# 题图教学评测集 v1 · 候选评审(WP4 唯一界面)

> **怎么用**:在浏览器里对下面候选做两件事——**选出 8 条**、**确认二级误区种子**。
> 每条含:题图链接 / 转录(图是源)/ 参考答案(终审)/ 误区种子(出处分级)/ 剧本摘要 / 三维分。
> 状态:`question.text`/`reference_answer` 取自 Dev A 逐字核对+争议终审(图是源);
> `student_turns`/`expected.outcome`/`misconception_seed` 为 Dev B(WP3)起草,已经 A 可应答性复核(13/13 每轮可被通用 scaffold 接住)。

## 0. 总览

| # | id | 桶 | 视觉依赖 | 对话承载力 | 答案确定性 | 难度 | 弧线 | 预期结果 |
|---|---|---|---|---|---|---|---|---|
| 1 | `image_v1_text_position_01` | text_position | none | low | text | easy | 恢复(犯错→引导→自纠) | ready_to_record |
| 3 | `image_v1_text_position_03` | text_position | required | high | text | medium | 未就绪 | not_ready |
| 4 | `image_v1_text_position_04` | text_position | required | medium | text | medium | 需揭示(犯错→需 reveal) | needed_reveal |
| 5 | `image_v1_text_position_05` | text_position | required | medium | text | medium | 未就绪 | not_ready |
| 6 | `image_v1_fraction_formula_06` | fraction_formula | required | low | integer | easy | 恢复(犯错→引导→自纠) | ready_to_record |
| 9 | `image_v1_fraction_formula_09` | fraction_formula | required | medium | text | medium | 恢复(犯错→引导→自纠) | ready_to_record |
| 14 | `image_v1_application_table_14` | application_table | helpful | medium | text | medium | 恢复(犯错→引导→自纠) | ready_to_record |
| 20 | `image_v1_circle_geometry_20` | circle_geometry | required | high | text | hard | 需揭示(犯错→需 reveal) | needed_reveal |
| 23 | `image_v1_percentage_multi_part_23` | percentage_multi_part | helpful | high | text | hard | 恢复(犯错→引导→自纠) | ready_to_record |
| 26 | `image_v1_visual_statistics_open_26` | visual_statistics_open | required | high | text | hard | 未就绪 | not_ready |
| 27 | `image_v1_visual_statistics_open_27` | visual_statistics_open | required | high | text | hard | 需揭示(犯错→需 reveal) | needed_reveal |
| 29 | `image_v1_visual_statistics_open_29` | visual_statistics_open | required | medium | text | medium | 恢复(犯错→引导→自纠) | ready_to_record |
| 30 | `image_v1_visual_statistics_open_30` | visual_statistics_open | required | high | text | hard | 未就绪 | not_ready |

**程序约束自检**:六桶全覆盖(text_position 4 / visual_statistics_open 4 / fraction_formula 2 / application_table 1 / circle_geometry 1 / percentage_multi_part 1);`visual_dependency=required` **10/13** ≥ 6/8;三弧齐全(恢复 6 / 需揭示 3 / 未就绪 4);溯源(question_id/sha256)齐备;全部 `reference_answer` 已终审可独立验证(硬规范 3)。

---

## #1 · 有序数对·电影票座位(misconception_recovery)

- **题图**:[pqfile_71fcf0b8e6eebb07898b870c.jpg](https://raw.githubusercontent.com/DeepDreamerLSC/edu-agent/main/edu_agent/api/static/bank/pqfile_71fcf0b8e6eebb07898b870c.jpg)  
  `sha256: 0cc92d5cdc052e02e03b7020e79a146c6e00c5ad166d1801e681f280d08d759d`
- **桶**:`text_position` · **视觉依赖**:`none` · **难度**:`easy` · **对话承载力**:`low` · **答案确定性**:`text`
- **溯源**:`question_id=6a61a8dabd464753061efdff` · `pujia_school_question_bank` · `1-1用有序数对确定位置`

**转录(图是源 · Dev A 逐字核对)**:

```text
如果电影票上的"8排6号"记作(6,8),那么"12排5号"记作( );(3,10)表示的位置是( )排( )号。
```

**参考答案**:`(5,12);(10)排(3)号` (answer_type=`text`, unit=`—`)

**误区种子**(单题单误区):把数对顺序写成“排在前、号在后”，即排号颠倒（一级：small_lecturer_target_mode_v3_question_bank.json 的 coordinate_notation 系列同型设计）

**剧本摘要**(弧线:恢复(犯错→引导→自纠) → `ready_to_record`,3 轮):

1. 学生:8排6号记作(6，8)，那12排5号就记作(12，5)吧？排写在前面、号写在后面。
2. 学生:等一下……8排6号里，8(排)写在后面、6(号)写在前面，我好像弄反了。
3. 学生:我明白了：第一个数表示号、第二个数表示排。所以12排5号是(5，12)；(3，10)就是10排3号。

---

## #3 · 坐标网格·读格与方位距离(misconception_not_ready)

- **题图**:[pqfile_d46906df654a97da043b6d7e.jpg](https://raw.githubusercontent.com/DeepDreamerLSC/edu-agent/main/edu_agent/api/static/bank/pqfile_d46906df654a97da043b6d7e.jpg)  
  `sha256: ad743dc44ffd43a51ec2443630a67cb8b630c1e2286421cf69ed99a58c783860`
- **桶**:`text_position` · **视觉依赖**:`required` · **难度**:`medium` · **对话承载力**:`high` · **答案确定性**:`text`
- **溯源**:`question_id=6a61a907bd464753061efe11` · `pujia_school_question_bank` · `1-1用有序数对确定位置`

**转录(图是源 · Dev A 逐字核对)**:

```text
200m 北↑ 网格0-10×0-9,点A,B,C,D,E,F,G。仔细观察,填一填。(1)B位置(2,4),位于A以东( )米再往北( )米。(2)C位置( , ),位于A以东( )米再往北( )米。(3)位于A以东1400米再往北600米的是( ),位置( , )。(4)(4,2)→(5,8)→(7,3)→(8,5)先后去了哪些地方?( )→( )→( )→( )。(5)小慧从D出发向东600米再向北800米,标o,位置( , )
```

**参考答案**:`(1)200米/600米；(2)C=(5,8)：800米/1400米；(3)坐标(8,4)（注:A=(1,1)下；(4)D(4,2)→C(5,8)→F(7,3)→G(8,5)；(5)(7,6)` (answer_type=`text`, unit=`米`)

**误区种子**(单题单误区):把数对里的行、列读反（先列后行），导致网格点整体错位（二级）

**剧本摘要**(弧线:未就绪 → `not_ready`,4 轮):

1. 学生:B在(2,4)，那我先横着数2格、再竖着数4格，就找到B了。
2. 学生:可是第(3)题要“A以东1400米、再往北600米”，1400和600各是几个格？我算得有点乱，和B的(2,4)对不上。
3. 学生:C的位置我读成(7,4)了，和B(2,4)横坐标差这么多，是不是我把行和列换了？
4. 学生:算了，网格点到底怎么数我还是不确定。

---

## #4 · 数对与平移·顶点坐标(misconception_needs_reveal)

- **题图**:[pqfile_89eb7cc428f91de39f2254e8.jpg](https://raw.githubusercontent.com/DeepDreamerLSC/edu-agent/main/edu_agent/api/static/bank/pqfile_89eb7cc428f91de39f2254e8.jpg)  
  `sha256: 31f0b683215098c2f230c64f3d117ed19686007e1e2071fcdbeb08f3084ace7e`
- **桶**:`text_position` · **视觉依赖**:`required` · **难度**:`medium` · **对话承载力**:`medium` · **答案确定性**:`text`
- **溯源**:`question_id=6a61a927bd464753061efe1e` · `pujia_school_question_bank` · `1-1用有序数对确定位置`

**转录(图是源 · Dev A 逐字核对)**:

```text
先用数对表示图形四个顶点的位置,再将图形先向右平移4格,再向下平移2格,画出平移后的图形,再用数对表示出平移后四个顶点A₁、B₁、C₁、D₁的位置,再想一想,这些顶点与ABCD的位置有什么关系?(网格0-10×0-6)
```

**参考答案**:`A₁(5,3) B₁(5,1) C₁(8,1) D₁(8,3)` (answer_type=`text`, unit=`—`)

**误区种子**(单题单误区):平移后只改一个坐标或方向算反（向右平移却把第一个数减4，或向下平移当成纵坐标加2）（二级）

**剧本摘要**(弧线:需揭示(犯错→需 reveal) → `needed_reveal`,3 轮):

1. 学生:先把四个顶点写成数对：A(1,5)、D(4,5)、B(1,3)、C(4,3)。
2. 学生:向右平移4格，第一个数加4；向下平移2格，第二个数减2。所以A₁是(5,3)。
3. 学生:可B₁我一开始算成(5,5)，把“向下”当成加2了。方向弄反坐标就全错——我得看看图上平移后顶点到底落在哪。

---

## #5 · 方位描述·两种说法互推(misconception_not_ready)

- **题图**:[pqfile_ee3a956c1d912c6a70fd014b.jpg](https://raw.githubusercontent.com/DeepDreamerLSC/edu-agent/main/edu_agent/api/static/bank/pqfile_ee3a956c1d912c6a70fd014b.jpg)  
  `sha256: 55853c6518b85c5689074e6a8998d9cc5454f740a69ee357bb448958d411832f`
- **桶**:`text_position` · **视觉依赖**:`required` · **难度**:`medium` · **对话承载力**:`medium` · **答案确定性**:`text`
- **溯源**:`question_id=6a69586fb0ffee286ba75532` · `pujia_school_question_bank` · `1-2描述物体的位置`

**转录(图是源 · Dev A 逐字核对)**:

```text
北↑ C岛 75° 灯塔 西 东 40° D岛 南。以灯塔为观测点,C岛和D岛分别在什么方位上?(1)C岛在灯塔的北偏( )( )°的方向上。(2)D岛在灯塔的南偏( )( )°的方向上。还可以这样描述:(3)C岛在灯塔的东偏( )( )°的方向上。(4)D岛在灯塔的( )偏( )( )°的方向上
```

**参考答案**:`(1)北偏东75°；(2)南偏西40°；(3)东偏北15°；(4)西偏南50°` (answer_type=`text`, unit=`—`)

**误区种子**(单题单误区):方位角只照抄图上标的那个角，不会用“90°−已知角”换另一种描述（北偏东75° ⇄ 东偏北15°）（二级）

**剧本摘要**(弧线:未就绪 → `not_ready`,3 轮):

1. 学生:C岛在灯塔的北偏东75°，这个我看到了。
2. 学生:但第(3)问要写“东偏北多少度”，北偏东75°和东偏北15°是一回事吗？我不确定。
3. 学生:90减75等于15……是这样算的吗？我怕把方向弄反。

---

## #6 · 分数乘整数·涂色个数(misconception_recovery)

- **题图**:[pqfile_4ac444b1134e8b753583308b.jpg](https://raw.githubusercontent.com/DeepDreamerLSC/edu-agent/main/edu_agent/api/static/bank/pqfile_4ac444b1134e8b753583308b.jpg)  
  `sha256: c97aa892fc2abc5eb330ef0949d367d0379b982e88ebd493d0b52c26e6d69baf`
- **桶**:`fraction_formula` · **视觉依赖**:`required` · **难度**:`easy` · **对话承载力**:`low` · **答案确定性**:`integer`
- **溯源**:`question_id=6a695a01b0ffee286ba75680` · `pujia_school_question_bank` · `2-1分数乘整数`

**转录(图是源 · Dev A 逐字核对)**:

```text
如右图,将这些圆片的 3/4 涂上蓝色,那么需要涂( )个圆片。(图:3×4=12个圆)
```

**参考答案**:`9` (answer_type=`integer`, unit=`个`)

**误区种子**(单题单误区):把“3/4涂蓝”理解成“涂3个（或4个）圆片”，而不是求这堆圆片的3/4是多少（二级）

**剧本摘要**(弧线:恢复(犯错→引导→自纠) → `ready_to_record`,3 轮):

1. 学生:3/4涂蓝，是不是就涂3个圆片？图上看着有十几个圆。
2. 学生:哦不对，3/4是把这堆圆片平均分成4份、涂其中3份。一共12个，12÷4=3，每份3个。
3. 学生:那3份就是3×3=9个。所以需要涂9个圆片。

---

## #9 · 分数乘整数·倒出量列式(misconception_recovery)

- **题图**:[pqfile_1767115b0e65e8727d903f95.jpg](https://raw.githubusercontent.com/DeepDreamerLSC/edu-agent/main/edu_agent/api/static/bank/pqfile_1767115b0e65e8727d903f95.jpg)  
  `sha256: 77c9e35e06095b3310e76ee75b828724b9f675625ecf8d759b4e8f30c30a2979`
- **桶**:`fraction_formula` · **视觉依赖**:`required` · **难度**:`medium` · **对话承载力**:`medium` · **答案确定性**:`text`
- **溯源**:`question_id=6a61b366bd464753061f0475` · `pujia_school_question_bank` · `2-1分数乘整数`

**转录(图是源 · Dev A 逐字核对)**:

```text
杯子中原来盛有800 mL水,小华将杯中的水倒出一些,如下图。求从杯子中倒出了多少毫升水,正确的列式是( )。A.800×3/5 B.800×3/8 C.800×5/8 D.800×5/9(图:两量杯水平对比)
```

**参考答案**:`C(800×5/8)` (answer_type=`text`, unit=`—`)

**误区种子**(单题单误区):把“倒出多少”当成“剩下多少”，用剩余的分率去乘总量（单位“1”找错）（二级）

**剧本摘要**(弧线:恢复(犯错→引导→自纠) → `ready_to_record`,3 轮):

1. 学生:杯子原来800 mL，倒出一些。图上看剩下的大概是3/8，所以倒出了800×3/8，选B。
2. 学生:等等，题目问的是“倒出”多少，不是“剩下”多少。剩下3/8，那倒出的就是1−3/8=5/8。
3. 学生:所以是800×5/8，选C。我刚才把倒出和剩下弄反了。

---

## #14 · 倒数·四幅图中找乘积为1(misconception_recovery)

- **题图**:[pqfile_8272d0b01d968c374d62c804.jpg](https://raw.githubusercontent.com/DeepDreamerLSC/edu-agent/main/edu_agent/api/static/bank/pqfile_8272d0b01d968c374d62c804.jpg)  
  `sha256: 6285f205dd2cd9ad5a8daa48e34469241e0d59d5aa1270aa08498762468b37d3`
- **桶**:`application_table` · **视觉依赖**:`helpful` · **难度**:`medium` · **对话承载力**:`medium` · **答案确定性**:`text`
- **溯源**:`question_id=6a62ca0099bf346827f052e4` · `pujia_school_question_bank` · `3-1倒数的认识`

**转录(图是源 · Dev A 逐字核对)**:

```text
下面四幅图中,若a和b表示不同的数,则( )中a与b互为倒数。A.三角形(高b m 底a m,面积1 m²) B.线段(a m,b m,总长1 m) C.长方形(长a m 宽b m,面积1 m²) D.长方体(长a m 宽b m 高c m,体积1 m³)
```

**参考答案**:`C` (answer_type=`text`, unit=`—`)

**误区种子**(单题单误区):看到图里出现“1”就选，不去验证两个量的乘积是否等于1（把面积1/总长1都当成互为倒数）（二级）

**剧本摘要**(弧线:恢复(犯错→引导→自纠) → `ready_to_record`,3 轮):

1. 学生:a和b互为倒数，那a×b=1。A图是三角形，面积1 m²，底a、高b——面积是a×b÷2，所以a×b=2，不是1。
2. 学生:B图线段a米、b米，总长1米，那是a+b=1，不是乘积。
3. 学生:C图长方形长a、宽b，面积1 m²，a×b=1，这才互为倒数。所以选C。

---

## #20 · 圆·半径与直径(misconception_needs_reveal)

- **题图**:[pqfile_d5c2943fff4f637a04a85dad.jpg](https://raw.githubusercontent.com/DeepDreamerLSC/edu-agent/main/edu_agent/api/static/bank/pqfile_d5c2943fff4f637a04a85dad.jpg)  
  `sha256: be22a630f78a463232cb3209ed65a5eee2aab521fd97a6209552c09be254170d`
- **桶**:`circle_geometry` · **视觉依赖**:`required` · **难度**:`hard` · **对话承载力**:`high` · **答案确定性**:`text`
- **溯源**:`question_id=6a69e0d72ef3251197be2556` · `pujia_school_question_bank` · `4-1圆的认识`

**转录(图是源 · Dev A 逐字核对)**:

```text
看图填空。(1)半圆的直径是( )cm。(2)长方形的长是( )dm,宽( )dm,圆的半径( )cm。(3)圆的直径是( )cm。(图:半圆/两圆并排/两圆重叠)
```

**参考答案**:`(1)4cm；(2)长5dm、宽2.5dm、半径12.5cm；(3)半径3cm、直径6cm` (answer_type=`text`, unit=`—`)

**误区种子**(单题单误区):半径当直径用（或直径当半径用）（一级）

**剧本摘要**(弧线:需揭示(犯错→需 reveal) → `needed_reveal`,3 轮):

1. 学生:半圆的直径是4 cm吧？我照着刻度数了数……
2. 学生:圆的半径和直径我老是搞混。图上标的那条线到底是从圆心到边，还是穿过圆心两头？我得看清它画到哪。
3. 学生:长方形里并排两个圆，长到底是两个直径还是两个半径？我不敢确定。

---

## #23 · 百分数·相对量与整体(misconception_recovery)

- **题图**:[pqfile_04ebc0048b42c1a5fe6e118b.jpg](https://raw.githubusercontent.com/DeepDreamerLSC/edu-agent/main/edu_agent/api/static/bank/pqfile_04ebc0048b42c1a5fe6e118b.jpg)  
  `sha256: 630e69be2d49107aae1d38f3654c859bd7c80d874542569ee76889a774ebc276`
- **桶**:`percentage_multi_part` · **视觉依赖**:`helpful` · **难度**:`hard` · **对话承载力**:`high` · **答案确定性**:`text`
- **溯源**:`question_id=6a69e6862ef3251197be2a0c` · `pujia_school_question_bank` · `5-1百分数的意义(1)`

**转录(图是源 · Dev A 逐字核对)**:

```text
我们学校的女生人数占全校学生人数的49%。(两校各49%)这两个学校的女生人数一定相同吗?为什么?反思:用彩色笔分别涂出下面各图面积的25%,涂色的小方块一样多吗?想一想这是为什么?(图1:10×10格 图2:5×10格)
```

**参考答案**:`不一定相同(总人数不同);格子数不同(整体不同)` (answer_type=`text`, unit=`—`)

**误区种子**(单题单误区):把百分比误当绝对数，认为相同百分比就是相同数量（把49%当成49人）（二级）

**剧本摘要**(弧线:恢复(犯错→引导→自纠) → `ready_to_record`,3 轮):

1. 学生:两个学校女生都占49%，那女生人数肯定一样多吧？都是49%嘛。
2. 学生:可是……如果两个学校总人数不一样，49%算出来的女生人数就不一样。百分数比的是“占谁的”。
3. 学生:涂25%也一样：整体格子数不一样大，涂出来的小方块数就不一样。

---

## #26 · 数与形·正方形数与三角形数(misconception_not_ready)

- **题图**:[pqfile_c3e4dd3fa4f2ddb3170ce228.jpg](https://raw.githubusercontent.com/DeepDreamerLSC/edu-agent/main/edu_agent/api/static/bank/pqfile_c3e4dd3fa4f2ddb3170ce228.jpg)  
  `sha256: 26f1ca46555a05900da574cd192f184a4e36a8ffef3b8f5559cbe8f6fe09dd6c`
- **桶**:`visual_statistics_open` · **视觉依赖**:`required` · **难度**:`hard` · **对话承载力**:`high` · **答案确定性**:`text`
- **溯源**:`question_id=6a69e8892ef3251197be2bec` · `pujia_school_question_bank` · `6-1数与形(1)`

**转录(图是源 · Dev A 逐字核对)**:

```text
探索规律。图1(正方形数点阵):4=1+3,9=1+3+5,16=1+3+5+7。图2(三角形数点阵):4=1+3,9=3+6,16=6+10。(1)按图1规律,将36写成几个数的和:36=___。(2)毕达哥拉斯学派:把1,4,9,16…称正方形数;把1,3,6,10…称三角形数。按图2规律,将36写成两个数的和:36=___。
```

**参考答案**:`1+3+5+7+9+11;15+21` (answer_type=`text`, unit=`—`)

**误区种子**(单题单误区):把点阵的“数”和“和式”当成同一种表示，忽略累加项数（只看首尾不数项数）（二级）

**剧本摘要**(弧线:未就绪 → `not_ready`,3 轮):

1. 学生:36是6的平方，按图1就是1+3+5+7+9+11，一共6个奇数，加起来是36。这个我会。
2. 学生:图2三角形数……4=1+3，9=3+6，16=6+10。为什么是这两个数相加？我没看懂点阵是怎么摆的。
3. 学生:36要写成哪两个数的和？我只知道它是三角形数，但不知道是第几个。

---

## #27 · 折线图·注水高度与时间(misconception_needs_reveal)

- **题图**:[pqfile_94305361eb60b442ae5a5725.jpg](https://raw.githubusercontent.com/DeepDreamerLSC/edu-agent/main/edu_agent/api/static/bank/pqfile_94305361eb60b442ae5a5725.jpg)  
  `sha256: be50fbd1a739519aae7d688804393fe2f470852791113b35dacbced856d90bd9`
- **桶**:`visual_statistics_open` · **视觉依赖**:`required` · **难度**:`hard` · **对话承载力**:`high` · **答案确定性**:`text`
- **溯源**:`question_id=6a69e89d2ef3251197be2c02` · `pujia_school_question_bank` · `6-1数与形(1)`

**转录(图是源 · Dev A 逐字核对)**:

```text
一个长方体水箱里有一个上部开口的圆柱形容器,底部与长方体容器连接,打开水管往水箱里注水。下面几幅图中,( )能准确描述水的高度与时间的变化关系。A/B/C/D 四幅height-time折线图。
```

**参考答案**:`A` (answer_type=`text`, unit=`—`)

**误区种子**(单题单误区):只看折线陡/平的外形判断，忽略“水先注圆柱、注满后再溢到长方体”造成的两段不同上升速率（二级）

**剧本摘要**(弧线:需揭示(犯错→需 reveal) → `needed_reveal`,3 轮):

1. 学生:水箱里有个圆柱容器，水先注入圆柱，注满后再往外溢到长方体里。
2. 学生:所以水的高度应该是先快后慢吧？圆柱细，水面升得快；注满后水面在长方体里升得慢。
3. 学生:到底是哪条折线？我得看清楚哪条是先陡后平。

---

## #29 · 折线图·速度与时间(misconception_recovery)

- **题图**:[pqfile_ce99ed9f9b97253cd5eb6c25.jpg](https://raw.githubusercontent.com/DeepDreamerLSC/edu-agent/main/edu_agent/api/static/bank/pqfile_ce99ed9f9b97253cd5eb6c25.jpg)  
  `sha256: 281c73713f3ae8912507fc068a89949c3d593d3e575ff2c192e5bc80384f1c6c`
- **桶**:`visual_statistics_open` · **视觉依赖**:`required` · **难度**:`medium` · **对话承载力**:`medium` · **答案确定性**:`text`
- **溯源**:`question_id=6a631f3d184f723b3592d084` · `pujia_school_question_bank` · `6-2数与形(2)`

**转录(图是源 · Dev A 逐字核对)**:

```text
明明和爸爸开车去动物园,画了汽车速度随时间变化情况(曲线:0-2升30,2-8保持30,8-10降0,10-12升30,12-16保持30,16-20降0)。(1)汽车行驶了多长时间?最大速度是多少?(2)出发后8分钟到10分钟可能出现什么情况?【小试牛刀】
```

**参考答案**:`18分钟;30千米/时;8=10分钟停车后起步` (answer_type=`text`, unit=`—`)

**误区种子**(单题单误区):把“速度保持30”当成还在加速，或把图上最后时刻直接当成实际行驶时间（忽略速度降到0的停车段）（二级）

**剧本摘要**(弧线:恢复(犯错→引导→自纠) → `ready_to_record`,3 轮):

1. 学生:汽车行驶了18分钟吧？图上的折线到18分钟就到底了。最大速度是30千米/时。
2. 学生:出发后8分钟到10分钟，速度是30，那是在匀速行驶吧？
3. 学生:不对，8到10分钟速度是从0升到30的，说明之前停了、这会儿又起步。中间6到8分钟速度降到0，才是停车段。

---

## #30 · 形数·三角形数与五边形数(misconception_not_ready)

- **题图**:[pqfile_99173d9ddc5ef6ecc7b2bbf2.jpg](https://raw.githubusercontent.com/DeepDreamerLSC/edu-agent/main/edu_agent/api/static/bank/pqfile_99173d9ddc5ef6ecc7b2bbf2.jpg)  
  `sha256: b16d0d587c5986a0f4efd769a4967b68df3a5d07604af38aef78dbfe2528a53c`
- **桶**:`visual_statistics_open` · **视觉依赖**:`required` · **难度**:`hard` · **对话承载力**:`high` · **答案确定性**:`text`
- **溯源**:`question_id=6a631f46184f723b3592d090` · `pujia_school_question_bank` · `6-2数与形(2)`

**转录(图是源 · Dev A 逐字核对)**:

```text
毕达哥拉斯学派研究了有趣的形数。(1)三角形数(点阵1,2,3,4…n)。数:___ 式:___。(2)选做:五边形数(点阵)。数:___ 式:___。
```

**参考答案**:`三角形数1,3,6,10,15…;T_n=n(n+1)/2;五边形数1,5,12,22,35…;P_n=n(3n-1)/2` (answer_type=`text`, unit=`—`)

**误区种子**(单题单误区):只写数列不找通项，或把形数的递推规律（每次多几个点）直接当成通项公式（二级）

**剧本摘要**(弧线:未就绪 → `not_ready`,3 轮):

1. 学生:三角形数是1,3,6,10,15……每次增加的比上一次多1。
2. 学生:通项式我只会写出前几项，不会写成n的式子。五边形数1,5,12,22我还没数清楚。
3. 学生:选做那题太难了，我连点阵怎么摆的都看不清。

---

## 待办(定稿前)

1. deepseek 盲测(visual_dependency 定稿)+ 答案通道——容器内无 `DEEPSEEK_API_KEY`,待密钥注入。
2. WP4:12-15 选 8 + 确认二级种子(本页)。
