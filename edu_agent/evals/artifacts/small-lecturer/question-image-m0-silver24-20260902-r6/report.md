# 小讲师题图真实基线运行报告

- 状态：`completed`
- 运行编号：`m0-silver24-20260902-r6`
- 生成时间：`2026-09-02T16:51:20.502924+00:00`
- 代码版本：`c12c7794207b37bcb56ffdd3b4d03c4e484283ae`
- 运行模式：`auditable`
- 题目数：`24`
- 模型调用数：`48`
- 正式准确率状态：`pending_gold`
- 证据溯源状态：`complete`
- 冻结装配状态：`complete`
- 冻结装配摘要：`c53c83d8f160d65a90b8a94eb6fb52b67391823ca9951f12a7bf5da22196df04`
- 题目清单摘要：`6f1b6166cbbdc5effcaf98218ac810cf4f20a888d892331a67fc5998766317e6`
- 注册清单摘要：`f9b4822c03cbb33532ac9135eb360a6d5a9c8268907af877d777c604c3cdd014`

每题证据保存在 `per-question/`。本报告不保存题图 URL；模型调用失败或运行前置条件不足时，样本保持 blocked，不能进入准确率。

## Top 失败切片

- `development:wide` / `question_image_understanding` / `MODEL_RESPONSE_PARSE_FAILED`：7 题（样本：pujia-silver-v0:development:6a61bb0ef0e25247f1ee36c7:3c5c84b5264a, pujia-silver-v0:development:6a62cc88184f723b3592aec7:849b55e5fa56, pujia-silver-v0:development:6a6311cb184f723b3592c8d5:80567c645e64, pujia-silver-v0:development:6a631d5199bf346827f09389:396043867148, pujia-silver-v0:development:6a6959136c232e289af524ff:d579476bba34）
- `reserved:wide` / `question_image_understanding` / `MODEL_RESPONSE_PARSE_FAILED`：3 题（样本：pujia-silver-v0:reserved:6a631186184f723b3592c8a5:f72f687a3dd4, pujia-silver-v0:reserved:6a699c052ebd2a1afb8782fc:f5ff1c3e5961, pujia-silver-v0:reserved:6a69e3c52ef3251197be27a7:0c39772176eb）
- `development:landscape` / `question_image_understanding` / `MODEL_RESPONSE_PARSE_FAILED`：1 题（样本：pujia-silver-v0:development:6a699b912ef3251197bdfffb:1bb21e9f644c）
- `development:portrait` / `question_image_understanding` / `MODEL_RESPONSE_PARSE_FAILED`：1 题（样本：pujia-silver-v0:development:6a69e2b02ef3251197be26db:95b651a1f7b8）
- `development:squareish` / `question_image_understanding` / `MODEL_RESPONSE_PARSE_FAILED`：1 题（样本：pujia-silver-v0:development:6a69586fb0ffee286ba75532:55853c6518b8）
- `development:tall` / `question_image_understanding` / `MODEL_RESPONSE_PARSE_FAILED`：1 题（样本：pujia-silver-v0:development:6a695f1e6c232e289af52f6b:28575ffb89f6）
- `development:wide` / `teaching_context_compile` / `TEACHING_CONTEXT_COMPILE_FAILED`：1 题（样本：pujia-silver-v0:development:6a631dc999bf346827f093da:418e28d012d4）
- `reserved:portrait` / `question_image_understanding` / `MODEL_RESPONSE_PARSE_FAILED`：1 题（样本：pujia-silver-v0:reserved:6a631f46184f723b3592d090:b16d0d587c59）
- `reserved:squareish` / `question_image_understanding` / `MODEL_RESPONSE_PARSE_FAILED`：1 题（样本：pujia-silver-v0:reserved:6a699e5b2ef3251197be025e:30b4d2f43174）

## 阶段结果

- `active_subquestion_order`：not_run=16，passed=8
- `input_resolution`：passed=24
- `question_image_understanding`：failed=16，passed=8
- `starter_teaching_action`：not_run=16，passed=8
- `structured_question`：not_run=16，passed=8
- `student_presentation`：not_run=16，passed=8
- `student_visible_gate`：not_run=16，passed=8
- `teaching_context_compile`：failed=1，not_run=16，passed=7
