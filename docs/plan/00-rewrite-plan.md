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
- 时限：自 M0 完成起 **4 周**（原 6 周；2026-09-06 压缩，依据 M0 实测半日完成、无外部
  对接压力，M1/M2 按 1 周/2 周重估）。时间盒是止损上限，不是进度表——**提前追平提前
  进 M3，完成即进，不等周数**。到期未追平，停下来复盘哪些老代码的复杂度是必要的，
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
| M0 骨架 | **第一个 PR 是执行机制**（budget.py、ruff、import-linter、CI、PR 模板、PR 元数据门、AGENTS.md，见 02 第 11 节；分支保护在 GitHub Free 私有仓库不可用，以程序性约定替代），之后才是 gateway、model_call 记录、基准与故障注入测试、两分钟部署脚本 | 规则红灯演练通过；gateway 对一个云 API 和一个本地服务跑通；故障注入测试进 PR CI，效率基准在 self-hosted runner 上跑通；`make deploy` 两分钟内 | 1 周 |
| M1 评测线 | 数据集迁入、runner、judge、报告；老系统作为 provider 跑出基线（落地清单见 8.2） | 一份完整基线报告入库 | 1 周 |
| M2 追平 | 小讲师 agent 重写、教学合同测试移植、逐数据集追平 | 全部数据集不劣于基线 | 2 周 |
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

### 8.2 M1 落地清单（进入里程碑时补齐，2026-09-06；执行看板与实时状态见 M1 看板 issue）

时限 1 周（原 2 周，压缩依据见 §4.3）。原则：**白天人环，夜里算力；跑与管分离**——
runner 幂等过夜，人只读晨间摘要做判断；同一套过夜设施 M2 调优循环直接复用。
依赖序：阶段 0 与 M0 收尾并行（已提前启动）→ 1 → 2 → 4；3 与 2 并行。

**阶段 0 前置件（A 线，进行中）**
- [ ] 数据集迁入与校验：21 个数据集 + `artifacts/small-lecturer` 101 个文件原样迁入，
      sha256 对账 100%，条数表入库（PR #29）
- [ ] runner 骨架：被测对象抽象（M1 接老系统适配器，M2 换内核三函数）、case 级
      checkpoint、失败分类（环境/内容）、限速退避、产物布局（每轮目录+manifest）、
      晨间摘要——过夜六需求，假对象单测，不接真适配器（PR #31）
- [ ] judge 评分 schema 草案 → 人审定稿（教学维度是产品判断，留人审；issue #32）
- [ ] （人/老环境侧）环境两卡点清零：test_school 题号歧义、/health 503
      （issue #3 实测仍暴露；数据/运维操作，不违老仓库冻结）

**阶段 1 适配器 spike（第 1–2 天，A 线，交互式调试）**
- [ ] 学生登录 → open → refresh → messages（含流式）→ confirm 单对话全流程驱动；
      幂等键重试返回同一 Attempt、`session_version` 409、token 过期续期、流式中断各验一次；
      凭据环境变量注入
- [ ] spike 结论一页入库：接口行为清单（超时/重试语义/流式帧格式/会话生命周期/实测安全并发）
- 止损：第 2 天末仍不通 → 升级人裁决（环境问题 or 合同理解偏差），不带病进阶段 2

**阶段 2 runner 集成（第 3–4 天，A 线）**
- [ ] 适配器实现被测对象 Protocol；并发由 runner 控制，gateway 不感知批量
- [ ] 小规模试跑：1 个数据集全 case，失败分类与 checkpoint 实战验证
- [ ] 限速实测定参（老环境安全并发，2 起步）

**阶段 3 judge 定稿（第 3–4 天，B 线，与阶段 2 并行）**
- [ ] judge 经 gateway 调用（DeepSeek 主选，与 tutor 不同模型），评分 prompt 按定稿 schema
- [ ] 一致性检查：同一批 case 双评，分差分布入档（judge 稳定性档案，追平门容差依据之一）

**阶段 4 基线两夜（第 4–5 夜）**
- [ ] 第一夜全量基线 → 晨间摘要 → 仅补跑环境类失败
- [ ] 第二夜复跑 → 两夜方差对照（方差 >10% 的指标标记，成为追平门容差依据）
- [ ] 基线报告入库 PR（报告即代码；教学指标逐数据集，效率/稳定性指标从 model_call
      记录汇总——老系统侧只有适配器可观测的端到端口径，见 01 第 5 节）

**出口（§8 表）**：一份完整基线报告入库。随后 M2 清单按 §8.1 规则补齐；
追平门（§4.3，4 周）自 M0 关门起算，完成即进、不等周数。

### 8.3 开工前已确认的事项（2026-09-06）

