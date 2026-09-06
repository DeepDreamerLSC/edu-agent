# 01 模型调用链路：效率与稳定性

状态：草案（2026-09-06）。这是重写的核心设计，其余部分围绕它展开。

## 1. 老链路的问题

老仓库 `edu_agent/app/models/` 的现状：

| 文件 | 行数 | 职责 |
|---|---|---|
| gateway.py | 2325 | 路由、优先级老化、身份、事实记录、流式，全在一个类里 |
| worker_sidecar.py | 1728 | 自研 worker 边车 |
| providers/external_http.py | 1382 | 外部 HTTP provider，含身份链路 |
| mlx_batch_engine.py + mlx_vlm_continuous_engine.py + mlx_vlm_batching.py | 2325 | 进程内推理引擎 |
| runtime_inventory / supervisor / manifest / release_preflight | 2200+ | 运行时身份与发布仪式 |
| worker_pool.py + batch_scheduler.py | 938 | 池与调度 |

另有 11 份 model_registry 配置、6 种 provider 类型（external_http、managed_external、mlx_text、
system_vision、question_render_service、openai_compatible）、30 余个模型条目。

最近 300 次提交中 33 次是在修这条链路上的租约、预载、身份恢复、并发配置。
症状是稳定性问题，根因是**链路承担了三个本不该属于它的职责**：

1. 进程管理（启动、预载、心跳、恢复本地推理进程）
2. 调度（worker 池、租约、批处理）
3. 发布治理（运行时身份、preflight、release smoke）

## 2. 设计原则

1. **gateway 是 HTTP 客户端，不是进程管理器。** 本地模型以独立服务进程运行
   （llama-server、mlx-lm server、vLLM 任一），暴露 OpenAI 兼容接口。进程的生死交给
   systemd / launchd / 容器编排，不交给 Python。
2. **一种协议。** provider 只实现 OpenAI 兼容 chat completions（含 streaming、json_schema、tool calls）。
   Anthropic 原生协议作为第二个可选 provider，仅在需要 prompt caching 或其独有能力时启用。
   不再有五六种 provider。
3. **调用是纯函数加边车。** `invoke(request) -> response` 不读全局状态、不持久化、不重试；
   重试、超时、限流、记录、脱敏都是围绕它的中间件，每个中间件单独可测。
4. **失败有类型。** 每个失败归入固定枚举，不允许裸 Exception 冒出 gateway。
5. **每次调用一条事实记录。** 不记录就等于没发生。事实记录是效率与稳定性指标的唯一来源。
6. **配置一份。** 一个 `models.yaml`，按角色（tutor、judge、simulator、vision）声明主选与备选模型。
   环境差异用环境变量覆盖，不复制整份文件。

## 3. 结构

```
edu_agent/
  gateway/
    __init__.py         # invoke / stream 两个入口
    request.py          # ModelRequest / ModelResponse / StreamEvent 数据类
    providers/
      openai_compatible.py
      anthropic.py      # 可选
    middleware/
      timeout.py        # 总超时 + 首 token 超时
      retry.py          # 按失败类型决定是否重试，指数退避 + 抖动
      ratelimit.py      # 按角色/模型的并发信号量
      fallback.py       # 主选失败按策略切备选
      redact.py         # 学生内容脱敏，在记录之前
      record.py         # model_call 事实记录
    errors.py           # 失败类型枚举
    registry.py         # models.yaml 加载与角色解析
  evals/
  agents/small_lecturer/
```

调用链固定为：

```
request → registry(解析角色→模型) → ratelimit → retry → fallback → timeout → provider
                                                                          ↓
                              response ← redact ← record ←────────────────┘
```

## 4. 失败类型

| 类型 | 含义 | 可重试 | 触发备选 |
|---|---|---|---|
| `timeout_first_token` | 首 token 超时 | 是 | 是 |
| `timeout_total` | 总时长超时 | 否 | 是 |
| `rate_limited` | 429 | 是（读 Retry-After） | 第二次起 |
| `upstream_5xx` | 上游服务错误 | 是 | 第二次起 |
| `upstream_4xx` | 请求本身错（模型不存在、上下文超长） | 否 | 否 |
| `schema_violation` | json_schema 输出不合规 | 是（一次，带修复提示） | 否 |
| `truncated` | finish_reason=length | 否 | 否 |
| `content_filtered` | 上游内容过滤 | 否 | 否 |
| `connection` | 连不上 | 是 | 是 |

