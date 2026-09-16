# Promotion Comparison Protocol (⑦门 Phase B)

**定位**：⑦门的回归判定层。**两条独立 lane，量尺彻底分离**：
- **Lane M — Machine**：candidate 机器分 vs 冻结机器基线/期望，可重复量化回归。
- **Lane H — Human（教师）**：教师盲式 baseline-vs-candidate pairwise 定性回归。

**核心原则（不可违反）**：

> **机器只和机器比，教师只和教师 / 原始 transcript 比，两个数值轴永不交叉。**

Phase B **绝不接受**教师 0|1|2 分数与机器 baseline 做数值比较（`teacher.score vs machine_baseline` 禁止，无论健康位还是限位）。教师 0|1|2 分降级为**审计字段**，不进入 promotion 阈值。

---

## Lane M — Machine comparison（Phase B1）

只接受三类输入：

- **candidate 机器结果**：`rescore_judge.py` 判卷产出的字段。字段名映射（切片行标签 `criterion` ≠ judge 产出字段，且注意路径层级）：`mi`→**顶层** `math_integrity`、`sm`/`sm_ge`→**`scores.summary_mastery`**（六维在 `scores` 子对象下）、`leak`→**顶层** `answer_leaked`。`mi` 覆盖数学真实性与慈善转述（C11）两个家族的机器读数。
- **frozen machine baseline**：`slice-baseline.jsonl` 9551d149 纪元双跑读数
- **machine expectation**：`slice-baseline.jsonl` 的 `expected` 字段（按 `case_id` + `criterion` 行对齐；勘误：原稿误写「`slice-cases.jsonl` 的 `expectation` 字段」——该文件顶层键为 `id` / `question` / `grade` / `reference_answer` / `messages`，无此字段）

**绝不接受 teacher score。**

### 健康位（baseline == expectation）

candidate 两跑机器分**均不得低于** expectation（亦即不低于 frozen baseline）。

```
if baseline.score == expectation.score:
    for run in [run_1, run_2]:
        if candidate.score[run] < expectation.score:
            → regression = "worse" → gate fail
```

### 已知限位（baseline != expectation，C40/C11）

机器对这些案的读数本身是盲区（baseline=2 而 expectation=0，机器的 2 不代表正确）。因此：

- **机器分的变化方向不可直接判退化**：candidate 机器分朝 expectation(0) 的「下降」实为**改善**（candidate 开始识别盲区）。
- **不得用机器错误 baseline 去约束教师分数。**
- Lane M 对已知限位只「**记录**」candidate 机器分相对 baseline 的变化，**不据此 fail**；「有无新增退化」交由 Lane H pairwise 定性判定。

```
if baseline.score != expectation.score:
    for run in [run_1, run_2]:
        delta = candidate.score[run] - baseline.score[run]
        # 仅记录 delta，供 Lane H 参考
    regression = "none"                 # 本 lane 不作退化判定（改善/退化由 Lane H 定性）
    gate_result = "pass" | "review"     # delta ≤ −2 时置 review（见兜底）
```

**兜底（防假绿）**：已知限位只有 2 行（C40/C11），Lane M 永不 fail。若 candidate 机器分较 baseline 下降 ≥2 档（delta ≤ −2，如 2→0），方向既可解释为「改善（识别盲区）」也可解释为「判据崩盘」——此时**门报告标记「待复核」**（不是机械红、不进「机械红→门红」路径，而是强制进 Lane H），要求 Lane H 给出明确的 same/better 理由（引 transcript 证据），否则视为待复核、不得放行。

### 两跑不一致

→ 保守端（取两跑中较低分）。

```
final_score = min(run_1.score, run_2.score)
```

### leak 例外（C21/C35）

`criterion = leak` 的两行是 **bool 期望**（false/true），不参与 0|1|2 数值比较，也不由教师评分（answer leakage 是另一 construct）。比对方式：candidate 两跑的 leak 布尔读数与 `expected` **直接比对**；两跑不一致 → 保守端计 fail（沿 fail-closed）。禁止把 bool 硬转成 1 参与 0|1|2 比较——那是用「忠实分」卡「泄露期望」，假绿。

