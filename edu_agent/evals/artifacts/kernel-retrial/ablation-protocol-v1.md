# Kernel 重新审判·三臂消融协议 v1(跑前冻结稿;sha256 见回执)

**依据**:架构师大裁定(#333 评论 5732081935,PM 核验入册)+PM 直发派单(2026-09-18)。
**性质**:零模型 calls 纯设计;跑前冻结——点火键=用户,冻结后跑判不改。
**第一原则**:prompt/model/dataset/judge 全冻结,只变 kernel 机制集(裁定第 4 条);
R2 prompt 迭代冻结延伸至消融收敛;靶①五选项已作废归档(target1/README.md)。
**生产不动**:线上继续跑 Arm C 等价物;消融全离线。

---

## 1. 三臂定义与基础设施

### 1.1 臂定义(裁定第 5 条)

| 臂 | 定义 | 教学机制(B类) | 安全(A类) |
|---|---|---|---|
| **A** | raw prompt shadow | **全旁路**(不改写模型输出;reveal/fallback 等不触发,模型文本直通学生面) | 检测只记 **would_block / would_rewrite / would_reveal** 事件,不动作 |
| **B** | thin safety kernel | **全关** | 保留:answer_leak block+**至多一次最小安全 regen**(只拒绝不重教:regen 指令仅要求去除终答,不注入教学话术)+数据 auth+gateway+状态+必要 deterministic stop |
| **C** | 当前 main | 现状(对照) | 现状 |

A 臂仅离线(raw 不达真实学生);B 臂「安全层只拒绝不重教」为硬约束。

### 1.2 B类机制清单对号入座(裁定 7 项+覆盖逻辑补 2 项;kernel.py 行号=main@57a18a04)

| # | 机制 | 落点(符号/行) | A 臂 | B 臂 |
|---|---|---|---|---|
| 1 | premature_confirm | `_gate_premature_confirm`(L828;处置 L845 走 `_regenerate`) | would_rewrite 记录,原文本直通 | 关 |
| 2 | deterministic reveal+telling | `_reveal_stuck_hint`(L370;三调用方:卡壳揭示/复读降级/输出面背板) | would_reveal 记录,模型文本直通 | 关 |
| 3 | `_soften_step_text` | ~L395(cut/mask 步文本动作化) | would_rewrite 记录 | 关 |
| 4 | repeat→regenerate | L942-944 `_is_repeat`→`_regenerate(_SELF_CRITIQUE)` 一次 | would_rewrite 记录 | 关 |
| 5 | repeat→fallback | L945-951 复读仍未破→`_reveal_stuck_hint` 阶梯推进 | would_reveal 记录 | 关 |
| 6 | bottom-out 文本 | L407(梯尽终答明示「这一步我们直接看结果:{answer}…」) | 随 #2 关 | 随 #2 关 |
| 7 | confirmation rewrite | 确认/赞许轮转述式改写(ready_to_confirm 不引终答值路径,L860 区) | would_rewrite 记录 | 关 |
| 8 | 复讲代喂修复 `_repair_feeds_method`(L958 区) | 「一切为教得更好覆盖模型输出的逻辑」入列 | would_rewrite 记录 | 关 |
| 9 | 确定性支持句族 `_SUPPORT_HINT`(L94)/`_STEP_LEADS`(L244)/`NEEDS_REVIEW_TEXT`(L430)/`_ELICIT_TEMPLATE`/elicit 确定性路径(L880) | 同上(教得更好类) | would_reveal 记录 | 关 |

**C类状态事实**(裁定第 3 条):session 状态机/步梯/first_question 保留——三臂
同构(字段存在≠复杂行为存在:状态字段照记,B 类不据此动作)。

### 1.3 实现形态建议(协议层设计,实现 PR 另过审)

- **门控载体**:`KernelSubject(arm: Literal["A","B","C"]="C")` 构造参数,runner
  (corpus_round 或独立 ablation runner)注入——**Run Spec YAML 非天然载体**:V0
  封闭键集(version/name/corpora/cases/judge/concurrency)管 corpus 选择不管
  kernel 行为,加键需 #350 评论提案流程;建议 runner CLI 参数(与 arm 同级的
  既有惯例),若后续要固化再走 #350 提 `kernel_arm` 键。
