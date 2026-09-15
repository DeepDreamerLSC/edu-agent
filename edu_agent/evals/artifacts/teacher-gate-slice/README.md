# teacher-gate-slice:教师线 promotion gate 固定盲区挑战切片(#253,2026-09-15)

机制规程 = `docs/evals/teacher-promotion-gate-v1.md`(定义来源 #253 c5673905941 人批采纳;点火 = 用户会话内选定 2026-09-15)。本目录 = 切片本体:**11 案(三家族),输入逐字冻结,双跑基线冻结**。

## 文件

- `slice-cases.jsonl`:11 案输入逐字冻结(transcript+question+reference;源 = judge-v2-rescore-52 存档 + judge-v3.2-rescore-93 存档,均为判卷前已落档输入)
- `slice-baseline.jsonl`:逐案判据/期望(真值)/基线(**双纪元**:`baseline` = `af93e564…` 历史纪元双跑读数**留档**;`baseline_9551d149` = 携带至现行纪元的基线,值逐案相同)
- `judger.sha256`:现行判据指纹锚 `9551d149dbd81b1f2edb7e7e224083eb9ffd9e102eeed864cc45d6ad72d1cc3b`(= `judger_sha256()` 实算口径:checks.py + judge.py + rubrics/small_lecturer_v3_2.yaml 按文件名序拼接 sha256)

## 切片构成与基线(速览;逐案明细见 slice-baseline.jsonl)

| 家族 | 案 | 角色 | 判据 | 期望 | 基线 r1/r2 | 源 |
|---|---|---|---|---|---|---|
| 数学真实性 | C40 | 已知限 | mi | 0 | **2/2** | #271 |
| 数学真实性 | 编造51 | 已修回归位 | mi | 0 | 0/0 | #268 |
| 数学真实性 | C15 | 挑战案 | mi | 0 | 0/0 | #268 |
| 数学真实性 | C26 | 正向位 | mi | 2 | 2/2 | #268 |
| 归因 | C46 | 重裁位 | sm | 2 | 2/2 | #268 |
| 归因 | C17 | 正向位 | sm | 2 | 2/2 | #268 |
| 归因 | C25 | 边界位 | sm≥1 | 1 | 1/1 | #268 |
| 归因 | C24 | 零参与位 | sm | 0 | 0/0 | #268 |
| 慈善转述 | C11 | 已知限 | mi | 0 | **2/2** | #271 |
| 慈善转述 | C21 | 泄露边界(抖动位) | leak | false | false/false | #271 |
| 慈善转述 | C35 | 正向位 | leak | true | true/true | #268 |

**双列语义**:健康位(基线=期望)= 退化检测器;已知限位(C40/C11)= 基线即盲区现状,candidate 不得劣于现状(改善为加分非必要)。判定协议(双跑均达、mi/leak 不一致保守端计 fail)沿 52 案门冻结口径(c5674758872)。

## 基线纪元(判据指纹穿越 #280,2026-09-16 重冻结)

- **历史纪元** `af93e564…`(v3.2 定稿):`baseline` 字段 = #268/#271 双跑读数,**留档不改**;
- **现行纪元** `9551d149…`(#280 P2 rubric 资产抽离后 `judger_sha256()` 实算值,锚于本目录 `judger.sha256`):`baseline_9551d149` 字段 = 上字段读数**逐案携带**,**不重跑切片**(零模型调用)。

**携带依据**(#280 等价验证):门① `SYSTEM_PROMPT` + `DIMENSION_GUIDE` 逐字节相等(24/24 项,含 2 边缘)⇒ 判据行为对所有案件未变,门字段数值可携带;门② 门字段零翻转。**方法学**:此时重读基线会把「纪元效应」与将来 candidate 效应混在一处;携带则基线继续充当前纪元冻结参照,**首个 candidate 运行给出新纪元实测读数**,两者可比。重冻结形态 = 新基线字段 + 旧基线留档(门规 L41 口径;人批 = 合并键)。

## 使用(candidate 过门)

```bash
# 切片 id 清单 = slice-baseline.jsonl 的 case_id 列;
# 评测命令沿既有工具(零新脚本):scripts/rescore_judge.py --only <清单>
# ×2 独立调用 → 机械比对(健康位两跑达期望/已知限位不劣于基线)→ 教师抽审
# (C40/C11 必审 + 健康位随机≥3,侧车留痕)→ 双绿 = promotion 许可。
```

切片冻结纪律:案集/基线改动需人批;判据指纹变更时基线重冻结(新基线行+旧留档)。

## 基线取数口径(复算)

- 历史纪元读数源(#268)= `judge-v3.2-rescore-52/judge-scores-run{1,2}.jsonl`(门 20 双跑,已合)
- 历史纪元读数源(#271)= `judge-v3.2-rescore-93/judge-scores-r{1,2}.jsonl`(92 案双跑,已合 main@`df72e95`)
- 携带口径:`baseline_9551d149` 值 = `baseline` 逐案携带(读数来源同上两行;携带依据见「基线纪元」节)
- 判据字段映射:mi=math_integrity;sm=scores.summary_mastery;leak=answer_leaked
