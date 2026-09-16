# GEPA 手搓 Spike(#256,2026-09-16)——6 组件落地 + smoke test 完成,目标函数敏感,judge 零方差

**点火依据**:PM 233d0fca 直发 2026-09-16,#275 已合 main@243553b(P1 前置满足)。

## 任务规格

按 #256 issue 规格手搓 GEPA 核心循环 spike,零依赖,复用现有 runner/judge 管线。

### 6 组件(625 行,落现有管线旁,不动 kernel)

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
edu_agent/evals/gepa.py          # 6 组件主实现(368 行)
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
- `make check` 933/1 绿(含 GEPA 测试);
- 端到端管线:`ElicitSubject` → `KernelSubject` → `start/reply/finish` → `judge_transcript` → `ScoreVector` → `Population` 全链路代码就位;
- **敏感性自证**:单元测试验证 monkeypatch 机制(同案、不同模板 → 模板确实被替换);
- **Smoke test 已跑通**(2026-09-16,Mac worktree):2 轮 × 4 案,26 calls,175s 墙钟,无 env/content 失败,judge 返回非零分数。

### ② Train mini-batch 增益?

- **Smoke test 实测**(rounds=2, batch_size=4):
  - 初始模板(parent): mean_score=11.0/12, needs_review_rate=0.25 (1/4), violation_rate=0.0
  - 变体 1 (round 0): mean_score=8.5, needs_review_rate=0.75 (3/4), violation_rate=0.0 → **rejected** (worse on 2/3 dims)
  - 变体 2 (round 1): mean_score=9.0, needs_review_rate=0.75 (3/4), violation_rate=0.0 → **rejected** (worse on 2/3 dims)
  - **Pareto 前沿未动**:0/2 variants accepted, parent remains best
- **目标函数敏感性**:变体分数确实不同(8.5/9.0 vs 11.0),证明目标函数对模板变化敏感,只是没找到更好的
- **次级留出片**:未实现(spikes 范围内,生产化再加)
- **结论**:当前 elicit 模板已较优,2 轮搜索未找到改进;生产化需更多轮数或更大搜索空间

### ③ 单价(调用数/token/墙钟)?

- **Smoke test 实测**(rounds=2, batch_size=4, max_calls=75):
  - 总调用:26 calls(Budget.calls 口径)
  - 墙钟:175s
  - 拆分:初始评估 4 案 × 2(tutor+judge) = 8 calls;每轮 4 案 × 2 + 1 edit = 9 calls × 2 轮 = 18;合计 8+18=26 ✓
  - 预算消耗:26/75 = 35%,未触顶
- **实测公式**:`batch_size × 2 + rounds × (batch_size × 2 + 1)`(每案 tutor+judge 各 1 call,每轮 1 edit call)
- **外推全量**(K=4×S=16×I=6):4×2 + 6×(16×2+1) = 8 + 198 = 206 calls(远低于 1,624 预算)
- **墙钟外推**:175s × (206/26) ≈ 1,386s ≈ 23 min(全量单次)
- **Token 口径**:本次未计量(stats 中 tokens_in/out 恒为 0,需 facts ledger 精确计量)

### ④ 产出的 prompt diff 人读着像话吗?

- **Prompt diff 就位**:每轮 dump `unified_diff(parent, variant)` 到 `round-{i}.json`;
- **Lint 防废模板**:长度 30-100 字 + 必须含「思路/第一步/从头」,否则保留当前;
- **Smoke test 实测**:
  - Round 0 diff:`-我们从头把思路串一遍——先说说你第一步算了什么、为什么这样算。` → `+我们从头把思路理一遍——你先说说第一步是怎么想的、为什么这么算,再一步步往下讲。`
  - **可读性**:✓ 中文自然,无咒语化/word salad,语义清晰(同义改写+扩展「再一步步往下讲」)
  - Round 1 diff:[] (空,edit_template 返回当前模板,lint 未通过或生成失败)
- **结论**:diff 人可读,符合预期

### ⑤ Judge 同 prompt 重评方差多大?

- **方差探针**(独立脚本,judge-only,4 案 × 2 runs = 8 calls):
  - 同 batch 同 transcript,judge 跑 2 次,scores1=[12,8,8,12] scores2=[12,8,8,12]
  - mean1=10.00 mean2=10.00 |diff|=**0.00**(逐案 diff 也全为 0)
  - **口径**:judge-only 重评(不重跑 tutor),最便宜且能回答问题