| 事项 | 结论 | 影响 |
|---|---|---|
| 仓库可见性 | 已改为 **private** | 合作方评测样本、题库、试点对话可以直接进 `evals/datasets`，不需要脱敏流程 |
| M0 的两个 provider | 云端：一个 OpenAI 兼容 API，M0 时以环境变量接入。本地：本机 Mac（M5 Max，128 GB）跑 mlx-lm server 或 llama-server | 效率阈值以这台机器为基准；老系统 tutor 用 Qwen3.5-27B MLX 4bit，judge 用 Qwen3.5-9B GGUF，可沿用作为本地首选 |
| M1 基线来源 | 老仓库公网测试环境在运行，能拿到访问凭据 | 评测 runner 把老系统接口当 provider 实时跑基线；凭据以环境变量注入，不进仓库 |
| 开发与评审模式 | **单人开发，双 agent 线并行**（评测线 / gateway 与模型服务线，见 8.1） | 02 §7 按单人模式落地：agent 只开 PR 不合并，合并即人批；`structural` 检查为主门，结构 PR 必须带 `structural-approval:` 行；不启用必需评审与 CODEOWNERS（单账户，GitHub 禁止自我批准） |

**待 M0 开工时补的两个输入**（不阻塞文档评审）：云 API 的 base_url 与模型名；judge 用云模型还是本地 9B。
默认假设：judge 用云模型，与 tutor 不同模型以保持独立性，本地 9B 作备选。

### 8.4 M2 落地清单（进入里程碑时补齐，2026-09-07；执行看板与实时状态见 M1 看板 issue 延续）

时限 2 周（§8 表）。原则：**先证明教学行为，再追平数字**——内核先过教学护栏全绿（行为
即合同），然后才进调优循环比基线；**靶子冻结**，M2 期间覆盖面不动（见开放决策②）。
依赖序：阶段 0 与 M1 收尾并行 → 1 → 2 → 3；4 与 3 交替多轮。

**阶段 0 前置件**
- [ ] M1 基线报告入库（两夜方差对照定追平门容差；Run 1 已完成：11/11 ok、
      单场景 p50 81.1s / p95 119.8s，数据集 release_acceptance_seed_question_bank）
- [ ] 开放决策①裁决（C 线是否开，见后）

**阶段 1 内核三函数（agents/small_lecturer）**
- [ ] `start(question, learner) -> Turn`、`reply(session, student_message) -> Turn`、
      `finish(session) -> Summary`：与传输无关的纯函数编排（§5.1，不引 agent 框架），
      状态机按 03 §4（Opened → Preparing → FirstQuestionReady/Failed → Dialogue →
      NeedsReview/ReadyToConfirm → Completed），对话状态 v1 内存化
- [ ] prompt 装配：#45 迁入的 `agents/small_lecturer/prompts/SKILL.md`（剪裁版 8 条 +
      教学边界）作系统提示词来源，风格档案 `configs/small_lecturer_style_profiles.yaml`
      按年级选 profile
- [ ] 题图校验：含图题目经 gateway `vision` 角色做图意理解与「题图不可信/多题混入」
      检测（03 §4 Preparing → Failed 的 fail closed）；纯文本题跳过
- [ ] 结构化输出走 gateway 路线 1（json 一次通过率是 M2 验收口径之一，见阶段 4），
      agent 不自己解析文本

**阶段 2 教学护栏对齐（写内核的第一验收）**
- [ ] `make check` 全绿，**tests/teaching/ 断言零跳过**（#45 迁入的 74 条：答案泄露/
      语气/格式三类，含假上游接线用例——02 §6 预定的五类测试之首）
- [ ] 内核输出路径上三护栏全部生效（泄露 FALLBACK / 语气 applied / 格式降级提示），
      护栏不过的输出不得到达学生可见面；测试用假上游，不调真实模型

**阶段 3 调优循环（白天人环、夜里算力，复用 M1 过夜设施）**
- [ ] 被测对象换内核：runner 的 Subject 协议新增 KernelSubject 实现（M1 适配器
      同款接口，评测线代码零改动）；judge 复用 #32 六维评分器
- [ ] 一轮 45 分钟级（11 场景收集 + 评分，评分与收集错峰——Run 1 纪律，8301 不争用）；
      计划按天多轮，每轮产物进 run 目录 + 晨间摘要
- [ ] 每轮对照基线报告逐维看差，prompt/风格档案级别调整优先，不动 gateway 与数据集

**阶段 4 追平门执行（§4.3，4 周时限自 M0 关门起算）**
- [ ] 11 场景逐条**不劣于**老系统基线；容差引 A 线两夜方差对照结论
      （**待基线报告 PR 定稿**，方差 >10% 的指标按基线报告口径处理）
