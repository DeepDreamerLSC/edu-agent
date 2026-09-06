# 00 重写计划：小讲师 + 评测主线

状态：草案（2026-09-06）。等待评审后转为 approved。

## 1. 决定

在 GitHub 新建本仓库，只重写两件东西：

1. **小讲师（Small Lecturer）教学对话 agent**：产品线。
2. **评测线路**：工程主线。评测先于 agent 建立，agent 的每一步改动以评测结果说话。

其余业务域（题目入库、PDF 裁题与排版、微课、讲评、作文批改、后台管理、Prompt Lab 控制台）
**不迁移，不重写**。老仓库（Gitee `edu_agent`）进入冻结维护，只接合作方缺陷修复。

这不是"从零重写整个平台"。老仓库约 100 万行 Python，其中小讲师 agent 约 1.2 万行、
评测约 5.6 万行、二者直接依赖约 4 万行；仅非主线的应用代码就超过 25 万行，连同测试与
脚本，全仓库近九成不迁移。我们保留并提炼的是那一成。

## 2. 为什么重写而不是在老仓库里重构

老仓库有一份 ADR-0006 草案提议"12 周时间盒重构窗口"。放弃它的理由：

- 重构要在 100 万行、85 个迁移、2130 行文件上限的豁免机制和 Local CI 门禁之间做外科手术，
  每一步都在和自己的治理机制对抗。
- 最近 300 次提交中 33 次在修租约、预载、运行时身份恢复。根因不是某个 bug，
  而是**自研模型 worker 池 + 进程内推理引擎 + 身份契约**这条链路本身过重。
  在原地改这条链路，等于在承载合作方联调的系统上换发动机。
- 新仓库让"对外合同冻结"免费成立：老仓库不动，合作方无感知。

被拒绝的另一种做法：**白纸重写**，什么都不带。拒绝理由：老仓库的评测数据集、
金标样本、教学合同测试是唯一的规格，扔掉它们就是扔掉两年的产品判断。
所以本仓库是"**资产迁移 + 代码重写**"。

## 3. 核心：模型调用链路

整体架构图（组件、边界、评测流程、会话状态机）见 [03-architecture.md](03-architecture.md)。

重写最重要的部分是模型调用链路的**效率**与**稳定性**。详细设计见
[01-model-call-chain.md](01-model-call-chain.md)。这里只列结论：

- 一个咽喉点 `gateway`，两个入口：`invoke`（同步）与 `stream`（流式）。所有模型调用必经此处。
- **不自建 worker 池、租约、心跳、预载恢复。** 本地模型以独立的 OpenAI 兼容服务进程运行
  （llama-server / mlx-lm server / vLLM），gateway 只当 HTTP 客户端。
- provider 协议只保留 **OpenAI 兼容**一种（可选加 Anthropic 原生），不再有
  `external_http` / `managed_external` / `mlx_text` / `system_vision` 等五六种。
- 每次调用产出一条 **model_call 事实记录**（JSONL 起步），这是唯一审计源，也是效率与稳定性指标的数据源。
- 效率与稳定性各有一组硬指标：故障注入测试进 PR CI，效率基准进 main CI 的
  self-hosted runner（可访问本机模型服务与云 API），见 01 文档第 5、6 节。

## 4. 评测线路（主线）

### 4.1 v1 不依赖数据库

评测 v1 必须能在**没有 PostgreSQL、没有后台、没有身份系统**的情况下跑通：

```
JSONL 数据集 → 小讲师 agent（经 gateway） → judge 模型（经 gateway） → 报告（Markdown + JSON）
```

这条规则的目的是防止"为了跑评测先把平台造回来"。

### 4.2 先拿老系统基线

第一个里程碑不是新 agent，而是**用新评测线跑老系统**：在 `evals/` 里写一个"被测对象适配器"，
驱动老仓库测试环境的合作方流程接口（open → refresh → messages → confirm），在迁移过来的数据集上出一份基线报告。
它不是 gateway 的 provider（gateway 只做 chat completions），凭据以环境变量注入。此后新 agent 的每个版本都与这条基线对比。

