# 00 重写计划：小讲师 + 评测主线

状态：草案（2026-09-06）。等待评审后转为 approved。

## 1. 决定

在 GitHub 新建本仓库，只重写两件东西：

1. **小讲师（Small Lecturer）教学对话 agent**：产品线。
2. **评测线路**：工程主线。评测先于 agent 建立，agent 的每一步改动以评测结果说话。

其余业务域（题目入库、PDF 裁题与排版、微课、讲评、作文批改、后台管理、Prompt Lab 控制台）
**不迁移，不重写**。老仓库（Gitee `edu_agent`）进入冻结维护，只接合作方缺陷修复。

这不是"从零重写整个平台"。老仓库约 102 万行 Python，其中小讲师 agent 约 1.2 万行、
评测约 5.6 万行、二者直接依赖约 4 万行；非主线代码超过 25 万行。我们放弃的是那 85%，
保留并提炼的是这 15%。

## 2. 为什么重写而不是在老仓库里重构

老仓库有一份 ADR-0006 草案提议"12 周时间盒重构窗口"。放弃它的理由：

- 重构要在 100 万行、85 个迁移、2130 行豁免机制和 Local CI 门禁之间做外科手术，
  每一步都在和自己的治理机制对抗。
- 最近 300 次提交中 33 次在修租约、预载、运行时身份恢复。根因不是某个 bug，
  而是**自研模型 worker 池 + 进程内推理引擎 + 身份契约**这条链路本身过重。
  在原地改这条链路，等于在承载合作方联调的系统上换发动机。
- 新仓库让"对外合同冻结"免费成立：老仓库不动，合作方无感知。

被拒绝的另一种做法：**白纸重写**，什么都不带。拒绝理由：老仓库的评测数据集、
金标样本、教学合同测试是唯一的规格，扔掉它们就是扔掉两年的产品判断。
所以本仓库是"**资产迁移 + 代码重写**"。

## 3. 核心：模型调用链路

重写最重要的部分是模型调用链路的**效率**与**稳定性**。详细设计见
[01-model-call-chain.md](01-model-call-chain.md)。这里只列结论：

- 一个咽喉点 `gateway`，两个入口：`invoke`（同步）与 `stream`（流式）。所有模型调用必经此处。
- **不自建 worker 池、租约、心跳、预载恢复。** 本地模型以独立的 OpenAI 兼容服务进程运行
  （llama-server / mlx-lm server / vLLM），gateway 只当 HTTP 客户端。
- provider 协议只保留 **OpenAI 兼容**一种（可选加 Anthropic 原生），不再有
  `external_http` / `managed_external` / `mlx_text` / `system_vision` 等五六种。
- 每次调用产出一条 **model_call 事实记录**（JSONL 起步），这是唯一审计源，也是效率与稳定性指标的数据源。
- 效率与稳定性各有一组硬指标，在 CI 里以基准测试和故障注入测试守护，见 01 文档第 5、6 节。

## 4. 评测线路（主线）

### 4.1 v1 不依赖数据库

评测 v1 必须能在**没有 PostgreSQL、没有后台、没有身份系统**的情况下跑通：

```
JSONL 数据集 → 小讲师 agent（经 gateway） → judge 模型（经 gateway） → 报告（Markdown + JSON）
```

这条规则的目的是防止"为了跑评测先把平台造回来"。

### 4.2 先拿老系统基线

第一个里程碑不是新 agent，而是**用新评测线跑老系统**：把老仓库测试环境的小讲师接口当作
一个 provider，在迁移过来的数据集上出一份基线报告。此后新 agent 的每个版本都与这条基线对比。

### 4.3 追平门

- 数据集：老仓库 `evals/datasets` 21 个数据集 + `artifacts/small-lecturer` 下的合作方样本
  （普加六年级数学批次等）。
- 门：新 agent 在全部数据集上**不劣于**老系统基线，且模型调用链路的效率与稳定性指标达到
  01 文档规定的阈值。
