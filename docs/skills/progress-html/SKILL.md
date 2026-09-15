---
name: progress-html
description: >
  里程碑进展全景 HTML 图的更新与重出（线框图风格）。单文件自包含、无外部
  依赖、五色状态语义、事实前置核验。Trigger: 「更新进展图」「重出进展图」
  「进展图」「画 M4/里程碑 图」「progress html」, 或用户要求按既定风格刷新
  进展图工件时。
---

# 里程碑进展图(progress-html)

更新或重出里程碑进展 HTML。**先核事实、后动文件**;风格与结构由
同目录 `template.html` 钉死。

## 复用方式

- **装入 harness skill 目录**:`cp -r docs/skills/progress-html ~/.dsh/skills/`
  (session 目录即生效;本文件即 DSH skill 格式,frontmatter 兼容);
- **直接遵循**:任何 agent 读本文件即可按规范执行,不依赖 skill 机制;
- **工件落盘位置**:私有工件目录(如 `calibration-private/`)或评审包目录,
  **不进本仓库**——图内含 issue/PR 号与进行中状态,且可能嵌未脱敏内容;
  文件名约定 `<里程碑>进展图.html`。

## 流程(每次必走)

### 1. 事实核验前置(更新前必做;跳过 = 禁止动文件)

图上每个状态点(✓⏳🔑⏸○)都要有出处。更新前用 gh 核:

```bash
gh pr list --state open --json number,title,headRefName
gh pr list --state merged --limit 8 --json number,title,mergedAt
gh pr view <N> --json state,mergeable,statusCheckRollup   # 在途 PR 的 CI
gh issue view <N> --json state,title                      # 关键 issue
```

规则:
- **无出处不改状态**;核验结果与图不符 → 以 gh 为准更新;
- 数据截至日期(header .sub 里)同步刷新;
- footer 溯源号(issue/PR/评论号)随事实走。

### 2. 结构(自上而下,区块顺序固定)

1. **header**:标题(里程碑+锚点一句话)/ sub(出口判据+数据截至)/
   `.pos` 当前位置 pill(一句话,指明焦点与下一步);
2. **legend 五色**(全局唯一状态语义):
   ✓ 完成 `#16a34a` · ⏳ 在途(已派单/在跑) `#2563eb` ·
   🔑 等用户的键 `#d97706` · ⏸ 阻塞 `#dc2626` · ○ 未开始 `#9ca3af`;
3. **总览 = 全景线框**(核心区块):
   - 主干道 `.wf-spine`:阶段 stage 卡,箭头相连,终点 = 出口黑块
     (`.stage.exit`,判据 mini 进度条);
   - 并行泳道 `.wf-parallel`:grid 排布的 stage 卡;
   - 每个 stage = 标题 + 完成% + 进度条 + 计数行(`3✓+1⏳(PR审查中)`)
     + items(状态点 + 事项 + 溯源号 `<small>#xxx</small>`);
   - **「▸现在」标记(`.now`)全图只钉一处** = 当前焦点/阻塞点;
4. 详表区:判据关键路径 `.flow`(step 芯片+箭头)/ 对比表(table)/
   旁线卡 `.mini` / 钥匙清单(`ol` + `.kbd` 序号键);
5. **footer**:溯源(issue 号 · PR 号 · PM id · 数据截至)。

CSS tokens、类名、配色全部照抄 template.html,不改样式只改内容。

### 3. 完成度规则(防伪装成测量值)

- **状态点 = 硬事实**(有 issue/PR 出处);
- **百分比 = 判断值**,不是测量值——交付时必须口头声明一句
  (「各阶段 % 是判断值,定性看状态点更准」),图内不伪装;
- 计数行与 items 状态点必须自洽(数得出来)。

### 4. 更新 vs 重出

- **更新**(默认):核验后**只改事实变化处**,用户默认要求「其他地方不变」;
  小改用 edit 定点,多处联动或结构变化用 write 全量重写(先 read 原文件);
- **重出**(新里程碑):复制 template.html → 重建全部区块 → 同一风格。

### 5. 交付

1. write/edit 落盘;
2. 向用户呈现该文件(提及路径不替代呈现);
3. 交付语三件:改了什么(事实变化清单)/ 一句诚话(% 为判断值)/
   下一步(当前钥匙是什么)。

## 禁止

- 外部依赖:无 CDN、无 JS 库、无字体请求——纯静态单文件,离线可开;
- 无出处的状态(暗数据)、无「▸现在」定位或钉多处;
- 把 %、进度条写成「测量值/客观得分」;
- 借更新之机改样式/配色/布局(风格已冻结,只有内容动);
- 工件本身进本仓库。