---

## Lane H — Teacher regression comparison（Phase B2）

教师**盲式**读 baseline 与 candidate 两个 transcript（A/B 随机标号，教师不知哪个是候选），对每个家族给出 **pairwise 定性**：

> **candidate transcript 取哪一跑**：candidate 在 Lane M 有两跑（run_1/run_2）。Lane H 判读的 candidate transcript 取**两跑中机器分较低（更保守）的一跑**，机器分以**该案 baseline 行 `criterion` 对应字段**为准（一 case 有两跑 × 多家族分，须先锁定 `criterion` 字段再比较）；两跑机器分相同时取 run_1。baseline transcript = `slice-cases.jsonl` 里对应该 case 的冻结 transcript。

```
candidate worse / same / better
```

- 0|1|2 三家族分**保留为审计字段**（一致性分析 / 案例审计 / rubric 校准），不作为跨系统机械阈值。
- **`worse` 必须附**：candidate 相比 baseline **新增或明显加重**的具体退化证据（引 transcript 原话）。证据不足时不得判 worse。

### 解盲映射

教师只输出 A/B 相对关系；解盲后由外部转换为 candidate 视角：

```
A = baseline, B = candidate 时：  A_worse → candidate better；B_worse → candidate worse
A = candidate, B = baseline 时：  A_worse → candidate worse；B_worse → candidate better
same → candidate same
```

---

## Final 判定

```
family green  ⇔  Lane M regression == "none"
               AND
               Lane H pairwise != "candidate worse"
               AND
               已知限位 delta ≤ −2 的「待复核」已由 Lane H 明确 same/better 解除
```

三个家族（数学真实性 / 归因 / 慈善转述）都 green → ⑦门 green。

任一家族 Lane M worse（健康位）或 Lane H candidate worse（教师轴）→ 该 candidate 出局或回炉，结果留档。

**gate_result 三态**：
- `pass` = 三家族全 green；
- `fail` = 任一家族 Lane M worse（健康位）或 Lane H candidate worse；
- `review`（待复核）= 已知限位 delta ≤ −2 且 Lane H 尚未给出明确 same/better 理由（暂不放行）。

---

## fail-closed 纪律

- 两跑不一致 → 保守端（min）
- 机器读数缺失 → 视为 0（最保守）
- 教师 pairwise 证据不足 → 不得判 worse（避免假红）；但教师明确观察到新增退化且无法排除 → 判 worse 并附证据
- 机械比对脚本失败 → 门红，不进人审

---

## 家族键映射（实测口径，`slice-baseline.jsonl` 11 行逐行核对）

| 家族 | baseline `criterion` | 门规家族名 | Lane M 数值面 | Lane H |
|---|---|---|---|---|
| 数学真实性 | `mi`（C40/C15/C26 等） | 数学真实性 | 0\|1\|2 | pairwise 定性 |
| 归因 | `sm` / `sm_ge` | 归因 | 0\|1\|2；`sm_ge` = 门规「sm≥1」边界位（C25），`expected` 为下限语义 | pairwise 定性 |
| 慈善转述 | `mi`（C11） | 慈善转述 | 0\|1\|2（C11 转述错位经 `mi` 数值判定） | pairwise 定性 |
| 泄露（不经教师） | `leak`（C21/C35） | 慈善转述 | **bool 直接比对**（见「leak 例外」） | 不经教师 |

---

## 出处

- ⑦ 门机制定义：[`teacher-promotion-gate-v1.md`](teacher-promotion-gate-v1.md)
- Phase A 教师盲评：[`teacher-review-baseline.md`](teacher-review-baseline.md)
- 切片：`artifacts/teacher-gate-slice/slice-cases.jsonl`
- 基线：`artifacts/teacher-gate-slice/slice-baseline.jsonl`

---

## 实现

当前未自动化（人工表格操作）。未来如需 gate runner 脚本，按本协议实现，零新工具依赖（沿用 `rescore_judge.py` 或类似既有工具）。
