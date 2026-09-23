# Trusted Completion Gate 设计件 v1:CompletionEvidence 最小不变量(执行链②,纯设计不写代码)

状态:草案待审(2026-09-23,PM 拟;呈用户+架构师)。依据:步骤7 结案终裁执行链②③④⑤⑥。
前置已闭:步骤7 Prompt hypothesis 关闭(#382 终裁);负向三案(2791/5106/3490)已实证不变量必要。

## 一、核心不变量(一句话)

> **session 迁移到 completed 当且仅当存在一条 trusted CompletionEvidence;Tutor 文本、summary、guard fallback、任何模型输出都不能创造这个事实——它只能来源于学生本轮消息经确定性 verifier 判定。**

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

**Evidence 生命周期(v1 显式设计选择)**:**turn-scoped / ephemeral**——evidence 只对当前 student turn 生成、当轮消费、跨轮不复用(上一轮已验证的答案在下一轮确认时不构成证据,该轮需重新命中)。保守口径,显式非隐含。

## 三、确定性窄面(领域层,小学数学第一批)

覆盖设计依据:题库 263 题 answer 形态实测分布(2026-09-23 普查):

| 窄面 | 覆盖形态(实测占比) | 判定逻辑(确定性) |
|---|---|---|
| numeric_with_unit | 纯数值 17% | 数值抽取+等价类归一(千分位/分数/小数/百分号——**等价类资产独立抽取为领域侧 normalizer/spec,产品层零 import eval/judge 依赖;评测亦不用与产品完全相同的 verifier 验产品,防 common-mode false green**)。**单位省略仅当题目 schema 显式声明 optional;同义单位须维度安全的确定性转换,无默认容差** |
| choice_letter | 选择 4% | 字母精确匹配(题面选项字母表为合法集) |
| true_false | 判断(题面含"判断"字样) | 对/错/√/× 映射 |
| equation_form | 方程算式 4% | 符号归一(**×/·→独立乘法 token \`*\`,绝不与变量 x 合并**——ASCII x 在本题域是变量,合并=灾难性等价;＝→==)后字符串等价(sympy 第二版) |
| ratio_or_expression | 比例/表达式 | 同上归一族 |
| short_text_exact | 短文本 39% | **normalized whole-answer exact/显式 alias match**:仅无语义归一(Unicode/全半角/空白/标点)+题库显式 alias;**不做编辑距离、不做裸 substring**("不是易变形"不得因包含"易变形"命中) |

**明确不覆盖(第一版)**:多空/复合 33%——**整体 needs_review,任何局部槽命中不得构造 CompletionEvidence**(未来若需部分进度,另建 ProgressEvidence,不偷"半完成态");开放式题(无可靠 verifier)——**宁可 needs_review,不让 8B 猜完成态**(终裁原话)。~67% 为 **answer-key 形态可判上限(eligibility upper bound)**,非运行时完成覆盖率。

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
    if True:  Tutor 可承认/简短深化/收束——**不得再把目标答案槽位当未知询问**
              (确认性重问"是不是52?"被结构性禁止——答案槽已 verified,再问=重问已给内容)
    if False: Tutor 不得 terminal close(硬门在 Kernel,但 prompt 侧给同一信号)
```

- 这解决 confirmation 正向门的"承认后确认性重问":不是再给 prompt 加"别确认"的词,而是**把 verified 状态作为轮级结构化只读事实注入**(如 `verified_complete=true, evidence_turn_id=N`)——**不把 canonical answer X 额外塞给模型**(模型已有学生原文,塞答案=引入新 answer-leak 面);模型不再需要自己判"学生给没给终答"(它判不稳的那个任务被移走了),只需消费一个已验证的布尔;
- prompt 变化面:极小(一处条件注入"学生已给出并验证答案 X"或未注入)——这与终裁"不追词"不冲突:这不是用词去教模型判状态,是把判状态的**结果**给它。

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
