# GEPA optimizer-feasibility spike(#253,2026-09-15)——**机器面可行;预算/门/优化器选择 = 人键**

点火依据:用户会话内选定(2026-09-15,与路 B / teacher-line 同批);执行序 ⑥「GEPA spike(仅 optimizer feasibility)」。**零 API**(全部读数 = 仓内机器核验 + 既有工件实测)。

## 一、三腿门现状(#238 §4;机器核验)

### 腿① prompt 表面(搜索空间)——**就位 ✓**

- `prompting.py` 模型面常量 **26 处**(语气/使命指令、TACTICS、总结指令、首问提示 ×3、HEAD/TAIL、ASK_FINAL_ANSWER、FIRST_QUESTION ×3、schema ×3、批评提示 ×3、护栏拒答模板 ×2;另有 3 处为资产路径常量非提示文本);
- #238 登记「存量 6 处 schema/批评提示外置 kernel.py→prompting.py」**已完成**:kernel.py 提示常量残留 = **0**(机器扫描);
- 不变量 2(搜索空间只有 prompt 面)边界未变:判停闸/泄露闸/弧线状态机仍在内核,非参数。

### 腿② corpus——**≥100 门 PASS(120 / 4)**

机器计数(datasets 文件逐个):dialogue_scenarios 3 + shadow_24 24 + gold 60 + b2 13 = **train 100**;+ 路 A(teaching_context_shadow_pilot_20,20,人审已批)= **train 120**;heldout = b2_heldout **4**(独立文件)。

- 切分纪律机器面成立:corpus_round 按显式路径加载,heldout 文件不传即不可见(#238 冻结规则);
- adaptive_shadow_pilot_20(期望面全空)与 dialogue_stability_20 等不在 train 计数口径内(#238 §4 既有裁定),本备忘不重裁。

### 腿③ 搜索预算——**未批(人键)**;参数化算术如下

实测锚点(仓内工件):corpus-round-v2 = 93 案 **≈577 次模型调用**(tutor 侧 485 = 轮次+start+summary 估算 + judge 92)≈ **6.2 调用/案/全跑**;#271 判卷实测 **2,751 input / 510 output tokens 均每调用**(184 调用:506,244 in / 93,879 out / 433,388 cache-read)。

| 场景(示例参数,非申请值) | 公式 | 调用量 |
|---|---|---|
| 每候选全 train 评估 | 120 案 × 6.2 | ≈744 |
| 迭代内切片评估(K 候选 × S 案切片 × I 轮) | K×S×6.2×I | K=4,S=16,I=6 → ≈2,381;K=6,S=24,I=8 → ≈7,142 |
| 优化器侧提案调用 | ≈K×I(提示编辑生成) | 数十~百级(相对小头) |
| heldout 终审(仅终审,不变量 1) | 4 × 6.2 + 人抽审 | ≈25 + 人 |

**结论**:腿③ 的「数百次量级」(#238 原文)对应**小切片首轮**;全 train × 多候选迭代为**数千次级**。档位/配额/切片大小 = 人批项,本备忘只供算术。

## 二、度量接口(机器核验,零胶水)

- `judge_transcript(gateway, case, role) -> dict`(scores/total/verdict)——**普通 Python 函数**,GEPA metric 直接可调(#215 既有结论,本次签名复核);
- `checks.py` 零模型调用(确定性 check 先行,判分双判面完整);
- `EvalRunner`/`JudgeSubject` 断点续跑批任务面可导入;#257 身份三件套(git HEAD / prompts_sha256 / models_sha256)+ facts 落工件已就位——每次迭代的可归因性有地基。

## 三、⑦ 门现状(GEPA 全量/promotion 前置)

「教师盲区 gate 或成熟路 B **至少一个就位**」——**当前未就位,在建**:教师盲区 gate(本波 ③ 件,启动中);路 B spike 已过抽取忠实性门(#272)但正式结构件未建。两者之一完成后 ⑦ 门才开。

## 四、可行性判定

| 面 | 判定 |
|---|---|
| prompt 搜索面(腿①) | **可行** |
| corpus 规模与切分(腿②) | **可行(120/4,过 ≥100 门)** |
| 度量接口(零胶水) | **可行** |
| 预算(腿③) | **待人批**(参数化算术如上;flash 判卷 2.7k in/0.5k out 每调用) |
| ⑦ 前置门 | **未就位(教师 gate/成熟路 B 至少一,在建)** |
| 优化器本体 | #215 调研「暂不引入」,触发器(corpus ≥100)现已满足——引入与否 = 人键 |

**一句话**:机器侧三面(表面/语料/度量)全绿,GEPA 可行性成立;点火全量前的三把人键 = 预算批、⑦ 门就位、优化器引入决定。

## 复算

```bash
# 腿①:grep prompting.py 常量 + kernel.py 残留扫描;腿②:datasets 文件逐个 len();
# 实测锚点:corpus-round-v2/collect results 逐案状态与轮次计数;#271 api-facts
# usage 字段求和。全部零 API,命令形态见本文件各节。
```
