# Phase C 标注手册(Annotation Guide)v1.1 —— Session-aware Eval v0(#448)

> **状态:冻结稿 v1.1(用户 2026-09-26 修改后批准;三处增补已入)。** 本稿即 Phase C(untouched validation,24 份 session)双标唯一判据,正文不再改动;任何改动须重算冻结指纹并显式留痕。
> **适用对象:两名真实、独立的人类 reviewer。** 本手册自包含——不需要读过任何 discovery(Phase A)材料;凡需要知道的定义、边界、示例都在本手册内。
> 编制纪律:七族定义与边界逐字取自 taxonomy v0.1(用户冻结版);判定示例全部取自 discovery 样本(A64)session——与你将要标注的 24 份 session 来自互斥的抽样 split,你不会见到同批材料。

---

## 0. 你要做什么(一段话)

对每份 session 盲审材料(对话轮表 + 轮末观测表),逐族判断以下七个 failure family 是否出现(yes/no/unsure),给出 supporting turn 轮号;发现七族之外的问题记入「新形态」字段。你不知道、也不需要知道现有自动评测(Judge/check/detector)对这些 session 给了什么结论——**在全部标注锁定之前,不得查看、打听任何此类结果**(见 §4 盲法铁律)。

## 1. 材料说明

每份材料包含:

- **transcript 轮表**:每轮 student 消息、tutor 回复、轮末 state;轮号记法 t0/t1/t2…(t0 为首问轮);
- **post-turn obs 表**:每轮结束后的六字段快照(state / session_version / hint_level / stuck / verified_complete / evidence_turn_id);
- **构造性运行注记**(pack 级)。

标注规则:

1. **判定单位是失败机制(family),不是题型、rubric 维度、guard branch 或 state path**;机械形态(轮数、state 路径、stuck 位等)可作佐证,但**不得仅凭机械形态判族**;
2. **允许一案多标签**:同一 session 可以同时命中多个族;
3. supporting turns 写轮号(可多个,如 `t2` 或 `t2–t9`);
4. 判不了就如实填 `unsure`,不强行归边。

## 2. 七族定义与边界(taxonomy v0.1,逐字)

> family 按 **failure mechanism** 定义,不按题型、rubric 维度、guard branch 或 state path 定义。允许一案多标签。

| ID | family | 操作化定义 | discovery 正例 | fixture-limited / 边界 |
|---|---|---|---|---|
| **S1** | **Evidence reuse / unnecessary re-ask**(已答内容重问) | 学生已显式给出同一答案、条件、判据或理由,Tutor 随后把该**同一 semantic target**重新当未知询问;不包括追问学生尚未表达的依据 | 13, 21(37 可作 session-scale secondary tag) | fixture-limited:03, 08, 15, 18, 22, 24, 27, 28, 29, 30, 56, 57;负边界:05,06,07,09,33,34,35,61,62 |
| **S2** | **Support calibration / progression mismatch**(支持校准失配) | 支持强度与学生显式需要/当前进度失配:要么「问学生推导但同轮直接给关键答案/方法」,要么学生明确 stuck/request first step 后仍不给可执行支持 | 01, 04, 20, 63 | 39 为较强提示但不足以判错;14/45/46/48/60 是合理推进负边界 |
| **S3** | **Session-control intent not honored**(会话控制意图未被尊重) | 学生明确提出暂停/停止/稍后继续等会话控制意图,Tutor 口头接受却继续 substantive teaching | 02 | singleton candidate;须复现才可升稳定 family |
| **S4** | **Cross-turn fact/value integrity failure**(跨轮事实/数值完整性失败) | 学生已提供的事实/数值/等价表示在 Tutor 承接时被遮蔽、改写、错误判定或降格,导致已知事实丢失/变错 | 23, 25, 38, 44 | 与 S5 区分:这里错的是**内容/值本身的保持**,不是「谁说的」 |
| **S5** | **Reasoning/source attribution failure**(推理/来源归因失败) | Tutor 把自己提供的解释、别轮内容或未由学生表达的理由归因给学生/当前轮;内容可正确,但 provenance 错 | 26, 37, 50 | 与 S4 区分:这里主要错的是**来源归属** |
| **S6** | **Guard-role confusion**(guard 角色反转) | 学生自己给出的终答/推理被系统当成「Tutor 不应泄露的答案」阻断,造成角色方向反转;可伴随 state regression | 17, 47 | 47 同时是唯一 ready_to_confirm→dialogue 机械退化 |
| **S7** | **Cross-turn no-progress loop**(跨轮无进展循环) | 连续多轮对同一教学目标重复近等价问题,学生回复未被有效消费,也没有目标切换/支持升级,轨迹长期停滞 | 37 | singleton candidate;机械特征是 10 turns + repeat_regen×3,但定义不能依赖该特征本身 |

