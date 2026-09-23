# Trusted Completion Gate 设计件 v3:CompletionEvidence 最小不变量(执行链②,纯设计不写代码)

状态:v3(2026-09-23,二审 3P0+3P1 修订毕)。v1 草案→v2 一审 7 项→v3 二审 6 项。
前置已闭:步骤7 Prompt hypothesis 关闭(#382 终裁);负向三案(2791/5106/3490)已实证不变量必要。

## 一、核心不变量(一句话)

> **任何成功的 completed 迁移都必须由 trusted CompletionEvidence 授权;无 evidence 时 fail-closed。Evidence 不自行触发状态迁移——它是必要授权条件,不是"出现即完成"的充分条件。** Tutor 文本、summary、guard fallback、任何模型输出都不能创造这个事实——它只能来源于学生本轮消息经确定性 verifier 判定。

与既有不变量的同源性:trusted ladder(P0-3)治"reveal 消费什么",本件治"completed 由什么授权"——同一治理原则:**provenance 先于模型觉得它应该成立**。

## 二、CompletionEvidence 类型化事实

```python
# 概念结构(设计件,非实现承诺)
class CompletionEvidence:
    source: Literal["student"]          # 恒为 student——其余来源不可构造本类型
    turn_id: int                         # 学生哪一轮(对本轮消息的判定)
    answer_type: Literal[                # 判定所用窄面(见 §三)
        "numeric_with_unit",            # 数值+单位("25.8度","7/36","0.5m")
        "choice_letter",                # 选项字母("A","C")
        "true_false",                   # 判断("对","错","√")
        "equation_form",                # 方程/算式形态("x-21=35")
        "ratio_or_expression",          # 比例/表达式("12:4=6:2","3/4")
        "short_text_exact",             # 短文本标准答案("易变形";多槽复合如"鸡3只兔5只"不属本窄面)
    ]
    verdict: Literal["matched"]          # 窄面内确定性匹配成立
    verifier: str                        # 哪个窄面 verifier 判的(可追溯)
    provenance: {
        ground_truth_ref: str            # 指向题库 answer/answer schema(非病例短语)
        matched_span: str                # 学生消息中命中的原文片段(审计凭证)
        normalization: list[str]         # 施加的归一化(如千分位/分数形态)——空=原样
    }
```

**不可构造面(设计红线)**:LLM 输出无构造权;summary 无构造权;guard 事件无构造权;教师转述的学生话无构造权(必须本人在本轮)。

**Evidence 生命周期(v1 显式设计选择)**:**turn-scoped / ephemeral**——evidence 只对当前 student turn 生成、跨轮不复用。

**verified 后同轮终局(防"答过还得再答"——二审 P0-2)**:一旦本轮 evidence 成立,该 student turn 内完成终局(承认+可选非交互式解释+finish);**不再开启下一轮提问**——否则学生不重复终答时 Gate 又无证据,重造"已答过还得再答"。跨轮深化若未来需要=evidence 转为 problem-scoped sticky+invalidate/reset 机制,**第一版明确不做**(防机制偷偷长出)。

## 三、确定性窄面(领域层,小学数学第一批)

覆盖设计依据:题库 263 题 answer 形态实测分布(2026-09-24 修订:PR #418 可复现普查为正本):

| 窄面 | 覆盖形态(实测占比) | 判定逻辑(确定性) |
|---|---|---|
| numeric_with_unit | 纯数值 33.1%(87) | 数值抽取+等价类归一(千分位/分数/小数/百分号——**等价类资产独立抽取为领域侧 normalizer/spec,产品层零 import eval/judge 依赖;评测亦不用与产品完全相同的 verifier 验产品,防 common-mode false green**)。**单位省略仅当题目 schema 显式声明 optional;同义单位须维度安全的确定性转换,无默认容差** |
| choice_letter | 选择 4.9%(13) | 字母精确匹配(题面选项字母表为合法集) |
| true_false | 判断 0.0%(0)(类型来自 **answer schema/spec** 声明,非题面文字猜) | 对/错/√/× 映射 |
| equation_form | 方程算式 1.1%(3) | 符号归一(**×/·→独立乘法 token \`*\`,绝不与变量 x 合并**——ASCII x 在本题域是变量,合并=灾难性等价;＝→==)后字符串等价(sympy 第二版) |
| ratio_or_expression | 比例/表达式 | 同上归一族 |
| short_text_exact | 短文本 18.3%(48) | **normalized whole-answer exact/显式 alias match**:仅无语义归一(Unicode/全半角/空白/标点)+题库显式 alias;**不做编辑距离、不做裸 substring**("不是易变形"不得因包含"易变形"命中) |

**Precision-first claim matching(三审 P0-②,verifier 的输入语法收窄)**:

value_match(答案值出现)≠ claim(学生提交该答案)。"不是 6,我觉得是 5"/"A 不对,应该是 B"/"是不是 0.5?我还不确定"——**正确值出现但学生未声明它为自己的答案,不得发 CompletionEvidence**。第一版不造通用 answer_commitment engine(那会重新长成语义分类器),只把确定性 verifier 的**可接受输入语法收窄**:

- **可认证形态**(白名单):裸答案("6")/裸答案+单位("25.8度")/少量明确声明式("答案是 6","所以是 0.5m","应该是 x-21=35")——声明式模板是**有限枚举的句法模式**,不是语义理解;
- **不可认证形态**(一律不发 evidence,宁 needs_review):否定句/疑问句(含"是不是"探问)/不确定表达("还不确定","可能")/多候选/纠正语境(明确说"刚才的不对")/复杂自由文本——**无法确定性判定时保守拒绝**;
- 此边界在 Phase A boundary gold 里钉住(负例即上述形态)。

**明确不覆盖(第一版)**:多空/复合 42.6%(112)——**整体 needs_review,任何局部槽命中不得构造 CompletionEvidence**(未来若需部分进度,另建 ProgressEvidence,不偷"半完成态");开放式题(无可靠 verifier)——**宁可 needs_review,不让 8B 猜完成态**(终裁原话)。**57.4%(151/263)为 answer-key 形态可判上限(eligibility upper bound)**,非运行时完成覆盖率。实测口径(2026-09-24 修订,PR #418 为可复现正本):263 题形态普查=纯数值 87/选择 13/判断 0/方程 3/短文本 48/复合 112,互斥分类规则不变(数值含单位>选择字母>判断>方程算式>短文本≤12字>复合);一条命令复现:`uv run python scripts/answer_census.py`(题库指纹 sha256-16=3e2fc480f30f526f;7 条裁定点见 #418 对账节)。**初版普查的 ~67% 口径未随数字落档、不可复现,已被本可复现口径取代**(分布差异主因:量词入数值面/短文本排除多槽/多方程归复合,详见 #418)。**Phase A verifier 接 Kernel 前须独立 boundary gold 集**(各窄面正/负边界案,与 32 案 regression corpus 分立)。

## 四、Kernel 消费契约(transition authority)

```
state == "ready_to_confirm" 时:
    if exists(trusted CompletionEvidence for 本轮学生消息):
        → 允许 completed 迁移(finish 路径照旧——收束话术仍由模型生成)
    else:
        → completed 迁移被拒(不变量硬门,类似 answer_leak 的 fail-closed)
        → session 保持 ready_to_confirm(教师可继续引导——生成层不知道门的存在)
```

- summary 语义收紧(已由 PR-0 原子性+本件):summary **不具 transition authority**——但 **Gate 不保证 summary 文本不代说答案**:5106 型文本代说仍由既有 answer_leak/summary policy 独立守门+独立测试,功劳不归 Gate;
- **负向三案冻结为 invariant regression**:2791/5106/3490(学生未落终答而 completed)在新架构下必须 needs_review——这是 §六验收硬门;
- 正向反向镜像的另一头由 §五 解。

## 五、Generation 消费契约(只读,无写权限)

```
verified_complete = exists(CompletionEvidence):  # generation 只读
    if True:  Tutor 同轮终局(见 §二 verified 后终局)——期望形态是不再就答案槽询问
    if False: Tutor 不得 terminal close(硬门在 Kernel,但 prompt 侧给同一信号)
```

**两向的不对称保证(二审 P0-3 降格表述)**:
- **负向(premature completion)= Kernel 结构硬门**(无 evidence 迁移被拒——确定性,模型不可绕);
- **正向(no-reask)= trusted-signal-assisted generation**——把"是否完成"的判别拿出模型,但"拿到 true 后不再确认性重问"**仍是模型行为,模型理论上可不听**;效果须 fresh holdout 验证,**不称结构性禁止**(除非未来做 verified-close 不可提问分支——第一版不做)。

- 这解决 confirmation 正向门的"承认后确认性重问":不是再给 prompt 加"别确认"的词,而是**把 verified 状态作为轮级结构化只读事实注入**(如 `verified_complete=true, evidence_turn_id=N`)——**不把 canonical answer X 额外塞给模型**(模型已有学生原文,塞答案=引入新 answer-leak 面);模型不再需要自己判"学生给没给终答"(它判不稳的那个任务被移走了),只需消费一个已验证的布尔;
- prompt 变化面:极小(轮级注入 `verified_complete=true, evidence_turn_id=N` 结构化事实或未注入——**不塞 canonical answer**,学生原文模型已有)——这与终裁"不追词"不冲突:这不是用词去教模型判状态,是把判状态的**结果**给它。

## 六、验收设计(fresh confirmation 前置)

1. **不变量回归**:负向三案(2791/5106/3490)+ confirmation 全 24 案+ablation 8 案(共 32 案=终裁的 regression corpus)在新架构上重放:正向案的 completed 不劣化、负向案 completed 必须消失、5106 的 summary 代说必须消失;
2. 正向四案(2322/2960/3695/3138,学生终答在 t2 而 said 置位)作为"Gate 正确放行"锚;
3. 之后才开 fresh holdout(终裁执行链⑦:baseline 系统 vs baseline prompt+Gate)。

## 七、#252 seam 抽取(前置已定位)

本设计触碰面:signals(完成判定纯判断→CompletionEvidence 产出)→state transition(Kernel 消费)→generation(只读消费)——**恰好落在 #252 原设计的 signals 纯边界**:判定逻辑(窄面 verifier)不写 session 状态,写权限留 kernel。实现期按此 seam 抽,不扩到五模块。

## 八、明确不做(YAGNI 清单)

- 不做运行时 LLM verifier(终裁⑥,第一版禁);
- 不做 sympy 符号等价(第二版再看);
- 不做多空/复合题逐槽(第二版);
- 不扩病例短语表(终裁红线);
- 不动 trusted ladder/answer_leak 既有不变量(正交,共存);
- 不改 judge 面(Gate 是产品层事实,与评测判分独立)。

## 九、实现拆分(三段,审查裁定)

- **A)CompletionEvidence + 确定性窄面 verifier(~250 行)——零行为变化**(纯新增数据结构+判定函数,不接线):等价类资产独立抽取为领域 normalizer,产品零 import eval/judge;
- **B)Kernel transition gate(~20 行)**:completed 迁移硬门+负向三案 invariant regression 冻结;
- **C)generation 只读消费+32 案全量 regression 重放**(~30 行+重放脚本)。
- 三段独立 PR 独立验收——**回归出问题时可分清是 verifier/状态迁移/生成消费哪层错**(证据纪律)。

## 待审问题裁定记录(架构师 2026-09-23,#414 审查)

1. short_text:**仅无语义归一(Unicode/全半角/空白/标点)+ whole-answer exact/题库显式 alias;不做编辑距离,不做裸 substring**——已落 §三;
2. 复合题:**整体 needs_review;局部匹配不产生 CompletionEvidence**(未来部分进度=另建 ProgressEvidence)——已落 §三;
3. verified_complete:**轮级注入,结构化只读事实(verified_complete=true, evidence_turn_id=N),不塞 canonical answer**——已落 §五。

## 审查 7 项 blocking 修订对照(全部已落)

①×/·→独立乘法 token,绝不与变量 x 合并(§三 equation_form);
②复合题口径统一:局部槽命中不得构造 evidence;67% 改称 eligibility upper bound(§三);
③单位省略仅 schema 显式授权 optional;同义单位须维度安全确定性转换,无默认容差(§三 numeric);
④short_text=normalized whole-answer exact/alias,无编辑距离无裸 substring;多槽样例移出(§三);
⑤summary 表述改"不具 transition authority";文本代说由 answer_leak/summary policy 独立守门独立测试,功劳不归 Gate(§四);
⑥等价类资产独立抽取为领域 normalizer/spec,产品零 import eval/judge;评测不用与产品同 verifier 验产品防 common-mode false green(§三);
⑦Evidence 生命周期钉死:turn-scoped/ephemeral,显式设计选择(§二)。

## 二审 6 项修订对照(2026-09-23,v2→v3)

**P0**:①iff→必要授权+fail-closed,非全局充分,不是状态跳转器(§一);②turn-scoped 与深化冲突→**verified 后同轮终局**,跨轮深化=sticky 机制第一版明确不做(§二);③正向门降格=trusted-signal-assisted generation 须 holdout 验证,非结构性禁止;负向才是 Kernel 硬门(§五不对称保证)。
**P1**:①"已给出并验证答案 X"残留删除,只留结构化事实(§五);②true_false 类型来自 schema 非题面猜(§三);③67% 附实测口径(263 分母/互斥规则/脚本 fingerprint)+Phase A 独立 boundary gold(§三)。

## 三审修订对照(2026-09-23,v3→v3.1,马尾辫自审后 2 blocking)

- **P0-①正文 iff 真修**:前版修订对照表已记但正文 replace 未命中(「一条」二字失配)——审查者抓的正文与对照表自相矛盾即此;现 §一 已改为「必要授权+fail-closed+不自行触发迁移」;
- **P0-② precision-first claim matching**:§三 新增专节——value_match≠claim;可认证形态白名单(裸答案/答案+单位/有限枚举声明式模板)/不可认证保守拒绝(否定/疑问/不确定/多候选/纠正语境);不造 commitment engine;boundary gold 钉边界;
- 其余 P1(problem_id digest/schema 来源/census 映射/标点白名单/验收组件归因)按三审降级为实现建议或 A 段事项,不阻塞设计件。

## 数字修订对照(2026-09-24,PR #418)

- §三 分布表与可判上限改为可复现正本(87/13/0/3/48/112,151/263=57.4%,fingerprint 3e2fc480f30f526f):初版普查(~67%)口径未随数字落档、不可复现——「数字没有可复现的锚」即本教训,现以 scripts/answer_census.py 一条命令复现为正本;互斥分类规则与窄面判定逻辑零变化。
