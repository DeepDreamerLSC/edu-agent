# GEPA 手搓 Spike(#256,2026-09-16)——6 组件落地,管线通,待 smoke test

**点火依据**:PM 233d0fca 直发 2026-09-16,#275 已合 main@243553b(P1 前置满足)。

## 任务规格

按 #256 issue 规格手搓 GEPA 核心循环 spike,零依赖,复用现有 runner/judge 管线。

### 6 组件(428 行,落现有管线旁,不动 kernel)

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
edu_agent/evals/gepa_driver.py   # CLI 驱动脚本(67 行)
tests/evals/test_gepa.py         # 单元测试(11 测试,零 API)
```

### 公开入口(已加入 `edu_agent/evals/__init__.__all__`)

- `gepa_loop`, `GepaConfig`, `Budget`
- `ElicitSubject`, `Candidate`, `Population`, `ScoreVector`
- `evaluate_batch`, `edit_template`, `sample_batch`

共 10 个 GEPA 专用符号。

### 依赖

- **零新依赖**:复用现有 gateway/judge/runner/kernel;
- **Gateway API**:`gateway.invoke(ModelRequest)` → `ModelResponse`;
- **Judge 管线**:`judge_transcript(gateway, case, role)` → 六维分数/verdict/mi/leak;
- **角色复用**:编辑调用走 `judge_independent`(DeepSeek 直评,不加新角色)。

## 五问(验收 = 回答这五问)

### ① 管线通不通?

- **单元测试 11/11 通过**(零 API,mock gateway);
- `make check` 932/1 绿(含 GEPA 测试);
- 端到端管线:`ElicitSubject` → `KernelSubject` → `start/reply/finish` → `judge_transcript` → `ScoreVector` → `Population` 全链路代码就位;
- **敏感性自证**:单元测试验证 monkeypatch 机制(同案、不同模板 → 模板确实被替换);
- **待验证**:smoke test(小配置跑真实 API,见下「复算」)。

### ② Train mini-batch 增益?

- **代码就位**:`sample_batch(cases, k, seed)` 确定性采样,换种子刷新;
- **待验证**:smoke test 跑多轮,观察 batch 间方差 vs 全 train 方差,判断 mini-batch 是否足够代表全 train;
- **次级留出片**:未实现(spikes 范围内,生产化再加)。

### ③ 单价(调用数/token/墙钟)?

- **预算计数就位**:`Budget` 跟踪 calls/rounds/wall_s;
- **代码简化口径**:`evaluate_batch` 统计 `len(cases) + judged`(非真实调用数,需 facts ledger 精确计量);
- **真实调用公式**(基于 GEPA feasibility spike 4.23 calls/case):
  - 初始评估:`batch_size × 4.23`
  - 每轮:`1(edit) + batch_size × 4.23`
  - 总计:`(1 + rounds) × batch_size × 4.23 + rounds × 1`
- **Smoke test 预算**(rounds=2, batch_size=4):`(1+2)×4×4.23 + 2×1 = 52.76 ≈ 53 calls`;
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
# - summary.json(预算 + 最优候选 + accepted 统计)
```

### 单元测试(零 API,已跑通)

```bash
uv run pytest tests/evals/test_gepa.py -v
# 11 passed
```

### 全量检查

```bash
make check
# 932 passed, 1 skipped, 1 warning
```

## 调用计数

- **本波零模型调用**(代码实现 + 单元测试全 mock);
- **Smoke test 预估**:≈53 calls(公式见 §五问③,基于 GEPA feasibility spike 4.23 calls/case 口径);
- **Tier-2 预算**:K=4×S=16×I=6=384 案次 / ≈1,624 calls(已批,spike 从 tier-2 扣)。

## 治理

- **搜索空间**:elicit 模板(`kernel._ELICIT_TEMPLATE`),不动 kernel 代码;
- **合并键在人**:产出 = prompt diff → PR → 独立审查 → 人合;
- **Train/held-out**:spike 范围内未实现 held-out 切分(生产化再加);
- **预算上限**:`Budget.max_calls` 硬上限,耗尽即停。

## 工件

- `README.md`(本文件);
- `smoke-test/`(待执行产出:round-*.json + summary.json)。

## 已知局限

### P2 级(spike 范围内未修,生产化再议)

- **P2-1 反思编辑器失败帧恒为初始批**:`gepa_loop` 第 309 行 `edit_template` 始终传入 `initial_failures`,不回流 `variant_failures`。后果:编辑器无法针对变体的具体失败模式调整,只能看到初始模板的失败。spike 范围内可接受(验证管线通断),生产化需改为传入当前轮的 variant_failures。
- **P2-2 选择策略简化**:`accepted` 只判断变体是否 dominates 父代,但不约束后续父代选择(被支配的变体仍可能当父代)。规格的「每 R 轮全量刷新」未实现。spike 范围内可接受(验证 Pareto 基本逻辑),生产化需加全量刷新或 tournament selection。
- **P2-3 `gepa_loop` 零测试**:seam 测试(`test_elicit_subject_calls_kernel`)只验证委托关系,不验证 monkeypatch 对 transcript 的实际影响。spike 范围内可接受(验证代码可跑),生产化需加集成测试(小数据集端到端)。

### P3 级(审查已登记,spike 范围内不修)

- **评分角色可比性**:编辑调用走 `judge_independent`(DeepSeek 直评),与既有 judge 基线(`judge` 角色,mlx_27b primary)不可比。spike 范围内可接受(验证管线),生产化需统一评分角色或做校准。
- **Content 失败不进向量**:`evaluate_batch` 的 `content_failures` 只计入 stats,不影响 `ScoreVector`(mean_score/needs_review_rate/numerical_violation_rate)。spike 范围内可接受(简化指标),生产化需加 failure_rate 维度。
- **初始评估固定前缀**:`gepa_loop` 第 293 行 `train_cases[:config.batch_size]` 取前 batch_size 个,非随机。spike 范围内可接受(验证初始分),生产化需改为随机采样。
- **Budget 轮内不查**:`gepa_loop` 第 298 行只在轮首检查 `budget.exhausted()`,轮中不检查。spike 范围内可接受(轮数少),生产化需每 case 后检查。
- **文档数字失准**:原版 README 多处数字错误(432→428 行、13→10 符号、108→53 calls),本版已修正。
- **Base 落后 main**:本分支 base 落后 main(#275 P1 已合),smoke test 前需 rebase。

## 代码改动摘要

- `edu_agent/evals/gepa.py`:新增(6 组件主实现,361 行);
- `edu_agent/evals/gepa_driver.py`:新增(CLI 驱动,67 行);
- `tests/evals/test_gepa.py`:新增(单元测试,11 测试);
- `edu_agent/evals/__init__.py`:GEPA 符号加入 `__all__`(10 个)。

**PR 只开不合**(合并键在人)。
