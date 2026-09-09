# 题图教学评测集 v1 · 误区池(Dev B 盲测线草稿)

> 用途:WP3 剧本的 `misconception_seed` 候选源(单题单误区,隔离变量)。
> 出处分级(s8):**一级** = 仓库既有场景错误模式(注明在库出处);
> **二级** = 教参常见错误(标注「待 WP4 用户确认」,人审时确认后才进数据集)。
> 本池是草稿,终版随 WP4 人审收敛(12-15 选 8 + 确认二级种子)。

## 桶 1 · text_position(坐标/位置)

- **一级** 排号顺序颠倒——把「(排, 号)」写成「(号, 排)」或反之。
  出处:`edu_agent/evals/datasets/small_lecturer_target_mode_v3_question_bank.json`
  (`coordinate_notation_full`/`coordinate_notation_encode_only`,8排6号记作(6,8)的反序设计)。
- **二级(待 WP4 用户确认)** 以「自身」为参照点描述他人相对位置(左右/前后方位反)。
- **二级(待 WP4 用户确认)** 数轴/方格图中「列 vs 行」混用(先读列还是先读行)。

## 桶 2 · fraction_formula(分数/公式运算)

- **一级** 异分母分数加法直接把分子加分子、分母加分母。
  出处:`edu_agent/evals/datasets/small_lecturer_math_gold_candidates.json`
  (`fraction_addition_misconception_repair`)+ `.../small_lecturer_prompt_lab_seed_question_bank.json`
  (`common_mistakes`: 把分子和分母分别直接相加)。
- **二级(待 WP4 用户确认)** 分数乘法「先乘后约」与「先约后乘」漏约分,结果不是最简。
- **二级(待 WP4 用户确认)** 分数除法把「除以一个数」错成「乘以被除数的倒数」或只对被除数取倒数。
- **二级(待 WP4 用户确认)** 单位「1」找错(整体量/部分量错位)。

## 桶 3 · circle_geometry(圆几何)

- **一级** 半径当直径用(或直径当半径用)。
  出处:issue #130 数据结构示例 `image_v1_circular_pond_race`(`misconception_seed`: 半径当直径用);
  同型见 `small_lecturer_math_gold_candidates.json` 的 `rectangle_perimeter_misconception_repair`(周长口径混用,几何量口径错配先例)。
- **二级(待 WP4 用户确认)** 周长公式 `2πr` 与面积公式 `πr²` 混用(该求周长用了面积,反之)。
- **二级(待 WP4 用户确认)** 半圆周长漏加直径(只算了半条弧)。
- **二级(待 WP4 用户确认)** 圆规两脚距离=半径,却直接当直径用。

## 桶 4 · percentage_multi_part(百分数)

- **一级** 折扣方向颠倒(「打八折」当成「乘 1.8」或「除以 0.8」之类)。
  出处:`small_lecturer_math_gold_candidates.json` 的 `percentage_discount_misconception_repair`。
- **二级(待 WP4 用户确认)** 单位「1」找错——增长率/成数问题里把「基期量」与「现期量」混为被除数。
- **二级(待 WP4 用户确认)** 百分数参与运算时忘「除以 100」(68% 直接当 68 用)。

## 桶 5 · application_table(应用表格)

- **二级(待 WP4 用户确认)** 表格行列读反(读取时拿错列/拿错行,或行标题与数据错位)。
- **二级(待 WP4 用户确认)** 从表格取关键数据时单位不统一直接运算(如 mL 与 L、km 与 m 混算)。
- **二级(待 WP4 用户确认)** 只完成表格第一步(取数/第一步运算),漏「求答」的最终结果。

## 桶 6 · visual_statistics_open(图形统计开放)

- **一级** 统计图只看条形高度、忽略纵轴起点或单位(非零基线误读)。
  出处:`small_lecturer_math_gold_candidates.json` 的 `average_score_misconception_repair`(平均数口径错配先例)。
- **二级(待 WP4 用户确认)** 速度/时间图像把「斜率/段」与「总量」混淆(只读曲线形状不读坐标)。
- **二级(待 WP4 用户确认)** 开放题只给结论不给过程(可判定性落在「核心结论可校验」上,s5)。
