# 03 整体架构图

状态：**M2 收尾对齐**（2026-09-10）；最后核对 commit：`b5b9c77`。

读法：**第 1 节是全景观（首屏）**，其后按"从外到内"排：分层依赖 → 教学时序 → 评测数据流 →
**隐形契约清单** → gateway 中间件链 → 会话状态机 → 与老仓库对照。
图中**只保留必要名称**（文件路径 / 类名 / 合同名 / 状态名 / 命令），其余一律中文。
每张图下方挂「**校验源**」——图与代码同源可查；文末有「如何验证本图仍成立」。

## 1. 全景观（上下文与部署）

```mermaid
flowchart TB
    subgraph Ext["外部"]
        App["合作方学生端"]
        QBank["合作方题库接口"]
        Cloud["云模型接口"]
        Local["本地模型进程<br/>8301 mlx · 8302 27B · 8303 VL-8B"]
    end

    subgraph Prod["生产路径（走 HTTP）"]
        Svc["scripts/serve_partner_api.py<br/>令牌验签 · 跨域白名单 · HTTP 三处修复"]
        Adapter["PartnerKernel / kernel_adapter<br/>状态机映射 · 冲突转 409"]
        Svc --> Adapter
    end

    subgraph Eval["评测路径（不经 HTTP）"]
        TR["scripts/tuning_round.py（夜评）"]
        Runner["evals/runner（评测运行器）"]
        Subjects["KernelSubject / legacy_adapter（被测对象）"]
        Judge["evals/judge（六维评审）"]
        TR --> Runner
        Runner --> Subjects
        Runner --> Judge
    end

    subgraph CI["持续集成与调度（Mac 自托管运行器）"]
        MainCI["main.yml<br/>检查 + 效率基准"]
        Nightly["evals-nightly.yml<br/>每日 15:00 UTC 触发"]
    end

    Core["内核三函数<br/>start · reply · finish"]
    GW["gateway（模型网关）<br/>唯一咽喉点"]
    Facts[("model_call 事实记录<br/>JSONL · 跨夜累计")]
    Rep["报告<br/>comparison.md 与工件"]
    Gate{"容差判定<br/>对照 baselines 与 R1×R2 区间"}

    App --> Svc
    Adapter --> QBank
    Adapter --> Core
    Subjects --> Core
    Core --> GW
    Judge --> GW
    GW --> Cloud
    GW --> Local
    GW --> Facts
    Facts --> Rep
    Nightly --> TR
    Rep --> Gate
    Gate --> Board["#34 判定表"]
```

**要点**（相对 2026-09-06 草案的更新：接口层已实现、不再是 M3 虚线；新增夜评与调度、模型端口）

- **一个咽喉点**：所有模型调用经模型网关（gateway）；内核与评审器都不直接碰模型供应商。
- **两条路径**：生产走 HTTP（`serve_partner_api.py`）；**评测不经 HTTP**，评测运行器直调内核三函数。
- **网关只是 HTTP 客户端**：本地模型进程独立，生死不归 Python 管。
- **事实记录是唯一审计源**：效率、稳定性、结构化输出合规率全部从 `model_call` JSONL 汇总，不另建观测后台。

> 校验源：`scripts/serve_partner_api.py`、`configs/models.yaml`、`.github/workflows/{main,evals-nightly}.yml`

## 2. 分层依赖（可执行的四条合同）

```mermaid
flowchart LR
    api["api"] --> agents["agents"]
    api --> store["store"]
    api --> contracts["contracts"]
    agents --> gateway["gateway"]
    agents --> contracts
    evals["evals"] --> agents
    evals --> gateway
    evals --> contracts
    gateway --> contracts
```

（图为 6 个包的**合法依赖方向**；包名与合同名为必要名称，故不译。）

| 合同（`import-linter`） | 禁止 |
|---|---|
| `gateway-no-agents-evals-api-store` | 网关不得依赖内核、评测、接口层、存储 |
| `agents-no-api-store` | 内核不得依赖接口层、存储 |
| `evals-no-api` | 评测不得依赖接口层 |
| `contracts-imports-nothing-internal` | 合同包不依赖任何内部包 |

