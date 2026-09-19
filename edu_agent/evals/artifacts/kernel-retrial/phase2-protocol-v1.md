# Kernel 消融·二阶段逐机制归因协议 v1(跑前冻结稿;sha256 见回执)

**依据**:PM 判读 #333 c5737621539(三臂混合:情况1 主面+M2 真消费者+自污染+情况2 局部)
+PM 直发派单 2026-09-19(sha256=kernel-ablation-phase2-dispatch-v1;用户已裁走此径并授权)。
**性质**:零模型 calls 纯设计;跑前冻结,跑判不改。**目标**:判别哪个机制在赚存在权
(真消费者)、哪个在拆台(拆台者)、哪个无感。

---

## 1. 选型论证:LOO-from-C(定案)

**LOO-from-C**(每次从 C 关掉一个机制跑判别切片)优于 AOI-to-B(从 B 逐个加回):

1. **问句对齐**:PM 判读的问题是「C 的现有组合里谁在拆台」——LOO 直接在产
   线组合内做单变量删除,归因路径最短;AOI 回答的是「最小可用内核是什么」
   (重建问题),与「删谁」的判读线不同向。
2. **参照复用**:一阶段已有同切片 C 臂数据(零额外 calls 即得「删除 vs 保留」
   的主对照);AOI 的参照(B)离生产组合远,差分混入多机制交互。
3. **预算**:7 变体 × 5 案 + C 复跑 ≈ 240 calls ≤ 250;AOI 同份数但信息量低
   (加回路径上单机制贡献被 B 的稀疏底稀释)。
4. **增强(本协议新增)**:**C 复跑变体(CREF)**——同配置重跑 C 切片,得
   逐指标**噪声底**(模型无种子,单样本差分必须校准);判「无感」以噪声带为界,
   否则一切 Δ 都是噪声。一阶段无此校准,二阶段补上。

## 2. 机制候选与关闭语义(冻结;实现=ablation.py off 集 + kernel.py 门控点)

关闭语义=该机制的不动作(旁路到无该机制的最近行为),其余机制照 C 原样。

| # | 机制名(frozen) | 关闭语义 | 落点 |
|---|---|---|---|
| 1 | `repeat_regen` | 复读检测命中→不 regen,原文本直通(fallback 链随 regen 一并不可达) | `_repeat_refine` L942 区 |
| 2 | `repeat_fallback` | regen 后仍复读→不落阶梯揭示,原文本直通(不置 stuck) | `_repeat_refine` L945 区 |
| 3 | `reveal_ladder` | `_reveal_stuck_hint` 整体降级为 `_SUPPORT_HINT`(只问不揭示;步内容/bottom-out 均不出) | L370 区(三调用方共享该函数) |
| 4 | `premature_confirm` | 判停闸不验:模型 ready_to_confirm 直用,不重写不强制降级 | `_gate_premature_confirm` L828 |
| 5 | `confirm_rewrite` | 兜底句不走「你已经说到了自己的结论…」确认话姿,落通用回引句 | `_contextual_fallback` L452 区 |
| 6 | `soften_step` | 步文本不做 cut/mask 动作化,原文直出(含数值形态) | `_soften_step_text` L395 |
| 7 | `bottomout_backboard` | 梯尽不披露终答(落 NEEDS_REVIEW_TEXT);输出面背板(精确等值复读→揭示)不动作,原文本直通 | L407 + reply() 背板分支 |

生产默认 off 集=空(=现 C,生产路径零改动);A/B 臂不受 off 集影响(臂门控优先)。

## 3. 判别切片(5 案,只跑有臂差案;PM 派单指定)

| 案 | 归因靶 |
|---|---|
| no-progress-real-6a61aa32-replay | M2 抑制主案(C m2=2 vs 裸 6) |
| image_v2_understanding_04 | 流畅破坏主案(C completed→needs_review 反转点) |
| no-progress-control-reasonable-review | 收束延迟案(C 4 轮 rate=2.25 vs A/B 2 轮 completed) |
| no-progress-control-thin-reasoning | 流畅对照(分裂信号) |
| image_v2_stuck_02 | stuck 分裂信号案(C m2=0 vs A/B=1) |

