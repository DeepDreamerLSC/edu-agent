# 优化器引入提案(GEPA 三键之③;结构改动提案,零依赖落地)

**性质**:四类结构改动(第三方依赖)的**提案件**——本文档只做提案与证据,不含依赖落地、不含代码改动、零模型调用。人批 + 外部评审通过后,另起一单才动 `pyproject.toml` 与代码。
**来源**:PM 直发 2026-09-16(`sha256=53fcf7c293033fc0`);用户裁定 2026-09-16「现在开」,趁 #280 合并与 ⑦ 门流程在跑,提前启动「人批 + 外部评审」长流程。
**先例**:`docs/evals/teacher-promotion-gate-v1.md`(机制件走 PR → 独立审查 → 人批)。
**一句话结论**:**不建议引入第三方依赖**。#256(2026-09-14 用户裁「手搓可以」)已裁定 GEPA 手搓核心循环、零依赖、复用现有 runner/judge 管线;本提案核实其依据在 2026-09-16 仍然成立且更强(#273 机器面三绿、#215 拦路条已消)。触发器满足 → 建议按 #256 点火手搓 spike,依赖路线留作全量阶段撞墙后的对照预案(§2.3)。

## 1. 为什么现在:#215 触发器四条逐条证据

#215 原结论「暂不引入,记触发器」;四条触发器现状:

