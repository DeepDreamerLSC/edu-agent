# ⛔ 证据留档(引擎已切换,2026-09-19)——本目录 best 模板已 REJECTED,禁止复用为候选

本目录为 GEPA 路线的证据留档,**非可用基线**。`checkpoint.json` 的 `/best/template`
(nr / epoch-2 复讲模板,即下文"请复讲:先说核心思路…"全文)已被教师盲审判负:
**4/4 worse**(用户亲审,2026-09-17,#293 记档 233d0fca,原话「太机械,不够亲切,
不像是面向学生的语气」),叠加试跑 delta=0 与「未审过的差异不上线」原则,
candidate 已重定义为 **内核修复 × 冻结默认模板**(引擎切换裁定见 #293)。
任何未来使用方**不得**把本目录的 fitness 读数或模板内容当作可复用候选;
GEPA 重燃仅走 #310 触发器条款。

---

# GEPA nets-in-loop main-03(2026-09-18 用户信封:2 代 / 300 calls 帽 / 停等审)

**信封**:用户直发 2026-09-18——泄露网作 loop 内约束跑 GEPA 进化,2 代 300 calls
硬帽,停等审;driver nohup 无人值守 + 每代 checkpoint + 看门狗只记录不重跑;
agent 只在开跑前三查与跑完打包两处出场。**红线遵守**:93 面语料 / rubric /
判据指纹零改动(facts 只读计数);held-out 4 帧零接触(三查验证)。

## 判读预注册(跑前冻结,见 run_nets.py 文档串)

接受判定 = HNU 接受函数(#332);泄露网拦截读数 = seed 批 vs 各代变体批;
初始 = main-02 best 双旋钮组合(逐字);editor_focus=mean(main-02 已穷尽 nr
方向)、editor_role=judge(r24 起本地跑口径,全程零远程依赖)。

## 运行时间线(全部本地,零远程零降级)

| 时点(本地) | 事件 |
|---|---|
| 00:46 | 三查全绿(checkpoint 干净 / facts 空 / 硬帽 300==300 / held-out 三集不相交 93·12·4 / 8301+8303 活) |
| 00:47 | nohup 驱动(PID 7433)+ 看门狗(PID 7460,#290 契约风格 liveness-watch.sh) |
| ~00:59 | seed 批(15 案)评估完成,checkpoint 落盘 |
| ~01:05 | cohort-0 刷新(当前最优重评)+ round-00 完成,checkpoint(236 calls) |
| 01:15 | **硬帽精确熔断:300/300,超顶 = 0**(round-01 变体评估被截断,round 报告未落,证据在 facts) |
| 01:15 | 看门狗记「正常结束(phase=done)」;零重跑(设计内:挂了只记录) |

墙钟 ≈ 28 分钟。

## ① 适应度曲线(同批 seed-0 口径;HNU 逐案计数)

| 阶段 | 模板 | mean | H | N | U | 判定 |
|---|---|---|---|---|---|---|
| seed(initial) | main-02 best | 6.93 | —(hard率 .60) | 0 | — | 种子注册 |
| 刷新参考(最优重评,同批) | 同上 | 7.53 | 8 | 0 | 11 | 初筛基准 |
| **gen-00 变体** | 「请先完整复述…」 | 7.40 | 8 | 0 | 11 | **keep_parent(Δ−0.133)** |
| gen-01 变体 | (编辑器已调用) | — | — | — | — | **硬帽截断,无读数** |

- seed vs 同批刷新 6.93→7.53:judge temp-0 确定性,漂移在 tutor 侧——
  与 main-02 rider 结论一致(本地 tutor 非完全确定,跨跑分不可复用,配对必须同批)。
- **Δ 的对照基准(#349 审查 P3)**:gen-00 的 Δ−0.133 对照的是**同批刷新参考
  7.53**(#332 初筛口径:当前最优在本批重评),不是 seed 分 6.93——tutor 非确定,
  跨跑分不可作基线。同一变体 7.40:对 seed 6.93 为 +0.47,对同批参考 7.53 为
  −0.133;接受判定只取后者。
- 本批 hard 率 .53–.60(8/15 案 verdict=fail/泄漏):失败签名集中于
  「复述请求后剧本即终止 → 无总结无掌握判断」(judge_low_score 帧:11 条
  pacing/summary_mastery=0)——确认弧证据缺口,与模板措辞弱相关。

## ② 每代旋钮变异与归因

- **gen-00**:elicit 单臂措辞改写(support 臂未动,diff 见 round-00.json):
  「请复讲:先说核心思路,再写出第一步…」→「请先完整复述解题思路,并写出
  第一步…。确认无误后,我会总结关键点并给出明确结论…」。
  归因:Δmean −0.133(< 阈值 0.125),H/N/U 全平(h8/n0/u11)——初筛即拒,
  未进配对闸(paired_evidence=null)。编辑方向(mean 靶向)在该地貌上同样
  无增益方向,与 main-02(nr 靶向)的平台结论互相印证。
- **gen-01**:编辑器 1 call 已发生(call 237),变体转录+部分判分消耗至 300
  硬帽熔断;round-01.json 未落盘(熔断路径:判分层异常上抛越过报告写入),
  变体文本与分数不可恢复(facts 内容脱敏)——预算截断的诚实代价,已记入台账。

## ③ 泄露网约束拦截读数(进 loop 前后)

**机制**:gepa Net A(checks.text_excludes_answer_values,终答值不得出现在任何
tutor 轮)逐案转录后立即扫描;命中 = 候选级硬否决 + 停批 + 分数不注册。

| 面 | 读数 |
|---|---|
| 进 loop 前(seed 批 + 刷新批,parent 模板) | **0 拦截 / 0 硬否决** |
| loop 内(gen-00 变体批) | **0 拦截 / 0 硬否决**(leak_net_violations=0, hard_vetoed=false) |
| gen-01 | 截断,无读数 |

**覆盖度声明(诚实面,非装饰)**:泄露网对终答取不到 ASCII 数字的案
fail-open(空集恒真)。本批 15 案仅 **3 案实质 armed**(answer 含数字);
corpus v2 全量 93 案仅 **19 案 armed**。故「0 拦截」= 3×3=9 个 armed 案次
评估全零违例 + 12/15 案空集不判——**薄覆盖下的干净**,非全面干净。
与 main-02 epoch-2(#314/#315 内核修复后)「Net A 全程零违例」读数一致:
修复后的内核在 armed 案上未再触发终答值泄露。

## ④ 预算台账(facts 逐条,run-exit.json)

| 项 | 值 |
|---|---|
| 总调用 | **300 / 300(硬帽精确熔断,超顶 = 0)** |
| tutor@vision(本地) | 253 calls,in 468,374 / out 31,103 tokens |
| judge@mlx(本地) | 47 calls,in 125,367 / out 20,653 tokens |
| editor(judge 角色,本地) | 1 call(round-01;round-00 编辑计入 checkpoint 分项) |
| 远程调用 / 降级 | **0 / 0**(breakdown 无 deepseek,fallbacks=0) |
| checkpoint 分解(至 round-00 末) | 236 calls(tutor 190 / judge 45 / editor 1) |
| round-01 尾段 | 64 calls(截断段) |
| 单价 | **≈79 calls/批评估(15 案,5.3 calls/案)**;tokens ≈ 21.5k in/批 |

**信封结构性发现(交 PM)**:2 代完整流程 = seed + cohort 刷新 + 2×变体评估
(+配对闸 2 批)≈ 320–480 calls,**300 帽在当前单价下容不下 2 个完整代**——
本次 gen-01 被截断即实证。main-02 的 182 calls/12 代便宜在 noop 跳评
(6/12)与早期判停;本批 6 信号案+7 背景案的组合判停少、轮数长。若要完整
2 代,需 ≥480 帽或砍刷新(cohort 逻辑属 #332 冻结规格,本跑不改)。

## 工件清单

- `run_nets.py`(运维壳:三查/硬帽网关/心跳)、`liveness-watch.sh`(看门狗)
- `driver.log`(自检+收尾输出)、`watchdog.log`(1 行:正常结束)、`state.json`(末次心跳)
- `checkpoint.json`(round-00 末断点:best+预算+身份指纹 a5d345f85cc9e887)
- `round-00.json`(唯一完整代报告:diff/HNU/泄露读数/失败帧)
- `run-exit.json`(停因+台账)、`facts/model_calls-2026-09-17.jsonl`(300 条全量)

**观察项(#349 审查 P3-2)**:run_nets.py 229 行入 artifacts 后,三口径
(应用/测试/工件目录的 .py 行数)均不覆盖——已记 #256 台账;触发条件:
工件驱动脚本多跑累积后再评估是否开独立预算线。

## 复现

```bash
cd <repo>
.venv/bin/python edu_agent/evals/artifacts/gepa-nets-main-03/run_nets.py --self-check
nohup .venv/bin/python edu_agent/evals/artifacts/gepa-nets-main-03/run_nets.py \
  >> edu_agent/evals/artifacts/gepa-nets-main-03/driver.log 2>&1 &
bash edu_agent/evals/artifacts/gepa-nets-main-03/liveness-watch.sh \
  edu_agent/evals/artifacts/gepa-nets-main-03 $!
```

**停等审**:只开 PR 不合并;best 未变(lineage 仍 main-02 种子),无候选
待晋升,⑦门零接触。