- 时限：自 M0 完成起 **6 周**。到期未追平，停下来复盘哪些老代码的复杂度是必要的，
  而不是继续硬写。

## 5. 小讲师 agent

### 5.1 内核：与传输无关的纯模块

- 目标形态：**可单测的纯函数**编排，不引入 agent 框架（LangGraph 等否决，理由与老仓库 ADR-0006 一致）。
- 对外只有三个函数，评测线直接调用，不经 HTTP：

```
start(question, learner)          -> Turn        # 生成首问
reply(session, student_message)   -> Turn        # 多轮苏格拉底交流
finish(session)                   -> Summary     # 学习总结，证据不足时返回 needs_review
```

- 教学合同（首问不泄露答案、语气护栏、年级表达适配、追问节奏）以**行为测试**形式从老仓库移植。
  实现耦合的单测不迁。
- 结构化输出（json_schema 强制）是 gateway 的能力，agent 不自己解析文本。
- 对话状态在 v1 内存化，持久化推到 M3。

### 5.2 外壳：复用老仓库的合作方接口合同

小讲师**不做成通用聊天接口里的一个 skill**。老仓库曾按 ADR-0002 做过这条路
（`/api/conversations` + `skill_id` + interaction 信封），但合作方最终对接的是一条
绑定题目的专用流程。教学对话有题目、有阶段、有不可违反的合同、有终态总结，
塞进通用聊天只能靠 metadata 私有约定，评测也无法稳定断言。

M3 对外接口**原样复用老仓库合作方正在调用的路径与字段**，合作方 App 零改动切换后端。
复用的是合同（路径、请求响应字段、错误码、语义），不是实现。

**复用清单**

| 步骤 | 端点 | 保留的字段与语义 |
|---|---|---|
| 开会话 | `POST /api/prepared-questions/{question_id}/open` | 请求只有 `idempotency_key`；响应 `conversation`、`skill_session_id`、`session_version`、`first_question_ready`、`retry_after_ms`。同键重试返回同一 Attempt |
| 等首问 | `POST .../skill-sessions/{id}/refresh` | 返回首问与新 `session_version` |
| 多轮 | `POST /api/conversations/{id}/messages` 与 `/messages/stream` | 请求 `content`、`skill_id`、`input.skill_session_id`、`input.expected_session_version`；响应 `assistant_message` + `skill_interaction/v1` |
| 结束 | 同上，`interaction_action=confirm` | 返回 `ready_to_confirm` → `completed`，或 `needs_review` |
| 身份 | `POST /api/openapi/v1/auth/native-codes`、`POST /api/auth/native/token` | 路径与 token 语义保留（ADR-0004），v1 实现只支持单合作方 |
| 错误码 | `409 QUESTION_SOURCE_PINNED`、`409 SKILL_SESSION_CONFLICT`、`409 TEACHING_CONTEXT_PRELOAD_NOT_READY`、`401` | 含义与合作方处理方式不变 |

**必须保留的约定**（直接对应教学合同与稳定性，评测一对一断言）：

1. 幂等键开会话，同键重试不创建第二个会话。
2. 题目在会话内固定，不能中途换题。
3. `session_version` 乐观并发，旧版本返回 409，不静默覆盖新一轮诊断。
4. 客户端不得提交 `answer`、`analysis`、`verified`、`mastery_status`，掌握结论只能服务端产生。
5. 首问未就绪时按 `retry_after_ms` 重试同一入口。新链路下首问通常同步返回，
   `first_question_ready` 字段保留，基本恒为 true。

**接口背后扔掉的实现**：

- prepared-questions 的导入、发布包、`question_version`、快照、租户与 Client App 可见性策略。
  v1 题目来源是一个适配器：调合作方题库接口（`GET .../v1/questions/{question_id}`）或读本地 JSON。
