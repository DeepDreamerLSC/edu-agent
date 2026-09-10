# JSON 首次通过率(#34 M2 出口条件)

## 1. 定义

M2 出口条件: **json 一次通过率 ≥ 98%**。

**一次通过** = metadata 型调用(配置了 `json_strict: true`)的首次尝试(`edu.attempt==1`)中,
未发生 `schema_violation` 事件。

**分子**: 分母中 `edu.outcome != "schema_violation"` 的行数。  
**分母**: 全部 metadata 型调用 = `edu.role in {tutor, judge}` 且 `edu.attempt == 1` 的行数。

> 背景:step p1 证实所有 tutor/judge 调用均挂 `response_schema`(kernel.py §open/reply/repair/summary
> + judge.py),不存在同一角色混用(部分有 schema 部分无),故角色全集即分母全集,无需给
> `build_payload` 加 `edu.schema` 布尔字段(YAGNI)。

## 2. 时间窗

脚本 `scripts/json_first_pass.py` 接受 `--since` 参数(可选)。默认:当前 facts 目录下所有文件。

夜评挂载时,时间窗为当日 23:00 帧(单帧);脚本同时支持累计窗口(多日 facts 合并)。

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

> **已知限制**:2026-09-09 第一个定时夜评的事实已被后续 `actions/checkout` 清理。
> 当前可用最大数据集 = 2026-09-10 的 40 行(两个 workflow_dispatch 夜评运行覆盖 11 场景)。

## 4. 排除规则

| 场景 | 是否计为一次通过 | 理由 |
|---|---|---|
| attempt=1 ok | ✅ 计 | 无 schema_violation |
| attempt=1 schema_violation → attempt=2 ok(重试) | ❌ 不计 | attempt=1 已发生 schema_violation |
| attempt=1 schema_violation → attempt=2(备选 fallback) ok | ❌ 不计 | 同上 |
| attempt=1 非 schema 失败(truncated/connection/rate_limited/…) → no retry | ✅ 按定义计 | 未发生 schema_violation 事件;但**报告中单列明细** |
| attempt=1 非 schema 失败 → attempt=2(备选 fallback) ok | ✅ 按定义计 | 同上 |
| 非 metadata 角色(vision/其它) | 排除 | 无 response_schema;旧 probe 数据不进入分子 |

> **透明度规则**: `--strict` 标志提供"严格一次通过"(仅 `outcome == "ok"`)作为辅助输出,
> 但 M2 门 98% 使用主定义(未发生 schema_violation)。

## 5. 输出格式

脚本输出 Markdown 表格(可直接贴入 night 报告对比段):

```markdown
## json_first_pass(01 §6 结构化输出合规率)

| role | calls | first_pass | rate | breakdown |
|---|---|---|---|---|
| tutor | 20 | 20 | 100.0% | ok=19, truncated=1, schema_violation=0 |
| judge | 20 | 20 | 100.0% | ok=20 |
| **合计** | **40** | **40** | **100.0%** | |

- M2 门 ≥98%: ✅ 达标
- 非 schema 首次失败(按定义计入通过): truncated=1 (role=tutor, session=…)
```

## 6. 夜评挂载

`scripts/tuning_round.py` 在生成报告时追加:

```python
from scripts.json_first_pass import json_first_pass_report
report += json_first_pass_report(facts_dir)
```

该行进入 `comparison.md`,天然出现在夜评步骤摘要和归档中。
<!-- PLACEHOLDER: PR 合并后挂载 -->

## 7. 参考

- `docs/plan/01-model-call-chain.md §6` — 指标定义总表
- `scripts/json_first_pass.py` — 实现
- `#34` — M2 出口条件
- `#113` — 评审记录