## 4. 跑批与预算

- 变体:7 个 LOO + 1 个 CREF(同配置 C 重跑,噪声底),各 × 5 案,串行,臂间复位。
- 估算:一阶段均 6.06 calls/案跑(含 judge 1);40 案跑 ≈ 240;**硬顶 250**
  (逐案预留 12,将越顶即停 exit 2 呈 PM)。
- 判读需要 C 主对照=一阶段工件(同案同 runner);CREF 只作噪声底,不覆盖主对照。

## 5. 判读预注册(冻结;跑后不改)

**逐机制贡献表**:机制 × {M1,M2,M4,M6-rate,judge,state} × 5 案,主对照=一阶段 C。

三分类判定线:
- **真消费者(M2 抑制)**:`repeat_regen`/`repeat_fallback`/`reveal_ladder` 任一
  关闭后,6a61aa32-replay 的 m2 相对一阶段 C 上升 **≥+2**(即回到裸 A/B 水平 6)
  且 stuck_02 m2/轮数不改善者,记该机制为 M2 抑制真消费者。
- **拆台者(流畅破坏)**:`premature_confirm`/`confirm_rewrite`/`soften_step`/
  `bottomout_backboard` 任一关闭后,understanding_04 或 reasonable-review 的
  judge_total 相对一阶段 C 上升 **>噪声带**(CREF 同案 |Δjudge| 最大值),且
  state 无降级(needs_review 不新增)者,记拆台者。
- **无感**:所有指标 Δ 均落在 CREF 噪声带内。
- **自污染读数**(M4):`bottomout_backboard`/`confirm_rewrite` 关闭后 C 的
  M4 污染案(一阶段 C M4>0 的案)计数变化,验证「C 背板/句族自造污染」归因。
- 单案反转(state 翻转)如实记不判读;单项异常不推翻三分类,呈 PM 裁。

## 6. 工件与回执

- `out/phase2/{LOO-repeat_regen,…,LOO-bottomout_backboard,CREF}/<case>.json`
  + `out/phase2/run-meta.json` + `phase2-summary.json`(逐机制贡献表 v2,
  口径函数复用一阶段 ablation_metrics.py 的 M1-M6 实现——同口径 by construction)。
- 回执 #333 首行 `task=kernel-ablation-phase2`;**完整回执=判读表+结论+异常
  如实报,禁裸回执**(上单已记)。
- 情况2 安全 regen 修复=本单只出零 calls 设计注(附录 A);实现等二阶段读数后
  随处置 PR。
- 上单补账(calls 分解/脚本口径/执行异常)已交付 #333 c5737629738,不重交。

## 7. 纪律

冻结面四不动(prompt/model/dataset/judge);生产零改动(off 集默认空);
需动 A类安全语义/状态机字段语义/DB → 停呈 PM。

---

## 附录 A:情况2 安全 regen 修复·设计注(零 calls;实现随处置 PR)

**现象**(一阶段 B 臂):最小安全 regen 把含 10 分内容的回复砸到 3 分——
critique「仅去除终答数值,不得新增教学内容」使模型连同结构一起删。

**修复方案(最小改,保结构不砸内容)**:
1. **round-1 改确定性数值掩码**(零模型 calls,结构保持 by construction):
   对 answer 源数值做逐 token 替换(数值→「□」),复用既有 `_mask` 式脱敏
   (代喂脱敏同款基建);掩码后文本过同一判据,净则用。
2. 掩码不可读(句法破坏)才落模型 regen,critique 改**逐字保留指令**:
   「逐字保留原回复,仅将终答数值替换为□,不得改写其他任何词句」。
3. round-2 纯 block 语义不变。
   预期:B 臂 judge 回升(结构在),安全面不变(数值仍不可达学生面)。

## 附录 B:一阶段 C 主对照引用(零 calls)

一阶段 `out/ablation/C/<case>.json`(分支 @c0ed8ab)为二阶段主对照;
CREF 变体仅用于噪声底校准,不覆盖主对照。
