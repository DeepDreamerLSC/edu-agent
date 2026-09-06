# 小讲师题图真实基线运行报告

- 状态：`completed`
- 运行编号：`m0-silver24-20260902-r6-postfix`
- 生成时间：`2026-09-02T23:16:03.526891+00:00`
- 代码版本：`63307c24c6a9d07693efd82c269a8bb6bb5b1f8f`
- 运行模式：`auditable`
- 题目数：`24`
- 模型调用数：`48`
- 正式准确率状态：`pending_gold`
- 证据溯源状态：`complete`
- 冻结装配状态：`complete`
- 冻结装配摘要：`59a8ffe097c6784b5358d638fe0b57cef31f5b9a79a829fd603be6a5c504e7f2`
- 题目清单摘要：`6f1b6166cbbdc5effcaf98218ac810cf4f20a888d892331a67fc5998766317e6`
- 注册清单摘要：`f9b4822c03cbb33532ac9135eb360a6d5a9c8268907af877d777c604c3cdd014`

每题证据保存在 `per-question/`。本报告不保存题图 URL；模型调用失败或运行前置条件不足时，样本保持 blocked，不能进入准确率。

## Top 失败切片

- `development:wide` / `teaching_context_compile` / `TEACHING_CONTEXT_COMPILE_FAILED`：4 题（样本：pujia-silver-v0:development:6a61bb0ef0e25247f1ee36c7:3c5c84b5264a, pujia-silver-v0:development:6a62cb2999bf346827f05354:b4d7e4d67ce3, pujia-silver-v0:development:6a631dc999bf346827f093da:418e28d012d4, pujia-silver-v0:development:6a6959136c232e289af524ff:d579476bba34）
- `development:landscape` / `teaching_context_compile` / `TEACHING_CONTEXT_COMPILE_FAILED`：1 题（样本：pujia-silver-v0:development:6a699b912ef3251197bdfffb:1bb21e9f644c）
- `reserved:portrait` / `teaching_context_compile` / `TEACHING_CONTEXT_COMPILE_FAILED`：1 题（样本：pujia-silver-v0:reserved:6a631f46184f723b3592d090:b16d0d587c59）

## 阶段结果

- `active_subquestion_order`：passed=24
- `input_resolution`：passed=24
- `question_image_understanding`：passed=24
- `starter_teaching_action`：passed=24
- `structured_question`：passed=24
- `student_presentation`：passed=24
- `student_visible_gate`：passed=24
- `teaching_context_compile`：failed=6，passed=18
