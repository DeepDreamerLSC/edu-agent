# elicit 触发对补跑 · 工件与判读(task=elicit-pair-topup,#293 教师盲审材料)

PM 直发(sha256=68e4bd0f86792e53);预注册 #293 评论 5713864212(v1)
+ 5713997440(更正 v2:臂 X 来源改 gepa-nets-main-02 epoch-2 正本)。

## 判读结论(预注册口径,跑后未改)

**有效对 = 0。**

- 预注册「有效对」判准:①elicit 埋点确实触发(该臂 guard_events 含
  `branch=elicit` 至少一轮);②两臂转录在 elicit 轮出现可观察差异
- 实测:**elicit 埋点 6/6 全 0**(两次跑 × chicken A/B + equation A,
  guard_events 的 branch 全为 `model`/无)→ 判准①不满足 → 两案均无效对
- chicken 对(双臂完整):两臂 5 轮 tutor 文本**逐字全同**,judge 同分
  (7/review)——「两臂相同→如实记录,那就是读数」(预注册原文)
- equation 对:仅 A 臂(30 calls 硬顶前置拦截 28+8>30,B 臂未产);
  A 臂 0 触发 + 学生信号与臂无关机理 → 同判无效对

## 执行错如实记录(两处,均自报)

1. **臂 X 引错源**(预注册 v1):引 gepa-longrun-01(epoch-1 旧最优),
   PM 点火前纠偏,更正 v2 落 #293——跑前修正,非跑后改口径
2. **改完脚本未重 scp**(第二次重跑仍错臂):本盒已改 ARM_X 为 epoch-2
   正本,但未同步 Mac worktree 即重跑——mapping.json note 旧文案
   (「X=长跑best」)为铁证;两次跑均为 epoch-1 错臂,各 28 calls,
   **共 56 calls 全作废,正确臂(epoch-2)从未跑过**

PM 裁定(采 b 拒 a):不为合规烧第三次 28 calls 换机理上可预知的空读数;
现有数据按机理采信入档。

## 机理三事实(PM 采信,判读承重)

1. **elicit 0/6 触发** → 模板(无论 X/Y 文本)从未注入对话
2. **两轮同臂重复逐字全同**(tutor 5/5 全同/judge 同分同 verdict)
   → 上游确定性实证
3. **学生信号与臂无关**:elicit 分支由学生 understanding 信号驱动,
   学生文本由数据集剧本固定 → 0 触发下臂 X 文本不参与对话 →
   正确臂重跑必然逐字相同(有效对=0 不变)——a 选项被判数字仪式的依据

## 成本台账

| 跑次 | 臂 X 实际文本 | calls | 状态 |
|---|---|---|---|
| 第 1 次 | epoch-1(错) | 28 | 作废(3 评测后硬顶前置 ABORT),档案 `aborted-run-1/` |
| 第 2 次 | epoch-1(错,未同步脚本) | 28 | 数据按 b 采信(0 触发机理下臂文本未参与),`out/` |
| 第 3 次(正确臂) | — | 0 | PM 裁定不跑(空读数) |

**合计 56 calls(tier=pro),全部错臂;正确臂 0。**

## 流程修正(PM 令,记档防复发)

> 下次任何配置纠偏后的重跑,起跑前必须从 Mac worktree **实际回显运行
> 配置(模板原文)** 进回执——空口确认不作数。

## 与 149 时代对照(给教师线/新单的案源线索)

149-ready-gate 时代(f9d80af 旧 kernel)20 案/54 轮 elicit 触发;当前
main(08f2fdcd)kernel + 本 2 案剧本 → 0 触发(复跑实证)。**但试跑
trial-run-01 的 2/15 轨迹变化案(案 0/1)证明 elicit 在当前内核+runner
下真的会触发**(模板文本进了对话才改轨迹)——那两案才是正确案源
(PM 已记,待用户裁新跑:两案×两臂×转录落盘,~30 calls)。

## 文件

