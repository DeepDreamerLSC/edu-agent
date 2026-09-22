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
        "short_text_exact",             # 短文本标准答案("易变形","鸡3只兔5只")
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

## 三、确定性窄面(领域层,小学数学第一批)

覆盖设计依据:题库 263 题 answer 形态实测分布(2026-09-23 普查):

| 窄面 | 覆盖形态(实测占比) | 判定逻辑(确定性) |
|---|---|---|
| numeric_with_unit | 纯数值 17% + 复合中的数值槽 | 数值抽取+等价类归一(千分位/分数/小数/百分号——**复用 ER judge v2 的 answer_keys 等价类**)+单位容差(可省/同义) |
| choice_letter | 选择 4% | 字母精确匹配(题面选项字母表为合法集) |
| true_false | 判断(题面含"判断"字样) | 对/错/√/× 映射 |
| equation_form | 方程算式 4% | 符号归一(×=x,＝==)后字符串等价或 sympy 级等价(**第一版字符串+归一,sympy 留第二版**) |
| ratio_or_expression | 比例/表达式 | 同上归一族 |
| short_text_exact | 短文本 39% | 题库 answer 原文匹配+**题目自带合法别名集**(题库若注 aliases;无别名则精确) |

**明确不覆盖(第一版)**:多空/复合 33%(多槽位——第二版逐槽拆);开放式题(无可靠 verifier)——**宁可 needs_review,不让 8B 猜完成态**(终裁原话)。第一版理论覆盖 ≈67%(104+45+13+12+比例类),复合题的数值槽可用 numeric 窄面部分覆盖,实际待试。

## 四、Kernel 消费契约(transition authority)

```
state == "ready_to_confirm" 时:
    if exists(trusted CompletionEvidence for 本轮学生消息):
        → 允许 completed 迁移(finish 路径照旧——收束话术仍由模型生成)
    else:
        → completed 迁移被拒(不变量硬门,类似 answer_leak 的 fail-closed)
        → session 保持 ready_to_confirm(教师可继续引导——生成层不知道门的存在)
```

- summary 语义收紧(已由 PR-0 原子性+本件):summary **只描述既有状态**——5106 型"summary 代说结论"在数据流上不可能再发生(summary 读状态,不写 completion evidence);
- **负向三案冻结为 invariant regression**:2791/5106/3490(学生未落终答而 completed)在新架构下必须 needs_review——这是 §六验收硬门;
- 正向反向镜像的另一头由 §五 解。

## 五、Generation 消费契约(只读,无写权限)

```
verified_complete = exists(CompletionEvidence):  # generation 只读
    if True:  Tutor 可承认/简短深化/收束——**不得再把目标答案槽位当未知询问**
              (确认性重问"是不是52?"被结构性禁止——答案槽已 verified,再问=重问已给内容)
    if False: Tutor 不得 terminal close(硬门在 Kernel,但 prompt 侧给同一信号)
```

- 这解决 confirmation 正向门的"承认后确认性重问":不是再给 prompt 加"别确认"的词,而是**把 verified 状态作为输入信号喂给生成**——模型不再需要自己判"学生给没给终答"(它判不稳的那个任务被移走了),只需要消费一个已验证的布尔;
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

## 九、实现规模预估(供审后排期)

- 领域层窄面 verifier:~200-300 行(六窄面+归一复用);
- Kernel 消费:~20 行(一个硬门检查);
- generation 消费:~10 行(只读信号注入);
- regression 电池:32 案重放脚本复用 confirmation 工程;
- 合计 <400 行,单 PR 可承载(或领域层/Kernel 各一)。

## 待审问题(呈架构师/用户)

1. short_text_exact 的匹配边界:精确匹配 vs 轻度容错(标点/全半角)——建议第一版仅标点+全半角归一,不引入编辑距离;
2. 复合题的**部分覆盖**策略:第一版遇到复合题是整体 needs_review,还是数值槽部分匹配给部分 credit?建议:整体 needs_review(保守,避免"半完成"新状态);
3. verified_complete 信号注入 prompt 的位置:系统级还是轮级?建议轮级(随 verified 事实出现,教师当轮可见)。
