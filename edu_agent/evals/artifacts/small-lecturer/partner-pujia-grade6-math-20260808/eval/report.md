# 小讲师合作方 30 题真实模型验收

- 状态：`blocked`
- 题目数：`30`
- 题目清单：`pilot-30.jsonl`
- 题目清单 SHA-256：`2ceffeac15a6eac600abb19ea0b50358b96958dff8050fd4ad2a9c3f1777ab33`
- 探针地址：`http://127.0.0.1:8199/health`
- 探针 HTTP 状态：`None`
- Worker 模型：`未知`
- Worker 提供方：`未知`
- Worker 构建版本：`未知`
- Worker 能力：`未知`
- 阻断原因：`question_image_understanding_worker_unavailable`
- 模型调用数：`0`

- 每题证据：`per-question/`（30 条阻塞记录）
- 人工审核画廊：`review-gallery/`（当前为空）

本报告没有把文本模型或模拟返回当作视觉验收结果。启动正确的视觉 Worker 后，必须重新执行并保存每题的模型调用编号、模型身份、部署身份和阶段结果。
