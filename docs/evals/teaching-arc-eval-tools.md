# 教学弧线评测工具:进仓清单与数字复现命令

> 来源:2026-09-10 PM 马尾辫审查——#143 只合了 docs+artifacts,产出数字的工具活在 worktree 里,
> "同口径复测"在 main 上不可执行。本文登记五个工具的进仓(原样搬,含两处已申报的最小改动)
> 与**逐条复现命令**。口径语义一律以冻结文档为准(pre-registration),脚本不定义规则:
> 判定规则见 `docs/evals/teaching-arc-eval-v1.md` §4/§5/§6;夜评口径见 `scripts/tuning_round.py`。

## 0. 工具清单(scripts/,#143/#148 数字的生产者)

| 脚本 | 用途 | 产出数字/文件 |
|---|---|---|
| `arc_eval_collect.py` | #101 双臂收集(11 场景 × 2 重复 × 口径 P/F,按臂在被测工作树里跑) | `<out>/<口径>/<臂>/{cases.jsonl, collect/…/results/*.json}`、`manifest-<臂>.json` |
| `arc_eval_judge.py` | 四指标盲判(judge 单遍 temperature=0;口径目录自动发现,支持 P/F/R/L) | `<out>/<口径>/<臂>/judge-scores/*.json` |
| `arc_eval_metrics.py` | 四指标汇总 + 确定性代喂语料扫描(阈值算术本地重算) | `<out>/metrics.json`、`<out>/feeding-corpus.jsonl` |
| `arc_eval_report.py` | 报告生成(§0 自述四要素 + 四指标表 + 两路径对照表) | `<out>/report.md`、`<out>/two-path-comparison.md`、`--doc-out` 镜像 |
| `arc_eval_fix112_frames.py` | #112 before/after(含 post-#101 2×2)帧网格 | `<out>/<帧>/{F,R,L,P}/M/…`、`manifest-<帧>.json` |

进仓两处已申报的最小改动(评审可见,其余原样):

1. `arc_eval_report.py`:原版把报告镜像硬编码写到 `/root/code/edu-w8-arc-eval/…`(worktree 本地路径)——
   改为可选参数 `--doc-out <路径>`,缺省只写工件目录内 `report.md`;
2. `arc_eval_fix112_frames.py` docstring「评测分支工具,不进 PR」一句随之失效,改为如实描述。
   另:该脚本新增 `--base-sha`(默认 `origin/main`)——post-#101 帧的清单比对基准参数化,
   pre-#101 帧(`before`/`after`)基准仍是 `6b69a4e`,以各 `manifest-*.json` 记录为准。

## 1. 复现 #143(teaching-arc-v1,88 份 transcript 双臂双口径)

前置:两份被测工作树——臂 M = main、臂 A = `tune/teaching-arc`(两臂只差 `prompting.py` 两常量);
tunnel:judge=mlx_27b、tutor 按注册表(密钥经 `. /root/.config/edu-agent/env` 注入)。

```bash
# 在臂 M 的工作树(该工作树的 prompting.py 即被测对象,臂标签只进路径不进 prompt):
.venv/bin/python scripts/arc_eval_collect.py --arm M --out edu_agent/evals/artifacts/teaching-arc-v1
# 在臂 A 的工作树:
.venv/bin/python scripts/arc_eval_collect.py --arm A --out <同上共享目录>
# 判分/汇总/报告(任一工作树,只读工件):
.venv/bin/python scripts/arc_eval_judge.py  --out edu_agent/evals/artifacts/teaching-arc-v1
.venv/bin/python scripts/arc_eval_metrics.py --out edu_agent/evals/artifacts/teaching-arc-v1
.venv/bin/python scripts/arc_eval_report.py --out edu_agent/evals/artifacts/teaching-arc-v1 \
    --doc-out docs/evals/teaching-arc-eval-v1-report.md
```

产物位置:`P/{M,A}`、`F/{M,A}`(各 22 用例 × transcript/judge 分);`metrics.json`(四指标率);
`feeding-corpus.jsonl`(代喂语料);`report.md` + docs 镜像;`two-path-comparison.md`。
数字对账:`report.md` §2 表 ← `metrics.json`;§4 语料 ← `feeding-corpus.jsonl`;§3 逐字差异 ← transcripts。

