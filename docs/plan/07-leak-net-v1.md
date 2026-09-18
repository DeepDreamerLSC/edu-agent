# 07 · 泄露网 V1:reveal 窄授权(#333 裁定 c5717512971 正本)

状态:实现 PR 落地(PM 49255c5dba108a0b);测试面备料 = #352(105 案分类 + 7 种子 + 覆盖盘点)。

## 1. 正确事实(设计文档载明,#333 PM 自我更正两条)

1. **reveal 档从未有过锚豁免**:`_soften_step_text`(kernel)自 #165 WS4 起一直把该步
   算好的结果收回去(「等于把这一步的结果算给学生,学生只剩抄写」);_SELF_CRITIQUE 指令
   叫模型给锚,但确定性 reveal 走 soften 收回、模型输出撞网被拦(viability stuck_02 即证)。
2. **本件 = 新产品 policy,不是 guard 误报修复**:重新决定 reveal 是否恢复部分中间值锚
   能力;「给锚语义部分活在 reveal 档」的旧记录不精确——活着的只是 telling 的动作化
   揭示,数值披露从未授权。

## 2. V1 授权面(极窄,裁定原文)

```
终答数字:永远 protected
中间步锚:仅 deterministic reveal/telling 路径 × 仅当前 next step 的 value
        × 仅非终答值(anchor=step数字−answer_pool,无双重身份)
        × 仅 hint_level>0 且再次 stuck × ready_to_confirm 禁止
模型自由生成路径:零例外(系统判该给锚时由 deterministic reveal 产生)
```

实现(kernel.py,唯一改动区):

- **`_current_step_anchor_numbers(session, step)`**(纯助手,不进 numeric.py——Q7:归因
  不知道 stuck/telling/hint_level):`anchor = numbers(step.value) − answer_pool`,且
  **无双重身份** = value 数字与 answer_pool 任一重叠即整步禁(返回空集 fail-closed)。
  单步题(value=终答)、多部件答案、末级步天然落禁面。answer_pool 用全量
  `_answer_numbers`(漂移池口径,question.answer 优先/steps 末值兜底);
  **勿用 `_answer_focus_numbers` 做锚减法**(focus 剔题面数是「已陈述」判据口径)。
- **七条件收敛**:stuck×telling 由调用方结构保证;next step 存在 = step 非 None;
  hint_level>0 = 进入函数前捕获(`_next_step` 推进前);state≠ready_to_confirm 在调用侧;
  anchor 非空 / ∩answer_pool=∅ 在 helper 内。
- **hint_level==0(首次 stuck)→ 现有动作化 reveal 原样**,不给任何数值。
- **授权渲染**:动作化文本后接「这一步先算,得到 X。」(与 soften 口吻衔接);
  未授权路径逐字不动。
