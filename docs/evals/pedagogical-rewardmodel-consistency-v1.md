# 教学奖励模型(Qwen2.5-1.5B-pedagogical-rewardmodel)与我们六维 judge 的一致性实验 v1

**一句话**:轮级配对判别力**很强**(真实改写对 96–100% 认可护栏改写),但 case 级与六维总分**负相关**(总体 ρ=−0.21,场景内中心化 ρ=−0.41)——两个尺子量的是不同的东西:它量「过程纯度」(中段追问密度),我们 judge 量「弧线完成度」(首问→引导→复讲→收束)。**不建议**作为六维总分的第二标尺进夜评趋势;留档还是删除 6GB 交 PM/用户裁定。

- 被测:`~/Desktop/work/models/Qwen2.5-1.5B-pedagogical-rewardmodel`(MathTutorBench,Macina et al. 2025;`Qwen2ForSequenceClassification` 单标量,基座 Qwen2.5-1.5B-Instruct,MathDial+MRBench 成对偏好,float32 6.0GB,英文语料)
- 实验:2026-09-10,Mac 本地(MPS),一次性 scratch 环境 `/tmp/rmenv`(torch 2.14 + transformers 5.17,**未进仓库依赖**);跑批前主 CI = completed
- 素材(全部现有工件,零模型调用):夜评 P 口径 4 晚 ×(11 场景 + 8 题图)+ 本仓 #149 帧 P 口径 4 轮 × 11 = **120 个带六维总分的 case**(2419 教师轮);#143/#148 弧线帧 88 + 308 个带四指标 case
- 产物:逐轮分数 `rm-scores-v1/`(见 §6),复现命令见 §7

## 1. 格式假设(最大的坑,先钉死)

**严格照抄官方推理代码** `eth-lre/mathtutorbench/reward_model/compute_scaffolding_score.py`(jsdelivr 镜像取回,非自创格式):

```
<|im_start|>system
Judge the pedagogical quality of the responses provided by two teachers. Focus on the quality of the
scaffolding guidance, correctness, and actionability of the feedback through nudges, questions and hints.
Do not give high scores for revealing the full answer.<|im_end|>
<|im_start|>user
Problem: {题面}
Reference Solution: {参考答案}<|im_end|>
<|im_start|>assistant
{教师第 1 轮}<|im_end|>          ← 历史:教师=assistant,学生=user
<|im_start|>user
{学生消息}<|im_end|>
<|im_start|>assistant
{待评教师回复}<|im_end|>          ← 末条 = 待评回复
```

加载与打分同官方:`num_labels=1`、`torch_dtype=bfloat16`、禁 dropout、`apply_chat_template(tokenize=True, return_dict=False)` → `model(inputs)` → `logits[0][0].item()`(MPS 2419 轮 79 秒)。参考答案取各帧 `cases.jsonl` 的 `reference_answer`;题图帧的 question 为 dict 字符串,取 `text` 字段。

## 2. 第 0 步:人造对照对判别力自检(中文,5 组 + 1 组英文对照)

同一上下文(真实场景中段)配两种教师回复:「直接报答案/整题演算」vs「苏格拉底引导/只给下一步」。

| 对 | 场景 | 报答案型 | 引导型 | 差(good−bad) |
|---|---|---:|---:|---:|
| P1 | 鸡兔同笼(中) | −2.48 | +6.88 | **+9.36** |
| P2 | 三角形面积(中) | −1.67 | +3.70 | **+5.38** |
| P3 | 分数加法(中) | −1.47 | +9.75 | **+11.22** |
| P4 | 学生已说出答案后的确认(中) | −5.13 | +7.09 | **+12.22** |
| P5 | 解方程冷启动(中) | −2.56 | +9.13 | **+11.69** |
| P6 | 英文对照(控制组) | −2.73 | +7.72 | **+10.45** |

**6/6 全部分对**,中文对的差值与英文对照同量级 → 粗粒度上**语种不是障碍**,继续刷全量。

## 3. 真实改写对 A/B(轮级配对,最强证据)

护栏事件里存有「原始输出」与「实际上线的改写文本」(**同上下文、同 case、同轮位**,内容前缀匹配 ratio≥0.35,配对 127 对):

