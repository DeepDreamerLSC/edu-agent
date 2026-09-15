# GEPA optimizer-feasibility spike(#253,2026-09-15)——**机器面可行;预算/门/优化器选择 = 人键**

点火依据:用户会话内选定(2026-09-15,与路 B / teacher-line 同批);执行序 ⑥「GEPA spike(仅 optimizer feasibility)」。**零 API**(全部读数 = 仓内机器核验 + 既有工件实测)。

## 一、三腿门现状(#238 §4;机器核验)

### 腿① prompt 表面(搜索空间)——**就位 ✓(#238 登记 6 处口径)**

- `prompting.py` 模块级常量 **29 = 提示面 25 + 资产路径/辅助 4**(后者 = `_REPO`/`SKILL_PATH`/`KNOWLEDGE_TREE_PATH`/`STYLE_PROFILES_PATH`,非提示文本);提示面 25 处全列:`_TONE_DIRECTIVE`、`_MISSION_DIRECTIVE`、`TACTICS`、`_SUMMARY_INSTRUCTION`、`OPENING_HINT_CORRECT`、`OPENING_HINT_INCORRECT`、`OPENING_HINT_UNANSWERED`、`_DIAGNOSE_TURN_HINT`、`_OPENING_HINTS`、`HEAD_TEXT`、`HEAD_IMAGE`、`TAIL_CORRECT`、`TAIL_COLLECT`、`ASK_FINAL_ANSWER`、`FIRST_QUESTION_CORRECT`、`FIRST_QUESTION_COLLECT`、`FIRST_QUESTION_COLLECT_IMAGE`、`TUTOR_TURN_SCHEMA`、`TUTOR_SUMMARY_SCHEMA`、`OPEN_SCHEMA`、`_SELF_CRITIQUE`、`_PREMATURE_CONFIRM_CRITIQUE`、`_FEEDS_METHOD_CRITIQUE`、`_GUARD_REJECTION_HIT_TEMPLATE`、`_GUARD_REJECTION_NUMBERS_TEMPLATE`;
- **#238 登记的 6 处外置(schema ×3 + 批评提示 ×3)已完成**——六个常量全在 `prompting.py`、kernel.py 无定义;「残留 = 0」**限定为此 6 处口径**(修复依据 c5677296654/c5677293566);
- **kernel.py 学生可见文本登记(5 处,均直接作为学生可见回复返回;prompting.py 无同名 ⇒ 现状不在搜索面)**,按不变量 2(搜索空间只有 prompt 面;判停闸/泄露闸/弧线状态机在内核非参数)逐处判定:

