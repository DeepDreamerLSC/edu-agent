# M0 完成审计

## 当前结论

`Development implemented / milestone acceptance pending`。

M0 的功能性退出条件已经具备直接证据：同一组 24 条 Silver 题图可通过受控入口重复运行，运行绑定数据、代码、模型、Prompt、策略、编译器和真实 Worker 身份；失败可落到明确阶段，并提供 Top 切片与样本级原始模型证据。

M0 尚不能按项目流程标记为完成。当前没有与本 Development 任务对应的合法 `task_id`，因此未运行项目 Local CI；独立 Reviewer 和 Software QA 也尚未执行。正式准确率仍为 `pending_gold`，不得把 24 条解析失败样本换算为识别准确率。

## 要求与证据

| M0 要求 | 状态 | 权威证据 | 审计结论 |
| --- | --- | --- | --- |
| 24 条初始 Silver 接入受控评测入口 | 已证明 | `scripts/build_small_lecturer_question_image_m0_manifest.py`、`scripts/run_small_lecturer_question_image_baseline.py`、r5 `report.json` | 18 条开发集与 6 条保留集均进入同一受控入口；本地图片只允许来自显式根目录。 |
| 绑定数据集、代码、模型、Prompt、策略和编译器 | 已证明 | r5 `run_snapshot`、每题 `evidence.model`、`evidence.prompt` | 快照状态和溯源状态均为 `complete`；实际 Worker 身份来自响应，不以逻辑模型冒充。 |
| 跑出未经优化的真实基线 | 已证明 | r5 `report.json`、`report.md` | 24 条样本完成 48 次真实模型调用；未使用 Mock 成功结果。 |
| 区分失败阶段 | 已证明 | r5 `stage_outcome_counts`、每题 `observed.stage_outcomes` | 输入解析 24/24 通过；题图理解 24/24 失败；后续阶段全部为 `not_run`，没有误归因为门禁或学生展示。 |
| Top 错误切片和样本级证据 | 已证明 | r5 `top_failure_slices`、`cases` | 每条记录包含请求、原始输出、调用身份、耗时和稳定错误码；Top1 为题图理解解析失败。 |
| 同一冻结快照可重复运行且差异可解释 | 已证明 | r4 `comparison.md`、r5 `comparison.md` | r4/r5 使用相同实际图片清单摘要，均为 48 次调用和同一失败分布；r5 只将逻辑数据集摘要改为与本机路径无关。 |
| 缺少 Gold 不进入正式准确率 | 已证明 | r5 `formal_accuracy_status=pending_gold` | 24 条失败样本没有被包装为通过，也没有输出虚假准确率。 |
| 项目 Local CI | 未证明 | 无合法任务身份 | 不得自行发明 `task_id`；当前没有不可变 Local CI 报告。 |
| 独立 Reviewer | 未证明 | 尚无当前 HEAD 审查结论 | PR91 的三个 P1 已有回归修复，但新分支仍需独立审查。 |
| Software QA | 未证明 | 尚无当前 HEAD 端到端验收 | 未部署测试环境，也未执行浏览器端学生流程。 |

## PR91 三项阻断回归

1. `QuestionImageRecropRequired` 在未请求捕获重裁产物时直接透传，不再被通用异常包装降回待处理状态。
2. Gold 列表使用规范化后的多重集合严格比较；多余数字、公式、选项及重复项均会失败。
3. 题图理解解析失败必须同时保留 `model_call_id` 和真实 `worker_model_id`；缺少任一身份时状态为 `blocked`，不能计为溯源完整。

## 当前真实失败

- 实际 Worker：`lecture-video-evaluation-qwen-vl-worker-v1`。
- Worker 状态：本次运行期间可用，无排队超时或批次失败。
- 失败表现：24 条最终模型输出均为 1025 个感叹号，原始输出摘要一致。
- 失败归因：模型生成或运行时兼容性导致题图理解响应不可解析。
- 不属于：OSS/本地文件、Gateway 路由、教学门禁、首问或学生展示。

## 后续根因证据

只读诊断沿实际 Worker 身份继续追踪到 `serialized_vlm_compatibility` 执行模式。题图请求的 `response_format` 已由 `ExternalHttpProvider`、Worker HTTP 合同与 `BatchScheduler.response_format_key` 保留，但 `MLXBatchEngine._stream_vlm_sync()` 调用 `mlx_vlm.stream_generate()` 时只传入 `max_tokens` 和 `sampler`，没有构建或传入结构化 logits processor；最终响应也没有 `structured_output_enforced` 指标。相同的带结构化合同请求可在无模型单元探针中稳定复现该参数遗漏。

`ModelGateway._invoke_to_chat_request()` 另有一个字段复制缺口，但当前题图链路通过 `ExternalHttpProvider.invoke()` 和 Worker Sidecar，不走该兼容转换，因此不能把它当作 r5 的直接根因。当前证据把断点定位在 MLX 批处理引擎的串行视觉路径；它与 24 条响应均退化为不可解析标点一致，但完整因果闭环仍需在独立 M2 分支修复真实执行路径、启动当前代码 Worker，并只用 18 条开发集重跑验证。当前 M0 PR 不包含该行为修改。

## 进入下一阶段前的动作

1. 取得控制平面分配的合法 `task_id`，运行 `$edu-agent-local-ci` 并保存不可变报告。
2. 对当前远端分支执行独立 Reviewer，确认三个 P1 与评测可信度边界。
3. 由 Software QA 复核 Runner、报告和保留集隔离，不把开发集调优结果当作保留集结论。
4. M1 只复核 18 条开发集；6 条保留集继续禁止参与 Prompt、规则和模型参数调优。
5. 独立 M2 修复应让 `MLXBatchEngine` 的串行和动态视觉路径真正执行 `response_format`，补充生成参数与 Worker 指标回归，并证明 Worker 返回 `structured_output_enforced=true` 后开发集不再出现同一退化输出；不得直接使用保留集调参。