> 校验源：`uv run lint-imports`（红灯测试 `tests/rules/test_import_contracts.py`）

## 3. 教学时序（含三护栏与判停点）

```mermaid
sequenceDiagram
    participant S as 学生
    participant K as 内核 reply()
    participant G as 模型网关
    participant GD as 护栏

    Note over K: start()：一次结构化调用 → 转写 · 分步解 · 首问
    S->>K: 学生消息
    alt 说「懂了」
        K-->>S: 固定复讲引导（确定性，不调模型）
    else 说「不会」
        K-->>S: 阶梯揭示（记 guard_events 事件：reveal）
    else 命中已知答案（#112 判据）
        K-->>S: 固定复讲引导（记事件：elicit）
    else 其他
        K->>G: 模型调用（结构化输出）
        G-->>K: 回复文本 · 可确认标志 · 自报引用数字
    end
    K->>GD: 三道护栏（泄露 / 语气 / 格式）+ 数字漂移（抽取制）
    GD-->>K: 通过 / 重生成 / 兜底句并记 stuck
    K->>K: 状态 = 可确认标志为真 ? 可确认 : 对话中
    Note over K: 【判停点】可确认标志为真 → 评测运行器立即跳出剧本循环，剧本被截断（#149 在此加闸）
```

> 校验源：`edu_agent/agents/small_lecturer/kernel.py`、`tests/teaching/`（157 例，零跳过）

## 4. 评测数据流（含口径注入点）

```mermaid
flowchart LR
    DS[("数据集（datasets/*.json）<br/>M2 冻结靶子＝11 个场景")] --> TR["scripts/tuning_round.py<br/>口径 P：仅 word_problem 注入 answer_status=correct"]
    TR --> Cases["用例集（含 student_turns 剧本）"]
    Cases --> Runner["evals/runner（评测运行器）"]
    Runner --> KS["KernelSubject<br/>【隐形】可确认标志为真即停发余下剧本轮"]
    Runner --> LA["legacy_adapter（老系统基线侧）<br/>【隐形】不接收 answer_status"]
    KS --> J["evals/judge（六维评审，经网关）"]
    LA --> J
    J --> CMP["报告 comparison.md 与 judge-scores.json"]
    J --> IPC["json_first_pass（结构化输出合规率，事实记录跨夜累计）"]
    J --> IMG["题图段（题图评测集 v1 · 8 题）"]
    CMP --> Tol{"tolerance_verdict（容差判定）<br/>对照 R1×R2 区间"}
    Tol --> Board["#34 判定表"]
    Bench["scripts/benchmark.py（效率基准）<br/>20 条固定回放"] --> Eff[("baselines/efficiency.json（效率基线）")]
```

另有三套口径并存：**P**（判门口径，夜评用）、**F**（生产同构，唯一能触发五步弧线）、
**R**（修复对照口径）——引用任何数字前先确认口径（历史上最容易混淆的一处）。

> 校验源：`scripts/tuning_round.py`、`edu_agent/evals/`、`baselines/efficiency.json`

## 5. 隐形契约清单（**本版新增，最重要**）

这些语义**不在任何报告里出现**，只能读代码或数工件才知道——上一轮定位一个判门失败场景，
代价是8 次工具调用 + 通读 4 个模块：

| # | 隐形契约 | 位置 | 后果 |
|---|---|---|---|
| 1 | **剧本截断**：可确认标志为真即停发余下剧本轮 | `evals/kernel_subject.py` | 4 轮剧本可能只跑 2 轮，报告不可见 |
| 2 | **口径注入不对称**：`answer_status` 只给内核侧 | `scripts/tuning_round.py:117` | 该场景对我们比基线更难（待裁定 → #152） |
| 3 | **护栏「无答案模式」**：评测不传答案 | `KernelSubject` 与内核放宽分支 | 评测泄露数字不等于生产；`_known_answer` 的分步解兜底**未接到护栏**（#149 第②项） |
| 4 | `minimum_student_turns` 无人读取 | 数据集 JSON | 装饰性元数据；"最少四轮"从未被强制 |
| 5 | 事实记录跨夜累计（`EDU_FACTS_DIR`） | `evals-nightly.yml` | 合规率分母是**累计样本**（134 而非 67） |
| 6 | 评审器单遍、温度为 0 | `configs/models.yaml` | 同输入判定确定 → 11 个场景跨帧逐项同值（已实证） |
| 7 | 评测不跑 HTTP；事实记录为唯一审计源 | 架构约定 | 生产路径的 HTTP 行为不由评测覆盖 |

