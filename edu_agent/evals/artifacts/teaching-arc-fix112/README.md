# teaching-arc-fix112 工件说明(#112 before/after 帧)

本目录为 issue #112(incorrect 弧线「答对后学生复讲」确定性触发 + 复读循环)的 before/after 证据工件。
报告正文:`docs/evals/teaching-arc-fix112-report.md`。冻结的 #143 工件(`teaching-arc-v1/`)**未改写**。

## 帧

| 帧 | 含义 | 内核 | prompt 层 |
|---|---|---|---|
| `before/` | 修复前基线 | `main 6b69a4e` 的 `kernel.py`(**逐字节相同**) | `main` 版 `prompting.py`(逐字节相同) |
| `after/` | 修复后 | `before` + #112 两提交(仅 `kernel.py`) | 同 before |

`manifest-{before,after}.json` 记录 `kernel_diff_vs_main_empty` / `prompting_diff_vs_main_empty`,
以及 git sha、`models.yaml` 哈希、tutor/judge 角色——**这两面旗是帧可比性的校验点**。

## 口径(每口径 2 重复,臂标签恒 M = 主干 prompt 层)

| 目录 | 口径 | 用例 | 说明 |
|---|---|---|---|
| `*/F/M/` | F | 22 | #143 冻结口径原样重跑(1 correct + 10 incorrect 场景) |
| `*/R/M/` | R | 20 | F 的 incorrect 场景各追加 S5「学生从头复讲」句 |
| `*/L/M/` | L | 4 | 复读探针:2 题 × 8 轮逐字重复同一句学生陈述 |
| `*/P/M/` | P | 22 | gate 现状 wiring(夜评 11 场景同源):10 条 None + 2 条 correct |

## 文件

| 路径 | 内容 |
|---|---|
| `<frame>/<口径>/M/cases.jsonl` | 该口径送入 runner 的用例(含 `answer_status`/`student_turns`) |
| `<frame>/<口径>/M/collect/<ts>/results/*.json` | 每例 transcript(`turns[].student/tutor/state/elapsed_ms`)、`summary`、`final_state`、`guard_events` |
| `<frame>/<口径>/M/judge-scores/*.json` | 盲判四指标逐条判定(judge id = sha256(base_id) 前 12 位 + 重复号) |
| `<frame>/metrics.json` | 四指标率(按口径/臂)+ 逐案明细 + 两重复分歧 |
| `<frame>/feeding-corpus.jsonl` | 确定性代喂语料(方法名词表 + 答案数字),含逐句与轮次 |
| `manifest-{frame}.json` | 帧溯源(见上) |

## 复现

见报告 §8。工具脚本(`arc_eval_fix112_frames.py` / `arc_eval_judge.py` / `arc_eval_metrics.py`)在评测分支,
`scripts/*.py` 属结构路径,不进本 PR。
