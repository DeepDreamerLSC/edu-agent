# Trusted Product Corpus v1(M4 overnight Lane A)

第一版可信内部产品面 corpus:引用式 manifest(不复制载荷),逐案记录 admission gate 判定、frozen input sha256、expectation+authority、set 归属与 coverage。

- **执行身份(冻结)**:`6f3e70785545b51932b32b41f7b6a3d226934a66`(= #509 合入点;worktree detached 复核)。
- **身份不变量**:零 runtime 改动(本目录仅 manifest.json + README.md 两件数据资产);不改 Authority/Policy/Product Contract/completion semantics;不新增 Judge/Evaluator/Framework;真实学生数据零入仓(全部来源=仓内数据集/合同件+/tmp 只读档案的合成与评测案)。
- **产物**:`manifest.json`(schema `trusted_product_corpus_v1/manifest/v1`);本件为读法与判定记录。

## 1. 集合与计数(全部可由 manifest 复算)

| set | 数 | 定义 |
|---|---|---|
| **Core** | **72** | Admission Gate G1–G8 全过(门列表见 manifest `admission_gates_core`) |
| Challenge | 84 | 历史 failure/边界/反事实/已修事故 80 + Bank Arc negative variants 4(§8e,合成安全探测,不并入 Core 统计) |
| Exploration | 136 | 信息不足/期望消费面已废/人审未定 |
| (reserve) | 4 | `math_gold_b2_heldout`:teacher_confirmed 但 holdout 角色,**不入任何 set** |

Core 72 介于目标 50–80,**未凑数**:bank 池 142 题 answer_spec 中仅 109 题通过文本面闭合检查,按确定性配额实际入 15(choice 仅 4 题、equation 0 题可用,见 §4);余量由 teacher-confirmed 语料补足,不虚填。

## 2. Core 构成(选样规则全部确定性,manifest `selection_rules` 可复算)

| 来源 | 数 | input 面 | expectation + authority |
|---|---|---|---|
| partner_bank(answer_spec 池) | 15 | text-only | answer_spec 显式声明面(147562e8 编译,#422 A 段透传);G7 冒烟实证 |
| image_teaching_v1(WP4 approved 全集) | 8 | **text+image**(图 sha256 逐案对账 8/8 一致) | reference_answer + expected_outcome;WP3/WP4 人审(issue #130,「图是源」仲裁定稿) |
| math_gold_b2(teacher_confirmed 全集) | 13 | text(branching 剧本) | teaching_arc_gold;receipt `issue-178#c5657431632` |
| math_gold_candidates(positive 子集,id 字典序前 12) | 12 | text(branching 剧本) | teaching_arc_gold;receipt `issue-178#c5653410144` |
| teaching_context_shadow_pilot_20(全集) | 20 | text(线性剧本) | **completion**:expect.final_states=completed+finish_status 检查,逐案 teacher_confirmed(review.csv 20/20) |
| signal_enrichment_v2(stuck 子集 4/4) | 4 | text | stuck 触发轮;kernel `_student_signals_stuck`(#198 八形态)——冻结身份正则级复验 4/4 PASS(零模型) |

- bank 选样:型内 `question_id` 字典序;配额 choice 5/equation 2/numeric 7/short_text 4——实际 choice 仅 4 题、equation 0 题可用(剔除规则见 §4),**不降门补位**。
- equation_form 面:Core 由 pilot 20 案的题内 answer(x=6/x=4 方程形)覆盖;bank 侧 2 题 1 题图引用剔除、1 题与 pilot 同题面去重。

## 3. Challenge / Exploration 构成

**Challenge 80**:
- `chal-m3-*` 18:M3-01 生存检查全量(13 SURVIVES / 4 FIXED / 1 BLOCKED),冻结输入=驱动器 CASES(/tmp/survival-out/driver sha256 钉身份);reval-final(d55ce9ef)七案判定并入 basis。
- `chal-gate32-*` 32:预注册 completion-gate 回归(#414 §六.1 终裁 regression corpus):负向=边界、form1/form2=反事实;Core 出口被 G4(replay_input 无 answer_spec 声明面;probe spec 仅 ADVISORY;1 案 composite 出六窄面)+pending_review 未清挡下。
- `chal-goldc-nb-*` 30:teacher_confirmed 边界教学弧(negative_or_boundary)。

**Exploration 136**:pilot-30(gold pending)、image_teaching_v2_enriched12(无人审回执)、adaptive_shadow_pilot_20(expectation 未声明)、S2 battery 23(判定线构造材料,标题级枚举;自述 24——C15-T3 仅以派生注记存在)、signal understanding/completion 8(matcher 已被 06e4ecee 删)、one_call_fast_path 6、qimg_reliability 5、target_mode_v3 图 4+回归 5、dialogue_stability_20(legacy v1,loader 不收)、dialogue_scenarios 3(legacy)。逐案 reason 见 manifest。

## 4. Admission rejection 清单(逐案 158 条,manifest `rejections`;按门分组)

| 门 | 数 | 要点 |
|---|---|---|
| G3(expectation authority) | 121 | partner_bank 无 answer_spec 题(121/263)——answer 文本未经 spec 编译,不作 Core expectation |
| G2(stem/source 闭合) | 33 | 图引用 stem(题面不自含)而 `question_image=null`——text-only 冻结面不闭合(如 6a62bdb9「以下图形…」、6a695b4f「图中斜线」) |
| G6(输入唯一性) | 1 | stem 逐字重复(6a61b319 ≡ 6a61afaa「一瓶水重2kg」;另一重复组两员均已被 G2 拒) |
| G8(选样规则) | 3 | 6a61b67e/6a61bd8d 已被 Challenge 事故案占用;equation_subtract 与 Core pilot 同题面去重 |

## 5. 6a61bd8d(live-distributive)机械判定:**Challenge**

| 门 | 判定 | 依据 |
|---|---|---|
| G1/G3/G4/G5/G6 | 过 | source identity 明确;answer_spec short_text_exact 在场且 #509 零改动;DATA-CONFOUNDED(vl-误读归因)经 #509 stem 闭合已 resolve |
| G2 | 过(带注) | stem 已对原图逐字闭合(#509:④6.7+组合行);**残余**:static/bank.json 演示面同案 50 字截断+④8.7 未修(#509 明示不在范围) |
| G7 | **不过** | ~~start() 含图截断~~(**勘误 2026-10-03:此半条不成立**——闭合 stem 在 main@6f3e7078 原产线 800 上限下实测 `finish_reason=stop`、output=749 tok,/tmp/reval-800-postmerge/facts 直接证据;族B 终局=historical REQUEST-LIMIT boundary / DATA-CONFOUNDED / no current change right,#496 评论 5954221906;#510 修复已按 YAGNI 关闭);G7 仍不过的真实理由:**档案学生脚本末轮「④8.7」与闭合后 stem(④=6.7)不符=脚本 stale,逐字重放不再忠实**(需按闭合后题面重铸脚本才可复验) |
| 结论 | Challenge | stem/answer/图三件套本身已可信;归 Challenge 的理由=历史事故案(BLOCKED/数据混淆正本)+档案脚本漂移,而非当前 main 截断(已证不存在)。重铸脚本并复验后可复议 Core |

## 6. Coverage matrix(Core;Challenge 全矩阵见 manifest)

| 维 | Core 读数(诚实口径) |
|---|---|
| modality | text 64 / image 8 |
| expectation 面 | numeric_with_unit 7(bank)+20(pilot 题内,含方程形);short_text_exact 4;choice_letter 4;math_gold_arc 25;reference_answer(numeric) 4;numeric_or_short_text 8(imgv1) |
| learner 面 | incorrect(声明) 27;incorrect→correct(剧本弧) 45;**unanswered 声明面 Core=0**(档案 unanswered learner 仅存于 live 两案→Challenge) |
| behavior 面 | math 72;support 53;completion 20+completion_arc 12;leakage 15(bank answer_spec 在场=守卫武装,确定性「start 不得含 ground_truth」断言可判);stuck 4;reveal_ladder 8;misconception_repair 13 |
| source 分布 | partner_bank 15 / pujia 题图 8 / gold_b2 13 / gold_candidates 12 / shadow_pilot 20 / signal_v2 4 |

**已知覆盖缺口(不凑)**:①true_false 在全部候选源中为 **0**(bank 142 题 spec 分布:numeric 87/short_text 48/choice 5/equation 2,无 true_false);②ratio_or_expression 仅 Challenge 面(gate32 probe 3 案+6a61b67e);③equation_form 无 bank Core 直选(2 题均被 G2/G8 剔);④unanswered 见上。

## 7. 冒烟核验(Core 抽 3 案,冻结身份真跑;证据 /tmp/edu-corpus-smoke/)

| 案 | start() | finish() | 形态记录 |
|---|---|---|---|
| core-bank-6a61afaa | `first_question_ready`,2.4s,guard 0/steps 3 | `needs_review`(确定性模板,32 字,0.0s) | answer_spec 透传在场;R6 首问「这道题你的答案是什么呀?讲讲你的思路吧!」 |
| core-pilot-stability_equation_subtract | `first_question_ready`,2.4s,guard 0 | —(未跑,预算) | 同款 R6 首问(text-only 变体) |
| core-imgv1-image_v1_fraction_formula_06 | `first_question_ready`,2.3s,**image=True**,guard 0 | —(未跑) | 首问含「我看到你发的题啦」图变体(题图 data URL 附着) |

tutor=qwen3_vl_8b@http://127.0.0.1:8303(default_gateway 产线默认参数,配置未动);start×3+finish×1,未跑更多。结论:**current main(6f3e7078)对 Core 三面(text/text 剧本/text+image)均可 replay**,输出形态与 reval-final 记录的确定性路径(首问分派/needs_review 模板)一致。

## 8. 发现记录(Failure Boundary → Root Operational Cause → Change Right)

| # | 发现 | Failure Boundary | Root Operational Cause | Change Right |
|---|---|---|---|---|
| F1 | [M] live-distributive 含图截断:**已解阻**(勘误 2026-10-03)——闭合 stem @ current main(6f3e7078)@ 原 800 上限实测 `stop@749`,族B 终局=historical REQUEST-LIMIT boundary / DATA-CONFOUNDED / **no current change right**(#496 评论 5954221906;#510 按 YAGNI 关闭) | 历史 product start() 图题面(旧 stem 时期) | 旧 stem 数据面驱动生成越过 800(#509 已修) | **本面 none**;当前 Challenge 身份=历史事故价值+learner 脚本 stale(末轮「④8.7」与闭合题面漂移),与 current-main 截断无关;重铸脚本复验后可复议 Core |
| F2 | [M] signal_enrichment_v2 understanding/completion 8 案期望面已废 | eval 数据集 vs kernel 机制 | #333 终裁 06e4ecee Thin Kernel 删七机制:两个 matcher 删除、验证测试同步删除,数据集未标废 | 数据集侧标废或重建消费面(人裁;本 corpus 仅降层) |
| F3 | [P] bank.json 演示面 150 处与合同面不一致:149 纯截断+1 值错(6a61bd8d ④8.7) | api 静态演示层 | 序列化生成截断/误录(#509 已明示独立缺陷未动) | 演示面再生成或删除(数据管道面,人裁) |
| F4 | [P] partner_bank 263 题 `question_image` 全 null,而 static/bank 存 257 图 | **snapshot 闭合面(非生产管道缺陷)**——question_source.py 现行合同明示「题图由客户端上传,不在快照内」 | 快照按合同设计不携带题图载荷;263/263 null 证明的是 partner-bank snapshot **不能独立承担离线 image replay** | **none currently**;仅当产品合同要求 bank snapshot 自身可独立恢复 image path,或实际客户端上传链发生缺图,才获得生产修复权。对本 corpus=snapshot/corpus closure limitation(核验前 bank 案仅 text-only 格) |
| F5 | [P] true_false 期望面全池 0 | corpus 覆盖 | 候选源(142 spec 题)分布即无此型 | 不造数;未来 partner 供给或人裁扩面 |
| F6 | [A] 档案 learner 默认无 unanswered/correct 声明源,Core learner 面靠剧本弧覆盖 | corpus 输入参数面 | kernel_subject 默认 incorrect;历史批次从未声明其他值 | 如产品面需要,人裁后以受控声明扩格(本版不扩) |

## 8a. v1.1:runtime_projection.answer_spec + Completion-Capable Core(WP3,Architect 2026-10-03 Morning 裁定)

schema 升 `trusted_product_corpus_v1/manifest/v1.1`(仅增字段,零删改;frozen_input_sha256 与 sets 不动)。**corpus-side 显式 answer_spec 投影**——把可信历史语料投影到当前 Product Contract(question.answer_spec 显式声明面);**禁止迁移/放宽 Kernel Gate 语义**,Gate 的 fail-closed 设计不动。

**六条件(逐字执行,全部确定性、零 LLM、零语义猜测)**:①source 存在明确 authoritative answer;②answer 类型用仓内已批准 deterministic compiler 规则判定(直接复用 `scripts/compile_answer_spec.py` 的 `compile_spec`——classify 互斥分类/composite 不编/choice letter_choices 从 stem 确定性识别/组装面/自回喂验收门;先例=partner_bank 142 题 spec @147562e8;代码面 6f3e7078 同规则文件);③不用 LLM;④不做语义猜测;⑤self-feed verifier 必须命中——投影 spec 喂 `completion.verify_completion`,对该案剧本学生终答轮(线性剧本=末轮)必须判 verified,不命中/无剧本→留空;⑥provenance 写明来源与规则版本。逐案六条件执行记录在 manifest `runtime_projection.conditions`。

**投影统计(Core 72:2 投影 / 70 留空)**:

| 留空原因 | 数 | 案群 |
|---|---|---|
| c1 无产品级 answer authority | 29 | math_gold_b2 13 + gold_candidates 12(仅 trajectory gold,裁定明示不得投影)+ signal_v2 stuck 4(reference_answer 为解题过程自由文本,非 canonical answer 声明) |
| c5 无学生剧本 | 15 | partner_bank 全部(start→finish 最小弧,无学生轮;c5 不可评估按「不命中→留空」fail-closed;15/15 重编译与仓内存储 spec 逐字一致=幂等对账通过,c1/c2 本身成立) |
| c2 compiler 留空 | 10 | composite 8(imgv1 多空 5 + pilot 鸡兔/按比例/余数 3)+ choice 选项列表不可靠 1(imgv1 open_27)+ 自回喂不命中 1(pilot probability「红球可能性更大」——「可能性」含不确定 marker「可能」,规则 fail-closed) |
| c5 终答轮 self-feed 不命中 | 16 | pilot 14(含 equation 形 3 案:剧本终答用「x等于6」中文系词,symbol_key 不识别=规则口径;「也是/等于」收尾非 claim 模板白名单形态) + imgv1 2(open_14 多候选字母存活、formula_06 终答「所以需要涂9个」非 claim 模板位) |

投影 2 案:`core-pilot-stability_rectangle_perimeter`(26厘米/numeric_with_unit,终答轮「结果是26厘米」命中)与 `core-pilot-stability_order_operations`(6/numeric_with_unit,终答轮「结果是6」命中);authority 均为 question.answer + teacher_confirmed(patha-pilot-20,issue-178#c5657431632)。

**Completion-Capable Core 新 denominator = 2**(manifest `completion_capable_core` 可复算;三条件:投影在场 ∧ 剧本终答轮可验证 claim ∧ expectation 明确要求 completion——后者唯一 Core 族=shadow_pilot_20 的 completion_final_state)。旧 completion 0/71(lane-b)保留为 historical schema-mismatch baseline,不动,两者不可直接相减。bank 15 案虽 c1/c2 成立且 answer_spec 在产线透传,但无剧本终答 claim,不进 denominator(与 lane-b 实测 bank 案 start→finish=needs_review 一致)。

**Completion Baseline v1**(新 denominator 2 案 ×1 遍,8303 真跑;驱动口径与 Lane B 一致=EvalRunner+KernelSubject+checkpoint+facts;测量件不是修复件,结果如实;五指标与 identity 四件套见 §8b 与 PR body)。corpus-side 投影的消费方式:replay 驱动把投影 answer_spec 附着到 question 载荷,经 `KernelSubject._question_payload` 既有透传契约(「answer_spec 声明面透传,有才传,零行为变化」)进内核——**零 runtime 代码改动**。

## 8b. Completion Baseline v1 结果(证据 /tmp/wp3/baseline/;run=cases-20261003T002207Z-4cc4)

新 denominator 2 案 ×1 遍,8303 真跑(qwen3_vl_8b,内核 `_invoke` temperature=0 产线默认;驱动=EvalRunner+KernelSubject+checkpoint+facts,与 Lane B 同纪律;corpus-side 投影经 question 载荷附着+透传契约,零 runtime 改动)。**测量件不是修复件,结果如实:**

| 指标 | 案数 | 说明 |
|---|---|---|
| evidence produced | **2/2** | 均在剧本终答轮(turn 4)出证——与投影 c5 self-feed 预检一致 |
| ready_to_confirm reached | **2/2** | order_ops 经 finish() 路径收 completed;rectangle 经 ready+evidence 同轮 close-on-final-statement 路径(turn 4 直接 completed) |
| completed | **2/2** | historical 0/71 → 新 denominator 口径 2/2;**口径不同不可直接相减**(旧 71 含无 answer_spec 声明面/无剧本终答的案) |
| needs_review | **0/2** | — |
| completion_gate_rejected | **0/2** | Gate 语义零改动下零拒 |

零 fallback 核验:11/11 model_call 全部 role=tutor、attempt=1、ok、request=qwen3_vl_8b→response=Qwen3-VL-8B-GGUF、fallback_from/to 均 null、finish_reason=stop;invalid 清单=空(零静默剔除)。identity 四件套:code `6f3e7078`(detached worktree)/corpus 分支 `data/completion-capable-projection@3c149a22`/manifest sha256 `936bce9e…`/8303 实读 `/v1/models`=llamacpp Qwen3-VL-8B-GGUF(详见 /tmp/wp3/baseline/analysis.json)。调用量纪律:denominator ×1 遍,零重试零补跑(全部 attempt=1 ok)。

## 8c. v1.2:投影刷新 on #515 surface(Completion-Capable 2→5)

schema 升 `trusted_product_corpus_v1/manifest/v1.2`(仅刷新受 #515 影响的面)。**触发**:#515 equation-form deterministic math-copula normalization 已合 main(d4fbdf60)——verifier `_verify_equation_form` 分派路径把数学系词「等于」保位规范化为 =,「x等于6」≡「x=6」进同一等价类(认证仍由既有符号等价 oracle 独立确认,守卫恒在原文坐标,不新增暴露面)。

**重跑口径**:六条件与 §8a 逐字不变(零 LLM/零语义猜测/不造编译器);代码面 6f3e7078 → d4fbdf60——`scripts/compile_answer_spec.py` 两 commit 逐字节相同(sha `b2a1ad71…`),受影响面仅 c5 verifier(sha `cb302f92…`→`4949fddb…`,双锚存 manifest `wp3_projection.rule_version`)。全部 Core 72 案六条件重算并与 v1.1 逐案对账:**其余 69 案结果逐字节一致、manifest 记录零改动**(含 v1.1 已投影 2 案,c6 锚保留 6f3e7078 原值);客观变化仅 §8a c5 留空表中 equation 形 3 案,全部 EMPTY→PROJ:

| 新增投影案 | spec | 终答轮命中证据(turn 4) |
|---|---|---|
| core-pilot-stability_equation_subtract | equation_form / x=6 | matched_span=`x等于6`(「…再同时除以3,得到x等于6,代回去等式成立。」),verifier=equation_form,normalization=[符号归一] |
| core-pilot-stability_equation_sign | equation_form / x=6 | matched_span=`x等于6`(「…x等于6,代入2乘6加5等于17。」),verifier=equation_form,normalization=[符号归一] |
| core-pilot-stability_equation_parentheses | equation_form / x=4 | matched_span=`x等于4`(「…最后两边同时除以4,x等于4,代回原式得到24。」),verifier=equation_form,normalization=[符号归一] |

**投影统计变化(Core 72:2 投影/70 留空 → 5 投影/67 留空)**:留空原因仅 c5_self_feed_miss_on_final_turn 16→13;c1 29/c2 10/c5 无剧本 15 不变。v1.1 统计存档于 manifest `wp3_projection.v1_2_refresh.stats_v1_1`。

**Completion-Capable Core denominator 2 → 5**(manifest `completion_capable_core` 可由逐案 runtime_projection 复算;三条件不变,新增 3 案均 shadow_pilot 族 expectation=completion_final_state;v1.1 旧 2 案条目逐字节不动)。**不重跑基线**:§8b Baseline v1(2/2)已存档于 v1.1,新分母 5 案的面值留给 v1.2 基线或下次任务。自查:JSON 可解析;frozen_input_sha256 全 446 指纹(sets+rejections)零漂移——重跑仅刷新 3 案 runtime_projection,零输入变化。

## 8d. v1.3:Bank Arc Contract v0——5 案学生弧剧本(#554 c6032153905,5-case spike)

schema 升 `trusted_product_corpus_v1/manifest/v1.3`。**定性**(Architect 收紧版):目标≠提升分数,=**恢复真实教学交互合同,让 evaluator 能观察系统完整教学能力**——v1.2 bank 族 15 案 soc_avg 0.13 的暴露面是「评测样本没有提供足够信息」(弧=首问+收尾两条固定句,无学生轮),非教学缺陷。本节为 5 案补学生弧(Bank Arc Contract v0 四要件:Student State / Interaction Opportunity / Tutor Decision Point / Exit Evidence),逐案结构化记录于 manifest 新字段 `student_script`(sub-keys:student_state / student_turns / interaction_opportunities / tutor_decision_points / exit_evidence / c5_self_feed_precheck)。

**identity 纪律**:5 案与 v1.2 基线同 case_id 并存,`arc_version: "v0"` 字段在场=新旧机械区分标记;`frozen_input_sha256` 零改动(学生弧=驱动面增量,不在 frozen input 冻结面内——题面/answer_spec/learner 不变);counts/runtime_projection/wp3_projection/completion_capable_core 等既有面零改动(六条件投影刷新是独立操作,arc 面的投影刷新留给 arc 合入后的下一轮)。选 5 案自 14 个 bank fail(6a62ca09=review 不在池):题型面 choice 1/short_text 1/numeric 3;教学场景面=概念辨析/说理题/应用纠错/错例倒推/多步过程量;全部六年级分数域(fail 池 14 案 11 案分数域,同构)。「原 transcript 最短」不区分——14 fail 案 v1.2 弧全部=2 轮固定句。

**确定性 precheck(零 LLM,入 manifest `student_script.c5_self_feed_precheck`)**:末轮(学生终答轮)经 `completion.verify_completion` 六窄面判定 5/5 命中(D / 无法确定 / 1.16 米[单位同义换算] / 3/100 / 0.5 米[单位同义换算]);早轮零认证命中、零 stuck 信号触发、文本面早轮零终答原文。

**live 重放 5/5(证据 /tmp/m81/arc/;branch i554/m8-1-bank-arc-v0)**:run_inspect_round + KernelSubject(现役执行 owner=Inspect),@8303 qwen3_vl_8b 产线默认 temp-0;26 tutor 调(预算闸 30,案均 5.2,零 fallback 污染,3 调 Gateway 内 schema 重试 attempt=2)+ 5 judge 调 = 31 调。结果:**5/5 final_state=completed**(v1.2 基线同 5 案全 needs_review 2 轮),末轮 verified_complete=True 5/5(与 precheck 一致),ready_to_confirm 于 turn 3-4 到达,3 案经 close-on-final-statement 收束。

**判卷对照(v3.3-contextual,显式 SMALL_LECTURER_RUBRIC env,生产 judge 面 @8301 mlx_27B temp-0)**:5 案新弧 pass 5/5,socratic_followup/summary_mastery/termination 全 2/2(v1.2 基线同 5 案全 fail,soc/sum/term 全 0);判语方向从「对话中无学生回答,未体现苏格拉底式引导」翻为逐轮引用真实追问/学生原话/掌握后自然收尾,leak 判定正确处理学生先述终答后 tutor 确认的形态(非泄)。**口径披露**:v1.2 基线判卷=mctx3 三字段装配(step4);本轮=生产 judge.py env 选用面(无 mctx3 管道)——两轮判卷面存在该装配差,解读分数时须知。结论(5 案 spike,如实):**socratic/summary/termination 三维从不可观察翻为可观察且判语有据**→归因「corpus owner(弧设计缺陷)」在 5 案上成立;建议扩展至其余 9 fail 案后重基线再定 ②/③ 方向(排序照 #554)。

## 8e. v1.4:Bank Arc Contract Phase 2——余 9 Core arcs + 4 negative Challenge variants(#554 Gate c6033889476)

schema 升 `trusted_product_corpus_v1/manifest/v1.4`(仅增字段/增条目;counts.challenge 80→84;Core 72 分母不变——9 案 bank arc 是替换旧最小弧不是新增)。两段分拆(Gate 拆分:Core arc completion + Challenge negative coverage,不为分布污染 Core)。

**script-first freeze(Gate 新增硬门,先冻后跑)**:13 案剧本(A 9 + B 4)先写完并冻结——逐案 sha256(canonical JSON)+ 正本文件 sha + UTC 时间戳存 `/tmp/m81/phase2/freeze.json`,**frozen_at_utc=2026-10-07T08:42:36Z**;重放 driver 每次启动先断言冻结 sha 一致。首调时间戳=首 run `manifest.json.started_at` **2026-10-07T08:43:09Z** > 冻结时间(顺序可证);判卷在重放之后,看分后零改本(manifest `student_turns` 与冻结正本逐字节一致,edit 脚本断言)。

**A 面(余 9 bank fail 补学生弧,四要件+Gate 预登记 learner_trajectory 起点/是否自纠/是否可验证终答/卡点或退出形态)**:确定性 precheck(零 LLM)——7 案末轮认证命中(A.10[剥空白标点]/0.4kg/300 步/13/D/D/A),2 案(acc7 分量抵消、b65d 不等式合并)**预登记为未完成轨迹**(末轮不落终答,命中=否);早轮零认证命中、零 stuck、9 案 frozen_input_sha256 复算与 v1.2 一致。live 重放(@8303 产线默认 temp-0,run_inspect_round+KernelSubject):**8 案 ok——6 案 completed(全部与 precheck 命中一致)+2 案 needs_review(恰为预登记未完成的 2 案,系统未强行 completed)**;1 案(6a699c32)content 失败:GatewayError schema_violation(模型 JSON 输出非法),**两跑同点位复现=确定性,非 transient**——产品面鲁棒性边界如实记录,该案未判卷。判卷(v3.3-contextual 显式 env,@8301 产线 judge,口径同 §8d 披露):8 案 soc 全 2(v1.2 全 0);6 completing 案中 5 pass(sum/term 全 2 或近 2)、1 review(afaa:completed 但 judge 判「未确认掌握即终止」,sum=1/term=1——完成态与判卷面分歧如实保留);2 未完成案 review(sum/term=0 符合未完成轨迹)。**结论:bank 族 soc/sum/term 从「结构不可测」恢复为可解释分布的归因,9 案中 8 案成立(1 案产品边界待修)**。

**B 面(4 negative Challenge variants,distinct case_id/variant_id,不覆盖 Core identity,不并入 Core 均分/pass rate)**:覆盖 Gate 三形态+可选第四——neg1 persistent misconception(降幅和 16% 相等陷阱,反例 0.24 元被合理化为误差)、neg2 partial progress·no final evidence(分段计税走到 100000 但不落答)、neg3 disengage(负温度畏难放弃,末轮 stuck「太难了」按设计触发)、neg4 repeated new errors·engaged(促销规则反复误读仍互动)。负向 precheck(零 LLM):任意轮零认证命中+ground_truth 原文零出现。live 重放:**4/4 final_state=needs_review——系统对负向弧全部正确不完成,零强行 completed、零答案泄露换闭环(leak=False 4/4)**;neg3 stuck 信号触发后安全停住。判卷 L1 仅参考(4 案 fail:sum/term=0 与负向终态一致;neg2 判语「学生已给出正确答案仍要求重来」与 final_state 面分歧——确定性 verifier 因学生问句/犹疑形态正确拒绝认证,保守不完成是对的,L1 叙事面供 Product 参考)。

**调用账(逐段,fail-closed 闸)**:product 68 调=首 run 60(12 案 ok+6a699c32 第 3 调 schema 失败)+resume 5(6a631898-neg)+单案补跑 3(6a699c32 复现同点位失败);judge 12 调(6a699c32 无 transcript 不判);**合计 80 调**——超本任务 ≤75 线 5 调,构成:13 案×5 调+判卷 12 的算术下界即 77,加 6a699c32 确定性失败消耗 3 调(两跑共 6 调中 1 跑计入首 run)。如实列账,不藏失败。

## 8f. v1.5:弧闭合——bank arc 投影刷新(projected 5→17;弧闭合线 exit #554)

schema 升 `trusted_product_corpus_v1/manifest/v1.5`。**触发**:#555/#556(§8d/§8e Bank Arc Contract v1.3/v1.4)已合 main——14 bank Core 案补齐 `student_script`,c5(剧本终答轮自回喂)由「无剧本不可评估→留空」变为可评估;§8d 与 #556 PR body 均明文「投影刷新独立操作,留给 arc 合入后的下一轮」,本节即该预留操作(弧闭合线收口)。

**重跑口径**:六条件与 §8a 逐字不变(零 LLM/零语义猜测/不造编译器);代码面 96f0f58f(=origin/main,#556 后)——`git diff d4fbdf60..96f0f58f` 于 compile 规则/completion verifier/answer_census 三文件**为空**,sha 与 v1.2 surface 相同(`b2a1ad71…`/`4949fddb…`,锚增记于 `wp3_projection.rule_version` 与逐案 c6)。**纯离线零调用**:#556 Gate 记的 budget-preflight 硬门照做——本操作 preflight 调用下界=0,机械证明:全部 socket 连接入口(connect/connect_ex/create_connection/getaddrinfo)禁用下全程重跑成功,且产物与常规运行逐字节一致(确定性);不触 8303/8301。

**逐案重算+对账(全部机械断言,任一失败不落盘)**:①57 非 bank 案重算与 v1.2/v1.4 逐字节一致、记录零改动(白名单外全树 deep-equal);②15 bank 记录 c2 重编译与仓内存储 `answer_spec` 逐字一致;③14 剧本案 c5 重算与 #555/#556 入库的 `student_script.c5_self_feed_precheck` 逐案一致,命中案早轮零认证;④15 bank 案 `frozen_input_sha256` 按 #556 precheck 同式复算一致(冻结面零漂移)。

**结果(12 投影/2 留空迁移/1 维持)**:

| 变化 | 案 | 终答轮命中证据(turn 4) |
|---|---|---|
| →projected(numeric 6) | 6a62bda2 / 6a62bdae / 6a62c353 / 6a62ca0e / 6a62cb51 / 6a61afaa | `1.16 米`[单位同义换算]/`0.5 米`[单位同义换算]/`300 步`/`13`/`3/100`/`0.4kg` |
| →projected(choice 3) | 6a62cc86 / 6a6955a9 / 6a6955b3 | `D` ×3 |
| →projected(short_text 2) | 6a61c351 / 6a61ba43 | `A.10`[剥空白标点]/`无法确定` |
| →projected(choice 1) | 6a699c32 | `A`(投影=确定性离线判定;该案 live 重放 GatewayError 为 #557 产品面边界,与本离线投影独立) |
| c5_no_student_script→c5_self_feed_miss_on_final_turn(2) | 6a61acc7 / 6a61b65d | #556 预登记未完成轨迹(末轮设计即不落终答),重算命中=否,与预登记一致 |
| 维持 c5_no_student_script(1) | 6a62ca09 | review 不在 arc 池,无剧本,c5 不可评估 fail-closed |

**投影统计(Core 72:5 投影/67 留空 → 17 投影/55 留空)**:empty_reasons 仅 c5_no_student_script 15→1、c5_self_feed_miss_on_final_turn 13→15;c1 29/c2 10 不变(v1.4 统计存档 `wp3_projection.v1_5_refresh.stats_v1_4`)。

**Completion-Capable Core 分母维持 5(不扩张,如实)**:规则③要求 expectation 明确声明 completion(expect.final_states=completed),Core 内满足该面唯一族=shadow_pilot_20(completion_final_state);bank 案 expectation.kind=answer_spec 不声明 completion——投影在场使条件①②成立,③仍不满足。分母扩张需 expectation 面人裁(合同边界变化),非投影操作可及;本节不越权改 expectation。

**b2/goldc 25 案维持 c1 留空(弧闭合线的不可达面,如实记录)**:math_gold_b2 13 + gold_candidates 12 案,源记录 73 条(small_lecturer_math_gold_b2.json 13 + small_lecturer_math_gold_candidates.json 60)`question` 均为裸字符串、无任何 answer 字段(机械核验 2026-10-10),且 §8a 已裁定「仅 trajectory gold,不得投影」。该族闭合需 teacher 侧在源数据集补 answer authority(teacher_confirmed gold 操作,人裁)或裁定变更——超出 corpus manifest 数据文件操作边界,本 PR 不为凑数从题面/剧本语义抽取答案。


**identity 区分**:A 面 arc_version=v0(与 #555 spike 5 案同标记,新 Case 同字段面+learner_trajectory 新子键);B 面 arc_version=v0-negative+variant_id+frozen_input_sha256 按 Core bank 同式实算(题面均不入 Core 的 bank 题,identity 与 Core 零重叠);Core 分母 72 不变,`completion_capable_core`/runtime_projection 面零改动(投影刷新独立操作,与 §8d 同纪律留给下一轮)。v1.3 Core baseline 重刷(Gate C 段)在 14 案 arc 齐备后另行执行,本 PR 只做 corpus+读出。

## 9. 复算命令(冻结身份)

```bash
git worktree add /tmp/edu-corpus-laneA 6f3e7078 --detach
cd /tmp/edu-corpus-laneA
# manifest 自检:JSON 可解析 + 逐案 sha256 可复算(frozen_input_sha256=案载荷 canonical JSON sha256)
python3 -c "import json;m=json.load(open('edu_agent/evals/datasets/trusted_product_corpus_v1/manifest.json'));print(m['counts'])"
# stuck matcher 复验(零模型)
uv run python -c "from edu_agent.agents.small_lecturer import _student_signals_stuck as f;print([f(t) for t in ['我一点都不太会','我还是不知道']])"
```

- sha256 口径:文件=`sha256(文件字节)`;frozen input=`sha256(canonical JSON:sort_keys+ensure_ascii=False+紧凑分隔符)`(bank 案含 learner 声明;scenario 案=整条 record;imgv1 附图字节实测 sha)。
- 冒烟产物与构建脚本在 /tmp(/tmp 证据目录只读纪律:本任务只读 /tmp/survival-out、/tmp/reval-final,新建 /tmp/edu-corpus-smoke)。
- `make check` 未跑:零 runtime 改动(本 PR 仅新增数据资产目录);PR 前自查 manifest JSON 可解析、全部 sha256 实算非占位。
- v1.1 投影复算(WP3;代码面同 6f3e7078 worktree):`python3 /tmp/wp3/project_answer_spec.py`(六条件逐案重算,与 manifest `runtime_projection`/`wp3_projection.stats` 对账);baseline 重放证据在 /tmp/wp3/baseline/。
- v1.2 投影刷新复算(#515 surface;worktree d4fbdf60=/tmp/wp3-v12-worktree):`python3 /tmp/wp3-v12/project_answer_spec_v12.py` + `apply_projection_v12.py`(六条件逐字不变重算 72 案、与 v1.1 逐案对账仅 3 案翻面、写入 manifest v1.2);产物 /tmp/wp3-v12/projection_report_v12.json。
- v1.4 Phase 2 复算(base 4248b816):冻结正本+sha/时间戳 `/tmp/m81/phase2/freeze.json`,precheck/重放/判卷/编辑脚本 `/tmp/m81/phase2/*.py`(driver 启动即断言冻结 sha);重放证据 `/tmp/m81/phase2/arc/collect/cases-20261007T084309Z-b157/`(12 案 ok)+ `cases-6a699c32-20261007T084851Z-f591/`(content 失败复现),判卷 `/tmp/m81/phase2/arc/judge/judge-results.json`;对照基线 /tmp/m80/step4/(只读)。
- v1.5 弧闭合投影刷新复算(surface 96f0f58f):`python3 /tmp/arc-closure-refresh/reproject_v15.py`(离线六条件重算+四门对账:57 案逐字节/15 案 c2 重编译/14 案 c5==precheck/15 案 frozen sha 复算;任一失败不落盘;零模型零网络);manifest 变更面=schema_version+wp3_projection+14 案 runtime_projection,余全树 deep-equal。
