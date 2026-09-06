# M0 24 条 Silver 真实基线重复运行对比

## 结论

同一份 24 条 Silver 冻结题图在两个代码提交上各运行一次。两次均完成 48 次真实模型调用，24 条样本全部在题图理解响应解析阶段失败；失败阶段、调用次数、实际 Worker 和原始输出指纹完全一致。

本结果证明运行入口和失败归因可重复，但不证明题图识别准确率。24 条样本仍为内部 Silver，字段级 Gold 尚未完成，因此正式准确率保持 `pending_gold`。

## 冻结身份

- 题目清单摘要：`2f512920e139f7da0b3110645bd47532d6921f4096aef48c75ce87d7113d56fa`
- 本地受控上传清单摘要：`c607564a20c4fb08f6fe968a8ce07913038bf58a1ea8d2a8c8acdb4b59a582c0`
- 实际 Worker：`lecture-video-evaluation-qwen-vl-worker-v1`
- Worker 构建版本：`290652d6badc6fa909ee247e1de1626b1613e97d`
- Worker 部署：`test_lecture_evaluation_model_worker_shadow`
- 权重摘要：`bd9c9f5a3c11846e1ee667c434651908460d5328d2f501f94ffb8b0f6495be18`
- Prompt 版本：`teaching_context_compile/v18`
- 执行器版本：`question_image_understanding_executor/v1`

## 两次运行

| 项目 | r3 | r4 |
| --- | --- | --- |
| 代码版本 | `289f5083afe6035e9a2f5de2d033b0c187fbcb2b` | `c249bd38d824fceb50a74e78513d24a9f79dccdf` |
| 运行编号 | `m0-silver24-current-head-20260821-r3` | `m0-silver24-current-head-20260821-r4` |
| 冻结装配摘要 | `0c9fa3a6d3753168ffceed2022fdc76b22bb6de7489e79f9ae5c167d14dae877` | `287648f6215914d02ff63dea293ccc735547e833f4520952a7ebe64305aa6e54` |
| 模型调用数 | 48 | 48 |
| 输入解析 | 24/24 通过 | 24/24 通过 |
| 题图理解 | 24/24 失败 | 24/24 失败 |
| 失败码 | `MODEL_RESPONSE_PARSE_FAILED` | `MODEL_RESPONSE_PARSE_FAILED` |
| 每题调用次数 | 2 | 2 |
| 原始输出长度 | 1025 | 1025 |
| 原始输出摘要 | `09bd13e8017803af7ed440bceda9028896f0edf5240e4e0d312f658f32dfccb4` | 同左 |
| 溯源状态 | `incomplete` | `complete` |
| 正式准确率状态 | `blocked` | `pending_gold` |
| 报告摘要 | `df29941a9be299870fd8dde8d78340cbbb19295b20a4e778ca3b039b2449f305` | `91d5e59061646698b176609ee217d419569504d866943dd27e49c0eb91ac49d7` |

## 差异解释

r4 仅修正报告的溯源聚合语义：题图理解解析失败后，教学上下文编译没有执行，因此不再要求不存在的编译调用身份。已执行的两次题图理解调用均具有 `model_call_id`、真实 Worker、部署、构建版本和权重摘要，所以 r4 的溯源状态为完整。

模型输出没有变化。两次运行的 24 条样本都得到相同的退化标点输出，内容为 1025 个感叹号，随后触发 `TYPEERROR` 解析异常。因此当前 Top1 问题是 Worker/模型生成质量或模型运行时兼容性，不是 OSS、本地文件、Gateway 路由、门禁或学生展示。

## 后续边界

- 18 条开发集可用于定位和修复退化生成问题。
- 6 条保留集只用于修复后的独立复测，不参与 Prompt、规则或模型参数调优。
- 在内部字段复核完成前，不计算题干、数字单位、公式选项或有序小问准确率。
- 在题图理解恢复前，首问、门禁和学生展示阶段均保持 `not_run`，不得包装成教学成功。