- **A 臂 shadow 埋点**:对齐 guard_events 既有键,additive——
  `{"shadow": "would_block"|"would_rewrite"|"would_reveal", "rule": <规则名>,
  "turn": <n>}`;**不改文本、不调 regen**(shadow 零额外模型 calls)。
- **B 臂最小安全 regen**:answer_leak 命中→block+一次 regen(critique 只含
  「去除终答数值,不得新增教学内容」);再命中→纯 block(安全句,非教学句);
  埋点 `{"arm_b": "safety_regen", "round": 1|2}`。
- **kernel.py 装配点**:guard 链入口(`_guard_output`)与 reveal 三调用方加
  arm 分支;**生产路径零改动**(默认 arm="C",生产不注入)。

### 1.4 A类保留清单(thin 面,裁定第 3/5 条)

终答泄露检测与 block(answer_leak 泄→block+至多一次最小 regen)/数据 auth/
gateway/状态+硬安全不变量/必要 deterministic stop(finish/needs_review 状态出口
保留——C类状态事实);**V1 泄露检测=A类保留,V1 deterministic reveal/hint 阶梯
=B类入审判名单**(裁定翻译:「刚部署也要受审」——诚实推论,如实入册)。

## 2. slice 选案(12 案,全离线)

| slice | 案 id | fixture | 现成/补 |
|---|---|---|---|
| fluent×2 | no-progress-control-reasonable-review | no_progress_controls_v1.json | 现成 |
| | no-progress-control-thin-reasoning | 同上 | 现成 |
| stuck×2 | image_v2_stuck_01 | enriched12 | 现成(V1 replay 已用) |
| | image_v2_stuck_02 | enriched12 | 现成 |
| no-progress×2 | no-progress-real-6a61aa32-replay(方位长对) | no_progress_real_v1.json | 现成 |
| | no-progress-real-paraphrase-probe(换写变体) | m1_probe_corpus 形态 | 现成(R1 已用) |
| leak-risk×2 | image_v2_answerhit_01 | enriched12 | 现成 |
| | image_v2_answerhit_02 | enriched12 | 现成 |
| anchor collision×1 | 千分位撞池案(answer「1,000」/value「1000」) | **补**:FINDINGS-4 千分位切断向量(tests/teaching/test_property_invariants.py L212)+P2-① 追认裁定 | **缺,列补** |
| image-production×2 | image_v2_understanding_04(circle_geometry) | enriched12 | 现成(V1 replay 已用) |
| | image_v2_understanding_02(visual_statistics_open) | enriched12 | 现成 |

补案仅 1(千分位):构造 answer「1,000」+steps value「1000」+两轮卡壳剧本,
冻结时附 case 全文;其余 11 案零新增 fixture。

## 3. M1-M7 操作化定义(裁定第 8 条;judge 冻结只作旁证)

