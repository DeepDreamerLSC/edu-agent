# M0 24 条 Silver 当前提交复测说明

## 结论

当前提交重新运行了同一组 24 条 Silver 题图。输入解析 24/24 通过，随后完成 48 次真实模型调用；24 条样本均在题图理解响应解析阶段失败，后续结构化题目、当前小问、首问、门禁和学生展示均未执行。

本次运行没有把失败样本计为通过。字段级 Gold 尚未完成，因此正式准确率保持 `pending_gold`。每条失败证据均包含 `model_call_id`、实际 Worker、部署、构建版本和权重摘要，溯源状态为 `complete`。

## 冻结身份

- 逻辑数据集摘要：`6aeffd9cc4cd332b0bd488aed043fdf2fae5e9987a8cfa49d7e66062c7006359`
- 本机运行清单摘要：`2f512920e139f7da0b3110645bd47532d6921f4096aef48c75ce87d7113d56fa`
- 代码版本：`68e91a63e4d89c1ee2ca40406616f92fe36b8bcf`
- 冻结装配摘要：`21dfb3b0069f8545823c1740e9b780542386898fb7200fbe9e2d866799dc46b3`
- 实际 Worker：`lecture-video-evaluation-qwen-vl-worker-v1`
- Worker 构建版本：`290652d6badc6fa909ee247e1de1626b1613e97d`
- Worker 部署：`test_lecture_evaluation_model_worker_shadow`
- 权重摘要：`bd9c9f5a3c11846e1ee667c434651908460d5328d2f501f94ffb8b0f6495be18`
- Prompt 版本：`teaching_context_compile/v18`
- 执行器版本：`question_image_understanding_executor/v1`
- 报告摘要：`375c17890d8b5d02bdbbf53e50108cafadd34b5aadb7e9afd8cab511b9824537`

## 与前次运行的关系

| 项目 | r4 | r5 |
| --- | --- | --- |
| 代码版本 | `c249bd38d824fceb50a74e78513d24a9f79dccdf` | `68e91a63e4d89c1ee2ca40406616f92fe36b8bcf` |
| 模型调用数 | 48 | 48 |
| 输入解析 | 24/24 通过 | 24/24 通过 |
| 题图理解 | 24/24 失败 | 24/24 失败 |
| 失败码 | `MODEL_RESPONSE_PARSE_FAILED` | `MODEL_RESPONSE_PARSE_FAILED` |
| 每题调用次数 | 2 | 2 |
| 原始输出长度 | 1025 | 1025 |
| 原始输出摘要 | `09bd13e8017803af7ed440bceda9028896f0edf5240e4e0d312f658f32dfccb4` | 同左 |
| 溯源状态 | `complete` | `complete` |
| 正式准确率状态 | `pending_gold` | `pending_gold` |

r5 将上传题图的逻辑数据集身份与本机路径解耦：逻辑摘要只绑定样本字段和图片 SHA256；运行清单摘要仍保存于报告快照，用于核对本次实际输入。不同机器使用相同图片内容时，逻辑数据集摘要保持一致，同时每次运行仍有独立的运行清单证据。

## 当前 Top 问题

模型最终响应稳定退化为 1025 个感叹号，24 条样本原始输出摘要完全一致，随后触发 `TYPEERROR` 解析异常。当前失败属于模型生成或运行时兼容性，不属于输入资源、Gateway 路由、教学门禁或学生展示。

- 18 条开发集可用于定位退化生成问题。
- 6 条保留集不参与 Prompt、规则或模型参数调优。
- 修复模型输出前，不计算题干、数字单位、公式选项或小问顺序准确率。
- 解析失败时缺少实际 Worker 身份会阻断报告，不会被标记为溯源完整。