- `/api/skills`、`/api/capabilities`、`general_chat`、interaction.json 渐进加载、`agent_id` 兼容。
- teaching_context 异步预载流水线。
- 多租户权限矩阵。

**合同快照来源**：老仓库 `scripts/check_public_openapi_contract.py` 中的 16 条必需路径、
`public_docs/small-lecturer-partner-pilot.md` 的 Postman 样例、`skill_interaction/v1` 的 schema。
M3 开始前先把这三样迁入本仓库作为合同测试。

## 6. 资产迁移清单

从老仓库原样迁入，不改内容：

| 资产 | 老仓库位置 | 说明 |
|---|---|---|
| 评测数据集 | `evals/datasets/` | 21 个 |
| 合作方评测样本与产物 | `artifacts/small-lecturer/` | 101 个文件 |
| 风格档案 | `configs/small_lecturer_style_profiles.yaml` | |
| Prompt Lab 中被采用的 prompt 版本 | `configs/prompt_lab/` | 只迁被 production 采用的版本 |
| 教学合同行为测试 | `tests/` 中与 small_lecturer 教学语义相关的断言 | 重写为新接口的测试，断言不变 |
| 公开接口文档 | `edu_agent/app/api/public_docs/small-lecturer-*.md`、`partner-sso.md` | M3 对齐用 |
| 合作方接口合同 | `scripts/check_public_openapi_contract.py` 必需路径、Postman 样例、`skill_interaction/v1` schema | 迁为本仓库合同测试，见 5.2 |

## 7. 不做清单（v1）

以下明确不做，出现在 PR 里就打回：

- 管理后台、Prompt Lab 控制台、流量页、自建 trace 页
- 自研 worker 池、租约、心跳、预载恢复、运行时身份契约
- 进程内推理引擎（MLX batch / continuous engine）
- 蓝绿发布、release preflight 仪式
- Alembic 迁移史、手写补列
- 多租户、权限矩阵、SSO（M3 前）
- 通用聊天接口与 skill 目录（`/api/skills`、`/api/capabilities`、`general_chat`），见 5.2
- 除小讲师外的任何业务域

## 8. 里程碑

| 里程碑 | 内容 | 出口标准 | 预计 |
|---|---|---|---|
| M0 骨架 | 仓库结构、gateway、model_call 记录、基准与故障注入测试 | gateway 对一个云 API 和一个本地服务跑通，效率/稳定性测试进 CI | 1 周 |
| M1 评测线 | 数据集迁入、runner、judge、报告；老系统作为 provider 跑出基线 | 一份完整基线报告入库 | 2 周 |
| M2 追平 | 小讲师 agent 重写、教学合同测试移植、逐数据集追平 | 全部数据集不劣于基线 | 3 周 |
| M3 对齐 | 用 5.2 复用清单中的老路径包装内核；会话持久化；单合作方身份端点；合作方切换预案 | 合同测试全绿，合作方 Postman 样例在新后端上原样通过，App 侧零改动 | 视情况 |

## 9. 老仓库处理

- 分支 `main` 冻结，只接合作方缺陷修复。
- ADR-0006（重构窗口）不再推进，缩为一条"冻结维护"决定。
- 老仓库测试环境保持运行，作为 M1 的基线 provider 和 M3 的对照。

## 10. 仓库规范（一页）

- 主分支 `main`，所有变更走 PR。
- 每个 PR 必须说明：改了什么、评测结果变化（若涉及 agent 或 gateway）、删掉了什么。
- 测试是规格：改断言必须在 PR 描述里单独说明理由。
- 没有 Local CI 仪式，CI 就是 GitHub Actions：lint + 单测 + gateway 基准 + 故障注入。
- 文件上限 800 行，超出即失败，不设豁免。
- 复杂度预算、PR 必答问题、"修三次就停"、结构性改动人批等规则见 [02-complexity-budget.md](02-complexity-budget.md)。