- **审计单字段(Q6)**:reveal 事件 additive 键 `anchor_numbers: [..]`,只在授权轮写
  (未授权轮不加键,既有整 dict 断言不变,#187/A4 指标连续);不造新事件类型。

## 3. 三层测试(Q5;merge blocker = ③)

1. **#352 四断言激活**(tests/teaching/test_anchor_reveal_v1.py):首次 stuck 不给数值 /
   再次 stuck 给当前级非终答锚 / 单步题 repeated stuck 仍不给 / 部件重叠仍不给。
2. **七边界对接入**(seeds-anchor-v1.json):A 锚合法(chicken_rabbit 真例)/ B 单步碰撞×2
   (stuck_02、answerhit_01)/ C support guiding_focus 零锚 / D ready_to_confirm
   (公开流实证:卡壳信号先降确认态 → 防御条件由源读核验,测试钉「state 检查读当前态」)/
   M 多部件重叠禁(understanding_04)/ F 答案不可判定 fail-closed(stuck_01)。
3. **92/93 泄漏=0 硬门(merge blocker)**:既有套件全绿
   (test_answer_leak_guardrails 13+ 锁 + test_kernel_invariants 终答两路径锁 +
   soften 三路径 9 形态)——锚数字由构造保证 ∉ answer_pool,硬门口径不变;
   viability 4 案重放首验 = `replay_viability.py`(预期预声明:stuck_02 锚过 /
   answerhit_01 仍拦 / stuck_01 与 understanding_04 无锚;泄漏=0 为硬判据;
   本地模型执行由 PM 路由)。

## 4. 覆盖盘点不破(#352 coverage-inventory.md)

soften cut/mask/none 三路径与 9 形态(含 #185 序数/导出值)、阶梯推进与防复读背板、
终答只走 bottom-out/finish 两路径不变量(**V1 锚为第三合法披露点:仅中间值、仅当前级、
仅七条件过——终答数字仍永远 protected,两路径锁语义不变**)、`_known_answer` 三处同源、
numeric.py 零改动。唯一精确串更新:`test_repeat_fallback_ladder_texts_differ_consecutively`
的 lead2(再次 stuck 授权轮文本),推进+互异不变量原样保持并加强(新增「16/5 不出现」
+anchor_numbers 断言)。

## 5. 已知边界与观察(如实记录)

- **`_STEP_ARITHMETIC_RE` 不含 U+2212(−)减号**:种子一律用真实 plan 形态(连字减号,
  同 L 口径帧「26-16=10」);是否扩类属 soften 词表收放(#185 先量再收纪律),不在本件。
- **ready 态与 re-stuck 公开流互斥**:学生卡壳信号把确认态降回 dialogue(test_D 实测),
  state 条件为防御性(kernel 保留,七条件正本要求)。
- **hint_level 是「再次 stuck」的机械代理**(裁定 Q2):guiding_focus 不消耗阶梯,
  不影响代理语义。
- spec/模型路径零例外;judge 两层解耦(kernel safety=能不能安全显示;judge=教学是否
  太直给)——不为 judge 绿把合法锚重定义为非法。

## 6. 数字等价类定夺(v1-property-supplement;四条缺口,该补的补、不该的记理由)

| 等价类 | 定夺 | 理由 |
| --- | --- | --- |
| 千分位「1,000」 | **补**(kernel 侧双侧归一,`_THOUSANDS_RE`) | 真漏 vector:answer「1,000」池={1,0} 而 value「1000」={1000} 交空 → 锚漏终答;归一后撞池即禁。numeric.py 归因不动(Q7);漂移池口径独立不受影响 |
| 分数值「3/4」/多位值 | **补**(单数值门槛:value 提取后非恰一个数字 → 禁) | 多位值渲染「得到 3、4」破相(渲染面);保护面本已保守({3,4} 双双入池)。门槛同时收窄跨形态面(见下) |
| 百分号「50%」 | **不补** | 「50%」→{50} 双侧一致,overlap 保护成立;渲染丢 % 由动作文本语境承接 |
| 负数「-5」 | **不补** | 符号双侧一致剔除=保守正确(「-5」与「5」撞池即禁);补符号解析反开「-5≠5 可锚」的漏洞面 |

跨形态观察(记档,不补):数值等价跨形态(「3/4」vs「0.75」)不在提取口径内——生产路径
answer 不喂(pool=steps 末值,形态与 value 自洽)无漏面;仅 feed_answer 测量断点下存在,
且单数值门槛已把多位分数收禁。**不造数值等价 ontology**(裁定 Q1:保守正确优先)。

## 7. soften 无分句边界收紧候选评估(记 finding,不硬改)

现状:soften 找不到分句边界 → 保留原句(「宁可直给,不出残句」)。V1 语义下的张力:
授权轮直给段(含结果值)与锚句「这一步先算,得到 X」可能重复;未授权轮直给=展示完整
算式,较锚 policy 过度披露。三候选:

1. **保留现状(推荐)**:授权轮重复无害(锚值本就授权,学生多看一遍算式无新信息面);
   未授权轮残句风险 > 过度披露风险;#185 纪律「先量再收」——等 soften:none 影子占比
   数据出来再定。
2. 无边界时放宽「几」改写 shape:改写质量不可控,残句风险回流,不取。
3. 无边界时整步弃用:浪费梯级 + NEEDS_REVIEW 噪声,不取。

若未来收紧,候选顺序 2 > 3;本件零改动。