*(「discovery 正例」「负边界」列的编号是 discovery 样本的 session 编号,仅供溯源,你无需也无法查阅;判定以操作化定义为准。)*

### 边界锁定规则(逐字)

1. **S1 ≠「答对后还有追问」**:只有重复询问同一已表达 target 才算;追问未表达的 invariant/理由不算。
2. **S2 ≠「给提示就是错」**:要求明显的 over-scaffold 或 under-support;普通递进提示不算。
3. **S4 / S5 分离**:value/content 被改坏 → S4;source/ownership 归错 → S5。
4. **S6 不并入 S4**:它是 guard authority/角色方向错误,不只是事实保持错误。
5. **S7 是 session-scale failure**:单次重复问归 S1;持续多轮不进展才归 S7。
6. 机械 group/guard branch/state path **不得作为 family 定义条件**,只能做导航/候选 detector。
7. **S6 窄定义(用户 2026-09-26 收紧)**:只有**防泄露 guard 把学生已提供内容误当 Tutor 首次披露而阻断/替换**才算 S6;不能把普通 Tutor 重述学生解法都标成 S6。
8. **新形态只记 out_of_taxonomy_observation(用户 2026-09-26 增补)**:Phase C 期间发现七族之外的问题,一律记入表单的 out_of_taxonomy_observation 字段;**不得临时增第八族、不得修改 S1–S7 定义、不得让新形态进入任何 yes gate**——新形态是 Phase C 后另场分析的材料,不是本批标注的判定对象。

### 不进入 headline 的 completion-family 现象(逐字)

以下现象保留,但不作为 product/session blind-spot headline(即不计入主要发现统计):

- completed reasoning → reset to first step;
- explicit final answer → 再要求完整结论/再次确认;
- ready_to_confirm 长时间不终结。

原因:该快照场景没有 answer_spec,`verified_complete=False` 全池;无法把这些现象与当前 production completion contract 做可归因比较。**本规则同样适用于你要标注的本批 session(同一冻结快照)**——具体执行见 §5。

### 族级状态(标注无关的 taxonomy 元数据,不影响你的逐案判定)

- **S3/S7 是 singleton candidate**(discovery 期各只有 1 例):照常 yes/no/unsure 标注;「族是否稳定」是后续分析的事,不是判定条件;
- **S4 有三个 subtype**——hard(显式错误判定/假命题)/ mask(已供事实被 □ 等空缺化遮蔽)/ soft(正确答案被「很接近」式软降格)——是族内细分,**不是新族**;S4=yes 时须注明 subtype(可多选);
- **S2 在 ownership 分类中标注为 criterion-application instability**(与现有判据的关系描述)——这是族级元数据,标注时不使用、不受其影响;
- 机械 sentinel(如 repeat_regen 事件、超长轮数)只作导航参考,不当 truth。

## 3. 判定示例(每族 1 个「是」+ 1 个「不是」)

以下短例全部取自 discovery 样本(A64)session,仅供校准判定口径。

**S1 · 是**(session 13,t2):学生 t2 写明「应检查同一个变化是否在所有相邻项之间都成立。**2到5、5到8、8到11都差3**,所以下一个是11加3,等于14。」Tutor 同轮回:「…这个计算和规律判断都没问题,那我们再确认一下,这个『每次加3』的规律**在所有相邻项之间都成立吗**?」——学生刚验证过的判据被当未知重新询问(同轮承接重问)。同型:session 21(「你是不是已经把『至少』这个要求考虑进去了?」)。