| # | 触发器(#215 原文) | 现状 | 证据(路径/命令) |
|---|---|---|---|
| 1 | `#198` 机制落地 | **满足**(issue CLOSED) | `gh issue view 198 --json state` → CLOSED |
| 2 | 提示表面 ≥3 | **满足,远超** | `grep -cE '^[A-Z_][A-Z0-9_]*\s*[:=]' edu_agent/agents/small_lecturer/prompting.py` → **29**(= 提示面 25 + 资产路径 4,#273 逐处登记);另 `edu_agent/agents/small_lecturer/prompts/SKILL.md`、`configs/small_lecturer_style_profiles.yaml` 两处外置提示资产(核对于 2026-09-16,main `c11b7d7`) |
| 3 | corpus ≥100 | **满足** | train 120(dialogue_scenarios 3 + shadow_24 24 + gold 60 + math_gold_b2 13 = 100,+ 路 A teaching_context_shadow_pilot_20 = 20)/ heldout 4(`edu_agent/evals/datasets/` 逐文件计数,#273 同口径可复算);tier-2 的搜索切片 S=16 ⊂ train |
| 4 | 真模型评测预算人批 | **满足** | ① 预算批(2026-09-16 用户裁定;口径勘误 #253 c5680957065——原 PM 直发「388 案」系输入错误):**tier-2 = K=4 候选 × S=16 案切片 × I=6 轮 = 384 案次**,× 4.23 = **1,624** 调用(保守 5.22 → 2,004);heldout 终审 4 案 ≈17 调用另计——复算见 §4 |

季度复查条款(#215)由此解除,进入「先做 1 天 spike 出对比报告,再走结构审批」的既定路径——spike 的机器面部分已由 #273 完成(#273 = ①②③ 腿的机器核验件),本件即「结构审批」环节。

## 2. 引入什么:先答 ponytail 两问,再给候选事实

### 2.1 为什么不自己写?(ponytail 第一问)

**已经决定自己写,且理由成立**:#256(2026-09-14 用户点头)逐条——
1. DSPy 路线要修 4 座桥(Module 包装 ~100-200 行反包多轮 kernel 会话 / 指令 docstring 映射 seam / 评估管线对接我们 runner 语义 / 工件溯源重落盘)≈ **300-600 行适配代码**,换来在别人的循环里 debug;
2. 它卖的核心机器(种群 + Pareto 记账 + 反思模板)本身很小:手搓组件分解合计 **~400-500 行**(prompt seam ~30-50 / mini-batch 采样 ~20 / 打分向量 ~50 / 反思编辑器 ~100-150 / 选择+种群 ~100 / 循环驱动 ~100),全部落在现有管线旁;
3. **零新依赖**:第三方依赖人批 + 02 §2 预算对冲直接免掉(现 runtime deps 5/15,配置 3/5);
4. spike 产出直接长成全量工具(加 checkpoint/resume),不是扔的原型;
5. 编辑器走判官模型,与被测 tutor 模型分离,天然防「自己改自己的题」;
6. 留门:全量阶段真撞上需要更重的机器(并行编排/断点/缓存),带具体痛点清单重评 DSPy。

### 2.2 为什么不用 stdlib?(ponytail 第二问)

GEPA 的「进化 + 多目标记账」没有现成 stdlib 对应——但**也不需要**:手搓路线用的是「简化 Pareto(新批次不劣于父代且一维更好才留)+ 轮换采样 + 逐轮 dump」(~100 行),不实现通用进化框架。`random`/`json`/`itertools` 即够;要的是**这一个循环**,不是搜索库。

### 2.3 依赖候选事实(留作对照预案;非本件申请项)

| 面 | DSPy(含 dspy.GEPA) | gepa(独立包,GEPA 作者分离发布) |
|---|---|---|
| 引入形态 | `uv add dspy`(进 `pyproject.toml` dependencies,uv.lock 锁定) | `uv add gepa`(同) |
| 版本/许可 | 3.x 线(GitHub Release 见 3.0.4/3.1.0b1;代理预核 PyPI 最新 3.3.1,落地单当场核验为准);许可以落地单当场核验 | 0.1.x 线(0.1.4,2026-07);MIT |
| 依赖足迹 | 重:自带 Module/LM 抽象 + litellm/pydantic/diskcache 等数十传递依赖 | 轻于 DSPy:黑盒 `gepa.optimize(seed_candidate, trainset, valset, task_lm, reflection_lm, max_metric_calls)`,**可完全脱离 DSPy**;LM 走 LiteLLM provider 串(litellm 为传递依赖) |
| 与本仓管线契合 | 需 dspy.Module 抽象 = #256 所述 4 座桥 | **evaluate 直调普通函数**——与 `judge_transcript`/确定性 check 形状最贴(#215 既有结论) |
| 离线/本地端点 | 可指 OpenAI 兼容 base_url(本地 llama-server);遥测需显式关闭(具体开关名落地单核验) | 同左 |

> 来源:gepa README 与 release 历史(github.com/gepa-ai/gepa、PyPI `gepa`),DSPy Release(github.com/stanfordnlp/dspy);核对 2026-09-16,均未本机安装。版本级数字(含传递依赖计数、遥测开关名)以落地单**当场核验**为准——本件零安装零调用,刻意不写未经本机复核的精确值;这也是把「引入」与「提案」分离的原因之一。
> 若外评推翻手搓结论、裁定引依赖:走四类结构改动全流程(人批 → 单独 PR 只做 `uv add` → 锁定审查 → CI 绿),且**先试 gepa 独立包**(黑盒直调,依赖面与抽象错配都小一档)。

## 3. 包依赖方向(02 §2.2 硬约束)

优化器属**评测侧工具**,无论手搓还是依赖路线,方向约束相同:

```
                    ┌─ evals(优化器/runner/judge/corpus)─→ gateway(HTTP 客户端)
用户/人审 ←─ 工件 ←─┘                 ↑
edu_agent/agents/**(kernel/prompting)─┘ 不反向:agents 不得 import evals
```

- 方向设计意图与 02 §2.2 一致(优化器属评测侧,agents 不该碰);**但现行 import-linter 合同未显式覆盖 `agents → evals`**(02 §2.2 合同 ② 与 `.importlinter` 的 agents-isolation 均只禁 api/store)——如需 CI 强制,须另起合同(四类结构改动,需人批,不在本件范围)。**优化器产出的只是 prompt 文本 diff(工件)**,合并走「人审 PR → 人合 → 重部署」,agent 运行时路径上没有也不应出现优化器符号;
- 手搓落点:`edu_agent/evals/` 旁(或 `scripts/`,落地单定),与 `corpus_round.py` 同层;**不碰** `edu_agent/agents/**`(#256 治理约束:搜索空间只有 prompt 面);
- 若引依赖(预案):依赖包只被 `evals` 侧 import;`gateway`/`agents`/`contracts` 零 import。

## 4. 预算接口(1,624 / 保守 2,004 计入哪本账、经哪个入口计量)

- **账本落点**:#253 执行序楼(本波 ①–⑦ 件在该楼流转记账:① 预算批、⑦ 门进度均挂此)。本件回执按纪律段格式落 #253;1,624(保守 2,004)为 ① 批定值,后续实际消耗按实跑报数增补,不预设上限调整。
- **复算公式**(#273 勘误后口径,审查已逐位复现):`tutor 调用 = Σturns − 首问轮数 + summary 案数;judge 调用 = 可判案数;每案次 = (tutor+judge)/案数`。锚点:92 案工件 `corpus-round-v2/collect/cases-20260914T032228Z-bda5` → 每案次 4.23(保守 5.22)。**① 批定值对账(#273 算术表口径 = `K × S × 每案次调用 × I`;「案次」= 案×轮的评估次数,勿读成「案数」)**:`4 × 16 × 6 = 384 案次 × 4.23 = 1,624`;保守 `384 × 5.22 = 2,004`——**与批定值逐位吻合**。对照行:全 train 单候选 120 × 4.23 ≈ 508;K=6/S=24/I=8 = 1,152 案次 × 4.23 = 4,873;heldout 终审 4 案 × 4.23 ≈ 17 调用,**不含在 1,624 内**。
- **计量入口 = 现成两件,零新造**:
  1. **Gateway facts 落盘**(`api-facts.jsonl`,#271 判卷 token 锚点同源:2,751 in / 510 out tokens 均每调用)——优化器编辑器与评估调用全走现有 `Gateway`,每次调用自动落 facts,调用数/token 就地可数;
  2. **#257 身份三件套**(git HEAD / `prompts_sha256` / `models_sha256`)+ run manifest(#273 已实证工件)——每轮迭代的可归因性直接复用。
- **02 §5 禁止项对照**:不建租约/心跳/队列/调度器/worker 池——轮次驱动是单进程顺序循环(#256 组件 6 ~100 行),断点续跑复用 EvalRunner 既有面,不新造。

## 5. 冻结冲突处理(#215 拦路条的消解)

#215 拦路条「模板在 kernel.py 与冻结冲突」**已被后续工作消解**,逐面核对:

| 冻结/基线面 | 内容 | 优化器为何不冲突 |
|---|---|---|
| kernel.py 残留 | **0**(#273 机器核验,#238 登记的 6 处外置 schema×3+批评提示×3 全在 prompting.py) | 搜索面在 prompting.py,内核零接触 |
| 判据指纹 | `judger_sha256`(checks.py+judge.py 指纹,#242/#280 报告头部盖戳;rubric 资产 `small_lecturer_v3_2.yaml` 版本化) | 优化器不改 checks/judge/rubric → 指纹跨优化轮**不变**;指纹变化只可能来自判据侧 PR,与优化器无关 |
| 冻结切片 | 教师盲区 gate 11 案(`artifacts/teacher-gate-slice/`,输入 `slice-cases.jsonl` + 基线 `slice-baseline.jsonl` 逐字冻结) | 切片是 ⑦ 门**评审面**:每个最终/短名单 candidate 过一次门;搜索只见 train(#256 不变量 1),切片输入/基线文件不被搜索触碰 |
| heldout | b2_heldout 4 案(独立文件;corpus_round 显式路径加载,不传不可见) | 同上:终审用,不进搜索 |
| 93 案基线 | judge-v3.2-rescore-93(#271 token/调用锚点);92 案有 transcript(#273 机器计数) | 优化轮产出落**新 run 目录**(corpus_round 既有落盘纪律),不覆写既有基线;基线重注册只在判据侧变更时走 #280 同款流程 |

**优化对象(搜索空间)的明确界定**(#273 逐处登记 + 不变量 2):
- **面内**:prompting.py 25 处提示面常量(首批 spike 对象 = #215 点名的 elicit 模板族;具体面内子集由 spike 报告按轮申请);
- **面外(明示 5 处)**:`FAIL_CLOSED_TEXT`/`_OPENING_FALLBACK`/`_ELICIT_TEMPLATE`/`NEEDS_REVIEW_TEXT`/`SAFE_FALLBACK_TEXT`——内核机制文本(闸面/兜底/弧线状态机输出,含字面比对 `prev == _ELICIT_TEMPLATE` 与前缀统计两处机械耦合)。任何一处纳入搜索 = 先外置 + 解耦 = 结构改动另批(#273 已留裁定接口)。

## 6. 回滚面

| 路线 | 移除动作 | 移除后旧候选件 |
|---|---|---|
| **手搓(建议路线)** | 删 `edu_agent/evals/` 下优化器模块 + `scripts/` 入口(若有)+ 生成工件目录;无 lockfile/CI/配置项变更 | **不失效**:候选件 = JSON 工件(种群/分数)+ prompt diff 文本,纯数据可读;已合并进 prompting.py 的 prompt 本就是普通代码,与优化器共存亡关系为零 |
| 依赖(预案,若外评裁定引入) | `uv remove <pkg>`(pyproject + uv.lock 同步)→ 删 CI 作业/step → 清 `~/.cache` 相关缓存(uv 缓存按 key 自然过期,无需清理动作)→ import-linter 合同不变 | 同上:候选件是文本与 JSON,不依赖优化器运行时;唯一失效面 = 「用优化器继续跑」能力本身(留档后不可续跑,可重装恢复) |

两路线共同点:**优化器可整体移除而不动 kernel/判据/工件语义**——移除回滚半径被 §3 的依赖方向与 §5 的面内/面外切分压到最小。

## 7. 复现与 CI

- **Mac 本地 = 唯一真跑面**(与既有评测线同纪律):tutor/判卷模型本就在 Mac(mlx/llama-server 本地端点),优化器循环纯本地 gateway 调用;复现 = spike 手搓件落地后 `python -m edu_agent.evals.<optimizer> --budget <n>`,工件含逐轮 prompt diff + 分数 + facts(人审原料)。
- **CI = 显式 skip**:CI 无本地模型端点,优化循环属真模型口径(与 corpus_round 批跑同边界,#216 「真模型不进 CI」);进 CI 的只有**零模型单测**(种子采样/Pareto 选择/lint/循环驱动的小步断言,假 gateway)——这部分随落地单走常规测试,不设 skip 标记。本件(提案件)本身 make check 全绿、零新测试。
- **token/成本可观测**:见 §4 计量入口,facts 逐调用落盘,超预算即停(循环内置计数,不靠人盯)。

## 8. 外评材料:载重主张清单(每条 = 主张 + 可核验方式)

| # | 载重主张 | 可核验方式 |
|---|---|---|
| 1 | 触发器四条已满足,#215「暂不引入」的前置障碍已消 | §1 表逐行:issue 状态 / `grep` 命令 / 数据集计数 / ① 批定值(#253 楼) |
| 2 | 手搓 GEPA 核心循环 ~400-500 行可行,复用现有 runner/judge 零胶水 | #256 组件分解表 + #273 §二(judge_transcript 普通函数 / checks 零模型 / EvalRunner 断点续跑);外评可抽查 `edu_agent/evals/` 现有代码规模对照行数估 |
| 3 | 引 DSPy 需 ~300-600 行适配代码且抽象错配(多轮 kernel 会话反包进 dspy.Module) | #256 决策依据;外评可按 DSPy 文档的 Module/Evaluate 契约对照本仓 kernel 多轮会话形状独立复估 |
| 4 | 优化器与判据指纹/冻结切片/93 案基线结构性无冲突 | §5 表:各冻结面的文件路径与耦合点(字面比对/前缀统计)逐条给出行号级锚点,#273 同 |
| 5 | 依赖候选(若走依赖路线)的版本/许可/传递依赖足迹/离线端点/遥测关闭 | 外评当场 `uv pip install --dry-run` + PyPI 元数据核验;§2.3 版本号取自公开来源(GitHub Release/PyPI,2026-09-16 核对),以落地单当场核验为准 |
| 6 | 预算 1,624(保守 2,004)的复算公式与计量入口现成 | §4:92 案锚点工件路径 + 计数公式 + api-facts/#257 三件套,外评可用既有工件逐位复算 |
| 7 | 搜索空间面内/面外切分(25 处 vs 明示 5 处面外)定义清楚且裁定权在人 | #273 腿① 逐处登记表(含每处理由);外评可挑战任何一处的归属判定 |
| 8 | 回滚半径最小(移除不动 kernel/判据/工件) | §6 两路线移除清单 + 候选件纯数据性质 |

## 9. 不做清单(本件边界)

- **不碰判据**:checks.py / judge.py / rubrics 资产 / 判据指纹机制零接触(优化器未来也不碰);
- **不碰 kernel**:`edu_agent/agents/**` 零改动;kernel.py 5 处机制文本保持面外;
- **不动预算上限**:1,624/2,004 为 ① 批定值,本件不申请调额;02 §2 各项硬上限(行数/依赖 15/配置 5)不在本件射程;
- **不落地依赖**:pyproject/uv.lock 零变更(DSPy/gepa 都只是 §2.3 的留档事实);
- **不碰 docs/plan/**:本件只新增 `docs/evals/optimizer-introduction-proposal.md`;
- **零模型调用、零 CI 变更**;
- **不代替 #256**:手搓 spike 的点火仍是 #256 的时间盒与五问流程,本件只消解其「优化器引入决定」这把人键的前置争议。
