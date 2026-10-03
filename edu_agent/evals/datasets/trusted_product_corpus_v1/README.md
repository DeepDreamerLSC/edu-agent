# Trusted Product Corpus v1(M4 overnight Lane A)

第一版可信内部产品面 corpus:引用式 manifest(不复制载荷),逐案记录 admission gate 判定、frozen input sha256、expectation+authority、set 归属与 coverage。

- **执行身份(冻结)**:`6f3e70785545b51932b32b41f7b6a3d226934a66`(= #509 合入点;worktree detached 复核)。
- **身份不变量**:零 runtime 改动(本目录仅 manifest.json + README.md 两件数据资产);不改 Authority/Policy/Product Contract/completion semantics;不新增 Judge/Evaluator/Framework;真实学生数据零入仓(全部来源=仓内数据集/合同件+/tmp 只读档案的合成与评测案)。
- **产物**:`manifest.json`(schema `trusted_product_corpus_v1/manifest/v1`);本件为读法与判定记录。

## 1. 集合与计数(全部可由 manifest 复算)

| set | 数 | 定义 |
|---|---|---|
| **Core** | **72** | Admission Gate G1–G8 全过(门列表见 manifest `admission_gates_core`) |
| Challenge | 80 | 历史 failure/边界/反事实/已修事故(有价值但不满足 Core 门) |
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

## 8b. Completion Baseline v1 结果(见 PR body;/tmp/wp3/baseline/ 证据)

(本节由 WP3 baseline 跑批后回填。)

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
