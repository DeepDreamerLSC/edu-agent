# 03 整体架构图

状态：草案（2026-09-06）。图中实线部分是 v1（M0–M2）范围，虚线部分在 M3 才实现。

## 1. 整体架构

```mermaid
flowchart TB
    subgraph External["外部"]
        Partner["合作方学生 App"]
        Cloud["云模型 API<br/>(OpenAI 兼容 / Anthropic)"]
        Local["本地模型服务进程<br/>llama-server / mlx-lm / vLLM<br/>由 launchd / systemd 管理"]
        QBank["合作方题库接口<br/>GET /v1/questions/{id}"]
    end

    subgraph Repo["edu-agent（本仓库）"]
        subgraph API["api（M3）"]
            Routes["老路径包装层<br/>open / refresh / messages / confirm<br/>native-codes / token"]
        end

        subgraph Agents["agents/small_lecturer"]
            Core["内核：纯函数<br/>start · reply · finish"]
            Teaching["教学合同<br/>首问不泄露答案 · 语气护栏<br/>年级表达 · 追问节奏"]
        end

        subgraph Gateway["gateway"]
            Invoke["invoke / stream"]
            MW["中间件链<br/>ratelimit → retry → fallback → timeout"]
            Prov["providers<br/>openai_compatible · anthropic"]
            Rec["record + redact"]
        end

        subgraph Evals["evals"]
            Runner["runner"]
            Judge["judge"]
            Report["report<br/>效率 · 稳定性 · 教学指标"]
        end

        Contracts["contracts<br/>接口合同快照 · schema"]
        Store["store（M3）<br/>会话持久化"]
        Facts[("model_call 事实记录<br/>JSONL，按天切分")]
        Datasets[("evals/datasets<br/>21 个数据集 + 合作方样本")]
    end

    Partner -. M3 .-> Routes
    Routes -. M3 .-> Core
    Routes -. M3 .-> Store
    Routes -. M3 .-> QBank

    Core --> Invoke
    Core --- Teaching
    Invoke --> MW --> Prov
    Prov --> Cloud
    Prov --> Local
    Prov --> Rec --> Facts

    Datasets --> Runner
    Runner -->|直接调用，不经 HTTP| Core
    Runner --> Judge --> Invoke
    Facts --> Report
    Runner --> Report

    Contracts -. M3 合同测试 .-> Routes

    classDef m3 stroke-dasharray: 5 5
    class API,Routes,Store m3
```

要点：

- **一个咽喉点**：所有模型调用经 gateway，agent 与 judge 都不直接碰 provider。
- **评测不经 HTTP**：runner 直接调内核三个函数，所以 v1 没有 api 层也能跑通评测。
- **gateway 只是 HTTP 客户端**：本地模型服务是独立进程，进程生死不归 Python 管。
- **事实记录是唯一审计源**：效率与稳定性指标全部从 JSONL 汇总，不另建观测后台。

## 2. gateway 中间件链

```mermaid
flowchart LR
    Req["ModelRequest<br/>role=tutor|judge"] --> Reg["registry<br/>角色 → 主选/备选模型"]
    Reg --> RL["ratelimit<br/>按角色并发信号量"]
    RL --> RT["retry<br/>按失败类型决定<br/>指数退避 + 抖动"]
    RT --> FB["fallback<br/>主选失败切备选"]
    FB --> TO["timeout<br/>首 token + 总时长"]
    TO --> P["provider<br/>HTTP 调用"]
    P --> Up["上游"]
    Up --> P
    P --> RD["redact<br/>学生内容 → 长度+哈希"]
    RD --> RC["record<br/>写一行 JSONL"]
    RC --> Resp["ModelResponse<br/>或 9 种失败类型之一"]
```

每个中间件单独可测；故障注入测试用假上游服务器逐一触发 9 种失败类型，断言链上每一环的行为。

## 3. 评测线流程

```mermaid
flowchart LR
    DS[("数据集<br/>JSONL")] --> R["runner<br/>控制并发"]
    R --> A["被测对象"]
    A --> A1["新内核<br/>start · reply · finish"]
    A --> A2["老系统<br/>evals 内的被测对象适配器<br/>驱动合作方流程接口（M1 基线）"]
    A1 --> J["judge<br/>经 gateway"]
    A2 --> J
    J --> Rep["报告<br/>Markdown + JSON"]
    F[("model_call<br/>事实记录")] --> Rep
    Rep --> Gate{"追平门<br/>不劣于基线<br/>指标达阈值"}
    Gate -->|通过| M3["进入 M3 对齐"]
    Gate -->|6 周未通过| Review["停下复盘<br/>哪些老复杂度是必要的"]
```

## 4. 小讲师会话状态机（对应合作方接口合同）

```mermaid
stateDiagram-v2
    [*] --> Opened: POST .../open，idempotency_key
    Opened --> Preparing: 解析题目，固定 question
    Preparing --> FirstQuestionReady: start() 成功
    Preparing --> Failed: 题图不可信 / 多题混入，fail closed
    FirstQuestionReady --> Dialogue: 学生首次回答，expected_session_version
    Dialogue --> Dialogue: reply()，session_version + 1
    Dialogue --> Conflict: 旧 session_version，409 SKILL_SESSION_CONFLICT
    Conflict --> Dialogue: 客户端刷新后重发
    Dialogue --> ReadyToConfirm: 掌握证据充分
    Dialogue --> NeedsReview: finish() 证据不足，或答案未复核
    NeedsReview --> Dialogue: 继续追问
    ReadyToConfirm --> Completed: interaction_action=confirm，写入不可变 summary
    Completed --> [*]
    Failed --> [*]
```

状态与老仓库合作方文档中的 `first_question_ready`、`session_version`、`ready_to_confirm`、
`completed`、`needs_review` 一一对应。v1 状态在内存，M3 落到 store。

## 5. 与老仓库的对照

| 维度 | 老仓库 | 本仓库 |
|---|---|---|
| 顶层包 | 30+ | 6 |
| 模型调用 | gateway 2333 行 + worker 边车 + 进程内引擎 + 6 种 provider | gateway 若干中间件 + 2 个 provider，本地模型进程外 |
| 对外接口 | 通用对话 + skill 信封 + 专用流程并存 | 只保留专用流程路径，内核纯函数 |
| 评测 | 依赖数据库、后台、身份 | 直接调内核，JSONL 进 JSONL 出 |
| 观测 | 自建流量页、trace 页、model_calls 表 十几个维度 | JSONL 事实记录，需要时 DuckDB 查 |
| 治理 | 113 行宪法 + Local CI 仪式 + 棘轮豁免 | 一页规则 + 硬预算无豁免 |