| 事件类型 | n | RM(原始) | RM(改写) | 改写胜率 | Δ 中位 |
|---|---:|---:|---:|---:|---:|
| `answer_leak`(报答案) | 103 | −0.28 | **+1.59** | **99/103(96%)** | +1.63 |
| `feeds_method`(喂方法名) | 20 | +0.41 | **+1.87** | 18/20(90%) | +0.57 |
| `premature_confirm`(#149 判停闸) | 4 | +7.06 | **+9.06** | 4/4 | +2.00 |

→ 在**我们自己的中文转录**上、其余一切不变时,RM 系统性地认可护栏改写、惩罚原始泄露。**轮级判别力真实且方向正确**。

## 4. 与六维 judge 的一致性(相关性表)

n = 120 个(帧,case)对;Spearman ρ,CI95 为成对自助 2000 次,p 为置换检验 2000 次;标准库自实现。

### 4.1 总分

| 口径 | ρ | CI95 | p | n |
|---|---:|---|---:|---:|
| 总体(RM mean vs judge 总分) | **−0.210** | [−0.377, −0.032] | ≈0.020 | 120 |
| 总体(RM min vs judge 总分) | −0.201 | [−0.424, +0.023] | ≈0.028 | 120 |
| **场景内中心化**(去掉场景均值) | **−0.409** | [−0.609, −0.203] | <0.001 | 120 |
| 场景层(19 场景均值排序) | −0.236 | — | — | 19 |
| 分源:149P-pre(main 侧) | −0.173 | [−0.546, +0.285] | ≈0.44 | 22 |
| 分源:149P-post(分支侧) | −0.262 | [−0.701, +0.342] | ≈0.25 | 22 |
| 分源:夜评 ×4 | −0.242 | [−0.452, −0.038] | ≈0.04 | 76 |
| P 口径 11 场景 | −0.220 | [−0.428, +0.007] | ≈0.04 | 88 |
| 题图 8 题 | −0.238 | [−0.526, +0.103] | ≈0.19 | 32 |

**负相关稳定存在**:同场景内,RM 给高分的转录,judge 倾向给低分(反之亦然)。

### 4.2 逐维(RM mean vs judge 各维)

| 维度 | ρ | CI95 | p |
|---|---:|---|---:|
| first_question | **+0.401** | [+0.223, +0.548] | <0.001 |
| socratic_followup | −0.235 | [−0.413, −0.054] | ≈0.013 |
| grade_fit | 恒为 2(无方差,不可算) | — | — |
| pacing | −0.326 | [−0.458, −0.180] | <0.001 |
| summary_mastery | **−0.474** | [−0.614, −0.317] | <0.001 |
| termination | −0.259 | [−0.398, −0.091] | ≈0.005 |

唯一正相关是 `first_question`;与「收束/总结/节奏」三维全部显著负相关。

### 4.3 机理:RM 的奖励形状(2419 轮按轮位分解)

| 教师轮位 | t0 首问 | t1 | t2 | t3 | t4 | t5 | 收尾 summary |
|---|---:|---:|---:|---:|---:|---:|---:|
| RM 均分 | **+0.13** | +7.25 | +5.70 | +3.58 | **+0.15** | +1.57 | **+0.34** |

- RM **最爱中段追问**(t1/t2 +7.3/+5.7),例:「下一步是这样:实际脚数比假设多出多少?你接着算下一步」= +10.5;
- RM **狠打两类轮**:冷启动首问(全部 428 例首问均分 +0.13)与收尾轮(t4 +0.15、summary 消息 +0.34,对比普通轮 +3.57);
- **地板分(−5.00)给的是 correct-path 首问模板「还有没有不懂的地方?」**——即我们 judge 打 12/12 满分的 equation 场景;
- 我们的 #112 复讲引导模板(「很好,你已经懂了。那请你从头讲讲你的思路…」,116 例)RM 给 **+4.91**(高于全体轮均值 +2.90)——它认可这一步。
  - **注(2026-09-12,#220 审查 P2)**:该 +4.91 针对旧文案;#179 问题 3 修法(#220)已将模板改为
    「我们从头把思路串一遍——先说说你第一步算了什么、为什么这样算。」——**新文案未测**,本条
    证据卡视为已被 #220 取代,RM consistency 重跑待排期。(同文档引用旧文案的 teaching-arc-149/
    fix112 帧属历史记录,按惯例不改。)

### 4.4 case 级四指标分组(fix112+v1,308 case)

| 分组 | RM mean | RM min 中位 | n |
|---|---:|---:|---:|
| feeding.fed=True(教师报答案) | +3.21 | −0.80 | 144 |
| feeding.fed=False | +3.75 | −1.77 | 164 |
| judge answer_leaked=True(六维) | +3.53 | −2.36 | 36 |
| judge answer_leaked=False | +3.68 | −2.56 | 84 |

→ **case 级聚合测不出报答案**(首问/收尾轮的系统性低分把它淹没;min 中位方向还反了)。§3 的判别力只在**轮级配对**时成立。

### 4.5 场景层反例(引用 RM 均分 / judge 总分)

- `equation_complete_reasoning`(correct 路径):judge **12.0**(满分)vs RM **+1.20**(19 场景中倒数第二);
- `visual_statistics_open_27/30`(题图,最难两题):judge **4.0/3.0**(垫底)vs RM **+5.02/+4.08**(中上);
- `chicken_rabbit`:judge 7.8 vs RM +6.49(喜欢长追问弧线)。

## 5. 结论与建议(**不下最终决定,交 PM/用户裁定**)

1. **语种/域错配不是主障碍**:中文粗粒度判别 6/6、真实改写对 96–100% 认可 → 它在中文、我们的域上「能干活」(轮级)。
2. **作为六维总分的第二标尺 = 不可用**:case 级负相关(总体 −0.21、场景内 −0.41、逐维收束侧 −0.26~−0.47)。原因不是语种而是**教学观分歧**:RM 的训练目标(MathDial 偏好)奖励「过程纯度/追问密度、永不收束」,我们的教学弧线(首问→引导→复讲→**确认收束**)的后半程恰是它系统性惩罚的部分;它连我们满分的 correct-path 首问都给地板分。若进夜评趋势,它与 judge 的差值读出来会是「越收束越报警」的系统性噪声,**会误导而非交叉验证**。
3. **轮级判别力是真实资产**:对「是否报答案/喂方法/提前判停」的配对判别 96–100%,且认可 #112 复讲模板。但同域轮级信号我们已有**确定性护栏**(免费、可解释、零误判口径),RM 在这个用途上没有增量,除非 M3 需要「护栏外」的更软信号(如追问质量分层)。
4. **留/删建议**:
   - 若 M3 规划里没有「轮级软信号」需求 → **删除回收 6GB**(本报告即全部留档:格式、分数、结论可复现);
   - 若想留一个选项 → 转存 bf16(≈3GB,打分与 float32 同格式)留档,并在 M3 立项时再决定;
   - 无论如何,**不接夜评趋势、不进门禁、不进依赖**(本实验全程未改 `pyproject.toml`/`uv.lock`/`configs/`)。

## 6. 工件

- `edu_agent/evals/artifacts/rewardmodel-consistency-v1/`:`rm_scores.jsonl`(2419 逐轮分)、`ab_scores.jsonl`(274 改写轮分,127 对配对成功)、`pairs_scores.jsonl`(对照对)、`case_level.json`(case 级聚合 + judge 分对齐)、`cases_meta.json`(uid 溯源)、`to_score.jsonl`(全部打分输入,自包含)
- 全部分数由格式 §1 产出;分析/打分/建集脚本以 `*.py.txt` 原样(逐字节)存档于同目录(`score_rm.py.txt`/`analyze.py.txt`/`build_dataset.py.txt`)——一次性脚本,改后缀以免落入仓库 lint 范围,内容即产出上表数字的原始代码

## 7. 复现

```bash
# Mac 一次性环境(已按需清理)
/opt/homebrew/bin/python3.12 -m venv /tmp/rmenv && /tmp/rmenv/bin/pip install torch transformers
/tmp/rmenv/bin/python score_rm.py to_score.jsonl scored.jsonl     # 格式见 §1
python3 analyze.py                                                # Spearman/自助/置换
```