## 2. 复现 #148(teaching-arc-fix112,四帧:内核 × prompt 层)

帧定义(内核/prompt 身份由 `manifest-<帧>.json` 的差异旗自证):

| 帧 | kernel | prompting | 基准(--base-sha) |
|---|---|---|---|
| `before` | main `6b69a4e` 逐字节同 | `6b69a4e`(pre-#101) | `6b69a4e` |
| `after` | `before` + #112 修复 | 同上 | `6b69a4e` |
| `before101` | 新 main `053133f` 逐字节同 | 新 main(#101 已合) | `origin/main` |
| `after101` | `before101` + #112 修复 | 同上 | `origin/main` |

```bash
# 在对应被测帧的工作树里(各帧一次;--calibers 按需,F,R,L,P = #143 F 重跑 + 复讲 + 复读 + gate 零回归):
.venv/bin/python scripts/arc_eval_fix112_frames.py --frame before     --calibers F,R,L,P --out edu_agent/evals/artifacts/teaching-arc-fix112
.venv/bin/python scripts/arc_eval_fix112_frames.py --frame after      --calibers F,R,L,P --out edu_agent/evals/artifacts/teaching-arc-fix112
.venv/bin/python scripts/arc_eval_fix112_frames.py --frame before101  --calibers F,R   --out edu_agent/evals/artifacts/teaching-arc-fix112
.venv/bin/python scripts/arc_eval_fix112_frames.py --frame after101   --calibers F,R   --out edu_agent/evals/artifacts/teaching-arc-fix112
# 逐帧判分与指标(判分器口径目录自动发现,<帧> 目录作 --out):
.venv/bin/python scripts/arc_eval_judge.py   --out edu_agent/evals/artifacts/teaching-arc-fix112/<帧>
.venv/bin/python scripts/arc_eval_metrics.py --out edu_agent/evals/artifacts/teaching-arc-fix112/<帧>
```

报告为 `docs/evals/teaching-arc-fix112-report.md`(人工撰写,数字全部注明工件来源);
逐帧指标在 `<帧>/metrics.json`,复讲/复读/零回归口径的读数方法见报告 §2/§3/§4。

## 3. 夜评 comparison.md:自述四行与离线重渲染

`tuning_round.py` 生成的 `comparison.md` 自 2026-09-10 起开头自述四要素(纯渲染,零新增埋点):

1. **口径名**:P(gate 冻结 wiring)+ hint 注入计数与场景清单(从本 run 的 `cases.jsonl` 读);
2. **剧本截断 N/M**:每场景 实发学生轮 / 剧本学生轮(`transcript.turns` − 1 vs `student_turns` 长度);
   `⚠` = `ready_to_confirm` 提前判停截断(如 word_problem 2/4);
3. **逐维均分**:复用 `edu_agent/evals/report.py::DIM_LABELS`(维度顺序 `judge.DIMENSIONS`,不新造维度表);
4. **护栏模式**:无答案(评测侧不传参考答案,读数 ≠ 生产读数)。

离线重渲染(Mac 纪律:优先用既有工件,不新跑批)——下载某夜 `nightly-eval-<run_id>` 工件后:

```bash
uv run python scripts/tuning_round.py --render-from <解包出的 run 目录>
# gate 段数字从 run 目录重算(cases.jsonl/collect/judge-scores.json);
# json_first_pass 段承接原 comparison.md 原文(facts 记录不在 run 目录,无法重算)。
```

验收基线:重渲染对既有字段逐字节不变(只加自述块)——已在 2026-09-10 夜评帧 34450995074 上验证
(diff 仅新增 22 行自述块,word_problem 两变体 2/4 ⚠,chicken_rabbit 两变体 3/4 ⚠)。

## 4. 边界(明确不做)

- 不改任何口径语义:P/F/R/L 协议、judge 判据、数据集、`baselines/` 一律不动;
- 四脚本**不合并不重写**;若未来要合并,先只加 `--protocol` 参数、保留原路径(2026-09-10 派发约定);
- `minimum_student_turns` 的语义处置留 M3(它现在无人读取);
- 门禁 `answer_status` 注入的对称性问题见 #152(只登记,不改口径)。
