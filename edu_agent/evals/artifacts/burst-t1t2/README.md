# burst-t1t2:课堂拍题压测 T1/T2 读数(2026-09-18,#255 判据2 第1件;PASS)

预注册:PM 直发 233d0fca,摘要 sha256=99ce7b99b7d47164(判读标准跑前锁定,跑后未改)。
隔离实例 = restore-into-service 演练同款复用(#255 第 3 件回执 c5717633546):Mac
`~/edu-agent-restore-drill-20260917T161259Z/`,fresh checkout **main 07dc4c09**,端口 8310,
DB = 自动备份 `edu-agent-20260916T193001Z.db` 副本(sha256 `27b89222…3860a9`,起跑基线 46
条会话),`.env.test` 夹具拷贝。生产服务/生产 DB/观察窗全程零触碰;零 API(deepseek 未拨)。

## 程序(照预注册)

- **T1(stub 上游,纯服务栈)**:`EDU_MODELS_YAML` 指向 `models.t1stub.yaml.txt`——
  与生产 models.yaml 同构,全部 provider 指向本地 stub 进程(`stub_server.py.txt`,
  127.0.0.1:8321,固定延迟 150ms)。stub 逆向利用路线 1(schema 以文本附在 user 消息),
  从请求里解析 JSON Schema 并按类型最小填充——覆盖 open/turn/summary 任意形状。
  **零产品代码改动**(网关 `EDU_MODELS_YAML` 既有覆盖点,gateway/__init__.py L151)。
- **T2(本地模型,真实推理)**:原版 models.yaml(tutor 主选 `qwen3_vl_8b` = 本地
  8303 VL 服务;llama 8302/mlx 8301 在跑,vision 缺口无——三上游 healthz 全 true)。
- **负载形态**(`burst_load.py.txt`,标准库 asyncio,合同步骤改自 scripts/m3_smoke.py):
  N 路(30 与 50 两档)在 2s 窗口内均匀随机起跑,每路完整合同走查:login →
  open(幂等键)→ open 幂等重放 → 轮1 → 轮2(消息幂等键)+ 重放 → SSE 轮(首 token
  计时)→ confirm。读数全走既有观测面:HTTP 状态分类、相位 P50/P95/max、SSE 掉线
  (无 done 帧)、幂等破坏(重放漂移)、/healthz 秒级轮询(store probe_failures)、
  进程采样(ps rss + lsof 句柄,`t*_sampler.log`)、网关 facts(`edu.queue_ms`)。
- 每场之间:停服、删 `edu-agent.db-wal/-shm`、重拷备份副本(基线回到 46)。

## 读数(四场,原始件 `t{1,2}_{30,50}.json`,每 worker 逐相位)

| 场 | 请求 2xx | 5xx/超时 | busy/locked | SSE 掉线 | 幂等破坏 | 完整走通 | confirm | probe_failures | wall |
|---|---:|---:|---:|---:|---:|---|---|---:|---:|
| T1-30 | 240/240 | 0 | 0 | 0 | 0 | 30/30 | completed×30 | 0 | 11.6s |
| T1-50 | 400/400 | 0 | 0 | 0 | 0 | 50/50 | completed×50 | 0 | 19.2s |
| T2-30 | 240/240 | 0 | 0 | 0 | 0 | 30/30 | completed×30 | 0 | 123.8s |
| T2-50 | 400/400 | 0 | 0 | 0 | 0 | 50/50 | completed×50 | 0 | 244.4s |

服务日志(T1/T2 各自 service log)grep busy/locked/Traceback:0/0。DB 计数逐场精确吻合
(46+30 → 77;46+50 → 96;T2 两场后 126 = 46+30+50)。

### 相位延迟(ms;P50 / P95 / max)

| 场 | open | 轮1 | 轮2(幂等) | SSE 首 token | SSE 总 | confirm |
|---|---|---|---|---|---|---|
| T1-30 | 1101/2243/2261 | 4304/4461/4472 | 1/3/4 | 1990/2297/2300 | 1990/2297/2300 | 1820/2172/2305 |
| T1-50 | 1863/3656/3801 | 7655/7674/7674 | 1/2/4 | 3707/3841/3845 | 3707/3841/3845 | 3102/3843/3844 |
| T2-30 | 19809/38787/38902 | 33045/39730/39740 | 1/3/3 | 30515/33985/33986 | 30515/33985/33986 | 28397/33340/33341 |
| T2-50 | 42561/79348/82743 | 67146/81303/82480 | 2/3/4 | 58245/65363/65837 | 58245/65363/65837 | 54789/64189/65161 |

- **T1 纯栈基线**:P95 全部 <8s,且与「stub 延迟 × tutor concurrency=2」排队算术吻合
  (30 路 open 30×153/2≈2.3s ≈ 实测 2.24s;50 路 50×153/2≈3.8s ≈ 3.66s)——服务栈
  (HTTP/SQLite/合同面/幂等/SSE)自身在 50 路拍题下毫秒级开销、零错。
- **T2 本地推理主导**(预注册:不作硬门):P95 = VL 真实推理 × concurrency=2 排队。
  facts 侧 `edu.queue_ms`:P50 3673 / P95 63789 / max 80002,零等待占比 1.9%。
- 内存/句柄:T1 峰值 rss 63MB / 60 句柄;T2 峰值 rss 76MB / 62 句柄(无泄漏迹象)。

### 调用计数(facts,`t{1,2}_facts.jsonl`)

- T1 stub 调用 405( sanity 5 + 30 路 150 + 50 路 250),T1 不计本地推理。
- **T2 本地调用 725**(30 路 ≈272 + 50 路 ≈453),全部 `tutor` / `qwen3_vl_8b`
  (本地 8303):**零 deepseek、零远端 API、零 fallback、attempt 全 1、outcome 全 ok**。
  真实内核每 worker ≈9 次调用(首问/轮复/自评/总结路径),高于 stub 路径的 5 次
  ——T2 负载是真实课堂形态,不是缩水版。

## 判读(预注册硬信号,唯一正本)

| 硬信号(任一出现=不通过) | 阈值 | 实测 | 判 |
|---|---|---|---|
| SQLite busy 风暴 | >1% 请求 | 0 起(日志+probe_failures 0) | ✓ |
| 5xx | >1% | 0/1280 | ✓ |
| SSE 掉线 | >5% | 0/80 路 | ✓ |
| 幂等破坏(双 committed turn) | 任何 | 0(open/消息两级重放全一致) | ✓ |

**T1/T2 通过。** T2 P95 绝对值(50 路 open ≈79s)由本地推理 × concurrency=2 主导,
属预注册的正常形态;差分信号(错误率/掉线/busy)全零。排队读数供 T3 试点并发策略
呈裁:concurrency=2 下 50 路拍题的 P95 排队 ≈64-80s——课堂场景建议随 T3 一并裁
上游并发配置与试点规模。

## 诚实账

- **WAL 残留坑**:换 DB 副本时只 cp 主文件会留下旧 `-wal/-shm`,SQLite 重放旧 WAL
  产生错配计数(首跑基线 48≠46 即此)——已删 WAL 重拷复核为 46,后续每场照办。
- **轮2 快路径**:带消息幂等键的轮 2 首发即命中服务端 turn_idem 缓存语义返回(1ms、
  0 模型调用)——合同面(200+形状+幂等重放一致)仍完整走通,四场一致。
- **SSE 首 token = 总时长**:网关 tutor 走非流式 invoke,SSE 端点成帧后一次下发
  (ttfb≈total)——架构现状,非掉线。
- T1 服务与 stub 起后曾隔夜闲置 9 小时再压,无状态劣化(顺带稳定性观察)。
- 压测客户端与被压服务同机(loopback),P50/P95 含本机网络栈开销,量级可忽略。

## 复现清单(runbook)

1. 隔离实例:clone main 07dc4c09;`data/edu-agent.db` ← 备份副本(删旧 `-wal/-shm`);
   `.env.test` 夹具拷贝(600)。
2. T1:`STUB_DELAY_MS=150 STUB_PORT=8321 python stub_server.py.txt` 起于后台;
   `EDU_MODELS_YAML=<dir>/models.t1stub.yaml.txt EDU_PARTNER_API_PORT=8310
   EDU_DB_PATH=data/edu-agent.db EDU_QUESTION_SOURCE=bank python
   scripts/serve_partner_api.py`。T2:去掉 `EDU_MODELS_YAML`(原版配置)。
3. 负载:`python burst_load.py.txt --base-url http://127.0.0.1:8310 --account …
   --password … --workers {30,50} --window-s 2.0 --out <场>.json`。
4. 读数:各场 JSON(tally/相位/SSE/幂等/healthz);facts `model_calls-*.jsonl`
   (queue_ms/角色/模型);服务日志 grep busy/locked/Traceback;DB 计数复核。

## 工件清单

| 件 | 说明 |
|---|---|
| `burst_load.py.txt` | 负载脚本(asyncio,改自 m3_smoke 合同步骤) |
| `stub_server.py.txt` | T1 stub 上游(固定延迟+schema 动态填形) |
| `models.t1stub.yaml.txt` | T1 覆盖配置(全 provider 指 stub;文本存档,不进配置面) |
| `t{1,2}_{30,50}.json` | 四场原始读数(含 per-worker 逐相位) |
| `t{1,2}_facts.jsonl` | 网关 facts 调用流水(T2 含 queue_ms;t2 文件含已过滤可辨的 stub 行) |
| `t{1,2}_sampler.log` | 进程采样(rss/句柄,每秒) |
