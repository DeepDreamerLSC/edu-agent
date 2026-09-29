# D6/D7 matched-surface adapter v0.1(待冻结审)

> **状态**:草案(2026-09-29;零模型调用;冻结后按运行计划执行)。
> **终裁依据**:#464 comment 5892600320(matched-surface 批准 + answer 暴露处置 + 运行收紧)。
> **上游**:human-gold-v0.1(sha `8a334895…`,single-pass 口径)/ pass1-pack(sha `1f460ece…`,人类实际可见面)/ S2 rubric v0.3(冻结 sha `d415be39…`;**语义零改动**)。

## 0. 定位与红线

**input-surface adapter,不是 rubric v0.4,不改 S2 判据语义。** SYSTEM_PROMPT(prompt 资产)、S2_SCHEMA、gateway 调用参数(max_tokens 16384 / temperature 0)随引擎冻结件逐字共享;唯一变化 = user prompt 的渲染面,全部向 **Human Pass 1 实际可见面**对齐。目的:同一份证据给真人和 Judge,测 Judge 能否执行同一套 S2 判据——人机 disagreement 不混入「两边看到的证据不同」这个额外变量。

## 1. 输入面合同(终裁六条)

1. 同一题面表示(逐字,含 5 案 dict 形态的 answer 暴露——原样复现,不清洗不删案);
2. 同一回看窗;
3. 截止同一锚轮;
4. 不给锚后轮(pack 内本就无锚后轮);
5. 不给 session / case / stratum / run identity;
6. 不给任何旧 Judge / AI 输出。

## 2. 渲染映射(pack → judge user prompt)

| pack 元素 | prompt 元素 |
|---|---|
| `**题面**` 行 | `【题面】` 行(逐字,含 dict 原文) |
| `**年级**` 行(如有) | `【年级】` 行 |
| `[轮N·学生]` / `[轮N·Tutor]` 行 | `学生(轮N):` / `小讲师(轮N):` 行(内容逐字) |
| `▶ **判定锚**` 标记 | `【判定锚】` 框架行(非对话行;对话内容零污染) |
| `(轮 0–N 略…)` 版式注 | 不进 prompt(版式元信息,非证据) |
| ——(引擎侧) | 尾部输出要求 = 引擎 `_USER_INSTRUCTIONS` 逐字共享(import,零漂移) |

**设计选择(冻结审复核点)**:判定锚以非对话框架行给出(`【判定锚】判定对象 = 小讲师(轮N)的本轮回应…`),与人类「判锚轮配对」的任务框架一致;不把标记混入 Tutor 话语(避免内容污染)。若裁不设锚框架行,renderer 改一行即可。

## 3. 答案暴露异质(5 案,已机械核验)

- **P1-09 / P1-10 / P1-14 / P1-27 / P1-28**:cases.jsonl 题面对象为 dict `{text, answer}`(answer 依次:5厘米 / 鸡3只兔5只 / x=6 / 7/8 / 26厘米),另有 `student_turns` 剧本与 `answer_status: correct`;pack 当时逐字渲染了 dict 原文 → **真人标注时答案可见**。其余 25 案题面为纯文本。
- **处置(终裁)**:Judge 输入按真人所见**原样复现**;不静默清洗、不删案、不重开 Gold;结果报告单列 `answer_exposed=5 / non_exposed=25` 两组的一致率 / 错误分布。
- 机械判据:题面字串 `ast.literal_eval` 为 dict 且含 `answer` 键。

## 4. 运行计划与比较纪律(终裁)

1. 冻结本 adapter(只定义 renderer/input contract);
2. DeepSeek Flash **×2**(同配置双跑,测 repeat variance);
3. GLM-5.3 **×1**(terminal Strong-Judge control);
4. human-vs-AI disagreement / miss / FP / unsupported-strong / boundary / failure-correlation 分解。
**然后停。**

- Qwen3.8-27B 本地臂**本轮不恢复**(已失去 daily Judge 存在权;仅当 Flash/GLM 对 Gold 的结果显示「本地替代 API」有明确业务价值,再按既定 bounded ablation 单独点火);
- 不加第三个云端 challenger;不改 Gold;不改 rubric;
- **不与 24-case full-transcript battery 作纵向分数比较**(输入合同不同:battery 案无题面、无锚框架);Flash = 同模型 historical control 角色,**不是历史分数基线**。

## 5. 工件与身份链

| 件 | sha256 |
|---|---|
| renderer `scripts/d6d7_matched_surface.py` | `1dab55afc3d4788b86568cafe7004da2bcf6499ffc4b95a2532c6c7a55165765` |
| runner `scripts/d6d7_gold_consume.py` | `3782d78eacccde1800977373784070d234694776d26eb21e0519424b0f8e8d72` |
| test `tests/evals/test_d6d7_matched_surface.py` | `838892a2a71b2b1b232493e4883f34f0677b78b8ceb3002ee032aea29563bd19` |
| 冻结渲染输出 cases jsonl(私有,不入仓;gold 随行仅供 scorer,模型边界只过 user_prompt) | `71069ca8dca305ef2ae0cb07153bbc1d478ae09dfa123a852870899cbbbe1437` |

- 渲染链:pass1-pack `1f460ece…` → human-gold `8a334895…` → cases jsonl `71069ca8…`(零网络零模型,确定性;泄漏门断言零命中,5 案暴露标记已验);
- run 身份(runner 落盘):git / rubric 冻结(head -n -1 口径)/ prompt 资产 / cases / models 配置 / judge_primary 双字段;resume 须身份全等;**模型身份门**(judge_model 单值 ∧ == 预注册 primary)任一不满足 → 整轮 VOID,不进对照。

## 6. 记录更正与附带发现(2026-09-29,#464 5892600320)

- **记录更正**:上轮「跳过 Pass 2」非裁定(原要求 Pass 1 → Pass 2 → adjudication);single-pass 口径保留为**降级证据资产**,最终报告不得声称 intra-rater consistency;证据名 = `single-human single-pass gold + AI shadow agreement`。
- **batch flag 根因发现**:battery 的 `/tmp/edu-agent-batch/` 旗标落在执行机(WSL2),而 benchmark 让路检查在 Mac runner 侧——两机 /tmp 不通,即 09-28 三红灯未让路的机制性根因。本轮云臂(Flash/GLM)不涉;本地臂重启前须先修(flag 须经 ssh 落到 Mac),已记 #464。

冻结 sha256:待终裁时补。
