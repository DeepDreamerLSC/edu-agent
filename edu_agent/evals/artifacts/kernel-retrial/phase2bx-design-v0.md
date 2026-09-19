# B+X 加回实验设计 v0(跑前呈点火;#333 方向修正单 2026-09-19 §14-④)

**依据**:架构师二次裁定(add-back 方向)+零调用因果归因(phase2-zero-call-attribution 回执)。
**预算带**:60-100 本地 calls(另呈点火键)。**禁 override**:机制变化走 owner-layer
真实 code diff(分支 patch),不走 harness off 集/配置开关——每个 B+X 变体=一次
kernel 代码改动,评测面零改动。

## 1. 基座与 parity 前置

- **基座 = B 臂(thin safety)——但必须先修 parity**(parity 回执四破口):
  ① Subject 喂 answer/analysis/knowledge_points(对齐生产题库 resolve() 契约);
  ② prompt 对齐生产 8a9bd9e5(剥 57a18a04 多出的 anti-reask 行,或生产先拉平——二选一呈裁);
  ③ learner.answer_status 补齐(image 案按题库 answer_correct 映射);
  ④ models.yaml 并发口径记录(行为面不敏感)。
- parity 修正后重跑 C/B 基线(判别切片 5 案+leak-risk 2+comma 1 ≈8 案 ≈50 calls,
  与 B+X 同批跑,预算带内)。

## 2. 加回候选(按因果指纹筛,2-3 个)

| 候选 | 指纹证据 | 正例案(赚) | 负例案(毁) |
|---|---|---|---|
| **repeat_regen** | 6a61aa32-T6 单点破复读链(m2 6→2,LOO 与因果链双证) | 6a61aa32-replay | reasonable-review(流畅误伤面) |
| **elicit(#9 确定性句族)** | u4-T3 模板替换毁 engaged 轮(judge 12→7)——**二阶段候选集漏网真凶,存在权待测** | stuck_02(支持面) | understanding_04(毁分面) |
| **reveal_ladder**(视预算) | reasonable-review 正贡献确认(judge 4→1 when off)+comma 锚拒 | stuck_02 | thin-reasoning |

每候选 2 正例+2 负例;B+X vs B 对照同批。

## 3. 判读线(预注册,呈点火时冻结)

- 存在权(KEEP):正例案显著改善(超 CREF 噪声带,带=0)+负例案不显著变差
- 收窄(NARROW):正例改善但负例变差超带 → 触发条件收窄设计
- 删除(DELETE):正例无改善
- elicit 特殊:正例/负例同体(stuck 支持 vs u4 毁分)→ 判据=净值,呈人裁

## 4. 实现形态

- 每变体=分支上一个 owner-layer kernel patch(把机制加回 B 臂路径),标注
  `phase2bx-<mech>` commit;评测 runner 只认代码状态,无配置开关。
- 工件 out/phase2bx/{BASE-B,B-repeat_regen,B-elicit,B-reveal_ladder}/<case>.json
  + phase2bx-summary.json(复用 M1-M6 同口径函数)。