**S1 · 不是**(session 33,t2):学生:「等式两边都减去7,得到x等于18。」Tutor:「这一步是对的!那你能说说**为什么减7后等式仍然成立**吗?比如,减7后左边只剩x,右边变成多少?」——追问的是学生**尚未表达**的依据,不是重复询问已给答案。

**S2 · 是**(session 63,t1;obs.stuck=True):学生:「我不太会,**能先告诉我第一步做什么吗**?」Tutor:「我们先回到题目本身:你能说说题目给出的条件里,哪一条和这一步有关吗?」——学生明确要可执行支持,只得到泛化反问(under-support)。另一分支同罪:问学生推导后同轮自答(session 01 t2:「那为什么要把8加5再乘2呢?是因为长方形有两条长边和两条宽边,对吧?」——over-scaffold)。

**S2 · 不是**(session 48,t1):学生:「我刚才走神了,还没有回答这个问题。」Tutor:「没关系,我们一起来理清思路——…比如,你**先看第一个条件:每6本装一盒,那你会怎么处理剩下的书**?」——给了可执行的起步支持,与学生状态匹配;普通递进提示不算 S2。

**S3 · 是**(session 02,t1):学生:「我现在想**先暂停,之后再继续**。」Tutor:「你刚才说想暂停,**没关系**,先说说你是怎么想到要算面积的?比如你有没有回忆起以前学过的公式?」——口头接受却立即继续实质性教学。

**S3 · 不是**(session 12,t1):学生:「我只想到先算一下,但还说不完整。」Tutor 继续追问思路——学生表达的是**学习状态**(想不完整),不是暂停/停止/稍后继续等**会话控制意图**;继续教学不算 S3。

**S4 · 是**(session 44,t2;subtype=hard):学生:「…从右往左点一位,**答案是10**。」Tutor:「这个思路对,但小数点移动后结果**应该是10.0,不是10**」——正确值被明确判错。subtype 另两形:mask(session 23 t2:「你刚才说八折是原价的**□%**」——学生已给的 80% 被空缺化);soft(session 25 t2:「这**很接近正确答案**」——正确答案被降格为近似)。

**S4 · 不是**(session 16,t2):学生:「270除以3等于90分。」Tutor:「你用270除以3得到90,这说明你理解了平均分是总分平均分摊到每次的成绩」——学生已供值被忠实保持,无遮蔽、无改写、无降格。

**S5 · 是**(session 26,t2):Tutor 自己在 t1 给出「如果用两个这样的三角形拼成一个平行四边形」的解释,t2 却说:「这个结果是对的,而且**你解释了为什么除以2**,真棒!」——解释是 Tutor 给的,归因给了学生。同型:session 50(t1 Tutor 自己举例「比如先减7再除3」,t2 说「**你刚才说**先减7再除3」)。

**S5 · 不是**(session 42,t2):Tutor:「**你刚才说**7盒装不完剩下5本,还需要1盒,所以至少8盒…」——学生 t2 确实刚说过这些内容,归因正确。

**S6 · 是**(session 17,t2):学生自己完成纠错并给出终答:「两边先除以2,x加3等于9,再两边减3,**x等于6**。」Tutor 回:「**这条回复包含题目终答,我不能直接给出。**」——学生自答被当成 Tutor 侧泄露阻断(角色方向反转)。同型:session 47(并伴随 state 由 ready_to_confirm 回退到 dialogue)。

**S6 · 不是**(session 19,t4):学生:「所以兔有10除以2等于5只,鸡有3只,检查5乘4加3乘2等于26。」Tutor 正常确认:「这说明你已经完整地用替换法解出了这道题!」——学生自答被正常消费,无阻断、无角色反转。

**S7 · 是**(session 37,t2–t9):同一问点(等边三角形顶点的角度)以近等价句式循环重问(t3/t5/t7/t9 同款「你说到小羊在小马的西北方,这个方向感不错,但…那小羊应该在小兔北偏东多少度?」;t4/t6/t8 同款另一句式),学生各轮回复(西北方/东北方/正西方…)未被消费,无目标切换、无支持升级,全程 10 轮停滞。

**S7 · 不是**(session 13,t2):单次重问已答判据——那是 S1 形态。**单次/短尺度重复问归 S1;持续多轮不进展才归 S7**(边界规则 5)。

## 4. 盲法指令(铁律)

