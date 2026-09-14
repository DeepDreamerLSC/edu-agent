# gepa-prereqs-trial 工件口径(#238 件 A + 件 B 验收小样)

**不是评测轮**:6 case 小样试跑,只为验收两件事的机器证据,不进任何对照基线。

- **件 A**:collect run 目录 manifest 出现 `identity` 三件套
  (git_sha = 跑批 commit / prompts_sha256 = prompting.py / models_sha256 = models.yaml)
- **件 B**:run 目录落 `facts.jsonl`(model_call 全轮 36 行 = tutor 30 + judge 6);
  report.md 出现「三口径 × 四指标」段(口径注记在段内)

复算两条路(#257 审 P3-2 起分开):

**真模型重跑**(切片语料在本目录,起端点):

```bash
sh scripts/corpus_round.sh \
  --corpus edu_agent/evals/artifacts/gepa-prereqs-trial/gepa-trial-b2.json \
  --corpus edu_agent/evals/artifacts/gepa-prereqs-trial/gepa-trial-pilot.json \
  --out <新目录> --concurrency 2
```

**离线重渲染**(零模型调用,只吃本目录落盘件;Mac 纪律:优先重渲染):

```bash
uv run python -m edu_agent.evals.corpus_round \
  --render-from edu_agent/evals/artifacts/gepa-prereqs-trial
```

重渲染会重写本目录 report.md(生成时间戳行随之更新,其余段应逐字一致)。

读数注意:本跑零 fallback(VL 主选/mlx judge 全程健康)→ primary-only 与
with-fallback 两行同值,这正是干净态的期望形态;非零 fallback 轮里两行会分开。
false-confirm 1/1 是代理口径的首个实测样本(该 case 学生未报期望数字,
口径盲区见 report 段内注记)。
