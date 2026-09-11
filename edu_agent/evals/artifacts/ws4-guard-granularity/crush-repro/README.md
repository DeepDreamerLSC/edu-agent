# 压分复现配置(scratch,不入库)——WS4 第 1 条验收第 1 半

**目的**:复现 #152 config ③ 的压分机制(「学生已陈述终答的末轮被守卫整轮替换 → needs_review」),
在**同一配置**下对照 main 与修复分支,隔离出守卫本身的效应。

**配置(只此一处,两棵树同注入、跑完即撤)**——`kernel.py::reply()` 的**逐轮 user 提示**
「输出提醒」尾部追加一句(不动 system 提示、不动 `start()` 首问):

```
【SCRATCH 复现】若学生本轮已算出并说出最终答案,这一轮做确认收尾,并在确认里写出「等式性质」四个字。
```

为什么用逐轮注入:首版把指令加在 **system** 提示里,结果模型把「学生已做对」提前到**首问**
(首问答非所问 + 泄露 → judge 首问维度 0 分),压分被配置本身污染、无法归因给守卫。
逐轮注入只作用于 reply 轮 → 单次命中落在**收束确认轮**,与 #152 的形态一致。

**运行**:
```bash
cd <worktree>(先打上上面那行 SCRATCH;before=4232fda,after=修复分支)
PYTHONPATH=. <venv>/python /tmp 脚本 ws4_crush.py <输出.json> .
```
脚本内容:跑 `equation_complete_reasoning`(11 场景中压分的那一个)→ `judge_transcript` 六维总分。

**读数**(同晚同机同 judge,单帧):

| 树 | final_state | 总分 | 六维(first/socratic/grade_fit/pacing/summary/termination) | 守卫处置 |
|---|---|---:|---|---|
| before(main `4232fda`) | **needs_review** | **5** | 1 / 2 / 2 / 0 / 0 / 0 | `feeds_method` 命中 → 整轮换复讲模板(原文:「你用等式性质一步步算对了…真棒!」) |
| after(修复分支) | **completed** | **12** | 2 / 2 / 2 / 2 / 2 / 2 | 命中原句 → **重生成**保留确认语义(`mode=regenerated`),不换模板、不强制不确认 |

#152 记的 config ③ 读数为 **3 分**(同机制、样本差);本配置隔离后 main 5 分、修复后 12 分
(**验收:原被压到 3 分的场景回到 ≥12 ✓**)。

**另有一组更重的故障注入**(system 提示强制每步点名「等式性质」,`system-prompt-*.json` 未留存)
用于确认「重生成失败 → 确定性脱敏」路径:main 1 分/needs_review → 分支 10 分/completed,
其中收束轮走 `mode=masked`(文本变成「你用**这种方法**把3x等于18化成x等于6…真棒!」,
确认语义保留)。该配置同时污染首问/总结(judge 首问维度被压),故绝对值低于 12——与守卫无关,
是配置自带损伤(#152 因 B + 总结点名),故仅作路径佐证、不作达标口径。
