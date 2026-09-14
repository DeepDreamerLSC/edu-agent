# math-gold-v1 工件口径边界(#242 审查 P2 登记)

本目录产物跑在 **b1 follow_up 触发词加宽前** 的语料口径上。加宽(#242,修首轮
13 条同机制 needs_review,归因见 #178 c5653783697)只改数据集
`small_lecturer_math_gold_candidates.json` 的 `when.assistant_contains_any`,
但 cases.jsonl 每行内嵌分支 `when` 子句 ⇒ 60/60 行全变,**加宽后的 main 无法
再离线复算本产物**。复算请检出加宽前 commit `41bfc49`(#240 合入点)。

两代口径的 cases.jsonl sha256(命令口径:`real_model_scenarios` + `build_cases`
重建后对整体字节做 sha256):

| 口径 | commit | sha256 |
|---|---|---|
| 本产物(加宽前) | `41bfc49` | `5280ccc136353e1f3813c6a0d0e1e00739118f85d7881f6290f1304c6f10ca1b` |
| 加宽后 | #242 合入起 | `a9dcd98ce901a24480be08bf1164050d39d26d31164d153c1979ee2ccffe3e28` |

配套边界:

- 本目录无 `judger.sha256`(判分器指纹自 b2 轮起落盘,#238 §5 首轮基线欠账);
  b2 轮 report 对照本基线时会自动注「基线无溯源」。
- 加宽改变了分支路由面(部分末轮从兜底句转投主分支),b2 轮对本基线的
  「维持绿/新增红」按此边界读。
