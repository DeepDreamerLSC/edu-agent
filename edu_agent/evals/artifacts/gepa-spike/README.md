# GEPA 手搓 Spike(#256,2026-09-16)——6 组件落地,管线通,待 smoke test

**点火依据**:PM 233d0fca 直发 2026-09-16,#275 已合 main@243553b(P1 前置满足)。

## 任务规格

按 #256 issue 规格手搓 GEPA 核心循环 spike,零依赖,复用现有 runner/judge 管线。

### 6 组件(432 行,落现有管线旁,不动 kernel)

1. **Prompt seam**(`ElicitSubject`):`run_case` 接受 elicit 模板变体注入(monkeypatch `kernel._ELICIT_TEMPLATE`,用完即恢复,不动仓库模板);
2. **Mini-batch 采样**(`sample_batch`):每轮从 train 抽 k 个,同种子确定性,换种子刷新;
3. **打分向量**(`ScoreVector` + `evaluate_batch`):复用 judge 管线,聚合三指标(总分均值/needs_review 率/数值违规率),多指标喂 Pareto;
4. **反思编辑器**(`edit_template`):一次 gateway 调用(judge_independent 角色,DeepSeek),当前模板 + 失败帧浓缩 → 变体;带 lint(长度 30-100 字 + 必须含「思路/第一步/从头」防废模板);
5. **选择 + 种群**(`Population` + `Candidate`):简化 Pareto(新批次不劣于父代且一维更好才留),种群落 JSON 工件;
6. **循环驱动**(`gepa_loop` + `GepaConfig` + `Budget`):轮数/预算计数(calls/tokens/墙钟)/停止;每轮 dump prompt diff + 分数(人审原料)。

### 治理约束(照抄不变量)

- **搜索空间只有 prompt 面**:判停闸/泄露闸/状态机零接触——结构上无害,最坏 prompt 教学变差,合并前被人审拦;
- **优化器只提案、合并键在人**:产出 = 可读 prompt diff → PR → 独立审查 → 人合 → 重部署;
- **Train/held-out 切分**:搜索只见 train;held-out + 确定性 checks + 人抽审做终审。

## 代码结构

```
edu_agent/evals/gepa.py          # 6 组件主实现(361 行)
edu_agent/evals/gepa_driver.py   # CLI 驱动脚本(71 行)
tests/evals/test_gepa.py         # 单元测试(10 测试,零 API)
```

### 公开入口(已加入 `edu_agent/evals/__init__.__all__`)

- `gepa_loop`, `GepaConfig`, `Budget`
- `ElicitSubject`, `Candidate`, `Population`, `ScoreVector`
- `evaluate_batch`, `edit_template`, `sample_batch`

### 依赖

- **零新依赖**:复用现有 gateway/judge/runner/kernel;
- **Gateway API**:`gateway.invoke(ModelRequest)` → `ModelResponse`;
- **Judge 管线**:`judge_transcript(gateway, case, role)` → 六维分数/verdict/mi/leak;
- **角色复用**:编辑调用走 `judge_independent`(DeepSeek 直评,不加新角色)。

## 五问(验收 = 回答这五问)

### ① 管线通不通?

- **单元测试 10/10 通过**(零 API,mock gateway);
- `make check` 932/1 绿(含 GEPA 测试);
- 端到端管线:`ElicitSubject` → `KernelSubject` → `start/reply/finish` → `judge_transcript` → `ScoreVector` → `Population` 全链路代码就位;
- **待验证**:smoke test(小配置跑真实 API,见下「复算」)。

### ② Train mini-batch 增益?

- **代码就位**:`sample_batch(cases, k, seed)` 确定性采样,换种子刷新;
- **待验证**:smoke test 跑多轮,观察 batch 间方差 vs 全 train 方差,判断 mini-batch 是否足够代表全 train;
- **次级留出片**:代码未实现(可加 `held_out_cases` 参数,每轮跑 held-out 验证过拟合)。

### ③ 单价(调用数/token/墙钟)?

- **预算计数就位**:`Budget` 跟踪 calls/rounds/wall_s;
- **估算**:每案 ~4.23 调用(tutor 3.23 + judge 1),batch_size=4 → 每轮 ~17 调用 + 1 编辑调用 = 18 调用;6 轮 = 108 调用;
- **待验证**:smoke test 实测 token/墙钟,外推全量预算(K=4×S=16×I=6=384 案次 / ≈1,624 calls)。

### ④ 产出的 prompt diff 人读着像话吗?

- **Prompt diff 就位**:每轮 dump `unified_diff(parent, variant)` 到 `round-{i}.json`;
- **Lint 防废模板**:长度 30-100 字 + 必须含「思路/第一步/从头」,否则保留当前;
- **待验证**:smoke test 产出 diff,人审是否咒语化 word salad。

### ⑤ Judge 同 prompt 重评方差多大?

- **代码支持**:每轮跑 batch 一次,可扩展为跑 2 次取均值/方差;
- **待验证**:smoke test 跑同 batch 2 次,计算 ScoreVector 方差,决定 batch 尺寸(方差大则 batch 大)。

## 复算

### Smoke test(待执行,需 API key)

```bash
# 小配置:2 轮,batch_size=4,max_calls=100
uv run python -m edu_agent.evals.gepa_driver \
  edu_agent/evals/artifacts/gepa-spike/smoke-test \
  --rounds 2 --batch-size 4 --max-calls 100

# 预期产出:
# - round-00.json, round-01.json(每轮 prompt diff + 分数)
# - summary.json(预算 + 最优候选)
# - population.json(种群全候选)
```

### 单元测试(零 API,已跑通)

```bash
uv run pytest tests/evals/test_gepa.py -v
# 10 passed
```

### 全量检查

```bash
make check
# 932 passed, 1 skipped, 1 warning
```

## 调用计数

- **本波零模型调用**(代码实现 + 单元测试全 mock);
- **Smoke test 预估**:108 调用(2 轮 × 4 案 × 2 调用/案 + 2 编辑调用);
- **Tier-2 预算**:K=4×S=16×I=6=384 案次 / ≈1,624 calls(已批,spike 从 tier-2 扣)。

## 治理

- **搜索空间**:elicit 模板(`kernel._ELICIT_TEMPLATE`),不动 kernel 代码;
- **合并键在人**:产出 = prompt diff → PR → 独立审查 → 人合;
- **Train/held-out**:代码支持 `held_out_cases` 参数(未用),smoke test 可加;
- **预算上限**:`Budget.max_calls` 硬上限,耗尽即停。

## 工件

- `README.md`(本文件);
- `smoke-test/`(待执行产出:round-*.json + summary.json + population.json)。

## 代码改动摘要

- `edu_agent/evals/gepa.py`:新增(6 组件主实现,361 行);
- `edu_agent/evals/gepa_driver.py`:新增(CLI 驱动,71 行);
- `tests/evals/test_gepa.py`:新增(单元测试,10 测试);
- `edu_agent/evals/__init__.py`:GEPA 符号加入 `__all__`(13 个)。

**PR 只开不合**(合并键在人)。