| 常量 | 文本(首句) | 引用 | 直接 return | 归属 | 理由 |
|---|---|---|---|---|---|
| `FAIL_CLOSED_TEXT` | 「这张题图我没法安全地开始讲解…」 | 2 | — | **面外** | 图安全 fail-closed 闸的固定输出;闸面(判停/安全)属不变量 2 非参数面 |
| `_OPENING_FALLBACK` | 「我们先看看这道题,你能说说题目给了哪些条件吗?」 | 2 | — | **面外** | 模型留空路径的确定性兜底首问(#185 注释明示「确定性兜底」);正常首问 `OPENING_HINT_*` 已在搜索面内,调语气应走那边 |
| `_ELICIT_TEMPLATE` | 「我们从头把思路串一遍——…」 | 5 | :798 | **面外** | 复讲(弧线状态机)确定性输出;且复读检测按**字面比对** `prev == _ELICIT_TEMPLATE`(kernel.py:166)——改文本即破检测,机械耦合 |
| `NEEDS_REVIEW_TEXT` | 「这一题的学习证据还不够,我们继续…」 | 6 | :362 | **面外** | 证据闸(NEEDS_REVIEW)路径确定性输出;#185 登记其统计**按前缀不按文本匹配**,文本与闸门行为耦合 |
| `SAFE_FALLBACK_TEXT` | 「先回到当前小问,你能说出题目明确给出的一个条件吗?」 | 1 | — | **面外** | 安全兜底路径文本(护栏面) |

  **边界申明**:以上 5 处按不变量 2 逐处判为**面外**(内核机制文本:闸面/兜底/弧线状态机输出,非 prompt 面);若要将任何一处纳入 GEPA 搜索面,须先外置到 `prompting.py` 并同步解耦耦合点(字面比对/前缀统计)= 结构改动,人批。搜索空间边界的定义权在人,本登记提供逐处判定与理由,不代替裁定。

### 腿② corpus——**≥100 门 PASS(120 / 4)**

机器计数(datasets 文件逐个):dialogue_scenarios 3 + shadow_24 24 + gold 60 + b2 13 = **train 100**;+ 路 A(teaching_context_shadow_pilot_20,20,人审已批)= **train 120**;heldout = b2_heldout **4**(独立文件)。

- 切分纪律机器面成立:corpus_round 按显式路径加载,heldout 文件不传即不可见(#238 冻结规则);
- adaptive_shadow_pilot_20(期望面全空)与 dialogue_stability_20 等不在 train 计数口径内(#238 §4 既有裁定),本备忘不重裁。

### 腿③ 搜索预算——**未批(人键)**;参数化算术如下

实测锚点(仓内工件 `corpus-round-v2/collect/cases-20260914T032228Z-bda5/results`,92 案有 transcript;**计数公式显式**):

- **Σturns(含每案首问轮)= 301;首问 92/92 `elapsed_ms=0`、`state=first_question_ready`、`student=""` ⇒ 模板驱动、非模型调用;有 summary 案 92(summary 为模型调用);judge 侧 92(#271 可判案数)**;
- **tutor = Σturns 301 − 首问 92 + summary 92 = 301**;保守口径(把首问计为调用)= 393;
- **合计 = tutor 301 + judge 92 = 393(保守 485)⇒ 每案 = 393/93 = 4.23(保守 5.22)**;
- **勘误(诚实账)**:原版「tutor 485 / 合计 577 / 6.2 每案」不可从工件复现——485 实为保守 tutor 393 + 与 judge 面同量的 92,再单加 judge 92 即 **judge 计了两遍**;且首问 92/92 `elapsed_ms=0` 证明其为模板驱动,本就不该计(审查 c5677293566 复算,本版已从工件逐位复现);
- #271 判卷 token 锚点(逐位核验命中,**源 = `judge-v3.2-rescore-93/api-facts.jsonl`**,184 调用):**2,751 input / 510 output tokens 均每调用**(合计 506,244 in / 93,879 out / 433,388 cache-read)。

| 场景(示例参数,非申请值) | 公式 | 调用量(实跑 4.23 / 保守 5.22 每案) |
|---|---|---|
| 每候选全 train 评估 | 120 × 每案 | ≈508 / 保守 ≈626 |
| 迭代内切片评估(K 候选 × S 案切片 × I 轮) | K×S×每案×I | K=4,S=16,I=6 → ≈1,624 / 保守 ≈2,004;K=6,S=24,I=8 → ≈4,873 / 保守 ≈6,013 |
| 优化器侧提案调用 | ≈K×I(提示编辑生成) | 数十~百级(相对小头) |
| heldout 终审(仅终审,不变量 1) | 4 × 每案 + 人抽审 | ≈17 / 保守 ≈21 + 人 |

**结论**:原表按 6.2/案 分母,较修正分母虚高约 19–32%(依保守/实跑口径;派单与审查区间),三行已按新分母重算;腿③ 的「数百次量级」(#238 原文)对应**小切片首轮**;全 train × 多候选迭代为**数千次级**。档位/配额/切片大小 = 人批项,本备忘只供算术。

## 二、度量接口(机器核验,零胶水)

- `judge_transcript(gateway, case, role) -> dict`(scores/total/verdict)——**普通 Python 函数**,GEPA metric 直接可调(#215 既有结论,本次签名复核);
- `checks.py` 零模型调用(确定性 check 先行,判分双判面完整);
- `EvalRunner`/`JudgeSubject` 断点续跑批任务面可导入;#257 身份三件套(git HEAD / prompts_sha256 / models_sha256)+ facts 落工件已就位(工件实证:`artifacts/gepa-prereqs-trial/collect/cases-20260914T084511Z-9dde/manifest.json` 的 `prompts_sha256`)——每次迭代的可归因性有地基。

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
# 腿①:ast/grep 枚举 prompting.py 模块级常量(29=25+4)+ kernel.py 五处学生可见
# 文本引用计数(2/2/5/6/1,两处直接 return :798/:362);
# 腿②:datasets 文件逐个 len(scenarios);
# 腿③ 计数公式:Σ len(turns)(含首问轮)→ 301;首问轮按 state=first_question_ready
# 且 elapsed_ms=0/student="" 识别(92/92,模板非调用);summary 有无逐案(92);
# judge = #271 可判案数(92);tutor = 301−92+92;每案 = 合计/93。
# token 锚点:judge-v3.2-rescore-93/api-facts.jsonl usage 字段求和(184 调用)。
# 全部零 API,读数 = 仓内工件 + 代码扫描。
```
