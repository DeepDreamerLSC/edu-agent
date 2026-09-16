# GEPA 手搓 Spike(#256,2026-09-16)——6 组件落地 + smoke test + 配对实验,Δ≈0 归因未定,红灯(冻结协议)

**点火依据**:PM 233d0fca 直发 2026-09-16,#275 已合 main@243553b(P1 前置满足)。

## 任务规格

按 #256 issue 规格手搓 GEPA 核心循环 spike,零依赖,复用现有 runner/judge 管线。

### 6 组件(731 行组件 / 95 行驱动 / 478 行测试,落现有管线旁,不动 kernel)

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
edu_agent/evals/gepa.py          # 6 组件主实现 + 配对实验(731 行)
edu_agent/evals/gepa_driver.py   # CLI 驱动脚本(95 行,含 --paired 模式)
tests/evals/test_gepa.py         # 单元测试(18 测试,零 API)
```

### 公开入口(已加入 `edu_agent/evals/__init__.__all__`)

- `gepa_loop`, `paired_loop`, `GepaConfig`, `Budget`
- `ElicitSubject`, `Candidate`, `Population`, `ScoreVector`
- `evaluate_batch`, `evaluate_batch_paired`, `edit_template`, `sample_batch`

共 12 个 GEPA 专用符号。

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
  - 初始模板(parent, 批 A): mean_score=11.0/12, needs_review_rate=0.25 (1/4), violation_rate=0.0
  - 变体 1 (R0, 批 B): mean_score=8.5, needs_review_rate=0.75 (3/4), violation_rate=0.0 → **rejected** (worse on 2/3 dims)
  - 变体 2 (R1, 批 C, **no-op 编辑**): mean_score=9.0, needs_review_rate=0.75 (3/4), violation_rate=0.0 → **rejected**
- **关键发现**:R1 变体与 parent 模板**逐字相同**(no-op 编辑),但分数从 11.0 降至 9.0,Δ=2.0。**这全部是批次方差**(不同随机批 × 同模板),不是模板效应。
- **敏感性判定**:**未定**。batch=4 / n=1 下无法区分模板效应与批次方差(R0 的 8.5 也混杂了批次差异)。需更大 batch 或配对评估(parent/variant 同批)才能分辨。
- **次级留出片**:未实现(spikes 范围内,生产化再加)
- **生产化启示**:配对评估(parent/variant 在同 batch 上跑)可零成本消除批次效应,是下一步首选方案。

### ③ 单价(调用数/token/墙钟)?

- **Smoke test 实测**(rounds=2, batch_size=4, max_calls=75):
  - Budget.calls = **26**(代码简化口径:`len(cases) + judged`,非真实调用数)
  - 墙钟:**175s**
  - R1 为 no-op 轮(省掉评估调用,只花 1 edit call)
- **双口径并列**:
  - **Budget 简化口径**:每案 2 calls(tutor 1 + judge 1),外推 K=4×S=16×I=6 → **≈206 calls**
  - **真实口径估算**(GEPA feasibility spike 实测 tutor ≈3.23 calls/case + 1 judge/case + 1 edit/轮):外推 K=4×S=16×I=6 → **≈478 calls**
  - **矛盾**:简化 vs 真实差 ≈2.3×,根因是 tutor 平均 3.23 calls/case(多轮对话),Budget 只计了 1。生产化需从 facts ledger 精确计量。
  - 两口径均远低于 1,624 预算上限
- **Token 口径**:未计量(stats 中 tokens_in/out 恒为 0,需 facts ledger 精确计量)

### ④ 产出的 prompt diff 人读着像话吗?

- **Prompt diff 就位**:每轮 dump `unified_diff(parent, variant)` 到 `round-{i}.json`;
- **Lint 防废模板**:长度 30-100 字 + 必须含「思路/第一步/从头」,否则保留当前;
- **Noop 标记**:round-*.json 含 `"noop": true/false` 字段,标记变体是否与父代逐字相同(未来运行含此字段,首轮 smoke 无此字段因代码后续补)
- **Smoke test 实测**:
  - Round 0 diff:`-我们从头把思路串一遍——先说说你第一步算了什么、为什么这样算。` → `+我们从头把思路理一遍——你先说说第一步是怎么想的、为什么这么算,再一步步往下讲。`
  - **可读性**:✓ 中文自然,无咒语化/word salad,语义清晰(同义改写+扩展「再一步步往下讲」)
  - Round 1 diff:[] (空,edit_template 返回当前模板,lint 未通过或生成失败)
- **结论**:diff 人可读,符合预期

### ⑤ Judge 同 prompt 重评方差多大?

- **Judge 方差**(独立探针,judge-only,4 案 × 2 runs = 8 calls):
  - 同 batch 同 transcript,judge 跑 2 次,scores1=[12,8,8,12] scores2=[12,8,8,12]
  - mean1=10.00 mean2=10.00 |diff|=**0.00**(逐案 diff 也全为 0)
  - **Judge 方差 = 零**(temperature=0 生效,确定性极高)
- **批次方差**(smoke R1 no-op 观测):
  - 同模板 × 不同 batch:parent 批 A=11.0,变体 2 批 C(no-op 编辑,模板逐字相同)=9.0
  - Δ=2.0,即 **17% 摆动**——这才是真噪声底
  - Judge 方差(0)≠ 批次方差(2.0)
- **对 batch 尺寸的启示**:batch=4 不足以分辨模板效应(噪声底 2.0 分,模板改进可能 <2 分)。生产化需:
  - 加大 batch(8-16 案)
  - 多 seed 取均值
  - **配对评估**(parent/variant 在同 batch 上跑)——零成本消除批次效应,首选方案
- **工件**:`smoke-test/variance-probe.json`(逐案 run1/run2 数据)

## 复算

### Smoke test(已执行,Mac worktree 2026-09-16)

```bash
# 实际跑法:rounds=2,batch_size=4,max_calls=75
uv run python -m edu_agent.evals.gepa_driver \
  edu_agent/evals/artifacts/gepa-spike/smoke-test \
  --rounds 2 --batch-size 4 --max-calls 75