- [ ] json 一次通过率 ≥98%（路线 1 口径，从 model_call 事实记录统计；
      参考 #39 judge 稳定性档案首档的测量形态）
- [ ] 每周归档一份完整报告（scheduled workflow 打 tag，§4.3）

**模型风险预案（tutor = 9B 数学可靠性，#34 已记录抽测算术口误）**
- 降级触发：judge 六维评分中与数学正确性相关的维度（#32 定稿口径）**连续两轮低于
  基线** → 切换动作 = models.yaml 的 tutor 主选一行换 `mlx_27b`（configs/ 结构路径，
  人批；judge 稳定性档案同步留痕）。不自行静默切换。

**开放决策（留人）**
1. C 线（agents 内核专线）是否开：00 §8.1 原计划「M2 增内核线」；内核工作量集中在
   `edu_agent/agents/`，与 B 线评测调优的并行度取决于此。开则三线并行（每线 PR 上限
   照 §8.1），不开则内核与调优串行。
2. 覆盖面冻结在 11 场景：M2 期间不动靶子（追平门按当前基线数据集执行）；扩到
   21 数据集全量属 M2 后决策，届时按 §4.3 重定门。

**出口（§8 表）**：全部数据集不劣于基线（M2 期间=11 场景），教学护栏全绿，
json 一次通过率 ≥98%。

### 8.5 M3 落地清单（进入里程碑时补齐，2026-09-07；执行状态挂看板 #34 延续）

时限「视情况」（§8 表）；硬锚点 = 合作方联调窗口 3–5 天（排期见开放决策②）。
原则：**合同是法律文本**——00 §5.2 复用清单与 #48 快照即全部规格，api 包装层只
装配不发明（#55 的 Kernel 协议注入已是装配形态，M3 = stub 换真内核 + 真实环境
接线，无新合同）；**App 侧零改动是硬承诺**，任何需要合作方改代码的方案都否决。
前置件双线并行（评测线 / gateway 与模型服务线），核心件串行。

**前置件（与清单 PR 并行开工，双线）**
- [ ] A 线·内核换插：api 层 Kernel 协议的 stub → 真内核三函数（#59/#60）——gateway
      注入接通；GatewayError→错误码映射（connection/timeout 族→503，
      SessionVersionConflict→409 SKILL_SESSION_CONFLICT，内核已承接语义）
- [ ] A 线·题源适配器：question_id → 题干/答案/解析/图/知识点（release_acceptance
      题库直读或本地 JSON 起步；`answer_status` 一并填入 learner——R6 首问策略
      分派与结构化 summary 的信号源，内核侧已就绪）
- [ ] A 线·vision 接线：models.yaml 加 vision 角色（8303）+ 内核 vision schema 扩
      transcription；answer/analysis 进教师侧 prompt（configs/ 结构路径，人批）
- [ ] A 线·知识点消费：按 #48 合同确认是否回传合作方；教学侧进 prompt 当追问锚点
      （题库 `knowledge_points` 字段已随 #29 迁入）
- [ ] B 线·store 与身份路由：会话持久化 v1 内存 → 文件级（additive-only，02：
      M3 只允许 additive）；identity HTTP 路由挂接（#63 RS256 纯逻辑已有，
      路由随 api server 扩展）

**核心（前置件全合后，串行）**
- [ ] 合同终审：审查者拿 #48 Postman 全量打真内核（真题图、真断言 PKCE、真题库
      适配），全绿 = M3 出口前置——#57 的回放测试从 stub 内核切真内核即成
- [ ] 切换 runbook 成文：cloudflare proxy 上游改指新服务（DNS 不动，切换动作最小）；
      回滚 = proxy 改回；老系统挪内网地址后继续供题库操作面（16 路径，#34 已定案：
      合作方只用对话面 5 + 身份 2，无路径分路）；合作方通知文案
- [ ] 测试域切换（人按键）→ 合作方 Postman 自行验证 → 联调窗口（3–5 天）

**出口（§8 表 + §4.3）**
- 合同测试全绿；合作方 Postman 样例原样通过；App 侧零改动
- 效率/稳定性在真实流量下达 01 §5/§6 阈值（main CI benchmark 持续绿）；
  报告按 #66 口径披露义务标注（工程模板兑现 vs 模型生成分开陈述）

**开放决策（人批；①③须在合同终审前定）**
1. 生产基础设施：机器放哪（本机 Mac 不适合作生产）；模型跟不跟（27B/9B 需大内存
   GPU 机器 vs 生产切云 API——隐私与成本的权衡）
2. 联调窗口时长与合作方排期（对方 App 发版周期）
3. 公网部署预案：域名、证书、监控

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
