# r5 → r6 对比

## 结论

1. **r5 根因修复验证通过**：r5 定位的 `MLXBatchEngine._stream_vlm_sync()`
   丢失 `response_format` 导致的响应退化（24/24 输出 1025 个感叹号）在 r6
   中未再出现。
2. **#206 严格输出合同已生效**：24 次真实调用的原始输出 100% 为合法
   JSON 且 15 键齐全。解析失败归因（`parse-failure-analysis.md`）表明
   **15/16 是解析器与合同不一致**（`g[].m` 合同定义为自由文本，解析层
   `evidence_type` 枚举归一化缺口），不是模型不遵守 schema。
3. **解析器修复后同清单复跑（`../question-image-m0-silver24-20260902-r6-postfix/`）：
   题图理解 24/24 全部通过**（预期约 21/24，超预期），18/24 走完全链路
   进入 pending_gold；剩余 6 题失败全部集中在 `teaching_context_compile`
   （27B 编译层质量，下一层问题）。修复前后的完整对照见下表。
4. **证据完整性达标**：两次正式运行均 status=completed、溯源 complete、
   注册清单摘要已提供（`f9b4822c…`）、正式准确率 pending_gold。

## 三次运行对照（同一冻结 24 张图片）

| 指标 | r5（退化在位） | r6 修复前（含 #206 合同） | r6 修复后 |
| --- | --- | --- | --- |
| 运行代码 | `68e91a63` | `c12c7794` | `63307c24`（+解析器修复） |
| question_image_understanding | 0/24（failed=24） | 8/24（failed=16） | **24/24** |
| teaching_context_compile | not_run=24 | passed=7，failed=1 | passed=18，failed=6 |
| 样本终态 | failed=24 | pending_gold=7，failed=17 | **pending_gold=18**，failed=6 |
| 溯源 / 正式准确率 | complete / pending_gold | complete / pending_gold | complete / pending_gold |

## 运行身份

| 项 | r5（2026-08-21） | r6（2026-09-02） |
| --- | --- | --- |
| 题目图片集合 | 冻结清单 `6aeffd9c…`（摘要按 upload 源归一） | 同一 24 张图片；OSS 注册源模式，图片同一性由 registration 的 24 个 `expected_sha256` 集合证明（与冻结清单完全一致）；清单摘要 `6f1b6166…`（按 oss_url 源计算，不可与 r5 摘要直接比较） |
| 理解 Worker | `lecture-video-evaluation-qwen-vl-worker-v1`（mlx_text） | 注册条目 `qwen3-vl-8b-mlx-worker-v1`，实际 Worker `qwen35-9b-gguf-vlm-test-v1`（openai_compatible，GGUF Q4_K_M+mmproj，build `cce518dd`，早于 #206） |
| 编译 Worker | 未到达该阶段 | `qwen36-27b-mlx-worker-v1`（mlx_text，build `96bc9a80`，端口 8200） |
| 注册清单摘要 | 未提供 | `f9b4822c…cbb33532ac9135`（提供） |

r6 的理解 Worker 与 r5 不是同一部署，且 Worker 代码早于运行代码。按组件级
验收规范分别记录身份；比较结论限定为"链路修复验证 + 合同行为验证 + 解析器
修复验证"，不构成两个 Worker 之间的质量结论。

## 修复后剩余失败（6 题，全部 compile 层）

- `teaching_context_compile` / `TEACHING_CONTEXT_COMPILE_FAILED`：6 题。
  理解已全过，教学上下文编译（27B Worker）未过结构校验，属下一层模型
  质量问题，待在开发集归因调优。

## 限制（读者须知）

- **并发与容量不在本基线覆盖范围**：理解 Worker 为宿主机单并发共享资源
  （registry 条目 max_concurrency=1，实测空闲时 queue_ms≈0.03s）；修复后
  首次复跑出现过 3 题 `MODEL_PROVIDER_TIMEOUT` + 2 题 `MODEL_QUEUE_TIMEOUT`
  （共享占用），正式复跑已避开。容量问题应另立 issue 跟踪，不应归因为
  格式/解析失败。
- **验收口径**：本基线是评测脚本直跑 #206 输出合同，"修复验证通过"≠
  "产品达标"。学生上传入口（含重传/开题链路，如 `04_6a61b366.jpg` 探针）
  与评审台 debug 路径的可用性**不在本 PR 范围**，属会话级/浏览器端验收。
  解析器修复后学生端题图理解成功率约 **24/24 = 100%**（本清单口径），
  全链路（含教学编译）18/24 = 75%；两者均为链路验证口径，不是产品
  验收口径。

## 后续动作

1. ~~修解析器~~（本 PR 已含：别名扩充 + 未命中兜底 `other`，30 项行为
   锁定测试；compiler.py 保持基线行数）。
2. compile 层 6 题失败在开发集归因（27B 教学编译质量）。
3. 濮家合作方 30 题会话级真实验收：Worker 就绪预检已通过，待测试环境
   后端按同一 manifest 执行真实调用。
4. Gold 审批到位后计算正式准确率。


