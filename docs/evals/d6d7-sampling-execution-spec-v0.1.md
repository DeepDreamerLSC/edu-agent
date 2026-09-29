# D6/D7 Sampling Execution Spec v0.1(待冻结审)

> **状态**：草案(2026-09-29;零执行;先冻结 script SHA + 本 spec,再跑)。
> **上游**：抽样协议 v0.1 冻结件(sha `9c00aa97…`,PR #479 merge bc74465);round 产物(cases-20260929T061613Z-41da,64 session,git bc74465 clean,judge=false)。

## 0. Metadata 前检记录(已通过)

| 项 | 值 |
|---|---|
| seed.txt 预注册时间 | 2026-09-29T05:19:47Z |
| run-spec.yaml 预注册时间 | 2026-09-29T05:19:47Z |
| prereg-metadata.yaml 预注册时间 | 2026-09-29T05:19:47Z |
| round manifest started_at | 2026-09-29T06:16:13Z(> 05:19:47 ✓) |
| round git_sha | bc744650246b3bac372f128062003568ddc6d92f2 |
| round git_dirty | false |
| round prompts_sha256 | cc3d1250a479f944a944184351424716bc2e2684669cec8a46d680e58927f55f |
| round models_sha256 | 98ca6ea4700243e9a6dbf00e67887388a41377644f341ad593c5a732031d9582 |
| round run_spec_sha256 | e0b05c5a9ef81fdfc15e58a15ecdf59b42a22a35dc86ffb3dcc2a45799ce462e |
| judge 调用 | 无(corpus round judge=false 生效) |
| 64/64 status | ok |

## 1. Multi-slice 分布(机械统计,内容未浏览)

| 统计 | 值 |
|---|---|
| sessions 总数 | 64 |
| multi-eligible-slice sessions(≥2 个可判窗口) | **62** |
| single-eligible-slice sessions | 2 |
| turn 数分布 | 3 turns×50, 5 turns×10, 10 turns×1, 4 turns×1, 2 turns×2 |

## 2. Session 内 tie-break 规则(预审 5885318757 修订)

**规则**:一个 session 多个 eligible slice 时,对每个 slice 的 `session_id:turn_index` 计算 **seeded hash rank**(`int(sha256(f"{seed}:{session_id}:{turn_index}")[:16], 16)`),取 **rank 最小**者。

理由:(a) 完全机械、可复现(同 seed 同输入 = 同结果);(b) **无早期 turn 偏置**(62/64 session 有多 slice,统一取最早 turn 会系统性偏向会话前段——预审指出);(c) 消除人为选择空间。

## 3. 分层条件操作化(确定性规则)

### 3.1 「学生明确求助」(条件 A)

**操作化**(机械正则,基于冻结判据 A-1a/A-1f 的请求形定义收窄):

```python
HELP_SEEKING_RE = re.compile(
    r"(怎么|如何|什么|为什么|能.*吗|可以.*吗|帮我|告诉|提示|指导|教我|不会|不懂|不知道|卡住|想不出|不明白)"
)
# 学生上轮文本匹配 → True
```

匹配逻辑:学生 turn 的 `student` 字段文本匹配上述任一模式 = `stratum_proxy_help=True`;不匹配 = False。**字段名**明确为 `stratum_proxy_*`(预审 5885318757:避免误读为 S2a/S2b 语义判断)。此为可观察表面分类,不是 S2 E1-E5 语义判定。

### 3.2 「Tutor 给出步骤/方法」(条件 B)

**操作化**(机械正则,基于冻结判据 B-0 的 giving-move 列表收窄):

```python
GIVING_MOVE_RE = re.compile(
    r"(先算|先看|再算|然后|接下来|步骤|第一步|方法|公式|规则|定律|先用|需要.*乘|需要.*除|需要.*加|需要.*减|等于|所以.*是)"
)
# Tutor turn 文本匹配 → True
```

匹配逻辑:tutor turn 的 `tutor` 字段文本匹配上述任一模式 = `stratum_proxy_giving=True`;不匹配 = False。**同样为表面分类(stratum_proxy),不是 S2b B-0 语义判定。**

### 3.3 局限声明

两个正则是**保守的表面匹配器**,不是 S2 判据的完整操作化:
- 可能漏判(如学生用非标准措辞求助,正则不命中→归入「未求助」层)
- 可能误判(如 Tutor 说「所以面积是 12」被视为「给出步骤」)
- **这不会污染 Gold**(Gold 由真人独立标注定);只会影响分层的纯度——某层可能混入异质 slice,但 Gold 真值不受影响
- 事后可统计分层纯度(标完后看层内 S2a/S2b 实际分布 vs 表面分类的对照率)

## 4. 抽样算法

```python
# 1. 候选池:64 session → 每 session 取 tie-break 后的 1 个 primary slice = 64 slice
# 2. 对 64 slice 逐个标注条件 A(学生明确求助)与条件 B(Tutor 给出步骤/方法)
# 3. 分 4 层(A×B, A×¬B, ¬A×B, ¬A×¬B),各层按 session_id 排序
# 4. 每层内用 seed 2617289367 生成确定性随机序(python random.Random(seed).shuffle)
# 5. 按层配额 8/8/7/7 抽取;层内不足时从最大剩余层同 seed 补足
    # 补位 tie(预审 5885318757):数量并列时按固定层序
    # (_LAYER_ORDER = help_sought_giving, help_sought_no_giving, no_help_giving, no_help_no_giving)
# 6. 替换:无效 slice(§7 规则)→ 同层下一候选(同 seed 序)
```

## 5. 无效判定规则(§7 的操作化)

| 条件 | 处理 |
|---|---|
| student 字段为空或全空白 | 无效 |
| tutor 字段为空或全空白 | 无效 |
| question 字段缺失 | 无效 |
| transcript turns 数 = 0 | 无效 |
| session_id 重复(同一 session 已有 slice 在池内) | tie-break 取第一个 |
| 人审两读 | **不无效**——标 unsure |

## 6. 输出格式(sampling manifest)

```json
{
  "spec_version": "v0.1",
  "protocol_freeze_sha": "9c00aa97…",
  "seed": 2617289367,
  "seed_derivation": "int(\"9c00aa97\", 16)",
  "round_manifest_started_at": "2026-09-29T06:16:13Z",
  "round_git_sha": "bc74465…",
  "candidate_pool_size": 64,
  "layers": {
    "help_sought_giving": {"quota": 8, "selected": [...], "exhausted": false},
    "help_sought_no_giving": {"quota": 8, "selected": [...], "exhausted": false},
    "no_help_giving": {"quota": 7, "selected": [...], "exhausted": false},
    "no_help_no_giving": {"quota": 7, "selected": [...], "exhausted": false}
  },
  "replacements": [],
  "total_selected": 30,
  "manifest_frozen_at": "…",
  "python_version": "…",
  "input_candidate_ids_sha256": "…",
  "source_results_sha256": "…",
  "source_file_count": 64
}
```

## 7. 执行时序

```
本 spec + 脚本冻结(script SHA 记入本文件)
    ↓
脚本单次执行(确定性,可复现)
    ↓
sampling manifest 生成并冻结(SHA + 时间戳)
    ↓
人工第一次独立标注(不看 manifest 以外的任何材料)
```

冻结 sha256:待终裁时补。
