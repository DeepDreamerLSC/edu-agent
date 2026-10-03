# Inspect 迁移合同 v0.1(I0 冻结件)

状态:**FROZEN(I0)** · 签发:#521 I0 · 日期:2026-10-03
本文档 = 可执行 contract;#521 = 计划与 Authority owner(不复制其全文,冲突时以 #521 §六
Architect Tightening v0.2 为准)。I0 零模型调用、零 runtime/test 改动、不装 inspect-ai、
不改 pyproject/lock;一切运行形态均为未来候选描述,不写成已实现事实。

## 执行身份(本件产出时记录)

- base = `origin/main` `949cb72da68df64844dd20b96aeff9d5812ed588`;独立 worktree
  `/tmp/edu-i0`(主仓 checkout 在 `data/completion-projection-v12`,未动)。
- 主仓既有 untracked(`.omc/`、`edu_agent/evals/artifacts/d1-e4-baseline-repro-v33-flash-92*/`、
  `edu_agent/evals/artifacts/m3-01/`、`scripts/m3_smoke.sh`):**既有,非本任务产物**。
- #521 正文抓取:sha256 `cb7b644349d1404c68c9b061db20a0bd58dc75b0940ff5586792eff6dfa14c2b`,
  抓取时间 2026-10-03T06:35:33Z(state OPEN)。
- 六个 runtime 文件开工 sha256(全程只读,收工复比;第六件 s2_judge.py 为 S2 Subject 本体):

| 文件 | sha256 |
|---|---|
| `edu_agent/evals/runner.py` | `0f838b580078788e2390cce2af26e1fb7bc5138e21429ffa486759b737509e74` |
| `edu_agent/evals/identity.py` | `2ea8a36e4f51f76eb2267bd6889ce09a69969cf33bd41ef673231ec1a4aa33db` |
| `edu_agent/evals/kernel_subject.py` | `068678a281a2b3d73a00d2376f6c98162a1f33b21ea45561fc3597d81fde8c36` |
| `edu_agent/evals/corpus_round.py` | `cc72d37991e089e6ddbca8ef04396918a7ec8c87b01503eaf7bd92b7f33a9e65` |
| `scripts/s2_judge_battery.py` | `7abd05b14fb4d61014f8e0335096f6f418bf26cff2043ae2f4e91bcdea0adac8` |
| `edu_agent/evals/s2_judge.py` | `fcf7cbb723912595e99d55c116b0d977524865a4d7400a17993b09ea8995f288` |

---

## 1. Scope

- 冻结 Inspect AI 迁移(#521)依赖的四份合同:Ownership Map、Canonical Eval Result、
  三层 Identity、Redlines + Rollback + Net Deletion Test;附 Current Execution Ownership
  Inventory(§2,实读仓库所得)与 I1 Entry Contract(§10,预先写死)。
- **不做**:不实现 Inspect、不写 adapter、不装依赖、不做 POC、零模型调用、零外部 API、
  零 runtime/test 修改。C 层 Harness Identity 字段是 **candidate/verify-in-I1**,本文档
  不把它们伪造成已冻结事实。
- 涉及语义的既有约束不重开:#464(测量有效性)、#490(execution identity / strict
  resume)、#494(变更影响协议)、#511(M4 已 CLOSED)。

## 2. Current Execution Ownership Inventory(逐文件实读,非摘要)

### 2.1 EvalRunner 现行 ownership(runner.py @ `0f838b58`)

