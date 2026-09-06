# 小讲师题图真实基线运行报告

- 状态：`completed`
- 运行编号：`m0-silver24-current-head-20260821-r4`
- 生成时间：`2026-08-20T19:04:10.552359+00:00`
- 代码版本：`c249bd38d824fceb50a74e78513d24a9f79dccdf`
- 运行模式：`auditable`
- 题目数：`24`
- 模型调用数：`48`
- 正式准确率状态：`pending_gold`
- 证据溯源状态：`complete`
- 冻结装配状态：`complete`
- 冻结装配摘要：`287648f6215914d02ff63dea293ccc735547e833f4520952a7ebe64305aa6e54`
- 题目清单摘要：`2f512920e139f7da0b3110645bd47532d6921f4096aef48c75ce87d7113d56fa`
- 注册清单摘要：`未提供`

每题证据保存在 `per-question/`。本报告不保存题图 URL；模型调用失败或运行前置条件不足时，样本保持 blocked，不能进入准确率。

## Top 失败切片

- `development:wide` / `question_image_understanding` / `MODEL_RESPONSE_PARSE_FAILED`：14 题（样本：pujia-silver-v0:development:6a61bb0ef0e25247f1ee36c7:3c5c84b5264a, pujia-silver-v0:development:6a62cb2999bf346827f05354:b4d7e4d67ce3, pujia-silver-v0:development:6a62cc88184f723b3592aec7:849b55e5fa56, pujia-silver-v0:development:6a6311cb184f723b3592c8d5:80567c645e64, pujia-silver-v0:development:6a631d5199bf346827f09389:396043867148）
- `reserved:wide` / `question_image_understanding` / `MODEL_RESPONSE_PARSE_FAILED`：3 题（样本：pujia-silver-v0:reserved:6a631186184f723b3592c8a5:f72f687a3dd4, pujia-silver-v0:reserved:6a699c052ebd2a1afb8782fc:f5ff1c3e5961, pujia-silver-v0:reserved:6a69e3c52ef3251197be27a7:0c39772176eb）
- `development:landscape` / `question_image_understanding` / `MODEL_RESPONSE_PARSE_FAILED`：1 题（样本：pujia-silver-v0:development:6a699b912ef3251197bdfffb:1bb21e9f644c）
- `development:portrait` / `question_image_understanding` / `MODEL_RESPONSE_PARSE_FAILED`：1 题（样本：pujia-silver-v0:development:6a69e2b02ef3251197be26db:95b651a1f7b8）
- `development:squareish` / `question_image_understanding` / `MODEL_RESPONSE_PARSE_FAILED`：1 题（样本：pujia-silver-v0:development:6a69586fb0ffee286ba75532:55853c6518b8）
- `development:tall` / `question_image_understanding` / `MODEL_RESPONSE_PARSE_FAILED`：1 题（样本：pujia-silver-v0:development:6a695f1e6c232e289af52f6b:28575ffb89f6）
- `reserved:landscape` / `question_image_understanding` / `MODEL_RESPONSE_PARSE_FAILED`：1 题（样本：pujia-silver-v0:reserved:6a695a176c232e289af525e7:a5f8bc234f84）
- `reserved:portrait` / `question_image_understanding` / `MODEL_RESPONSE_PARSE_FAILED`：1 题（样本：pujia-silver-v0:reserved:6a631f46184f723b3592d090:b16d0d587c59）
- `reserved:squareish` / `question_image_understanding` / `MODEL_RESPONSE_PARSE_FAILED`：1 题（样本：pujia-silver-v0:reserved:6a699e5b2ef3251197be025e:30b4d2f43174）

## 阶段结果

- `active_subquestion_order`：not_run=24
- `input_resolution`：passed=24
- `question_image_understanding`：failed=24
- `starter_teaching_action`：not_run=24
- `structured_question`：not_run=24
- `student_presentation`：not_run=24
- `student_visible_gate`：not_run=24
- `teaching_context_compile`：not_run=24
