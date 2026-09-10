# teaching-arc-v1 工件索引(#101 双臂评测)

口径与判定规则见 `docs/evals/teaching-arc-eval-v1.md`(pre-registration,开跑前冻结);
结果与对照表见 `docs/evals/teaching-arc-eval-v1-report.md`。

| 路径 | 内容 |
|---|---|
| `manifest-M.json` / `manifest-A.json` | 两臂 worktree、git sha、models.yaml sha256、tutor 模型 |
| `P/<臂>/cases.jsonl` | 口径 P 的 22 份输入(11 场景 × 2 重复) |
| `P/<臂>/collect/<run>/results/*.json` | transcript(EvalRunner 原始落盘,含 turns/summary/final_state) |
| `P/<臂>/judge-cases/*.json` | 盲判输入(内容不含臂标记;臂只出现在目录名) |
| `P/<臂>/judge-scores/*.json` | judge 四指标判定 + 证据 + judge_model |
| `F/…` | 口径 F,同构 |
| `metrics.json` | 四指标逐臂率、r1/r2、min–max、两重复分歧检测 |
| `feeding-corpus.jsonl` | 确定性代喂语料(方法名词表 + 答案数字) |
| `report.md` | 本次报告全文(= docs 里那份) |
| `two-path-comparison.md` | 两条修复路径的数据对照表(报告 §5) |

臂标签:`M` = origin/main(`acb5b89`),`A` = main + merge `tune/teaching-arc`(`0902a76`)。
口径:`P` = 现状 gate 口径(answer_status 照 `tuning_round.build_cases` 现状),
`F` = 生产同构(剧本语义复原 answer_status,唯一能触发五步弧线的口径)。