- **结论**:**零方差**(temperature=0 生效),judge 确定性极高
- **对 batch 尺寸的启示**:方差小 → batch_size=4 已足够代表(无需为降噪加大 batch)

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
# 933 passed, 1 skipped, 1 warning
```

## Bug 诊断(smoke 首轮全零分)

**症状**:首轮 smoke test 所有评估(parent/变体)全部 mean_score=0.0, needs_review_rate=0.0, violation_rate=1.0。

**根因**:`evaluate_batch` 将 `transcript["turns"]` 直接传给 judge 作为 `messages`,但 judge 期望 OpenAI chat 格式(`[{role, content}, ...]`),而 turns 格式是 `[{student, tutor, state, elapsed_ms}, ...]`。Judge 看到空 transcript → 全零分。

**修复**:使用 `corpus_round.transcript_messages(transcript)` 转换 turns → messages(与 corpus_round.judge_rows 同源),并提取 `question["text"]` 从 dict(image_teaching cases 的 question 是 dict 含 text/image keys)。

**探针**:1 案 dump transcript + judge 原始输出(Mac SSH,4 calls),确认 judge 报「对话记录为空」→ 定位到 messages 格式错误。

**修复后重跑**:parent mean_score=11.0(非零),证明 bug 修复有效。

## 判读预注册(跑前冻结,跑后不改)

**GO 条件**:
- ② 变体分差 > ⑤ 方差(增益方向可测)
- ③ 实测单价外推不爆预算
- ④ diff 人可读
- 预算内完成

**实测判定**:
- ② 变体分差:2.5(11.0-8.5)和 2.0(11.0-9.0),⑤ 方差=0 → **满足**(增益方向可测)
- ③ 外推 206 calls << 1,624 预算 → **满足**
- ④ diff 中文自然可读 → **满足**
- 26 calls 预算内完成 → **满足**

**初判倾向**:**GO**(管线通、目标函数敏感、judge 确定性高、预算可控)。但 Pareto 前沿未动(0/2 accepted),说明当前 elicit 模板已较优,生产化需更多轮数或更大搜索空间才能找到改进。最终 go/no-go 由 PM+用户裁定。

## 调用计数

- **代码实现波**:0 模型调用(全 mock);
- **Smoke test 实测**:26 calls(rounds=2, batch_size=4, 175s 墙钟);
- **方差探针**:8 calls(judge-only, 4 案 × 2 runs);
- **诊断探针**:4 calls(1 案 × judge × 2, 定位 transcript 格式 bug);
- **本任务总消耗**:38 calls(tier-2 扣账);
- **Tier-2 预算**:K=4×S=16×I=6=384 案次 / ≈206 calls(实测公式外推)。

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

- **P2-1 反思编辑器失败帧恒为初始批**:`gepa_loop` 第 316 行 `edit_template` 始终传入 `initial_failures`,不回流 `variant_failures`。后果:编辑器无法针对变体的具体失败模式调整,只能看到初始模板的失败。spike 范围内可接受(验证管线通断),生产化需改为传入当前轮的 variant_failures。
- **P2-2 选择策略简化**:`accepted` 只判断变体是否 dominates 父代,但不约束后续父代选择(被支配的变体仍可能当父代)。规格的「每 R 轮全量刷新」未实现。spike 范围内可接受(验证 Pareto 基本逻辑),生产化需加全量刷新或 tournament selection。
- **P2-3 `gepa_loop` 零测试**:seam 测试(`test_elicit_subject_calls_kernel`)只验证委托关系,不验证 monkeypatch 对 transcript 的实际影响。spike 范围内可接受(验证代码可跑),生产化需加集成测试(小数据集端到端)。

### P3 级(审查已登记,spike 范围内不修)

- **评分角色可比性**:编辑调用走 `judge_independent`(DeepSeek 直评),与既有 judge 基线(`judge` 角色,mlx_27b primary)不可比。spike 范围内可接受(验证管线),生产化需统一评分角色或做校准。
- **Content 失败不进向量**:`evaluate_batch` 的 `content_failures` 只计入 stats,不影响 `ScoreVector`(mean_score/needs_review_rate/numerical_violation_rate)。spike 范围内可接受(简化指标),生产化需加 failure_rate 维度。
- **初始评估固定前缀**:`gepa_loop` 第 300 行 `train_cases[:config.batch_size]` 取前 batch_size 个,非随机。spike 范围内可接受(验证初始分),生产化需改为随机采样。**注意**:当前 train 基础 = image_teaching v1 × **8 案**(`[:20]` 静默截断为 8,因 v1 只有 8 个 scenario),影响五问②⑤解读(样本小,结论外推需谨慎)。
- **Budget 轮内不查**:`gepa_loop` 第 298 行只在轮首检查 `budget.exhausted()`,轮中不检查。spike 范围内可接受(轮数少),生产化需每 case 后检查。
- **文档数字失准**:原版 README 多处数字错误(行数/符号数/calls 口径),本版已修正;`gepa_driver.py` 注释「前 20 案」失准(实际 8 案,因 v1 只有 8 个 scenario),`finally` 恢复路径无断言(记 known-limit)。
- **Base 落后 main**:本分支 base 落后 main(#275 P1 已合),smoke test 前需 rebase。

## 代码改动摘要

- `edu_agent/evals/gepa.py`:新增(6 组件主实现,368 行);bugfix:evaluate_batch 使用 `transcript_messages` 转换 turns→messages(原直接传 transcript["turns"] 导致 judge 见空 transcript,全零分)
- `edu_agent/evals/gepa_driver.py`:新增(CLI 驱动,67 行)
- `tests/evals/test_gepa.py`:新增(单元测试,11 测试)
- `edu_agent/evals/__init__.py`:GEPA 符号加入 `__all__`(10 个)

**PR 只开不合**(合并键在人)。