# 实际产出:
# - round-00.json, round-01.json(每轮 prompt diff + 分数 + noop 标记)
# - summary.json(预算 + 最优候选 + accepted 统计)
# - variance-probe.json(五问⑤ 重评方差探针)
```

### 单元测试(零 API,已跑通)

```bash
uv run pytest tests/evals/test_gepa.py -v
# 18 passed
```

### 全量检查

```bash
make check
# 940 passed, 1 skipped, 1 warning(本地基座 e2ae9c2d;PR 头 CI 口径以 CI job 为准)
```

## Bug 诊断(smoke 首轮全零分)

**症状**:首轮 smoke test 所有评估(parent/变体)全部 mean_score=0.0, needs_review_rate=0.0, violation_rate=1.0。

**根因**:`evaluate_batch` 将 `transcript["turns"]` 直接传给 judge 作为 `messages`,但 judge 期望 OpenAI chat 格式(`[{role, content}, ...]`),而 turns 格式是 `[{student, tutor, state, elapsed_ms}, ...]`。Judge 看到空 transcript → 全零分。

**修复**:使用 `corpus_round.transcript_messages(transcript)` 转换 turns → messages(与 corpus_round.judge_rows 同源),并提取 `question["text"]` 从 dict(image_teaching cases 的 question 是 dict 含 text/image keys)。

**探针**:1 案 dump transcript + judge 原始输出(Mac SSH,4 calls),确认 judge 报「对话记录为空」→ 定位到 messages 格式错误。

**修复后重跑**:parent mean_score=11.0(非零),证明 bug 修复有效。

## 配对实验(2026-09-16,消除批次方差)

**目的**:smoke test 发现批次方差 2.0 分(同模板跨批),无法分辨模板效应。配对实验固定全 8 案,逐案对比 parent vs variant,批次方差在配对内抵消。

**设计**:
- 全 8 案 × 2 轮,预算硬顶 104 calls
- 父代模板跑一遍 → 逐案分 P1..P8
- 每轮变体(编辑器产出)→ 同批跑 → 逐案分 Vi/Wi
- **配对差 Δi = 变体i − 父代i**(每案一对)

**实测结果**(Mac worktree,2026-09-16):
- Budget: 50 calls(simplified 口径,见下)/ 372s 墙钟
- **Mean Δ = -0.06**(16 配对案例,15 个 Δ=0,1 个 Δ=-1)
- Verdict: **红灯**(冻结协议:Δ≈0 → 停,报 PM 红灯)

**三项验证**(首轮,代码修复前):
1. **编辑器反馈**:parent_failures 传给 edit_template,report 含 editor_feedback_sample ✓
2. **硬失败筛选**:hard_fail_validation = "pass (no leaked variant)" ✓
3. **模板命中**:hit_count=0/8(工件实录,代码读取 transcript["first_question"] 但 transcript 无此键 → 结构性失效;修复后读取 turns[0].tutor,**待重跑验证**)

**代码修复**(2026-09-16,审查 review-303):
- P1-1: 模板命中验证修复(读取 turns[0].tutor,逐案对比 parent vs variant 首问,含空转检测)
- P1-2: 判读逻辑修复(冻结协议:Δ≈0 → 红灯,非 mixed)
- P1-3: 调用计数接 facts ledger(真实 tutor 多轮调用 + judge + editor,非简化 +=2)
- P2-1: 编辑器反馈用完整失败帧(含 evidence 原句,非仅 total/hard_fail)
- P2-2: 归因改为「未定」(空转未排除,judge 不敏感 vs 空转 vs 搜索空间窄三可)
- 辅助函数提取(_build_paired_cases / _compute_paired_verdict)
- 契约测试用真实转录形状(无 first_question 键,首问在 turns[0].tutor)
- _validate_hard_fail 对齐 dominates 原则(无 acceptable 分支)
- budget.rounds 计数修复

**判读**(冻结协议):
- Δ ≈ 0 → **红灯**(停,报 PM,进入设计对话)
- **归因未定**:judge 对 elicit 措辞不敏感 vs 空转(模板未改变 tutor 行为)vs 搜索空间窄(三可皆容,首轮未验证模板命中)
- **建议**:需重跑实验(新代码 + facts 实测 calls)验证模板是否真改变行为;若仍 Δ≈0 → PM+用户裁定下一步(更大搜索空间 / 换优化目标 / 停)

**工件**:`paired-experiment/`(round-00.json, round-01.json, paired-report.json,首轮数据)

## 判读预注册(跑前冻结,跑后不改)

**GO 条件**:
- ② 变体分差 > ⑤ 方差(增益方向可测)
- ③ 实测单价外推不爆预算
- ④ diff 人可读
- 预算内完成

**实测判定**:
- ② 变体分差 > 批次方差? → **不可分辨**(R1 no-op Δ=2.0 全部是批次方差;R0 跨批混杂)
- ③ 外推 206-478 calls << 1,624 预算 → **满足**
- ④ diff 中文自然可读 → **满足**
- 26 calls 预算内完成 → **满足**

**初判倾向**:**条件 GO**(管线通、judge 确定性高、预算可控、diff 可读)。但 ② 敏感性在 batch=4/n=1 下不可分辨(噪声底 2.0 分 >> judge 方差 0),需更大 batch 或配对评估才能判定模板是否可改进。最终 go/no-go 由 PM+用户裁定。

**配对实验补充判读**(2026-09-16,冻结协议):
- 配对实验消除批次方差后,Mean Δ = -0.06(16 配对案例,15 个 Δ=0,1 个 Δ=-1)
- Verdict: **红灯**(冻结协议:Δ≈0 → 停,报 PM,进入设计对话)
- **归因未定**:judge 不敏感 vs 空转(模板未改变 tutor 行为,首轮顺验③失效)vs 搜索空间窄 — 三可皆容,需重跑验证模板命中后定论
- **下一步**:待 PM+用户裁定(是否重跑实验 / 更大搜索空间 / 停)

## 调用计数

- **代码实现波**:0 模型调用(全 mock);
- **PM 代跑 smoke**:26 calls(rounds=2, batch_size=4, 首轮全零分);
- **D 重跑 smoke**(bug 修复后):26 calls(同配置);
- **诊断探针**:4 calls(1 案 × judge × 2);
- **方差探针**:8 calls(judge-only, 4 案 × 2 runs);
- **配对实验**:50 calls(全 8 案 × 2 轮 + 编辑器 2 calls);
- **本任务总消耗**:**114 calls**(tier-2 扣账,64+50);
- **Tier-2 预算**:K=4×S=16×I=6=384 案次 / ≈206-478 calls(双口径,见 §五问③)。

## 治理

- **搜索空间**:elicit 模板(`kernel._ELICIT_TEMPLATE`),不动 kernel 代码;
- **合并键在人**:产出 = prompt diff → PR → 独立审查 → 人合;
- **Train/held-out**:spike 范围内未实现 held-out 切分(生产化再加);
- **预算上限**:`Budget.max_calls` 硬上限,耗尽即停。

## 工件

- `README.md`(本文件);
- `smoke-test/`(round-*.json + summary.json + variance-probe.json);
- `paired-experiment/`(round-*.json + paired-report.json,配对实验产出)。

## 已知局限

### P2 级(spike 范围内未修,生产化再议)

- **P2-1 反思编辑器失败帧已修**(原恒为初始批,现传 `last_failures` 滚动更新;每轮结束后用 `variant_failures` 覆盖,no-op 时保留上轮)
- **P2-2 选择策略简化**:`accepted` 只判断变体是否 dominates 父代,但不约束后续父代选择(被支配的变体仍可能当父代)。规格的「每 R 轮全量刷新」未实现。spike 范围内可接受(验证 Pareto 基本逻辑),生产化需加全量刷新或 tournament selection。
- **P2-3 `gepa_loop` 零测试**:seam 测试(`test_elicit_subject_calls_kernel`)只验证委托关系,不验证 monkeypatch 对 transcript 的实际影响。spike 范围内可接受(验证代码可跑),生产化需加集成测试(小数据集端到端)。

### P3 级(审查已登记,spike 范围内不修)

- **评分角色可比性**:编辑调用走 `judge_independent`(DeepSeek 直评),与既有 judge 基线(`judge` 角色,mlx_27b primary)不可比。spike 范围内可接受(验证管线),生产化需统一评分角色或做校准。
- **Content 失败不进向量**:`evaluate_batch` 的 `content_failures` 只计入 stats,不影响 `ScoreVector`(mean_score/needs_review_rate/numerical_violation_rate)。spike 范围内可接受(简化指标),生产化需加 failure_rate 维度。
- **初始评估固定前缀**:`gepa_loop` 第 300 行 `train_cases[:config.batch_size]` 取前 batch_size 个,非随机。spike 范围内可接受(验证初始分),生产化需改为随机采样。**注意**:当前 train 基础 = image_teaching v1 × **8 案**(`[:20]` 静默截断为 8,因 v1 只有 8 个 scenario),影响五问②⑤解读(样本小,结论外推需谨慎)。
- **Budget 轮内不查**:`gepa_loop` 第 305 行只在轮首检查 `budget.exhausted()`,轮中不检查。spike 范围内可接受(轮数少),生产化需每 case 后检查。
- **文档数字失准**:原版 README 多处数字错误(行数/符号数/calls 口径),本版已修正;`gepa_driver.py` 注释「前 20 案」失准(实际 8 案,因 v1 只有 8 个 scenario),`finally` 恢复路径无断言(记 known-limit)。
- **Base 落后 main**:本分支 base 落后 main(#275 P1 已合),smoke test 前需 rebase。

## 代码改动摘要

- `edu_agent/evals/gepa.py`:新增(6 组件主实现 + 配对实验,731 行);bugfix:evaluate_batch 使用 `transcript_messages` 转换 turns→messages(原直接传 transcript["turns"] 导致 judge 见空 transcript,全零分);no-op 检查(edit_template 返回与父代相同 → 跳过评估省预算);P1 修复:① 编辑器收低分维度+证据(原只收 GatewayError);② 硬失败(answer_leaked/verdict=fail)进 ScoreVector 第四维,不能成为最优;P2-1 修复:编辑失败帧滚动更新(last_failures);配对实验:evaluate_batch_paired + paired_loop(逐案配对 Δ + 三项验证);**review-303 修复**:模板命中验证读取 turns[0].tutor(非不存在的 first_question 键);facts ledger 实测调用计数;verdict 冻结协议(Δ≈0→红灯);归因未定;空转检测;辅助函数提取
- `edu_agent/evals/gepa_driver.py`:新增(CLI 驱动,95 行,含 --paired 模式)
- `tests/evals/test_gepa.py`:新增(单元测试 18 个,含契约测试:turns↔messages 形状断言、硬失败选择行为、硬失败 dominates 阻断、低分证据进 failures 列表、evaluate_batch_paired、paired_loop、verdict 红灯;**契约测试用真实转录形状**:无 first_question 键,首问在 turns[0].tutor)
- `edu_agent/evals/__init__.py`:GEPA 符号加入 `__all__`(12 个,含 paired_loop + evaluate_batch_paired)

**PR 只开不合**(合并键在人)。
