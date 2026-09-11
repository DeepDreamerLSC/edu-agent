# WS4 第 4 条(续) · 提示阶梯 #107:脚手架渐隐评测报告

> 依据:#165 WS4 第 4 条 + **#146 M3**(「脚手架**渐隐** = 现有 #107 提示阶梯」)。
> 本单接 PR #173(#107 方案 A:题库解析 → 确定性阶梯),做**渐隐**这一半。
> 基线:`4232fda`(post-#164 main)。工件:`edu_agent/evals/artifacts/ws4-scaffold-fade/`。

## 0. 渐隐的判据设计(为什么是"有证据才撤支持")

- **掌握度信号(零模型、可复算)**:学生本轮消息里出现**刚揭示那一步 `value` 的数字**
  (`_student_performed_revealed_step`)——即"这一步他自己算出来了"。
  `hint_level=0`(还没揭示过)恒 False:**没有证据就不撤支持**(fail-closed)。
- **渐隐动作**:下一次卡住 → `_faded_stuck_hint` 只**问**不揭示
  (「这一步你先自己想想:你觉得接下来该先算什么?想到多少说多少。」),
  **不消耗阶梯**(`hint_level` 不动)、**只用一次**;再卡住 → 升回揭示下一级。
  → 学生不会被"撤了支持又不会"困住(一次后就补回来)。
- **埋点** `{branch: "fade", hint_level}`:与 `reveal` 分开记 —— 度量侧能数出渐隐触发次数
  与阶梯消耗速度(是否把 bottom-out 推后)。
- **与 #107 原文「答对复位」的映射**:#107 写「`hint_level`:卡住 +1、答对复位、切题复位」。
  本实现**不重置 `hint_level`**,因为该索引同时承担"阶梯进度"(重置会重揭示已完成的步);
  同名意图用「做出该步 → 撤一级支持 / 再卡住 → 升回」表达。**支持档与进度分离**属 #107 的
  更大重构,未在本单展开(见 §4)。

## 1. 改动(两个纯函数 + 一处分支 + 一个会话字段)

| 位置 | 内容 |
|---|---|
| `session.py` | `scaffold_faded: bool = False`(additive,随 `asdict` 持久化) |
| `kernel._student_performed_revealed_step` | 掌握度信号(该步 value 数字 ⊆ 本轮消息数字,含中文数字单字) |
| `kernel._faded_stuck_hint` | 渐隐档提示(一次性;记 `branch: fade`) |
| `kernel.reply` | ① 收到学生消息先更新 `scaffold_faded`;② 卡住分支按标志选「先问」或「揭示」 |

不新增模型调用;不动判据/基线/词表;`_reveal_stuck_hint` 与 bottom-out 语义不变。

## 2. 证据

### 2.1 真模型探针(脚本化学生,四轮实录)

| 轮 | 学生 | 期望 | 实得 |
|---|---|---|---|
| ① | 「我不会做。」 | 揭示第 1 级 | 「我们从这里入手:假设8只全是鸡,脚数应该是多少?。你接着算下一步。」`hint_level=1` |
| ② | 「我算了一下,答案是 16 对吗?」 | 撤一级支持 | `scaffold_faded=True`(该步 value=16 出现在本轮) |
| ③ | 「我不会了。」 | **渐隐:先问不揭示** | 「**这一步你先自己想想:你觉得接下来该先算什么?想到多少说多少。**」`hint_level=1`(未消耗)+ `{branch: fade, hint_level: 1}` |
| ④ | 「我不会做。」 | 升回揭示第 2 级 | 「下一步是这样:实际脚数比假设多多少?。你接着算下一步。」`hint_level=2` |

(同帧顺带观察到 PR #168 的泄露重生成在实跑中生效:②轮模型原句把答案讲完 →
`answer_leak` 命中 → `regenerated: True` 换掉。)

### 2.2 专测(+3,公开路径)

- 做出该步 → 再卡住**先问不揭示**(且 `hint_level` 不消耗、`fade` 事件在);
- 未做出该步 → **不撤支持**(继续揭示下一级,无 `fade` 事件);
- 渐隐**一次性**:触发后标志复位,下一次卡住直接给揭示。

### 2.3 帧(P 口径 11 场景)

| 帧 | 配置 | gate | reveal/fade 事件 |
|---|---|---|---|
| P-before | main `4232fda` | 11/11,+4.41 | — |
| **P-after(本 PR)** | 常规词表 | **11/11,+4.41(逐场景逐项相同)** | **无**(见下) |
| P-expanded(scratch) | 本 PR + **复原 #158 词表** | 11/11,+4.23 | reveal ×2(chicken_rabbit)、**fade ×0** |

**"无 fade 事件"是仪器事实,不是缺陷**:评测脚本里没有「卡住 → 得到揭示 → **自己做出这一步**
→ 再卡住」这一形状(现有卡壳形状只有"同一句重复"与"说不会"),所以渐隐在评测面**不可达**——
这与本单开工时的侦察结论一致(L 口径 = 同句重复 8 轮,学生永不推进)。

## 3. 复现命令

```bash
# 探针(真模型,脚本化学生;动态用 steps[0].value 构造"学生自己做出来"那一轮):
PYTHONPATH=. <venv>/python <报告 §2.1 脚本>(见 PR 附件 /tmp/ws4_fade_probe.py 同名脚本)
# 帧:
.venv/bin/python scripts/tuning_round.py --out <工件根>/P-after
# scratch 词表版:_student_signals_stuck 正则前置 "不知道|还不会|不太会|不明白|不会算|我不会(?!吧)|"
.venv/bin/python scripts/tuning_round.py --out <工件根>/P-expanded
# 单测:
.venv/bin/python -m pytest tests/teaching/test_kernel_state_machine.py -q
```

## 4. 边界与待裁定(登记)

1. **渐隐的"效果"量化缺仪器**:#146 M3 的验证口径是「提示随掌握度渐隐 | **代喂率 + 独立解题能力**」,
   其中"独立解题能力"没有载体;要测渐隐效果需新增「卡住 → 提示 → 完成该步 → 再卡住」的探针口径
   ——按 #165 纪律 1(**测量条件变更需条件对照帧 + 断点标注**),本单**不擅自加**,登记待裁定;
2. **#107 剩余**:提示词改写(教师侧"已按步骤列出…不要自己编数值")、方案 B
   (generate-once-then-reveal + 自校验,面向无 answer/analysis 的纯图场景);
3. **支持档与进度分离**(#107 原文的 `hint_level` 语义重构)未做:本单用"问了不揭示"表达渐隐,
   风险最小;若要做多档支持(给动作 / 给动作+数值 / 只给问),需与 PR #170(揭示动作化)一起排。

## 7. rebase 说明(PM 合入 #168/#169/#170/#173 之后)

原分支基于 `4232fda`;PM 先合了 **#168(守卫粒度)/#169(逐轮列)/#170(揭示动作化)/#173(解析阶梯)**,
`origin/main` 已到 `50c4c132`,本分支 rebase 到该头。rebase 中两处**必要的适配**(均为工程性,不改语义):

1. **C901**:新 `reply` 已到复杂度上限(12),本单新增的一处 `if` 与一处三元把它顶到 13 →
   处置:掌握度更新改为无分支赋值(`session.scaffold_faded = _student_performed_revealed_step(...)
   or session.scaffold_faded`,语义不变:置位即保持,直到渐隐触发复位),并把「渐隐/揭示」二选一
   移进 `_stuck_hint()` 纯函数 → `reply` 复杂度回落,`ruff` 全绿;
2. **测试断言**:#169 起 `guard_events` 事件**另带 `turn` 字段** → 本单原先的全等断言过期,
   改为 `[e for e in guard_events if e.get("branch") == "fade"]` 的字段级断言(容忍 additive 字段)。

rebase 后复验(全部在新基线上重跑):
- 门全绿:`ruff` / `lint-imports` / `budget(suppressions 10/10)` / `infra-keywords` / `test-imports`
  + **650 passed**;
- **探针重跑(真模型,四轮实录)**,与 §2.1 同结论,且可见已合 PR 的叠加效果:
  揭示句已是**动作化**形态(#170)、事件带 `turn`(#169)、渐隐在 turn 3 触发:
  `{'branch': 'reveal', 'hint_level': 1, 'turn': 1}` → `{'branch': 'fade', 'hint_level': 1, 'turn': 3}`
  → `{'branch': 'reveal', 'hint_level': 2, 'turn': 4}`;
- 帧(P-after/P-expanded,§2.3)采集于 rebase 前基线 `4232fda`:rebase 未改动渐隐逻辑路径,
  两帧结论(评测面不触达)不受影响;如需在 `50c4c132` 上重取帧,属**重新跑批**,未在本单做。