| 能力 | 位置(file:line) | 现行语义 |
|---|---|---|
| Subject 契约 | runner.py:50-59 | `Subject` Protocol:`name` + `run_case(case)->dict`;环境问题抛 `EnvironmentFailure`,内容缺陷抛其他异常/返回带缺陷记录 |
| concurrency owner | runner.py:160-161(配置 runner.py:45-47) | `ThreadPoolExecutor(max_workers=config.concurrency)`,`RunnerConfig` 仅 `concurrency: int = 2` |
| per-case checkpoint owner | runner.py:157, 165, 215-220 | 每 case 一份 `results/<safe_case_id>.json` 即 checkpoint;`_needs_run`:文件缺失或 `status=="environment"` 才补跑,`content` 不补 |
| resume scheduling owner | runner.py:136-171 | `run()` 过滤 pending→并发→`KeyboardInterrupt` 取消未开始用例、保留已完成 checkpoint(runner.py:166-170);corpus_round 侧另有 `resume_run_dir`(corpus_round.py:300-325) |
| environment/content 失败语义 | runner.py:33-38, 222-235 | `EnvironmentFailure`→`status="environment"`;其余异常→`status="content"`(不中断过夜批);台账按 kind 分列 |
| retry 语义 | runner.py:226-230 注释 + attempts 恒 1(runner.py:229/233/235) | **无进程内整案重跑**;单次模型调用可靠性只归 Gateway;历史注记:2026-09-10 artifacts manifest 可见已退役的 `env_retry_attempts/backoff` 配置面(#254 P1 删除),现行 `RunnerConfig` 无任何 retry 字段 |
| manifest owner | runner.py:173-190 | 新开 run 落 `manifest.json`:started_at / dataset{name,sha256} / config{…,sha256} / subject / total_cases / identity(可选);atomic 写(189) |
| strict identity resume gate | runner.py:88-113(`_identity_resume_diffs`)+ 192-213(`_verify_resume`) | strict 下 stored/current identity 两边必须存在且全等;current 缺失 fail closed;stored 缺失→覆盖旧 run 拒绝;先于 dataset/config/subject 三面(runner.py:149-151);不等即 `ResumeMismatch` |
| failure ledger | runner.py:249-254(锁 :134) | `failures.jsonl` 追加写,kind=environment|content,detail 截 500B |
| atomic result write | runner.py:116-120 | tmp 文件 + `os.replace`;结果文件(165)与 manifest(189)共用 |
| Canonical 结果记录 | runner.py:237-247 | `_result` 七字段:`case_id/status/attempts/duration_ms/finished_at/error/transcript`(§4 的现状来源) |
| case id 安全化 | runner.py:71-85 | `safe_case_id`:240B 预算 + 病理长 ID 哈希后缀(#450) |

identity 指纹构造公共 helper(identity.py @ `2ea8a36e`):`file_sha256`(:19-21)、
`head_sha256`(冻结件 head -n -1 口径,:24-30)、`git_head_sha`(check=True fail
closed,:33-38)。构造侧收口在此,stored-vs-current 比较侧在 runner 的 strict 门。

### 2.2 Subject 契约现行实现

- `KernelSubject`(kernel_subject.py:71-174):`name="kernel-small-lecturer"`;`run_case`
  按剧本驱动 start→reply×N→finish;`GatewayError.failure ∈ ENV_FAILURES` →
  `EnvironmentFailure`(:157-160),其余照抛 = 内容失败。
- `S2JudgeSubject`(s2_judge.py:135-149):`name="s2-judge"`;同款 env 映射(:146-149),
  schema_violation/truncated 等按内容失败。
- `LegacyAdapter`(M1)与 `JudgeSubject`:legacy_adapter 仅 `__init__` 导出 + 测试驱动,
  无现行脚本经 EvalRunner 跑它;JudgeSubject 由 judge_score/rescore_judge 驱动(下表)。

### 2.3 Consumer inventory(`git grep -l "EvalRunner\|RunnerConfig\|strict_identity"` 全量判定)

**执行消费者**(构造 EvalRunner 并真跑批)——判 active 的标准:有现行接线(模块入口/
CI/strict 门消费者)且非冻结里程碑一次性工具:

| # | 消费者 | 证据 | 分类 |
|---|---|---|---|
| 1 | `edu_agent/evals/corpus_round.py:685-693` | 模块入口 `python -m edu_agent.evals.corpus_round`(薄包装 scripts/corpus_round.sh);**I5 起默认 execution owner = Inspect**(inspect_adapter;scorer 编排/checkpoint/guard/identity preflight),显式 `--legacy-runner` 才走 EvalRunner(:685-693,禁自动 fallback) | **switched**(I5)· default active EvalRunner=0;`--legacy-runner` 过渡 |
| 2 | `scripts/s2_judge_battery.py:249-272` | S2 battery 入口;**I6-A 起默认 execution owner = Inspect**(execution-only 轮:GA/GB/VOID 判分留 battery 自 checkpoint 复算),显式 `--legacy-runner` 走 EvalRunner+`strict_identity=True`(legacy 通道语义不变);identity 六键(:63-77)+ owner/harness 面 | **switched**(I6-A)· default active EvalRunner=0;`--legacy-runner` 过渡 |
| 3 | `scripts/tuning_round.py:448` | **nightly CI 接线**(evals-nightly.yml「夜评」step,每日 23:00) | **active** |
| 4 | `scripts/image_teaching_round.py:106` | **nightly CI 接线**(evals-nightly.yml image 段 step) | **active** |
| 5 | `scripts/d6d7_gold_consume.py:190-195` | `strict_identity=True`;#464/#485 冻结审时代的运行器(云臂),identity 链与 strict 门均为现行 #490 M3 形态 | **active** |
| 6 | `scripts/rescore_judge.py:140-141` | offline rescore 路径(JudgeSubject 经 EvalRunner;#254 件1)——#521 中「offline re-score」候选能力的现状本体 | **active**(离线工具) |
| 7 | `scripts/judge_score.py:68` | #32(M0)judge 稳定性档案工具;无 CI/夜间接线 | runnable · 里程碑绑定(非 active path) |
| 8 | `scripts/arc_eval_collect.py:92` | #101/#143 双臂评测收集器,口径冻结于 teaching-arc-eval-v1.md | runnable · 里程碑绑定 |
| 9 | `scripts/arc_eval_fix112_frames.py:167` | #112/#148 帧网格工具(一次性 before/after) | runnable · 里程碑绑定 |
| 10 | `edu_agent/evals/finish_evidence_eval.py:156` | 2026-09-16 finish() 语义验收跑批器(一次性验收) | runnable · 里程碑绑定 |

**非执行消费者**(不得计入 active):tests/evals/ 下 test_runner / test_corpus_round /
test_s2_judge(+I6-A 的 test_s2_battery_switch)/ test_d6d7_matched_surface /
test_legacy_adapter / test_inspect_adapter(测试);docs/evals/ 4 篇
proposal/trial 文档与 artifacts/datasets README(历史证据);`scenario_corpus.py`(仅
docstring 提及,不构造 runner);`classroom_burst.py`(stub 内核服务小压测,**不消费
EvalRunner**,审计排除)。

**审计事实(交 §9/§11)**:#521 叙事以 corpus_round + S2 为两个迁移证明面;实读仓库,
执行消费者共 **6 active + 4 里程碑绑定 = 10 个可调用执行面**。COMPLETE 的
consumer-zero 审计(§7/§8)必须覆盖全部 10 个(迁移或删除),不能只数两个证明面。

**I6-A 时点分类口径(五类,2026-10-03 回填,#521 UTC 口径)**:①default active(仍以 EvalRunner 为
默认执行面:tuning/image/d6d7/rescore 4 面)②switched · 显式 legacy 过渡
(corpus_round、S2:default active EvalRunner=0,各自 `--legacy-runner` 保留过渡回退,
均计 I6-C 删除面)③runnable · 里程碑绑定(judge_score/arc×2/finish 4 面)④test-only
(tests/evals 合同测试,不产 artifact)⑤artifact reader(offline 消费历史 run 工件,
不构造 runner)。active 从 I0 的 6 → I5 后 5 → **I6-A 后 4**(S2 出列)。

## 3. Ownership Map(冻结)

| 能力 | Owner | 备注 |
|---|---|---|
| Construct definition | **edu-agent** | 测什么,不随 runtime 迁移 |
| Corpus schema(scenario/case 形状) | **edu-agent** | loader 校验面(scenario_corpus) |
| Gold / expectation(expect.checks、battery expected) | **edu-agent** | expected 只进 scorer 的泄露防火墙不变 |
| Corpus promotion authority | **edu-agent** | Inspect 无晋升权 |
| Subject contract(Protocol) | **edu-agent** | runner.py:50-59 的契约本体 |
| KernelSubject(及 Subject 实现) | **edu-agent** | Inspect 只能调用,不能改写 |
| deterministic check 语义(`run_check()`) | **edu-agent** | 未来至多 Inspect scorer wrapper,逻辑不重写 |
| v3.3 Judge 语义(judge_transcript/rubric) | **edu-agent** | 同上;transport/model abstraction 不与迁移捆绑 |
| S2 ruler 语义(GA/GB/VOID) | **edu-agent** | S2 VOID Policy 归 S2;Inspect status 不自动取代 |
| Human review | **edu-agent** | |
| Release policy / verdict | **edu-agent** | Inspect score/metric 不自动成为 Gold Truth |
| Product Contract | **edu-agent** | Inspect 不获得任何产品变更权 |
| Model retry / fallback | **Gateway** | 单次模型调用可靠性;Inspect 不叠加模型层 retry |
| Model usage / trace(facts) | **Gateway** | facts/session_id 回联义务不迁移 |
| sample scheduling(哪些 case 待跑) | **Inspect candidate** | 现行 = EvalRunner `_needs_run` + corpus_round `resume_run_dir` |
| concurrency | **Inspect candidate** | 现行 = ThreadPoolExecutor(runner.py:160) |
| checkpoint(per-case) | **Inspect candidate** | 现行 = results/<case>.json |
| execution retry / resume | **Inspect candidate** | 仅 sample execution 层(§6 分层) |
| EvalLog storage | **Inspect candidate** | 存储格式归 Inspect,**语义本体归 Canonical Result(§4)** |
| scorer execution(调度执行 scorer) | **Inspect candidate** | scorer 语义本体仍归 edu-agent(上行) |
| offline re-score | **Inspect candidate** | 现行本体 = scripts/rescore_judge.py |

总原则:«**Inspect 可以拥有 Mechanism,但不能因此获得 Policy 或 Authority**»。

结构性禁令(双 Runner 禁止):
- 禁止 `EvalRunner → Inspect → Subject`(把 Inspect 包进现有 runner 当库用);
- 禁止 `Inspect → EvalRunner → Subject`(把旧 runner 包进 Inspect solver)。
- Shadow 阶段允许同一批输入产两套 artifact 做对照,但**一次 execution 只能有一个
  execution owner**——不存在嵌套 owner,不存在静默双跑。

## 4. Canonical Eval Result Contract(edu-agent owner,冻结)

edu-agent 自己拥有的结果语义本体。最小七字段(现状来源 runner.py:237-247,逐字段
product/execution 归属与缺失处置):

| 字段 | 语义 | Owner | 事实类 | 未来 Inspect adapter 映射来源(候选) | 缺失时 |
|---|---|---|---|---|---|
| `case_id` | 案件标识(safe_case_id 口径,#450) | edu-agent | Execution fact | Inspect sample id 经 adapter 映射;**映射不可逆信息不得丢**(前缀/截断规则保留) | **fail closed**(identity 对不上即拒) |
| `status` | `ok` \| `environment` \| `content`(闭集,§6) | edu-agent | Execution fact | 由 Inspect 执行事实 + Subject 异常分类**经 adapter 翻译**;Inspect 自身 status 枚举不直接透传 | **fail closed**(未知状态即拒,不猜) |
| `attempts` | 该 sample 在本 run 内的执行尝试次数(现状恒 1) | Inspect candidate(机制) | Execution fact | Inspect sample 的执行尝试计数;Product 不解释次数含义 | **fail closed** 缺字段视为不可信记录 |
| `duration_ms` | 单 case 执行时长(ms) | Inspect candidate(机制) | Execution fact | Inspect sample 时间戳差;口径缺失时记 null 并披露 | fail-open(可 null,报告层不计入) |
| `finished_at` | 完成/失败时刻(UTC ISO) | Inspect candidate(机制) | Execution fact | Inspect 完成 timestamp | fail-open(可 null,晨间摘要降级) |
| `error` | 失败原文(类名+信息+截断 traceback) | edu-agent | Execution fact | Inspect error 文本经 adapter 附着;**Inspect error type 不自动成为 taxonomy**(§6) | ok 行允许 null;失败行缺失 = fail closed |
| `transcript` | Subject 返回的原始记录(judge 输入,runner 不解读) | **edu-agent(Subject)** | **Product fact** | Inspect 不拥有此字段语义;adapter 原样搬运,零改写(I1 红线) | 非 ok 行允许 null;ok 行缺失 = fail closed |

数据流红线(冻结):

```
Inspect EvalLog → 单向 adapter → Canonical Result → checks / judge / report / policy
```

- 上层(checks/judge/report/policy/human/release)**不得直接依赖 Inspect result shape**;
  Inspect-specific 字段不得泄漏进 Authority / Release Policy(#521 §六 B)。
- **Inspect status 不自动成为 Product verdict**;Product 侧判定永远从 Canonical +
  edu-agent 语义出发。
- **Inspect error type 不自动成为 failure taxonomy**;taxonomy 冻结为 §6 三类。
- **historical artifacts 不重写**:旧 EvalRunner 结果只需 reader/adapter 适配进
  Canonical,不回填、不改写历史事实(与 #521 红线 5 同源)。

## 5. Identity Contract(三层,冻结字段集)

规则«同一层内任一字段变化 = 该层 Identity 变化;不得伪装成同一 run»贯穿三层。
改 scorer/rubric 只能改变 Scoring Identity,**不得伪装成同一 scoring run**。

### A. Execution Identity(现状口径,按现行消费者实际要求)

| 字段 | 现状来源 | 要求 |
|---|---|---|
| git SHA | corpus_round run_identity(corpus_round.py:87)/ s2 `_identity` git_head_sha / d6d7 同 | 必填;s2/d6d7 fail closed(git 缺失即抛),corpus_round 允许 None 但**如实披露不伪造** |
| dirty / diff identity | corpus_round:git_dirty + git_diff_sha256(+worktree.patch 落 run 目录,#350 ⑧) | **按现有 consumer 实际要求**:corpus_round 要求;s2/d6d7 现行 identity 不含 dirty 键,迁移时**不得单方面加严或放松**(加严/放松 = 改 #490 纪律 → STOP 回 #521) |
| prompt(资产指纹) | file_sha256(prompting.py / prompt_asset) | 必填 |
| model config | models.yaml 文件 sha256(或等价模型配置指纹) | 必填 |
| dataset / corpus | dataset 文件 sha256(manifest.dataset.sha256)+ corpus/cases 指纹(corpus_round cases.jsonl sha) | 必填 |
| subject | subject name(manifest.subject) | 必填 |
| runtime | 现状 = EvalRunner 本体隐含(config sha 进 manifest);**未来 Inspect 执行时 runtime 面升级为 C 层 Harness Identity**(如下,不隐含) | 必填(形式随 owner 变) |

strict resume 门语义(#490 M1/M3):stored/current 两边必须存在且全等,任一缺失或
不等 → `ResumeMismatch` fail closed;此门**归 edu-agent,不随 execution 迁移而迁移**
(#521 I0 表:strict identity preflight → edu-agent)。

### B. Scoring Identity

| 字段 | 说明 |
|---|---|
| scorer implementation + version | 现状锚:judger_sha256(checks.py+judge.py+rubrics 资产拼接 sha,corpus_round.py:636-644);S2 侧为引擎/schema/转换器指纹链 |
| rubric identity | 冻结件 head -n -1 口径 sha(head_sha256;末行版本标记行不算漂移) |
| grader model identity | 服务通告名比较(compare_models;judge_primary 双字段:id 仅追溯、model 是比较基准;s2/d6d7 任一不满足 → VOID/作废) |
| scorer config | temperature/max_tokens/response_schema 等随 scorer 冻结的配置面 |

### C. Harness Identity(**已回填:I1/I2 实证口径,#521 I2 授权增量 1;docs-only,不改其余各节**)

Inspect 作为 execution/scoring substrate 时,Execution Identity 至少再记录(字段
口径已经 I1 Frozen Shadow 与 I2 Offline Ruler Bridge 实证):

- `inspect_version` = `0.3.276`(获取面:`importlib.metadata.version("inspect-ai")`;
  I1/I2 实测值);
- dependency / lock identity:仓内 `uv.lock` **无 inspect-ai 条目**(I0 纪律:spike
  阶段不装进仓),uv.lock inspect 闭包口径暂不可算——如实记为 experimental
  identity:丢弃式 venv sorted `pip freeze` 行 sha256 =
  `d154b799925492b2f611dd16f1aab871856ce11edb9b52fd44e36454379a0b84`
  (79 行,`/tmp/i1-venv`;inspect 相关子集 = inspect-ai 0.3.276 + pydantic 2.13.5
  + pydantic_core 2.46.5 + typing-inspection 0.4.4)。进仓安装后再改定为 uv.lock
  inspect 依赖闭包子集行的 sorted-sha,不伪装最终口径;
- Inspect task implementation SHA = scorer bridge(Subject bridge)实现文件字节
  sha256,随 run 落档(I2 spike `/tmp/i2/i2_harness.py` =
  `03c3baa91db0d2481836d533723672ffa367ffd61a7a4bba8677872e0232cfb9`,
  spike 不入仓,进仓后以仓内文件 sha 为准);
- adapter implementation SHA = EvalLog→Canonical + Canonical→scoring view adapter
  实现文件字节 sha256(I2 与 task bridge 同文件同 sha;分体实现后分记);
- EvalLog schema / version:`EvalLog.version: int` 字段稳定存在,0.3.276 写出与
  读回均为 **2**。

规则:«**Inspect version change = Harness change,不是透明依赖升级**»——同一
Product/Model 下升级 Inspect 产生的 execution,不得默认视为同一 Harness Identity。
回填履行:本节为 §10 预留的 I1 实证回填面,#521 I2 授权评论(5967774564)增量 1
授权本修改;其余各节(Ownership/Canonical Result/Failure semantics/Rollback/
Net Deletion)零改动。

## 6. Failure & Retry Semantics(I0 只冻原则,不实现)

| 类别 | 定义 | 处置 | 重跑权 |
|---|---|---|---|
| `environment` | 外部/运行环境失败(网络、凭据、服务不可用;Subject 抛 `EnvironmentFailure`) | 落 environment 状态入台账 | **可**由 execution resume/retry 重跑该 sample(现行 = `_needs_run` 补跑) |
| `content` | Product/Subject 已执行但内容失败(未知异常、状态机拒绝、schema violation) | 落 content 状态入台账 | **不得整案 retry**(重跑改变不了内容缺陷) |
| grader / scorer failure | 评分失败(judge/scorer 路径异常;现行 judge_rows 记 `{"error": …}` 不炸整轮) | 记 unscored / grader_failed(I2 目标映射) | **不得重跑 Product**;Product evidence 保持有效,只重 score |

分层原则(冻结):«**Gateway retry/fallback 只拥有单次模型调用可靠性;future Inspect
retry 只拥有 sample execution;两层不得形成 retry multiplication**»。
现状即按此执行(runner 无进程内重跑、attempts 恒 1;#254 P1 已删 env_retry 配置面);
迁移后由 I4 fault injection 证明不退化。三类失败不得互混;健康映射候选(Product
content failure → Inspect sample execution successful + canonical `product_status=content`;
environment → Inspect retryable error;grader → unscored)**必须实证,不得默认成立**
(#521 §六 D)。

## 7. Shadow / Switched / Complete 状态定义

| 状态 | 定义 | Inspect 权限 |
|---|---|---|
| **SHADOW ONLY** | Inspect 仅消费 frozen evidence(读旧 artifact/EvalLog);EvalRunner 仍是全部 execution owner | 只读;零 Product 调用(I1)、零 Judge 调用 |
| **CONSUMER SWITCHED** | 某真实 consumer 默认 Inspect execution;legacy 仅允许临时显式 rollback 开关(如 `--legacy-runner`),**不得静默双跑** | 该 consumer 的 execution owner |
| **COMPLETE** | active EvalRunner consumers = **0** ∧ default path = 0 ∧ hidden path = 0 ∧ CLI rollback path = 0 ∧ test-only production invocation = 0(§2.3 全部 10 个可调用执行面迁移或删除) | execution owner(全量) |

COMPLETE 时允许保留:legacy **artifact reader / compatibility reader**(读旧 run 目录
的 load_results/render/rescore 类路径)。COMPLETE 时**禁止保留**为活的第二套机制:
legacy execution scheduler、per-case checkpoint owner、resume owner、failure ledger
writer、concurrency owner(即 §9 清单的执行面本体)。

## 8. Rollback Contract(状态机)

```
SHADOW ONLY ──(I3–I5 通过)──▶ CONSUMER SWITCHED(逐 consumer)──(全部 consumer + 删 legacy 执行面)──▶ COMPLETE
     ▲                                   │
     └──── 显式 rollback(每 consumer)────┘
```

- 每个 consumer 独立切换、独立 rollback;rollback = 显式开关(过渡期允许),不是静默
  回退到旧 runner 仍跑。
- `CONSUMER SWITCHED → COMPLETE` 的硬门之一:legacy execution switch **deleted**
  (#521 §六 E)——COMPLETE 后不存在任何活的 EvalRunner execution rollback path。
- `COMPLETE → 任何回退` = 新变更,走 #494 变更影响协议 + #521 重开;不存在"悄悄
  切回来"。

## 9. Net Deletion Test(I0 只定义检查方法)

**候选删除面清单**(现行 EvalRunner execution machinery,以 §2 audit 实读为准):

1. ThreadPoolExecutor 并发执行面(runner.py:160-171)与 `RunnerConfig.concurrency`;
2. per-case checkpoint 机制(`_needs_run` runner.py:215-220 + results/<case>.json 写入 :165);
3. resume 调度逻辑(runner.py:136-157 pending 过滤 + corpus_round.resume_run_dir:300-325);
4. strict execution resume gate 的 execution 侧承载(`_verify_resume` runner.py:192-213
   ——语义门归 edu-agent 不删,**execution 侧实现**在迁移后可删;strict 语义必须在
   Inspect 路径等价重建);
5. atomic execution result owner(`atomic_write_json` 对 results 的写入;manifest 写入
   owner 同问);
6. failure ledger writer(`_ledger` runner.py:249-254);
7. execution manifest portions(`_run_dir` runner.py:173-190 中 dataset/config/subject
   三面在 Inspect 路径的对应物)。

**检查方法**(未来宣布 COMPLETE 前必须逐项回答,书面留档):

- 哪些**删了**(列文件/函数/行,以删除 diff 为证);
- 哪些**只是 compatibility reader**(只读旧 artifact,零执行路径);
- 哪些**仍在,为什么**(每项给理由;「Inspect 也能做到」不是保留理由)。

判定:«**adapter + Inspect + old runner 全保留 = Net Deletion FAIL,不得宣布
COMPLETE**»。外部框架只有在真实减少自建 execution mechanism 后才获得长期存在权;
#521 I2 Decision Gate 的问题口径:Inspect 替我们省掉了什么,而不是又增加了什么。

## 10. I1 Entry Contract(预先写死)

I1 只允许 «**Frozen Artifact Shadow**»:

- Product calls = 0;Judge calls = 0;
- 不改 corpus;不改 Canonical Result(§4 字段/状态集一字不动);
- 不迁 Authority;不改 current EvalRunner / 六个 runtime 文件;
- 不新增第二套 truth(不复制 Gold/Dataset);
- Inspect adapter 只读 frozen evidence(Baseline v1.1 frozen artifacts / Trusted Product
  Corpus 对应 frozen results),输出 Inspect EvalLog,零改写 transcript;
- PASS 口径沿用 #521 I1 节(case identity 100% 对齐、deterministic wrapper 逐案 100%
  一致、denominator 零 silent exclusion、source artifact SHA 可追溯)。

**STOP 规则**:I1 实现中若发现需要修改本合同任一节(Ownership Map / Canonical
Result / Identity / Failure 语义 / Rollback / Net Deletion 口径),«STOP → 回 #521
升级,不得实现中顺手修改»。须改 corpus schema 才能适配、须复制第二套 truth、
transcript 需有损 reshape、adapter 开始拥有 Domain Policy —— 同为 STOP(沿用 #521
I1 STOP 节)。

## 11. Open Questions(仅列阻 I1 的;更远的进 #521 跟踪)

1. **无阻 I1 项。** I1 输入全部为已存在 frozen artifact,§4/§5/§6 冻结面已足以
   写只读 adapter。
2. (不阻 I1,记档)§2.3 审计出的 10 个可调用执行面 vs #521 叙事的 2 个证明面:COMPLETE
   审计范围按本合同 §7(全部 10 个)执行;里程碑绑定脚本(§2.3 #7-#10)届时是删是迁,
   在 I5/I6 规划时入 #521 裁定。
3. (不阻 I1,记档)§5 C 层 Harness Identity 五字段的实际取值口径(inspect_version
   暴露形式、lock 子集指纹、EvalLog version 字段有无)由 I1 实证后回填;回填即修
   合同,走 §10 STOP 规则报批。