- `run_pairs.py`:跑批脚本(本盒版本,ARM_X=epoch-2 正本——注意
  Mac 实跑的是旧版,见执行错 2)
- `out/`:第 2 次跑产物(chicken A/B + equation A + mapping + facts 28 行
  + run.log);mapping.json note 旧文案系错臂脚本残留,真实臂 X 对应
  见本文档执行错记录
- `aborted-run-1/`:第 1 次跑作废料(3 件 + facts 28 行 + log)

## 复现口径

Mac(linmacbook-pro)worktree@08f2fdcd,`PYTHONPATH=$PWD` + 原 checkout
.venv(3.12.13);`python edu_agent/evals/artifacts/teacher-delta-review/run_pairs.py`
(注意:重跑前先核对 worktree 内脚本 ARM_X 与预注册一致——流程修正条)。

---

# v3:全题图 4 对(用户裁 a,PM 派单 task=elicit-pair-topup-v3,sha256=5be473b98887dda3)

预注册 v3 #293 评论 5714357402(判读冻结);硬顶 240 本地 calls 全程。

## 判读:**4 对全部有效对**——教师盲审材料成立

每对(4 案 × 两臂):
- 判准①:两臂 elicit 埋点**同轮触发**(understanding_04/02 = 轮 3;answerhit_01/02 = 轮 2)
- 判准②:elicit 轮 tutor 文本 = **各自臂模板逐字注入**(A 臂=kernel 默认原文 / B 臂=nets-main-02 epoch-2 全角正本)——elicit 轮即两臂唯一差异轮
- 上游确定性:除 elicit 轮外两臂转录逐字全同(diff 轮=elicit 轮)
- 判分:04 对 X 优 1(6v5)/ answerhit_01 对 Y 优 1(4v5)/ 02 与 answerhit_02 平——judge 对末轮模板文本分差敏感度低(±1/0,方向不一致)
- 结构限制(如实):elicit 轮均为**末轮**(剧本 turns 用尽)——学生无后续复讲轮,双臂轨迹无 elicit 后分歧;材料的教学语义差异集中在复讲引导措辞本身

## 筛段读数(8 案单臂,35 calls)

- 触发 4/8:understanding_04/02(Tier1 实证复现)+ **answerhit_01/02(Tier3 意外触发——路径 B 运行时真实成立,静态数字半判偏低)**
- 未触发 4:understanding_01/03(**ready_to_confirm 提前终态**,「懂了/会了」轮未达 reply——试跑无感矛盾解开)+ answercollect_01/02(「算出来了」走 completion 追问,语义不触发复讲)
- 两条触发路径均实证:A=理解信号(understanding 案)/ B=答案命中(answerhit 案)

## 成本台账(v3)

| 段 | calls | 明细 |
|---|---|---|
| 筛段(8 案单臂) | 35 | tutor 29 + judge 8(v3-facts 前 35 行) |
| 配对段(4×2) | 32 | tutor 22 + judge 8 |
| **v3 合计** | **67** | ≤240 硬顶;零 API 零 editor 零远程 |

(v2 作废 28 行与 v3 67 行已从 Mac 混合 facts 分账:v3-facts.jsonl;时间序单调,切分安全。)

## 文件(v3)

- `screen_v3.py` / `pairs_v3.py`:两段脚本
- `out/screen/`:8 案筛段转录+guard+summary+log
- `out/pairs/`:4 案×2 臂(盲标 A/B)+ mapping.json(臂→盲标 seed=20260918)+ pairs-summary + log
- `out/v3-facts.jsonl`:v3 67 行台账

## 飞行前检查执行记录(流程修正合规)

- 筛段起跑前:Mac worktree 回显 ARM_DEFAULT 逐字 ✓(run.log 首行)
- 配对段起跑前:Mac worktree 回显两臂模板原文逐字 ✓(pairs run.log 前三行,X 全角正本/Y 默认原文)
- 每案落盘即验 guard_events(两段 log 逐案 elicit 计数)