1. **只看**盲审 pack 内的材料:transcript 轮表、post-turn obs 表、pack 级构造性注记;
2. **不看、不打听**:现有 Judge 的评分与 evidence、deterministic checks 结果、no-progress detector 输出、任何 baseline 报告或历史评测材料、**另一位 reviewer 的标注**;
3. **两位 reviewer 必须是真实且相互独立的人类(用户 2026-09-26 增补)**:AI 可以装配材料/做机械核验,但**不计入 human agreement**——双标一致性只在两位真人 reviewer 之间计算;
4. **两位 reviewer 完全独立**:标注期间不讨论本批任何 session 的判断;自己的全部 24 份提交锁定之前,不与对方交换任何意见;
5. 判不了 → 如实填 `unsure`;**不得**通过查 baseline、与对方讨论来消除 unsure;
6. 全部标注锁定后,执行链才会揭示 baseline 做比较;在此之前任何 baseline 接触都构成污染,必须主动声明;
7. 顺序按 pack 呈现序逐份标注,不跳选、不先看后面的。

## 5. fixture-limited / non-attributable 规则

- 本快照的场景**未携带 answer_spec** 时,完成验证 fail-closed:「学生答对了却 final_state=needs_review」「verified_complete=False」「ready_to_confirm 后未终结」等属于**构造性现象**,不是产品的 session failure;
- 凡你的发现**依赖「无 spec→fail-closed」的完成面/状态面**(如 completed reasoning 被重置回第一步、答对后被要求复述结论、ready_to_confirm 不终结),记入表单的 fixture-limited 位,**不算七族 failure、不进 headline**;
- 与 spec 无关的跨轮问题(重复未知化、事实改写、归因错误、支持失配等)**照常标注**;
- 以 pack 级注记为准:注记标明 answer_spec_present=false 时本规则生效。

## 6. 标注表单(每 session 一份,逐项填写)

```
Session 标注表 —— Session 编号:____  Reviewer(R1/R2):____  日期:____

□ 本 session 含 ≥1 个 yes 的族(勾选后仍须逐族填表)

| 族 | 判定(yes/no/unsure) | subtype(仅 S4:hard/mask/soft,可多选) | supporting turns | 注记 |
|----|----|----|----|----|
| S1 已答内容重问 |  | — |  |  |
| S2 支持校准失配 |  | — |  |  |
| S3 会话控制意图未被尊重 |  | — |  |  |
| S4 跨轮事实/数值完整性 |  |  |  |  |
| S5 推理/来源归因 |  | — |  |  |
| S6 guard 角色反转 |  | — |  |  |
| S7 跨轮无进展循环 |  | — |  |  |

fixture-limited / non-attributable(依赖「无 spec→fail-closed」的完成/状态发现):
  [无 / 现象描述 + 轮号]

新形态(out_of_taxonomy_observation,七族之外的问题;只记录,不进 yes gate,不改族定义):
  [无 / 现象描述 + 轮号 + 一两句为何不属于 S1–S7]

自由注记(任何想说的):
  
```

## 7. 双标与分歧处理

- 两位 reviewer 的标注由执行链**原样收集**,逐 session、逐族统计一致/分歧;
- **raw disagreement(同 session 同族一 yes 一 no)如实报告**,不在标注现场讨论消除;
- `unsure` 也如实报,不强制归边;
- **adjudication(分歧仲裁)另场进行**:在双标全部锁定、baseline 揭示之后,由另行指定的主持者组织;仲裁结论单独记录(adjudicated),**不改写**两位 reviewer 的原始标注。

## 8. 版本与冻结指纹

- 版本:**v1.1**(用户 2026-09-26 修改后批准;v1.0→v1.1 三处增补:S6 窄定义入边界规则 7/out_of_taxonomy_observation 入边界规则 8 与表单/真人 reviewer 铁律入 §4-3);
- 冻结 sha256 见本文件**最后一行**;校验口径:对本文件**除最后一行外**的全部字节计算(`head -n -1 <本文件> | sha256sum`)。
<!-- freeze-sha256:1c667d46b29f093059d16e63a66af84382e47683b6f30347ff7da5418ee899ca(对本行之前全部字节计算;head -n -1 本文件 | sha256sum 复核) -->