## 6. 模型网关的中间件链

```mermaid
flowchart LR
    Req["模型请求<br/>角色 = 内核 / 评审 / 视觉"] --> Reg["registry<br/>角色注册表：主选与备选"]
    Reg --> RL["ratelimit<br/>按角色并发信号量"]
    RL --> RT["retry<br/>按失败类型 · 指数退避"]
    RT --> FB["fallback<br/>主选失败切备选"]
    FB --> TO["timeout<br/>首 token 与总时长"]
    TO --> P["provider<br/>供应商适配"]
    P --> Up["上游"]
    Up --> P
    P --> RD["redact<br/>内容转为长度与哈希"]
    RD --> RC["record<br/>落盘一行 JSONL"]
    RC --> Resp["模型响应<br/>或 9 种失败类型之一"]
```

每个中间件单独可测；故障注入用假上游逐一触发 9 种失败类型（PR 持续集成只跑故障注入，不测真实延迟）。

> 校验源：`tests/gateway/`、`.github/workflows/ci.yml`

## 7. 小讲师会话状态机（对应合作方接口合同）

```mermaid
stateDiagram-v2
    [*] --> Opened: 建会话（幂等键）
    Opened --> Preparing: 解析题目并固定题面
    Preparing --> FirstQuestionReady: start() 成功
    Preparing --> Failed: 题图不可信或多题混入，直接失败
    FirstQuestionReady --> Dialogue: 学生首次回答
    Dialogue --> Dialogue: reply()，会话版本加一
    Dialogue --> Conflict: 旧会话版本，返回 409
    Conflict --> Dialogue: 客户端刷新后重发
    Dialogue --> ReadyToConfirm: 掌握证据充分（★ 隐形契约一的判停点）
    Dialogue --> NeedsReview: finish() 证据不足或答案未复核
    NeedsReview --> Dialogue: 继续追问
    ReadyToConfirm --> Completed: 确认后写入不可变总结
    Completed --> [*]
    Failed --> [*]
```

状态名（必要名称，与老仓库合同逐字对应）释义：Opened＝已开启，Preparing＝准备中，
FirstQuestionReady＝首问就绪，Dialogue＝对话中，NeedsReview＝待复盘，ReadyToConfirm＝可确认，
Completed＝已完成，Failed＝失败。旧版本状态在内存（接口层已实现）；存储落在 M3。

## 8. 与老仓库的对照

| 维度 | 老仓库 | 本仓库 |
|---|---|---|
| 顶层包 | 30+ | 6 |
| 模型调用 | gateway 2333 行 + worker 边车 + 进程内引擎 + 6 种 provider | 网关注干中间件 + 两种供应商，本地模型进程外 |
| 对外接口 | 通用对话 + 技能信封 + 专用流程并存 | 专用流程路径已实现（`serve_partner_api.py`），内核纯函数 |
| 评测 | 依赖数据库、后台、身份服务 | 直调内核，JSONL 进 JSONL 出；夜评每日一帧 |
| 观测 | 自建流量页、链路页、调用表十几个维度 | JSONL 事实记录 + 夜评报告 |
| 治理 | 113 行宪法 + 本地持续集成仪式 + 棘轮豁免 | 一页规则 + 硬预算无豁免 + PR 关卡 |

## 9. 如何验证本图仍成立

```bash
make check                                   # 测试 / 合同 / 预算 / 结构全绿
uv run lint-imports                          # 第 2 节的四条依赖合同
gh run list --workflow nightly --limit 3     # 第 1、4 节的夜评线是否仍在跑
gh pr view <n> --json files                  # 改动是否落在本图所示模块
```

改图时请同步更新文首的「最后核对 commit」。**不做**图自动生成与持续集成校验图（收益低于成本）。
