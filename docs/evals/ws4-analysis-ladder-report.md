# WS4 第 4 条 · 提示阶梯 #107 方案 A(题库解析 → 确定性阶梯)评测报告

> 依据:#165 WS4 第 4 条(「#146 的 M3 项:提示阶梯 #107(ITS 标配:脚手架渐隐)」)+
> **#107 方案 A**(「analysis 按分隔词切成步骤 → 每题一张阶梯(纯函数)」)。
> 基线:`4232fda`(post-#164 main)。工件:`edu_agent/evals/artifacts/ws4-analysis-ladder/`。

## 0. 现状与缺口(侦察)

| #107 方案 A 的要素 | 现状 |
|---|---|
| 阶梯来源 | **只有**模型 `start()` 当场生成的分步解(`_store_steps` 校验后入 `session.steps`) |
| 题库解析(`analysis`) | 只进**教师侧 prompt**(`_user_prompt`/`_masked_question`),**不参与阶梯** |
| 卡住 → 揭示下一级 | 已有(`_reveal_stuck_hint` + `hint_level` + bottom-out) |
| 「不现场生成数值」 | 未达成:阶梯里的 value 就是模型当场生成的中间值 |

#107 背景实测的致损正是这一环:tutor 现场生成中间值会幻觉(「脚总数就是8」实为 16)。
方案 A 的意图 = 题库带解析时,**既定分步**成为阶梯,模型只做「选择并复述」。

## 1. 改动(纯函数 + 一处优先序)

- `_analysis_steps(analysis)`:确定性切片(句末标点 + 序列词 先/再/然后/接着/最后/其次);
  每片取**该步结果**(有等号取末个等号右侧数字,否则取末个数字),无数字片与 ≤3 字片丢弃;
  **切不出 ≥2 片返回空**;
- `_step_value(fragment)`:上条的结果抽取(纯函数);
- `start()`:模型 OPEN 之后,**解析切片存在时优先于模型分步解**(`session.steps = ladder`);
  不存在/切不出 → 保持模型分步解(**零回归**)。

## 2. 证据

### 2.1 生产形探针(真模型,题库带解析)

| 来源 | 阶梯 |
|---|---|
| 模型 OPEN 当场生成 | `假设8只全是鸡…→16`、`算实际脚数…→10`、`每换一只…→2`、`多出的脚数…→5`、`鸡有多少只→3` |
| **本 PR 采用(解析切片)** | `先假设8只全是鸡,算出脚的总数8×2=16→16`、`再算实际脚数比假设多26-16=10只→10`、`然后每把一只鸡换成兔,脚数多4-2=2只→2`、`最后多出的脚数能换10÷2=5只兔,鸡有8-5=3只→3` |

- 阶梯文本 = **题库既定解析**(不再是模型当场措辞);
- `_known_answer`(阶梯末级兜底)= `'3'` —— 干净结论数字
  (对比:评测侧 common case 的模型末级常是**算式**「8 - 5 = 3」,曾是 #152 判停闸误触发的根因之一);
- 阶梯构建**零模型调用**(纯函数);模型调用次数不变(仅 OPEN 一次)。

### 2.2 专测(+3,全部公开路径)

1. 带解析 → 阶梯 = 解析切片,且**不含**模型自拟步骤,末级 value = 解析结论;
2. 无解析 / 解析切不出 ≥2 步(纯叙述无数字)→ **保持模型分步解**(零回归);
3. 复读兜底揭示的下一级 = **解析切片的第一级**(证明阶梯真的接上揭示路径)。

### 2.3 P 口径 gate 零回归

| 帧 | 配置 | 结果 |
|---|---|---|
| P-before | main `4232fda` | 11/11 达标或不劣,均值差 +4.41(工件见 PR #168 `ws4-guard-granularity/before`) |
| P-after | 本 PR | **11/11 达标或不劣,均值差 +4.41;逐场景分数逐项相同** |

**为什么评测面零触达**(可复核):评测用例(`tuning_round.build_cases` / 弧线帧)的
`question` 只有 `text`(+ 评测侧不传 `analysis`),`_analysis_steps("")` 返回空 →
优先序不生效。**生产面**(题源适配器填 `analysis`)才生效。

## 3. 复现命令

```bash
# 生产形探针(真模型,带解析的题):
PYTHONPATH=. <venv>/python /tmp/ws4_ladder_probe.py <树根>
# P 口径(gate 零回归):
.venv/bin/python scripts/tuning_round.py --out <工件根>/P-after
# 单测:解析切片优先 / 无解析零回归 / 切片接上揭示路径
.venv/bin/python -m pytest tests/teaching/test_kernel_state_machine.py -q
```

## 4. 边界与未做(留给后续片)

- **未做 #107 的「脚手架渐隐」**:渐隐需要一个「掌握度信号」(学生完成刚揭示的那一步 → 降支持),
  而**现有仪器没有这个形状**——L 口径是「同一句重复 8 轮」(学生永不推进,阶梯每轮升一级),
  P/F 口径不产生卡壳揭示。要做渐隐,先要加一个「卡住 → 得到提示 → 完成该步 → 再卡住」的探针口径
  (属**测量条件变更**,按 #165 纪律 1 需条件对照帧 + 断点标注,故未在本单擅自加);
- **未做** #107 的提示词改写(「教师侧解析已按步骤列出…不要自己编数值」):同属生产面改动,
  评测面零触达,建议与渐隐同批做并配生产形对照;
- **未做** 方案 B(generate-once-then-reveal + 自校验,面向无答案/纯图场景);
- 不动判据/基线/数据集;不动 `docs/plan/*`。

## 附:生产形探针(脚本原文,便于复算;注:`# noqa` 不落仓文件——预算按注释抑制计数,02 §11.3)

```python
# 用法:cd <含本次改动的树> && PYTHONPATH=. <venv>/python <此脚本>
import sys
from pathlib import Path

REPO = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
sys.path.insert(0, str(REPO))

import edu_agent.agents.small_lecturer.kernel as kernel  # noqa: E402
from edu_agent.agents.small_lecturer import start  # noqa: E402
from edu_agent.gateway import Gateway, load_registry  # noqa: E402

ANALYSIS = ("先假设8只全是鸡,算出脚的总数8×2=16。再算实际脚数比假设多26-16=10只。"
            "然后每把一只鸡换成兔,脚数多4-2=2只。最后多出的脚数能换10÷2=5只兔,鸡有8-5=3只。")
QUESTION = {"text": "鸡和兔一共8只,共有26只脚。鸡和兔各有多少只?", "answer": "",
            "analysis": ANALYSIS, "knowledge_points": ["鸡兔同笼"]}
model_steps: list[dict] = []
_orig = kernel._store_steps


def _record(session, steps):          # 记录模型 OPEN 当场生成的分步解(对照用)
    model_steps.clear(); model_steps.extend(steps or [])
    return _orig(session, steps)


kernel._store_steps = _record
registry = load_registry(REPO / "configs" / "models.yaml")
gateway = Gateway(registry, facts_dir=Path("/tmp/ws4_ladder_facts"))
try:
    turn = start(dict(QUESTION), {"grade": "六年级", "answer_status": "incorrect"}, gateway=gateway)
finally:
    gateway.close()
for s in model_steps:
    print("模型自拟:", s.get("step"), "→", s.get("value"))
for s in turn.session.steps:
    print("本 PR 阶梯:", s["step"], "→", s["value"])
print("_known_answer =", kernel._known_answer(turn.session))
```