| # | 定义 | 怎么算(确定性) | 工件字段(rows[]) | 谁读 |
|---|---|---|---|---|
| M1 turn grounding(方位案已实证严重失败) | 导师轮对上一轮学生表述的锚定度 | 每 tutor 轮(非首问)与前学生轮 SequenceMatcher ratio+学生实体词覆盖率,case 均值 | `metrics.turn_grounding` | 脚本,判读面 |
| M2 已答重问 | 同问点换措辞重问 | `possible_no_progress_cycle` 现成(advisory 行) | `advisories` | 脚本 |
| M3 证据过采集 | 充分后仍持续要证据 | 完成判定后非收束轮计数+同实体问句重复数 | `metrics.evidence_over_collect` | 脚本 |
| M4 answer-in-question | 题面答案数字污染教学证据(非终答泄露) | answer_pool 数字在 tutor 轮出现次数(排除 bottom-out 合法明示与收束轮;A 臂无 bottom-out=裸计) | `metrics.answer_in_question_rounds` | 脚本 |
| M5 充分证据到收束轮数 | 证据充分→finish 距离 | first_sufficient_evidence_turn(确定性代理:学生轮含关键步骤词+结论)到 final turn 差 | `metrics.turns_to_closure` | 脚本 |
| M6 kernel 介入密度(流畅案 75%=架构 smell) | 介入频率(量化器底子=机械感归因口径) | reveal/regen/leak_block/soften/pc 各计数+轮比;**A 臂同口径数 would_***(shadow 计数)** | `metrics.interventions`+`intervention_rate` | 脚本 |
| M7 人审只看真差异对 | 盲评限真差异 | 逐轮文本 A vs C 不等即真差异,预筛出对 | `arm_diff_vs_C.rounds_differ`+`pairs_for_review` | 用户/nr |

**判读主面=M1-M6 三臂对照表(每指标×每案);M7 只看预筛真差异对;judge 12×3
全跑作旁证(不进判读线)。**

## 4. 预算估算(3 臂×12 案,本地零远程)

| 项 | 估算 |
|---|---|
| tutor calls | A≈75(模型直出,无 regen)/B≈85(leak-risk 案+安全 regen 1-2)/C≈90(现状 regen/fallback) |
| judge calls(旁证) | 3×12=36 |
| **总 calls** | **≈290 本地**(带 250+judge 36) |
| **硬顶** | **360**(+25% 余量;超顶即停呈 PM) |
| 时长 | Mac qwen3_vl_8b 并发 4:~17min/臂×3+judge≈**1-1.5h** |
| 分批 | 不分批(三臂同批跑——四情况判读需 B 臂区分「删机制」vs「重设计 recovery」,B 为判读必要臂) |

## 5. 判读预注册(裁定第 6 条四情况,引用原文+操作化)

| 情况 | 判读 | 操作化信号 |
|---|---|---|
| A 好 B 好 C 差 | 教学 kernel 过度→**删** | M1/M3/M5 A≥B≫C;M6 C 介入率显著高 |
| A 好 B 差 C 更差 | 硬安全 recovery 有副作用→**重设计** | M6 B 臂 safety_regen 高频+C 更差面 |
| A 自身循环 | prompt/model 问题,**kernel 不背锅** | M2/M6(A 的 would_* 低但 A 文本自循环) |
| A stuck 差 C 好 | 某机制有真消费者→**二阶段逐机制归因** | stuck slice M5/M1 C≫A |

**冻结纪律**:判读线跑后不改;单项异常不得推翻四情况框架,如实报 PM 裁。

## 6. 纪律与红线

- 冻结面:prompt/prompting.py·model·dataset(除千分位补案,冻结时全文附)·
  judge 配置——**全不动**
- 生产路径零改动(kernel 装配默认 arm="C",生产不注入);消融全离线
- 停止条件:需动 A类安全语义/状态机字段语义/DB → 停 PR 报 PM(章程)
- 工件:out/ablation/{A,B,C}/<case>.json+汇总 ablation-summary.json
  (M1-M6 三臂对照表)+真差异对清单(M7 材料);回执 #333 首行
  task=kernel-ablation-run

## 7. 点火前置清单(用户点火键前须齐)

①本协议 PM 过审→用户点火;②千分位补案全文冻结附本协议附录;③Mac 环境
确认(models.yaml 消融 worktree 独立,不触生产);④shadow 埋点字段命名
冻结(additive,不改既有键);⑤M1-M6 量化脚本就绪(跑前自测空转一遍,零模型)。

---

## 附录 A:千分位补案全文冻结(前置件②;正本=ablation-cases-comma.json)

