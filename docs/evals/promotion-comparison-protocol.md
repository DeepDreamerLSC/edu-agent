# Promotion Comparison Protocol (⑦门 Phase B)

**定位**：机械比较器，接收 Teacher 盲评结果（Phase A），与 baseline / expectation 对比，输出 regression 判定。

**核心原则**：Phase B 是纯程序 / 人工表格操作，不引入新判断。Teacher 的独立评分已在 Phase A 完成。

---

## 输入

- Teacher 评分（Phase A 输出）：`math_integrity` / `student_mastery` / `paraphrase_fidelity`，每个 0|1|2
- Baseline（来自 `slice-baseline.jsonl`）：当前系统在 9551d149 纪元的双跑读数
- Expectation（来自 `slice-baseline.jsonl` 的 `expected` 字段，按 `case_id` + `criterion` 行对齐）：本案例的期望真值（勘误：原稿误写「`slice-cases.jsonl` 的 `expectation` 字段」——该文件顶层键为 `id` / `question` / `grade` / `reference_answer` / `messages`，无此字段）
- leak 读数（仅 `criterion = leak` 两行，门规表 C21/C35）：candidate 两跑的现行判据 leak 读数（**bool**），不经 Phase A——Phase A 把 answer leakage 排除在教师范围外（另一 construct，见 `teacher-review-baseline.md`「与 Judge 的边界」）

---

## 机械规则

### 健康位（baseline == expectation）

candidate 两跑教师评分**均不得低于** expectation。

```
if baseline.score == expectation.score:
    for run in [run_1, run_2]:
        if teacher.score[run] < expectation.score:
            → regression = "worse"
            → promotion gate fail
```

### 已知限位（baseline != expectation）

candidate 两跑**均不得劣于** baseline。改善可以记录，但不是必须。

```
if baseline.score != expectation.score:
    for run in [run_1, run_2]:
        if teacher.score[run] < baseline.score:
            → regression = "worse"
            → promotion gate fail
        elif teacher.score[run] > baseline.score:
            → regression = "better" (记录但不构成必须)
```

### 两跑教师判断不一致

→ 保守端（取两跑中较低分）。

```
final_score = min(run_1.score, run_2.score)
```

### leak 例外（C21/C35）

`criterion = leak` 的两行是 **bool 期望**（false/true），不参与 0|1|2 数值比较，也不由 Phase A 评分（answer leakage 是另一 construct，Phase A 明确排除）。比对方式：candidate 两跑的 leak 布尔读数与 `expected` **直接比对**；两跑不一致 → 保守端计 fail（沿 fail-closed 纪律）。禁止把 bool 硬转成 1 参与 0|1|2 比较——那是用「忠实分」卡「泄露期望」，假绿。

---

## 输出

```json
{
  "case_id": "...",
  "family": "math_integrity" | "student_mastery" | "paraphrase_fidelity",
  "baseline_score": 0 | 1 | 2,
  "expectation_score": 0 | 1 | 2,   # leak 家族例外（C21/C35）：bool（false/true），不参与数值比较
  "teacher_run_1": 0 | 1 | 2,
  "teacher_run_2": 0 | 1 | 2,
  "final_score": 0 | 1 | 2,
  "regression": "none" | "worse" | "better",
  "gate_result": "pass" | "fail"
}
```

---

## Promotion 判定

任何家族触发 regression = "worse" → promotion gate 不通过。

全部家族 regression = "none" 或 "better" → promotion 许可（合并键仍属人）。

---

## fail-closed 纪律

- 两跑不一致 → 保守端
- 教师评分缺失 → 视为 0（最保守）
- 机械比对脚本失败 → 门红，不进人审

---

## 出处

- ⑦ 门机制定义：[`teacher-promotion-gate-v1.md`](teacher-promotion-gate-v1.md)
- Phase A Teacher 盲评：[`teacher-review-baseline.md`](teacher-review-baseline.md)
- 切片：`artifacts/teacher-gate-slice/slice-cases.jsonl`
- 基线：`artifacts/teacher-gate-slice/slice-baseline.jsonl`

---

## 实现

当前未自动化（人工表格操作）。未来如需 gate runner 脚本，按本协议实现，零新工具依赖（沿用 `rescore_judge.py` 或类似既有工具）。

---

## 家族键映射（实测口径，`slice-baseline.jsonl` 11 行逐行核对）

| Phase A 家族键 | baseline `criterion` | 门规家族名 | 数值面 |
|---|---|---|---|
| `math_integrity` | `mi` | 数学真实性 | 0\|1\|2 |
| `student_mastery` | `sm` / `sm_ge` | 归因 | 0\|1\|2；`sm_ge` = 门规「sm≥1」边界位（C25），`expected` 为下限语义，Phase B「不得低于」规则天然覆盖 |
| `paraphrase_fidelity` | `mi`（C11） | 慈善转述 | 0\|1\|2（C11 转述错位经 `mi` 数值判定）；Phase A 的 `paraphrase_fidelity` 分数无基线机械对照，供教师抽审定性读 |
| —（不经 Phase A） | `leak`（C21/C35） | 慈善转述 | **bool 直接比对**（见「leak 例外」） |
