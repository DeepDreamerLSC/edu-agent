# JSON 首次通过率(#34 M2 出口条件)

## 1. 定义

M2 出口条件: **json 一次通过率 ≥ 98%**。

**一次通过(合规)** = schema 模式调用首次尝试(`edu.attempt==1`)中,模型**产出了合规 JSON**
(`edu.outcome == "ok"`)。

**合规分母** = 产出了模型响应的行(`edu.outcome ∈ {ok, schema_violation, truncated, content_filtered}`)。
模型没产出响应的基础设施失败(`timeout_* / rate_limited / upstream_* / connection`)移出分母,
单列 availability —— 那是 01 §6「成功率/首次成功率」的职责,不混入合规率。

**分子** = 分母中 `edu.outcome == "ok"` 的行数。

> 背景:step p1 证实所有 tutor/judge 调用均挂 `response_schema`(kernel.py §open/reply/repair/summary
> + judge.py),不存在同一角色混用,故角色全集即分母全集,无需给 `build_payload` 加
> `edu.schema` 布尔字段(YAGNI)。
>
> 2026-09-10 评审修订:原 v0「未发生 schema_violation 事件」头条与 01 §6「json_schema 一次通过」
> 字面矛盾(一条 truncated 没产出合规 JSON 却计通过,管道全坏时仍显示 100%)。
> 修订为 ok 分子 + 响应分母,基础设施失败移出分母单列 availability(01 §6 成功率职责)。

## 2. 时间窗

脚本 `scripts/json_first_pass.py` 接受 `--since` 参数(可选)。默认:当前 facts 目录下所有文件。

夜评挂载时,时间窗为当日 23:00 帧(单帧);facts 目录持久化在 checkout 之外
(`EDU_FACTS_DIR=$HOME/edu-agent-facts`,见 evals-nightly.yml),脚本支持多日 facts 合并,
M2 判门可用累计样本。

## 3. FILES(事实来源)

所有 `model_calls-*.jsonl` 文件由 `gateway/middleware/record.py:FactWriter` 追加写生成,
按 UTC 天切分文件名。facts 目录由 `EDU_FACTS_DIR` 环境变量指定,默认为仓库根 `facts/`。

| 来源 | 路径 | 行数 | 说明 |
|---|---|---|---|
| 夜评(actions-runner, 2026-09-10) | `~/actions-runner/_work/edu-agent/edu-agent/facts/model_calls-2026-09-10.jsonl` | 40 | 两次 workflow_dispatch 产生的累计事实;20 tutor + 20 judge,全部 attempt=1,39 ok + 1 truncated |
| WP5b 图像基线(actions-runner 历史) | (被 `actions/checkout` 清理,不可追溯) | — | WP5b 规范流程应产生 image_teaching 段事实,但当前 checkout 不保留历史 facts |
| 4 个本地 worktree(小规摸) | `/root/code/edu-w9-wp5/facts/model_calls-2026-09-09.jsonl` | 14 | tutor 13 + judge 1 |
| 同上 | `/root/code/edu-agent/facts/model_calls-2026-09-09.jsonl` | 6 | tutor 3 + judge 2 + vision 1 |
| 同上 | `/root/code/edu-w9-image-wiring/facts/model_calls-2026-09-09.jsonl` | 2 | tutor 2 |
| 同上 | `/root/code/edu-w8-arc-eval-main/facts/model_calls-2026-09-10.jsonl` | 30 | tutor 30 |

> **已知限制(2026-09-10 修复)**:2026-09-09 第一个定时夜评的事实已被后续 `actions/checkout`
> 清理。夜评 workflow 已加 `EDU_FACTS_DIR=$HOME/edu-agent-facts`(checkout 之外),
> 自 2026-09-11 夜起 facts 跨夜持久化,多日累计窗口可用。

## 4. 排除规则

| 场景 | 是否计为一次通过 | 理由 |
|---|---|---|
| attempt=1 ok | ✅ 计 | 产出合规 JSON |
| attempt=1 schema_violation → attempt=2 ok(重试) | ❌ 不计 | 首次产出不合规 |
| attempt=1 schema_violation → attempt=2(备选 fallback) ok | ❌ 不计 | 同上 |
| attempt=1 truncated/content_filtered | ❌ 不计 | 产出了(不完整/被过滤)响应但非合规 JSON |
| attempt=1 timeout_*/rate_limited/upstream_*/connection | 移出分母 | 未产出响应 → availability 职责,不计合规率 |
| 非 schema 角色(vision/其它) | 排除 | 无 response_schema;旧 probe 数据不进入分子 |

> **透明度规则**: 合规分母内不合规明细(schema_violation/truncated/content_filtered)
> 逐行单列(role + session);availability 失败数单列。

## 5. 输出格式

脚本输出 Markdown 表格(可直接贴入 night 报告对比段):

```markdown
## json_first_pass(01 §6 结构化输出合规率)

M2 门 98%: ❌ 当前 **97.5%** (39/40 产出了结果)

| role | responded | ok | rate | breakdown |
|---|---:|---:|---:|---|
| judge | 20 | 20 | 100.0% | ok=20 |
| tutor | 20 | 19 | 95.0% | ok=19, truncated=1 |
| **合计** | **40** | **39** | **97.5%** | |

> **不合规明细**(在合规分母内,计入未通过):
> · truncated (role=tutor, session=20260910T021359Z-tutor)
```

基础设施失败(如有)附加一行 availability 说明。

## 6. 夜评挂载

`scripts/tuning_round.py` 在生成报告时追加:

```python
from scripts.json_first_pass import json_first_pass_report
report += json_first_pass_report(facts_dir).splitlines() + [""]
```

该行进入 `comparison.md`,天然出现在夜评步骤摘要和归档中。
`evals-nightly.yml` 设置 `EDU_FACTS_DIR: $HOME/edu-agent-facts` 使 facts 跨夜持久化。

## 7. 参考

- `docs/plan/01-model-call-chain.md §6` — 指标定义总表
- `scripts/json_first_pass.py` — 实现
- `#34` — M2 出口条件
- `#113` — 评审记录