### 4.3 追平门

- 数据集：老仓库 `evals/datasets` 21 个数据集 + `artifacts/small-lecturer` 下的合作方样本
  （普加六年级数学批次等）。
- 门：新 agent 在全部数据集上**不劣于**老系统基线，且模型调用链路的效率与稳定性指标达到
  01 文档规定的阈值。
- 时限：自 M0 完成起 **6 周**。到期未追平，停下来复盘哪些老代码的复杂度是必要的，
  而不是继续硬写。
- 进度可见性不加新流程：`evals/report` 直接输出逐数据集 vs 基线的对比表，追平进度自然可见；
  M2 期间每周归档一份完整报告（scheduled workflow 打 tag），复盘时有逐周轨迹。

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
- 题目解析在 `start()` 内完成：题面文本直接使用；含图题目经 gateway 以 `vision` 角色做
  图意理解与"题图不可信 / 多题混入"检测（对应 03 状态机 Preparing → Failed），
  纯文本题跳过该步。
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
| 错误码 | `409 QUESTION_SOURCE_PINNED`、`409 SKILL_SESSION_CONFLICT`、`409 TEACHING_CONTEXT_PRELOAD_NOT_READY`、`401` | 含义与合作方处理方式不变。新链路下 `PRELOAD_NOT_READY` 预期不再触发，仅为合作方既有错误处理兼容而保留 |

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
| Prompt Lab 中被采用的 prompt 版本 | `configs/prompt_lab/` | 只迁被 production 采用的版本，落到 `agents/small_lecturer/prompts/` 作为代码而非配置，不占配置文件预算 |
| 教学合同行为测试 | `tests/` 中与 small_lecturer 教学语义相关的断言，以及 `skills/small-lecturer-coaching/SKILL.md` 的 12 条交互规则与教学边界 | 重写为新接口的护栏测试，断言不变；SKILL.md 剪掉绑定老架构的第 2、3、8、10 条后作为系统提示词来源 |
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
- 合作方 API 的限流、配额、计费（M3 前；单合作方试点期不做）
- 除小讲师外的任何业务域

## 8. 里程碑

| 里程碑 | 内容 | 出口标准 | 预计 |
|---|---|---|---|
| M0 骨架 | **第一个 PR 是执行机制**（budget.py、ruff、import-linter、CI、PR 模板、分支保护、AGENTS.md，见 02 第 11 节），之后才是 gateway、model_call 记录、基准与故障注入测试、两分钟部署脚本 | 规则红灯演练通过；gateway 对一个云 API 和一个本地服务跑通；故障注入测试进 PR CI，效率基准在 self-hosted runner 上跑通；`make deploy` 两分钟内 | 1 周 |
| M1 评测线 | 数据集迁入、runner、judge、报告；老系统作为 provider 跑出基线（落地清单见 8.2） | 一份完整基线报告入库 | 2 周 |
| M2 追平 | 小讲师 agent 重写、教学合同测试移植、逐数据集追平 | 全部数据集不劣于基线 | 3 周 |
| M3 对齐 | 用 5.2 复用清单中的老路径包装内核；会话持久化；单合作方身份端点；合作方切换预案 | 合同测试全绿，合作方 Postman 样例在新后端上原样通过，App 侧零改动 | 视情况 |

### 8.1 并行分工与里程碑清单规则

M0 单线：执行机制 PR 合并之前没有可并行的对象。M1 起两条并行线（一位开发者统筹调度，各配一个
agent），文档只锁线的划分：

- **评测线**：老系统适配器、数据集、runner、judge、报告与基线（清单见 8.2）。
- **gateway 与模型服务线**：本地模型服务稳定化（launchd 托管、27B/9B 常驻）、`models.yaml`
  角色配置、效率基准与故障注入在 main CI 沉淀出趋势、gateway 按评测线暴露的问题迭代。

