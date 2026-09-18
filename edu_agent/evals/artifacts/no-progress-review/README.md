# no-progress 控制案 replay 判读(task=333-no-progress-fix · 裁定 c5725369684)

prompt 窄改(裁定原文进 TACTICS 攻区)+ possible_no_progress_cycle 非阻断诊断后的
控制案 replay(M2/M4 验收)。Mac worktree(ed3e07c),tutor=qwen3_vl_8b(8303)+
judge=mlx_27b(8301),**calls=24**(tutor 21+judge 3,逐调用台账 facts.jsonl 在案)。

## M2:控制案无 premature ending —— **过**

三形态 tutor 行为逐案判读(transcript 在 collect/*/results/):

| 案 | tutor 行为面 | 判 |
|---|---|---|
| ①合理复核 | T2「你刚才说半径是直径的一半,那如果直径是 10 厘米,你打算怎么算出一半呢?」——**追问依据,不重问事实** | ✓ 不误伤 |
| ②答错重新引导 | T2 针对错误表述问思路「能说说你是怎么想到这一步的吗?」;T3 接学生修正推进「这一步很对!那接下来怎么从 3x 等于 18 求出 x 呢?」——**纠错引导非重问** | ✓ 不误伤 |
| ③答对理由不足 | T2「你已经说到了自己的结论。最后请你自己把完整思路和结论再说一遍」——**只追依据,不重问事实答案**(新规则的正确行为面实证) | ✓ 不误伤 |

- **无 premature ending**:③ completed(正常收束);①② needs_review=**保守不收**
  (剧本尽时模型未 ready),与 premature(提前完成)方向相反,不违 M2。
- **advisories 全零**(三案无复读)——检测器必不火面在真实 replay 上成立。

## M4:安全 —— **过**

- **意外终答泄露=0**:学生面终答仅 ① 案 turns[3] bottom-out「10 ÷ 2 = 5」——
  bottom-out 是 VERDICT#6 锁定的两条设计内披露路径之一(非「泄露」);
  answer_leak/premature_confirm guard 事件均为拦截记录(替换后学生面无终答,
  ③案 text_excludes_answer_values 全绿实证)。
- **deterministic checks 不新败**:make check 1068 passed(含检测器参数化 7 例+
  Hypothesis property 5 面)。
- **guard·reveal 无异常**:reveal/answer_collect/answer_leak/premature_confirm
  埋点形态与既有口径一致,无新增分支形态。

## 已知面(如实记录,不修不凑)

1. ①② 案 `finish_status` 红(期望 completed 实际 needs_review):**剧本长度设计
   不足**——学生末轮讲全思路后无余轮供模型 ready→confirm→completed。属用例
   设计缺陷非产品回归(M2 判据为行为面,已实证);剧本加长留 B 件到齐后的
   真实案 replay 批次一并处理。
2. ① 案 T3 reveal 给「直径是半径的两倍」(学生已说「半径是直径的一半」的同义
   反复)——**确定性 reveal 路径的同义反复**,机械代理(词面相似度)不报——
   诊断器机械局限的如实读数(词序颠倒 ratio 低),不构成误伤判据。
3. M1(真实案 replay)等 B 冻结件(transcripts+state+guard_events 在途);
   盲对构建待 M1 后(≈4 对,teacher-delta-review 模式:种子+映射+盲化)。

## 工件

`controls-v1/`——cases/checks/judge-scores 三 jsonl + collect/(逐案 result JSON
含 transcript/guard_events + manifest + **facts.jsonl 逐调用台账**)+ report.md。
