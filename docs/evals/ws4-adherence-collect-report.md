# WS4 第 5 条 · 弧线 adherence「采集不评判」(行为面修法)评测报告

> 依据:#165 WS4 第 5 条 + #146 登记(09:14「弧线 adherence 两项」/本轮取证登记
> `#146 issuecomment-5623021308`)。F 口径「采集不评判」= `arc_eval_judge` 规则 2。
> 基线:`4232fda`(post-#164 main)。工件:`edu_agent/evals/artifacts/ws4-adherence/`。

## 0. 缺陷(行为面)

规则 2 的窗口 = **采集轮 + 紧随的回应**。实测(基线帧)20 例 applicable,**4/20 合规**;
判词逐条显示根因:**弧线第②步「追问他这个答案是怎么想出来的」被跳过**——tutor 从①采集
直接跳到③纠正/引导,于是紧随的那一轮就出现判定:

| 场景 | judge 原句 | 性质 |
|---|---|---|
| fraction_addition | 「但分数加法不能这样算哦」并给出反例 | 行为(判定+纠正) |
| triangle_area | 「你算出10×6=60,**这一步很准!**」 | 行为(判定) |
| word_problem | 「你把买来的和原有的加在一起是对的,**但借出的书要从总数里去掉**」 | 行为(判定+纠正) |
| equation_subtract | 「**这一步很对**」 | 行为(判定) |

根因定位:`opening_hint(answer_status)` 只在**首问**注入(`_opening_user_message` /
`_open_user_message`),**后续轮次没有任何弧线步骤指引** → 模型自行决定推进方式。

## 1. 改动(一处注入点 + 一个纯函数)

`reply()` 的逐轮 user 提示里加一个 `弧线步` 字段(仅当适用):
`diagnose_turn_hint(answer_status, reply_index)` —— **仅 incorrect 弧线「首问后的第一次回应」
(reply_index=0)** 返回第②步提示:

> 【弧线第②步 · 这一轮只做一件事】学生刚说出他的作答。请**只追问他是怎么想出来的**…
> 这一轮**不要判定对错**(不出现「对/很准/真棒/不能这样算」这类评价)、**不要纠正**、
> **不要给反例或下一步**。

- `reply_index = len(session.history) // 2`(首问不入 history,每次 reply 提交两条);
- 非 `incorrect` 状态**一律空串** → correct/unknown 路径零改动(P 口径 gate 内含 10 条 None +
  1 条 correct ×2,**代码路径不被触达**);
- **不新增学生可见模板**(仍是模型生成)、不动判据/基线/词表。

**被数据否决的扩展(留痕)**:把窗口从「只第②轮」扩到②+③(诊断阶段)后,F 口径**反而
4/20**(判词显示判定后移;另有 2 例被复讲引导接走)→ 已回退,只保留第②轮,常量也未保留
(避免死代码)。两版对照同一晚同机。

## 2. 帧证据(F 口径,20 例 applicable)

| 帧 | 配置 | 采集不评判 | 说明 |
|---|---|---:|---|
| F-before | main `4232fda` | **4/20** | 基线(#146 登记同值) |
| F-after | ②+③ 扩展版 | 4/20 | **否决** |
| F-after2 | 本 PR(只②) | **10/20** | 同配置第二样本 **8/20** → 区间 **8–10/20** |

判词对照(同一场景、同一重复):fraction_addition / triangle_area 从 ❌ 翻 ✅,
after 原句「能说说你是怎么想到这个办法的吗?」(②步真的执行了)。

**剩余 10 例失败的两面**(按判词分类,不改判据):
- **口径面(约 4 例)**:chicken_rabbit 的剧本首轮是「我还不知道怎么同时算两种动物。」、
  equation_subtract 是「我还没有想清楚,能先给我一个方向吗?」——**学生从未给出作答**,
  而规则 2 要求「教师确实采集到了学生的作答」→ 该指标对这 4 例**结构性不可达**
  (F 口径把 answer_status=incorrect 强制套在不含作答的剧本上;与本 PR 无关,已随本轮登记);
- **行为面(约 6 例)**:判定发生在**更后面的轮次**(如 word_problem 第 3 轮「这想法很对!」、
  equation_subtract「这一步完全正确」)。该窗口已超出第②轮;是否继续抑制属弧线④
  「苏格拉底式追问修正」的措辞边界,**需人裁定**,本单不再扩大。

## 3. P 口径 gate 零回归

| 帧 | 配置 | 结果 |
|---|---|---|
| P-before | main `4232fda` | 11/11 达标或不劣,均值差 +4.41(工件见 PR #168 `ws4-guard-granularity/before`) |
| P-after | 本 PR | **11/11 达标或不劣,均值差 +4.41**;逐场景分数**逐项相同** |

代码路径论证(可复核):本改动只在 `answer_status == "incorrect"` 时注入;P 口径
`build_cases` 的 11 场景为 10 条 None + 1 条 correct(word_problem)× 2 重复 → **零触达**。

## 4. 专测(+2)

- `test_arc_diagnose_hint_only_on_first_reply`:提示出现在首问后的**第一次**回应,之后不再出现;
- `test_arc_diagnose_hint_absent_without_incorrect_status`:无 `answer_status`(unknown)零注入。

## 5. 复现命令

```bash
# F 口径(采集不评判仪器):collect + 判分
.venv/bin/python scripts/arc_eval_fix112_frames.py --frame {before|after} --calibers F \
    --base-sha 4232fda --out <工件根>
.venv/bin/python scripts/arc_eval_judge.py --out <工件根>/{before|after}
# 统计:读 judge-scores/*.json 的 collect_not_judge.{applicable,compliant}
# P 口径(gate 零回归):
.venv/bin/python scripts/tuning_round.py --out <工件根>
```

## 6. 边界与未做

- **不改判据/基线**:规则 2 的窗口与措辞原样;口径面(「反问『对吗』是否算判定」、
  以及上述 4 例结构性不可达)只登记、不处置;
- 不动 `docs/plan/*`;不动首问措辞(`OPENING_HINT_INCORRECT` 原样);
- 与 #107(提示阶梯)无交集:本条只补「②追问思路」这一轮,不涉及阶梯分级。
