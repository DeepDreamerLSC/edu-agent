# D6/D7 独立 Gold 集抽样协议 v0.1—— M2 缺口①(草稿,待冻结)

> **版本**:v0.1 草稿(2026-09-29;文件 `d6d7-gold-sampling-protocol-v0.1.md`;零模型零跑批,纯抽样协议件待人审冻结)。
> **定位(用户点火指令 2026-09-29)**:验证 S2 v0.3 在**未参与修尺的新案例**上是否成立。顺序铁律:**抽样规则冻结→人工独立定真值→gold 冻结→Judge 才能看**。
> **纪律**:抽样阶段只按可观察条件分层,不提前用语义标签;gold 冻结前任何 Judge 输出不进标注界面。

---

## 0. 候选池盘点(先核事实,再定资格)

### 已有证据源及其污染状态

| 来源 | 案数 | 参与过(逐项) | 独立性判定 |
|---|---|---|---|
| Phase A 64 session | 64 | **failure discovery**(A64 baseline judge 全评);**coverage mapping**(Matrix v0.1 层 3 证据源);**rule formation**(D1-D16 层 3 证据引此);**人工讨论**(Phase A review pack) | **不可作为 untouched**;可作「新人工 gold / held-out-from-judge」(对 Judge 是新的,对规则形成链不是) |
| Phase C 24 案 | 24 | **judge calibration**(C24 adjudication 分歧矩阵);**boundary discussion**(S2 定义/判据锚案);**rubric revision**(S2 v0.1→v0.3 全链);**battery 组成**(24 案 dev 集) | **完全排除** |
| S2 Step 3 battery 24 案 | 24 | 同上 + **rubric revision 直接调参对象** | **完全排除** |
| 定义/判据 14 锚案 | 14 | **rule formation**(锚案=定义 §5/§6 案卷);**rubric revision** | **完全排除** |
| A64 judge 侧锚案(#01/#20/#63 等) | ~10 | **rule formation**(锚案+反锚);**rubric revision** | **完全排除** |
| OOT 带外观察 | ~10 | **人工讨论**(A64/C24 读数附注) | **完全排除** |
| #453 parity 复现 session | 0(目录空) | — | **不可用** |

**结论:当前仓内/私有证据源中,没有任何可标「untouched」的现成 session。** Phase A 64 session 是唯一可扩展池,但只能标「**新人工 gold / held-out-from-judge**」——对 Judge 是新案(没有任何 Judge 输出),但其失效模式已被 coverage review 消费、可能间接影响了规则形成。

### 新 session 通道

| 通道 | 说明 |
|---|---|
| corpus round 新跑 | 跑一轮新 seed 的 corpus round,产新 session;身份可追溯(run-spec/manifest);**S2 判定面零消费**(S2 judge 是独立标注线,不进 corpus round) |
| 用户侧真实 session | 产品在用中产生的新 session;身份可追溯(facts/session_id);需用户批准访问 |

## 1. 抽样单位

**一个可判 S2a/S2b 的 transcript slice** = 一个 session 中「学生暴露 need → Tutor 回应」的**最小可判窗口**。

操作化:
- 以 **tutor turn** 为锚(每个 tutor turn 产生一个 S2a/S2b 双轴判定机会);
- slice 范围 = 该 tutor turn 的学生上轮(t 或最近学生轮) + 该 tutor turn 本身 + 跨轮所需回看窗(E3/R4/A2 需 3 轮回看);
- 一个 session 可产出多个 slice(每 tutor turn 一 slice);
- **slice ID = `{session_id}:{turn_index}`**,全局唯一。
- **session 去重(终裁钉子 2)**:默认一个 session 最多进入 **1 个 primary slice**;确需多个时须预注册原因(如「该 session 含两个独立 S2a/S2b 判定窗口,覆盖不同场景层」),并按 session 聚类统计(报告 session-level vs slice-level 读数差)。

## 1.5 时间边界(终裁钉子 1)

**只有「协议冻结之后」产生的新 session 才有 primary-pool 资格。** 协议冻结时间戳记入冻结 SHA 行;此前产生的所有 session(含 Phase A/C/OOT/未入档)一律无 primary 资格。

## 2. 候选池资格(逐条,全须满足)

1. **可追溯身份**:session_id 或 run manifest 可定位原始 transcript;
2. **transcript 完整**:学生/Tutor 逐轮文本非空,无截断/损坏;
3. **题面与终答可获取**:S2b 的 B-1a 层次识别需知「该题当前阶段的核心构造性推理」——需至少有题面文本(question 字段)以支持人审;
4. **排除全部已消费案**:凡进入过 S2 definition/criteria/rubric/battery/boundary discussion/judge calibration/coverage review 证据链的 session,**整个 session 排除**(不只排除特定 turn)。

## 3. 污染排除(不按名单机械排,做 provenance 反查)

### 已确认排除集(整个 session 排除)

```
Phase C 24 案的 session_id(全部)
S2 Step 3 battery 24 案的 session_id(= Phase C 子集,已覆盖)
定义/判据 14 锚案的 session_id(映射回 Phase A/C ID)
A64 锚案/反锚案的 session_id(映射回 Phase A ID)
OOT 观察案的 session_id
```

### Phase A 64:集合级确认暴露,本轮 primary gold 全量排除(终裁 2026-09-29)

Phase A 64 session **已集合级确认暴露**(全部被 A64 baseline judge 评分 + coverage review 消费)——本轮 primary gold **全量排除**,无需为本轮逐案反查(终裁 C:反查不会改变抽样资格,只消耗时间)。未来若作为 secondary 对照再查。

### 本轮策略(终裁 A:只接受新 session)

| 来源 | 独立性标签 | 资格 |
|---|---|---|
| **corpus round 新跑**(协议冻结后产生) | **untouched**(对规则形成链与 Judge 均全新) | **primary pool(唯一)** |
| Phase A 64 session | 集合级已暴露 | **本轮排除**;未来 secondary 对照另议 |

## 4. 分层目标(覆盖设计,不偷看标签)

**抽样阶段只用以下可观察条件分层**(与 S2a/S2b 语义无关的表面特征):

| 可观察条件 | 取值 | 分层目的 |
|---|---|---|
| 学生明确求助 | 是 / 否 | 覆盖 E1-E4 vs 无 need 侧 |
| 学生已有尝试 | 是 / 否 | 覆盖有/无先前计算路径 |
| 先前提示失败 | 是 / 否(回看 3 轮) | 覆盖 A2/E4 侧 |
| Tutor 给出步骤/方法 | 是 / 否 | 覆盖 giving-move vs 纯提问 |
| Tutor 给出终值/结论 | 是 / 否 | 覆盖 answer_leaked vs 未泄 |

**五条件产生 2⁵=32 个理论格子;实际只需控制关键格子非空**(不用全格等量):至少覆盖「有求助+有给出」「有求助+无给出」「无求助+有给出」「无求助+无给出」四个大类。

**分层 ≠ 标签配额(终裁钉子 3)**:五个可观察条件只用于保证场景覆盖,**不允许预先凑 S2a/S2b YES/NO/UNSURE 比例**。标注后才统计 S2a/S2b 分布——如果某关键类别严重缺失,按 §7 补样规则补(按可观察条件补,不按语义标签补)。

## 5. 选择方法

1. 候选池形成后(排除+资格过滤后),按 §4 可观察条件做**机械分层**;
2. 每层内按 **session_id 排序后随机序机械抽取**(seed 预注册,抽样脚本可复现);
3. **不人工挑案例**;如果某 slice 被抽中但 §7 判定无效,按 §7 替换;
4. 抽样结果(候选池+分层+选中列表)作为抽样协议附录落盘,与协议同冻结。

## 6. 规模与停止规则

- **预注册 30 案**(slice 级)为第一轮;
- 如果有效可判样本 < 30(因无效/替换不足),按同规则从剩余候选补到 30;
- **上限 50**;不跑后扩样;
- 30 案 = kill-test 规模,不用于声称 production 级准确率。

## 7. 无效样本/替换规则

| 情况 | 处理 |
|---|---|
| transcript 截断/损坏 | 标无效,按原抽样规则取下一候选 |
| 题面不可获取(B-1a 不可判) | 标无效,替换 |
| 非中文/非小学数学语境 | 标无效,替换 |
| 人审无法判定(证据不足两读) | **不标无效**——标 unsure(这本身是 gold 真值);只有结构性缺陷才替换 |
| 替换来源 | 同层(§4)下一候选(同 seed 随机序),**不得人工挑替代** |

## 7.5 标注流程(终裁修订 2026-09-29:单真人 + 重复盲标 + AI 只做独立 Shadow)

### 流程

```
新 corpus round → 按冻结协议抽 30 slice
    ↓
真人第一次独立标注(不看任何 AI 输出)
    ↓
真人第二次盲化复核(重新打乱顺序/ID,不显示第一次答案)
    ↓
两次不一致案由真人终裁
    ↓
Human Gold 冻结
    ↓
AI 独立 Shadow 标注(不参与真值投票)
    ↓
统计人机一致/分歧/failure pattern
    ↓
Flash/GLM/Qwen 等 Judge 正式消费 Gold
```

### 权限边界

- **真人**:唯一 Gold / expectation authority;
- **AI**:只做对照、发现分歧和潜在边界,**不拥有真值权**;
- **不采用「真人 1 票 + AI 1 票」多数决**;
- Gold 冻结前,AI 输出不影响真人第一次标注,也不参与样本筛选。

### 第二次盲化复核的最低要求

- **首选**:30 案全部重新盲标一次(测 intra-rater consistency);
- **压缩口径**(报告中必须声明):至少复核 ①第一次标 unsure 的案 ②边界案 ③真人低信心案 ④后续 AI shadow 与真人不一致的案;
- 两次不一致案由真人终裁(终裁时可见两次答案+transcript);
- **gold 冻结 = 全部 slice 终裁完成 + intra-rater 一致率记录 + 终裁人签字时间戳**。

### 证据名称

> **single-human adjudicated gold + AI shadow agreement**

不称 multi-rater gold。足以回答 M2/D6-D7 的问题(S2 判据在新现实数据上是否成立 + 不同 Judge 能否可靠执行),暂不足以宣称 production-grade 人工标注可靠性。

## 8. 防火墙

1. **gold 冻结前**:Qwen/Flash/GLM/旧 Judge(v3.2/ER)的任何输出,不进入标注界面,不用于样本筛选,不告知标注者;
2. 标注者只见:transcript(逐轮原文)+ 题面 + 终答 + 抽样编号(盲化);
3. 标注者不知该 slice 来自哪个 session / 哪个跑面(盲化 ID);
4. 抽样协议与 gold 标注分别冻结(抽样协议先行,间隔明确);
5. gold 冻结后才允许 Judge 消费——任何 Judge 输出不反向修改 gold。

---

## 附:终裁决策记录(2026-09-29)

| # | 决策 | 终裁 |
|---|---|---|
| A | 候选池 | **新 corpus round**。只接受协议冻结后新产生/采集的 session 进入 primary gold;Phase A 64 全量排除 |
| B | 标注者 | **单真人 + 重复盲标**(第一次独立标注→第二次盲化复核→不一致案终裁);AI 只做独立 Shadow 不参与真值投票;证据名称=single-human adjudicated gold + AI shadow agreement(修订 2026-09-29) |
| C | Phase A provenance | **冻结前不逐案反查**;已有集合级证据足以判定全部已暴露;未来若作 secondary 对照再查 |

## 附2:正式口径(一句话)

> **Primary gold = 协议冻结后新 corpus round → 机械条件分层 + 固定 seed 随机 → 30 个 primary slice → 原则上一 session 一 slice → 单真人第一次独立标注 → 第二次盲化复核 → 不一致案真人终裁 → Human Gold 冻结 → AI 独立 Shadow 标注 → Flash/GLM/Qwen Judge 正式消费。**

冻结 sha256:待终裁时补(head -n -1 本文件 | sha256sum 口径)。