重试次数、退避、备选策略全部在 `models.yaml` 按角色声明，不写死在代码里。

## 5. 效率指标

| 指标 | 定义 | v1 阈值（tutor 角色） |
|---|---|---|
| TTFT p50 / p95 | 请求发出到首 token | 云 API：p95 < 1.5 s；本地：p95 < 3 s |
| 端到端 p50 / p95 | 请求发出到完成 | 按数据集记录，不设绝对阈值，只设"不劣于基线 10%" |
| 生成速度 | 输出 tokens / 生成秒数 | 本地服务 p50 > 20 tok/s |
| 并发吞吐 | 16 并发下每分钟完成的对话轮数 | 不劣于基线 |
| 缓存命中 | prompt caching 命中的输入 token 占比（支持的 provider） | 系统提示词部分 > 80% |
| 单轮成本 | 按 provider 定价折算 | 报告中列出，不设阈值 |

所有指标来自 model_call 事实记录，由 `evals/report` 汇总。基准测试进 CI，
用固定的 20 条对话回放，比较 p95 与上次基线，劣化超过 10% 即失败。

## 6. 稳定性指标

| 指标 | 定义 | v1 阈值 |
|---|---|---|
| 成功率 | 最终返回有效响应的调用比例（含重试与备选） | > 99.5% |
| 首次成功率 | 不经重试即成功 | > 97%，用于发现上游劣化 |
| 结构化输出合规率 | json_schema 一次通过 | > 98% |
| 备选触发率 | 切到备选模型的比例 | < 1%，超过报警 |
| 超时率 | timeout_* 占比 | < 0.5% |

**故障注入测试**是 CI 的一部分。用一个假 OpenAI 兼容服务器按脚本注入：
延迟、429、500、连接中断、截断响应、非法 JSON、流式中途断开。
每种故障对应一个测试，断言 gateway 落到正确的失败类型、重试次数正确、
备选按策略触发、事实记录完整。

## 7. model_call 事实记录

每次调用一条 JSON 行，字段固定：

```
call_id, ts, role, requested_model, actual_model, provider, attempt,
outcome(ok|<失败类型>), ttft_ms, total_ms, input_tokens, output_tokens,
cached_input_tokens, finish_reason, fallback_from, redacted, trace_id
```

- v1 写 JSONL 文件，按天切分。M3 再决定是否入库。
- 学生内容不进记录。`redact` 中间件在记录之前把消息体替换为长度与哈希。
- 老仓库的 model_calls 表有 tenant_id、client_id、traffic_class 等十几个维度列，
  v1 只保留上面这些，多租户维度在 M3 按需加。

## 8. 本地模型的运行方式

老链路把 MLX 引擎放在 Python 进程内，导致预载、显存、并发、恢复全部成为应用层问题。
新做法：

- 本地模型服务以独立进程运行，OpenAI 兼容接口，由 launchd（Mac）或 systemd（Linux）管理。
  v1 目标机器是本机 Mac（M5 Max，128 GB）；首选 mlx-lm server 跑 Qwen3.5-27B 4bit 作 tutor，
  llama-server 跑 Qwen3.5-9B GGUF 作本地 judge 备选，两者都是老系统已验证可跑的模型。
- gateway 对它与对云 API 一视同仁，只是 base_url 不同。
- 健康检查是 gateway 启动时对每个 base_url 发一次 `/v1/models`，不通即在事实记录里标记，不阻塞启动。
- 需要更强的路由、预算、多 key 轮换时，在 gateway 与上游之间放 LiteLLM proxy，
  gateway 代码不变。这一步不在 v1。

## 9. 不做

- 不自研 worker 池、租约、心跳、预载。
- 不做运行时身份契约与 release preflight。
- 不在 gateway 里做批处理调度。需要批量时由评测 runner 控制并发，gateway 只管单次调用。
- 不做 provider 插件系统。两个 provider 文件够用。

## 10. 验收

M0 结束时：

- [ ] 对一个云 API 与一个本地服务，invoke 与 stream 均跑通
- [ ] 9 种失败类型各有一个故障注入测试
- [ ] 基准测试进 CI，产出第一份效率报告
- [ ] 事实记录字段齐全，脱敏测试通过
- [ ] `models.yaml` 一份，tutor / judge 两个角色各有主选与备选