```json
{
 "id": "ablation-comma-collision-01",
 "title": "千分位撞池案(answer「1,000」归一池 {1000},step value「1000」双重身份→anchor 禁)",
 "bucket": "fraction_formula", "visual_dependency": "none", "grade": "六年级",
 "question": {"text": "一个数的一半是 500,这个数是多少?", "answer": "1,000",
              "analysis": "先算用一半倒推:500×2=1000。再写出带千分位的数:1,000。"},
 "reference_answer": {"value": "500×2=1000,即 1,000", "steps": ["倒推:500×2=1000", "千分位写法:1,000"]},
 "student_turns": [
  "一半是 500……是要用 500 加什么吗?我想不出来。",
  "还是不会,倒推到底怎么算,我又卡住了。",
  "哦!一半倒过来就是乘 2,500×2=1000,这个数是 1,000!"
 ],
 "misconception_seed": null,
 "expected": "anchor_collision_refused",
 "source": {"question_id": "ablation-comma-collision-01", "provider": "kernel_retrial_ablation",
            "lesson_name": "千分位",
            "note": "#333 kernel-ablation slice:anchor collision——step value 1000 撞 answer『1,000』千分位归一池(#360 P2-① 收紧向量),C 臂二次卡壳 anchor 应正确拒绝(零锚);A/B 臂无 anchor 机制对照。冻结附录=本文件全文。"}
}
```

## 附录 B:shadow/arm_b 埋点字段命名冻结(前置件④;additive,不改既有键)

- A 臂 shadow:`{"shadow": "would_block"|"would_rewrite"|"would_reveal", "rule": <机制名>,
  "turn": <n>}`——`shadow`/`rule` 为新键;`turn` 由既有 `_stamp_turn` 补打(setdefault,
  与 #146 M2 同机制),不新增写入路径。
- B 臂安全埋点:`{"arm_b": "safety_regen", "round": 1|2, "rule_ids": [...]}`——`arm_b`
  为新键;round 1=最小安全 regen 已发起,round 2=再命中→纯 block。
- 机制名 rule 值域(冻结):`elicit_restatement` / `stuck_hint` / `answer_hit_restatement` /
  `answer_collect` / `premature_confirm` / `repeat_regen` / `output_repeat_fallback` /
  `feeds_method` / `<guard 名>`(guard 级 shadow 用既有 guard 名,如 answer_leak/format)。

## 附录 C:执行侧合规注记(B 执行,2026-09-18;交接核对后修两处)

1. **B 臂最小安全漏斗补齐(协议 §1.1/§1.3)**:A 的在飞件让 B+answer_leak 走 C 全漏斗
  (教学化 critique+情境化兜底句)——违反「只拒绝不重教」硬约束。已修:`_arm_b_leak_funnel`
  (block+至多一次最小 regen,critique 仅「去除终答数值,不注入教学」;再命中→纯安全句;
  arm_b 埋点 round 1|2)。
2. **#8 代喂 A 臂 shadow 补齐(协议 §1.2 #8)**:A 的在飞件在 A/B 臂静默跳过代喂检测
  (M6 会低估 A 介入率)。已修:A 臂记 `would_rewrite(feeds_method)` 后旁路。
3. **#7 确认话姿 A 臂 shadow 读法(记档不改码)**:#7(确认/赞许轮转述式改写)仅在
  guard 命中的兜底路径触发(_contextual_fallback L452 区),A 臂 guard 级 shadow
  (would_block/would_rewrite)已覆盖其触发轮——M6 计数不缺,不重复记(避免同轮双计)。
4. **C 臂基线口径**:C=协议冻结基线 main@57a18a04(分支基),**不并**冻结后 main 的
  kernel 变更(#358 leak-net 等)——消融单变量;行号表(§1.2)与此基一致。
5. first_question 模板/状态机/步梯=协议 §1.2 C类保留,三臂同构(核对无误,未改)。
