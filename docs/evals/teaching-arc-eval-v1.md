# 教学弧线四指标双臂评测 v1(#101) · pre-registration

> **本文档先于任何批跑写定**。四指标判定规则、两个口径、judge prompt/schema、盲判与升级规则
> 全部在开跑前冻结(#130 纪律:口径先写下来再跑,禁止看完数据再定规则)。
> 目的:**只交数据与对照表**,不下"可否合入/走哪条路径"的结论——裁定权在用户/PM。

## 1. 问题

PR #101(`tune/teaching-arc`)改写 `edu_agent/agents/small_lecturer/prompting.py` 的
`OPENING_HINT_CORRECT` / `OPENING_HINT_INCORRECT` 两个首问策略常量(教学弧线),并扩 R6 测试。
PR 自述残留:**复讲问句仍出现「假设法」**(教师侧解析含方法名,8B 两轮明令禁止仍代喂),
且注明"评测齐前不合入"。本评测回答:四指标上两臂差异如何、代喂语料长什么样。

## 2. 两臂定义(公平对照)

| 臂 | 工作树 | 代码状态 | SHA |
|---|---|---|---|
| **M(main 臂)** | `edu-w8-arc-eval-main` | `origin/main` 只读检出 | `acb5b89` |
| **A(弧线臂)** | `edu-w8-arc-eval` | `task/arc-eval` = `origin/main` + `merge origin/tune/teaching-arc` | `0902a76`(第一父 `acb5b89`) |

A 相对 M 的**全部**差异(逐字核对,无其他改动):

```
edu_agent/agents/small_lecturer/prompting.py | 27 +++++++++++++++++++++++----
tests/teaching/test_kernel_r6.py             | 10 ++++++++--
```

即:两臂差异只经 `prompting.opening_hint(answer_status)` 注入 tutor prompt;测试文件不参与运行时行为。
**未向 `tune/teaching-arc` 推送任何东西**(只 `fetch` + `merge` 到评测分支)。

其余全同:同一 `configs/models.yaml`、同一 tutor 模型、同一场景数据、同一 judge、
`RunnerConfig(concurrency=2)`、同一 11 场景。

## 3. 场景(11 条,固定)

来自 `scripts/tuning_round.py::build_cases()`(基线同款口径):

| # | case_id | 学生剧本首轮 | 语义起始 |
|---:|---|---|---|
| 1 | `small_lecturer_dialogue_scenarios_equation_complete_reasoning` | 「我先把等式两边都减去7…」 | **正确** |
| 2 | `…dialogue_stability_20_stability_chicken_rabbit` | 「我还不知道怎么同时算两种动物。」 | 错误 |
| 3 | `…dialogue_stability_20_stability_equation_subtract` | 「我还没有想清楚,能先给我一个方向吗?」 | 错误 |
| 4 | `…dialogue_stability_20_stability_fraction_addition` | 「我能不能直接把分子和分母分别相加?」 | 错误 |
| 5 | `…dialogue_stability_20_stability_triangle_area` | 「我先算10乘6等于60。」 | 错误 |
| 6 | `…dialogue_stability_20_stability_word_problem` | 「我把三个数直接加在一起。」 | 错误 |
| 7 | `…shadow_pilot_20_stability_chicken_rabbit` | (同 2) | 错误 |
| 8 | `…shadow_pilot_20_stability_equation_subtract` | (同 3) | 错误 |
| 9 | `…shadow_pilot_20_stability_fraction_addition` | (同 4) | 错误 |
| 10 | `…shadow_pilot_20_stability_triangle_area` | (同 5) | 错误 |
| 11 | `…shadow_pilot_20_stability_word_problem` | (同 6) | 错误 |

### 3.1 口径 P(现状 gate 口径 · 控制组)

`answer_status` **完全照 `build_cases()` 现状**:`word_problem` → `"correct"`,其余 9 条 → 不传(`None`)。
用于记录**现有 gate 实际测到了什么**。

### 3.2 口径 F(生产同构 · 测量组)

`answer_status` 按**剧本语义**复原(唯一依据是表 §3「语义起始」列 + 生产映射
`edu_agent/api/service.py:160`:`"answer_status": "correct" if answer_correct else "incorrect"`):
case 1 → `"correct"`;case 2–11 → `"incorrect"`。**其余一切不变**(同场景、同学生剧本、同模型、同 judge)。

> **开跑前已知的设计事实(确定性探查,不调模型,见 PR #101 评论 `5611822988`)**:
> 口径 P 下 **9/11 场景两臂送给 tutor 的首问 prompt 逐字节相同**(`opening_hint(None)` 返回空串),
> 仅 2 条 `word_problem` 有 hint;且 `answer_status="incorrect"` 的场景 **0 条**,
> 即 #101 的五步弧线在口径 P 下**从未被触发**。口径 F 是为消除这一盲区而设。
> 两个口径各自 11×2 重复×2 臂 = 44 份,合计 88 份。

## 4. 四指标定义(字段 → 规则)

**transcript 字段**(`KernelSubject.run_case` 返回):`turns[i] = {student, tutor, state, elapsed_ms}`,
其中 `turns[0].student == ""` 且 `turns[0].tutor` = **首问**;`summary` = 收尾总结;`final_state`;`learner`。

### 4.1 首问合规率 `first_question_ok`(二元,率 = ok / 适用数)

- **判定字段**:`turns[0].tutor`(只用首问这一轮)。
- **`answer_status == "correct"` 时**:`ok = 首问只问「还有没有不懂的地方」,且
  不出现复讲指令(「讲一遍」「复述」「说说你的思路」「你是怎么想的」),且不重新讲解本题、不评判对错`。
- **`answer_status == "incorrect"` 时**:`ok = 首问 = 友好开场 + 采集学生当前作答(问选项 / 问算出的答案),
  且不出现对错评判、不直接纠正`。
- **`answer_status is None` 时**:该指标**记 NA**(两臂 prompt 相同,无口径依据),不计入分子分母。
- 结果同时报 `ok 数 / 适用数` 与逐条 ok。

### 4.2 采集不评判率 `collect_not_judge_ok`(二元,**仅 INCORRECT 弧适用**)

- **判定字段**:`turns[0].tutor`(必要时含 `turns[1].tutor`,因"采集"可能跨首轮)。
- **适用** = `answer_status == "incorrect"`;其余记 NA。
- `ok = 教师采集到了学生的作答(问出选项/答案) **且** 全程未对该作答作对错判定
  (无「对/错/不对/正确/错误/应该/其实」类判定与纠正)`。
- 率 = ok / 适用数。

### 4.3 复讲达成率 `restate_ok`(二元,11 条全适用)

- **判定字段**:全部 `turns[*].tutor` + `summary`。
- `asked = 教师任一轮明确请学生复讲/讲解题思路`(「你讲一遍」「从头讲一遍」「说说你是怎么想的」等)。
- `delivered = 在 `asked` 之后存在学生复讲轮`(剧本轮 `turns[j].student`,j > asked 所在轮)`
  且 `教师未在学生讲之前代讲(不含方法名/答案数字)`。
- `ok = asked && delivered`。率 = ok / 11。

### 4.4 方法名代喂率 `feeding`(二元,11 条全适用)

- **判定字段**:全部 `turns[*].tutor` + `summary`(学生可见面;**不含**教师侧 prompt 里的解析)。
- 两条独立通路,**任一命中即 `fed = true`**:
  - **(a) 方法名词表命中**(确定性扫描,逐字匹配):
    `假设法 / 方程法 / 代入法 / 消元法 / 画图法 / 画线段图 / 列表法 / 枚举法 / 比例法 / 转化法 / 数形结合 / 移项 / 通分 / 约分 / 公式法 / 面积公式`
  - **(b) 答案数字代喂**(确定性扫描):该场景的 `reference_answer` 数值(或其关键中间数:
    由参考答案解析得出的数)出现在教师文本中,而**学生尚未说出该数**。
- 率 = fed / 11。
- **另出语料**(步骤 6):逐条抄录命中原句(`case_id / 臂 / 轮次 / 命中类型 / 原句`),不加工。

## 5. judge(单遍 + schema,同夜评口径)

- **模型**:`mlx_27b`(`configs/models.yaml` 的 `judge` 角色 primary),单遍,**不重复**。
- **盲判(p8)**:judge 的 system/user prompt **不含臂标签、分支名、commit、路径或任何标识**;
  judge-case 的 `id` 为不含臂名的稳定哈希;按臂分目录存放输入,但**送进模型的 JSON 内无标记**;
  每个 case 的两个臂分别在独立调用中评分(不并列比较)。
- **传入 judge 的内容**:`question`、`grade`、`answer_status`(口径值)、`messages`
  (由 `turns` 展开的 user/assistant 序列 + summary)。不含 `session_id`、不含工作树路径。
- **response_schema 原文**(与 `docs/evals/teaching-arc-eval-v1.md` 冻结版一致,一字不改):

```json
{
  "type": "object",
  "properties": {
    "first_question": {
      "type": "object",
      "properties": {
        "applicable": {"type": "boolean"},
        "compliant": {"type": "boolean"},
        "evidence": {"type": "string"}
      },
      "required": ["applicable", "compliant", "evidence"]
    },
    "collect_not_judge": {
      "type": "object",
      "properties": {
        "applicable": {"type": "boolean"},
        "compliant": {"type": "boolean"},
        "evidence": {"type": "string"}
      },
      "required": ["applicable", "compliant", "evidence"]
    },
    "restate": {
      "type": "object",
      "properties": {
        "asked": {"type": "boolean"},
        "delivered": {"type": "boolean"},
        "evidence": {"type": "string"}
      },
      "required": ["asked", "delivered", "evidence"]
    },
    "feeding": {
      "type": "object",
      "properties": {
        "fed": {"type": "boolean"},
        "quotes": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "string"}
      },
      "required": ["fed", "quotes", "evidence"]
    }
  },
  "required": ["first_question", "collect_not_judge", "restate", "feeding"]
}
```

- **阈值算术不托付模型**:率由本地按 §4 规则重算;judge 只提供逐条二元判定 + 证据。
  确定性通路(§4.4 词表/数字扫描)与 judge 判定**分别落盘、并列出**。

## 6. 升级规则(开跑前定死)

任一指标在**某场景**上两重复判定不一致(不同臂分别看) → **仅对该场景该臂补第三份**(口径 F 优先;
若口径 P 也分歧则一并补),其余不动。补跑的第三份**只增加分母**,不改判定规则、不挑样本。

## 7. 工件布局(冻结不重写)

```
edu_agent/evals/artifacts/teaching-arc-v1/
  manifest.json           # 两臂 SHA、models.yaml sha256、judge 模型、口径定义哈希
  P/cases.jsonl           # 口径 P 的 11×2 份输入
  P/collect/<run>/results/*.json   # transcript 原始落盘(EvalRunner)
  P/judge-cases/<arm>/*.jsonl      # 盲判输入(按臂分目录,内容无标记)
  P/judge-scores/<arm>/*.json      # judge 输出
  F/…                     # 口径 F,同构
  metrics.json            # 四指标逐臂率 + min-max + NA 计数
  feeding-corpus.jsonl    # 代喂原句语料
  two-path-comparison.md  # 护栏重生成 vs 解析脱敏 数据对照表
```

## 8. 本评测不做的事

- 不判"#101 可否合入"、不推荐修复路径——只交数据与对照表(裁定权在用户/PM)。
- 不改 `tune/teaching-arc`、不向它推送。
- 不因看到了数据而调整上述任一规则;规则变更须另开 v2 并注明触发原因。
