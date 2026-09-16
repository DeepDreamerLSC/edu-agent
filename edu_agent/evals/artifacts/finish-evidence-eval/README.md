# finish() 完成判定语义修订——最小真实内核验收(#用户裁 2026-09-16)

**被测**:分支 `fix/finish-evidence` @ `a338477`(撤销摸底答对直接完成,完成判定改由会话内讲述证据支持);内核 = `KernelSubject(start→reply×N→finish)`;tutor = qwen3_vl_8b@8303(本地),judge = mlx_27b@8301(本地,六维单遍盲评)。

**零远程硬保证**:跑批器(`scripts/finish_evidence_eval.py`)运行时从注册表剥离 deepseek provider 并摘除引用它的 fallback(configs/models.yaml 未动,manifest 申明);facts 审计 `providers_used=['mlx','vision']`、`fallback_to=无`——全部调用落在本地端点,零远程 API。

## 验收矩阵(用户裁:缺一不可;每案 2 重复)

| 案例 | 剧本 | 期望 | 实测 | 判定 |
|---|---|---|---|---|
| finish_evidence_zero_utterance | 零发言(start 后直接 finish) | needs_review | needs_review / needs_review | **PASS** |
| finish_evidence_answer_only | 只报「9 个。」 | needs_review | needs_review / needs_review | **PASS** |
| finish_evidence_vague_two | 「好像还行吧。」「就那样算的呗。」 | needs_review | needs_review / needs_review | **PASS** |
| finish_evidence_full_explanation | 「12 个平均分成 4 份,每份 3 个,取其中 3 份,所以是 9 个。」 | completed | completed / completed | **PASS** |

判卷要点(逐字抽查 transcript,证据 = `collect/*/results/*.json`):
- **answer_only**:tutor 未置确认,转而引导「先回到你刚说的『9 个。』——你能从题目里再确认一个已知条件吗?」;finish 落专项文案(用户裁逐字)「这道题之前已经答对了,我们还需要听你把关键思路讲清楚。」;
- **full_explanation**:单轮讲述(含步骤/依据/结论)即达确认态——与教学定义例句「一轮即可充分」一致;零调用模板总结引学生原话,无「每一步都是你自己的思路」「这道题你已经完整讲清楚」(已撤销断言);
- **原有完成态幂等 + 零调用路径**仍成立(mock 断言钉:tests/teaching/test_kernel_r6.py;真实会话 completed 由确认态进入,summary 不可变不变量未动)。

## 调用量与复现

本地模型调用:tutor 18 + judge 8 = **26 次,零远程**(`remote-audit.json`;含判停闸重写/护栏重生成耗用)。

复现(Mac,worktree 于被测分支;勿碰 gitee 镜像,取数走 GitHub remote):

```bash
~/.local/bin/uv sync
~/.local/bin/uv run python scripts/finish_evidence_eval.py \
    --out edu_agent/evals/artifacts/finish-evidence-eval
```

判定规则:每案 `final_state` 全重复等于期望 → PASS;零远程审计(facts 的 provider/fallback)失败 → 非零退出。运行身份见 `manifest.json`(git_sha/prompts_sha256/models_yaml_sha256)。

## 文件清单

- `cases.jsonl` / `manifest.json` / `summary.md` / `judge-scores.json` / `remote-audit.json`——输入、身份、判定表、六维分、零远程审计;
- `collect/cases-20260916T100003Z-3663/`——EvalRunner 原始结果(8 份 transcript + manifest);
- `facts/model_calls-2026-09-16.jsonl`——26 次调用的 facts 台账(内容已脱敏)。