每个里程碑进入时的第一个 PR 补该里程碑的落地清单（格式同 02 第 10 节）。M1 的清单见 8.2；
M2、M3 到时再写——M2 的清单取决于 M1 基线报告暴露什么，M3 取决于追平后的合作方状态，
现在预写只会返工。

### 8.2 M1 落地清单

顺序即依赖：适配器 spike 未知最多、风险最高，放第一周；runner 与 judge 在 spike 结论上铺开。

- [ ] 第一周：老系统适配器 spike——驱动老仓库测试环境，单条对话跑通
      open → refresh → messages → confirm；幂等键重试返回同一 Attempt、
      `session_version` 409 冲突、流式中断各验一次；凭据以环境变量注入
- [ ] 数据集迁入与校验：21 个数据集 + `artifacts/small-lecturer` 101 个文件原样迁入，
      条数与内容哈希和老仓库一致，哈希清单随迁移 PR 提交
- [ ] 评测 runner：面向"被测对象"抽象（M1 的实现是老系统适配器，M2 换成内核三函数），
      并发由 runner 控制，gateway 不感知批量
- [ ] judge：经 gateway 调用，与 tutor 不同模型；评分 schema（教学维度）定稿
- [ ] 报告：Markdown + JSON；教学指标逐数据集，效率/稳定性指标从 model_call 记录汇总
      （老系统侧只有适配器可观测的端到端口径，见 01 第 5 节）
- [ ] 基线报告入库，作为 4.3 追平门的对照物

### 8.3 开工前已确认的事项（2026-09-06）

| 事项 | 结论 | 影响 |
|---|---|---|
| 仓库可见性 | 已改为 **private** | 合作方评测样本、题库、试点对话可以直接进 `evals/datasets`，不需要脱敏流程 |
| M0 的两个 provider | 云端：一个 OpenAI 兼容 API，M0 时以环境变量接入。本地：本机 Mac（M5 Max，128 GB）跑 mlx-lm server 或 llama-server | 效率阈值以这台机器为基准；老系统 tutor 用 Qwen3.5-27B MLX 4bit，judge 用 Qwen3.5-9B GGUF，可沿用作为本地首选 |
| M1 基线来源 | 老仓库公网测试环境在运行，能拿到访问凭据 | 评测 runner 把老系统接口当 provider 实时跑基线；凭据以环境变量注入，不进仓库 |
| 开发与评审模式 | **单人开发，双 agent 线并行**（评测线 / gateway 与模型服务线，见 8.1） | 02 §7 按单人模式落地：agent 只开 PR 不合并，合并即人批；`structural` 检查为主门，结构 PR 必须带 `structural-approval:` 行；不启用必需评审与 CODEOWNERS（单账户，GitHub 禁止自我批准） |

**待 M0 开工时补的两个输入**（不阻塞文档评审）：云 API 的 base_url 与模型名；judge 用云模型还是本地 9B。
默认假设：judge 用云模型，与 tutor 不同模型以保持独立性，本地 9B 作备选。

## 9. 老仓库处理

- 分支 `main` 冻结，只接合作方缺陷修复。
- ADR-0006（重构窗口）不再推进，缩为一条"冻结维护"决定。
- 老仓库测试环境保持运行，作为 M1 的基线 provider 和 M3 的对照。

## 10. 仓库规范（一页）

- 主分支 `main`，所有变更走 PR。
- 每个 PR 必须说明：改了什么、评测结果变化（若涉及 agent 或 gateway）、删掉了什么。
- 测试是规格：改断言必须在 PR 描述里单独说明理由。
- 没有 Local CI 仪式，CI 就是 GitHub Actions：PR CI 跑 lint + 单测 + 故障注入；
  main CI 另跑 gateway 效率基准与评测冒烟（self-hosted runner）。
- 文件上限 800 行，超出即失败，不设豁免。
- 复杂度预算、PR 必答问题、"修三次就停"、结构性改动人批等规则见 [02-complexity-budget.md](02-complexity-budget.md)。
- 两分钟部署、合并即验证、黄金路径 e2e、评测作为集成门见 [04-deploy-and-integration.md](04-deploy-and-integration.md)。
