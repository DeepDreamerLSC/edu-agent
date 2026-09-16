# Promotion Comparison Protocol (⑦门 Phase B)

**定位**：机械比较器，接收 Teacher 盲评结果（Phase A），与 baseline / expectation 对比，输出 regression 判定。

**核心原则**：Phase B 是纯程序 / 人工表格操作，不引入新判断。Teacher 的独立评分已在 Phase A 完成。

---

## 输入

- Teacher 评分（Phase A 输出）：`math_integrity` / `student_mastery` / `paraphrase_fidelity`，每个 0|1|2
- Baseline（来自 `slice-baseline.jsonl`）：当前系统在 9551d149 纪元的双跑读数
- Expectation（来自 `slice-cases.jsonl` 的 `expectation` 字段）：本案例的"正确答案"

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

---

## 输出

```json
{
  "case_id": "...",
  "family": "math_integrity" | "student_mastery" | "paraphrase_fidelity",
  "baseline_score": 0 | 1 | 2,
  "expectation_score": 0 | 1 | 2,
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
