# 步骤7 confirmation 预注册 v1(B-new 独立确认)

状态:草案待审(2026-09-22,PM 拟;呈用户+架构师过目后冻结)。**跑前冻结跑后不改。**
依据:六条裁令之⑤(#382)+post-ablation-ruling;上承 r3 FAIL 封存(不拼统计)。

## 一、主假设(一个问题)

> **B-new 在从未看过的新案例上,能否减少「学生已显式给出题目所求结论后,教师仍重问/盘旋」,同时不增加「学生尚未显式给出结论时教师提前收束」?**

## 二、臂与身份(冻结项)

| 项 | 值 |
|---|---|
| baseline 臂 | main@6719637e 现行 prompt 原样(prompting.py sha256 待冻结时记录) |
| candidate 臂 | baseline + **B-new 单行**(sha16=044e630e96d8e658,`step7-bnew-prompt-frozen-v1.md`,不改字) |
| tutor 模型 | qwen3_vl_8b @ 8303(生产同款,SSH 隧道) |
| judge | **ER judge v2**(#411 已合,判分器+gold labels 随 PR 入仓;sha 于冻结时记录) |
| 跑面工程 | run_ab 同码双臂(r3 模式:只读注入/装配同码/manifest 指纹) |
| 统计 | discordant counts(baseline-only/B-new-only/ties)+ exact paired test + effect size;**绝不与 r3 合并 p** |

## 三、样本集(新案源,运行前冻结)

**编译纪律**:选择条件只看源题面与学生话语,**不看任何臂输出**;#398 编译制度沿用(真实学生文本/强依赖分支化/禁改写);数量与 SHA 跑前冻结入本文件。

**三个 slice**:

1. **正向 slice(主战场)**:学生已**显式给出题目所求的最终结论**(含关键数值/选项字母/文字终答)——测 unnecessary re-ask 与 closure;
   - 规模:**12-16 案**;源:SocraticMATH normalized 余量(筛选时排除 r3 已用 23 案)+ 自产新形态(若有);
2. **负向边界 slice(防 premature)**:学生只给方法/原则/部分关系/高度暗示,**尚未落到题目所求终答**——专门测 B-new 会不会提前收束(val_13 型防线);
   - 规模:**8-12 案**;源:同上,编译时逐案注明"学生止步于哪一步";
3. **866 型补充**:题目实质已满足但教师可能为"全面性"无限延伸的形态;
   - 规模:**3-5 案**;
   
合计 **~25-30 案**×双臂(预算 ~300-400 本地 calls,不耗云端;judge 侧 v2 为词面+结构判定,零模型)。

## 四、判读门(裁令⑥,贴机制四门)

| 门 | 口径 | 判定 |
|---|---|---|
| **正向门** | 显式终答后 unnecessary re-ask / false continuation 相对 baseline 下降(exact paired,报 discordant counts) | 主判据:下降方向成立(p<0.05) |
| **反向硬门** | 负向 slice 上 premature completion **不增加**;val_13 型(学生未落终答而 completed)目标 **保持 0** | 硬线:任何一例新增即 FAIL |
| **closure 质量门** | 新增 completed 须为「学生证据充分的合理收束」(人审抽验,不只看 final_state) | 全绿后仍须人审确认 |
| **不劣化面** | grounding/no-progress(分族)/safety(answer_leak/stuck)/语气 | 硬线:不劣化;语气面顺带盲审(delta 对) |

**判读规则**:四门全绿 → B-new 冻结为 production-form candidate → 恢复 Candidate→C1 状态链;任一 FAIL → 新 failure 分诊(不补词,不自动追分);A-only 重开条件(866 型失败面)同时在案。

## 五、INFRA 口径

环境失败单独记 ENV 不算质量失败;按预注册 infra retry 口径重跑对应单元;不因内容评分不佳 rerun。

## 六、冻结清单(点火时填)

- [ ] baseline SHA(main 头)与 prompting.py sha256
- [ ] B-new 行 sha16=044e630e(已冻结)
- [ ] ER judge v2 判分器 sha + gold labels sha
- [ ] 三个 slice 的案源清单+dataset sha256(编译毕即冻)
- [ ] tutor 端点与 manifest 口径
- [ ] 统计脚本版本(unified 判分链+v2)

## 七、执行序(点火后)

编译(零模型,子代理)→ 冻结清单填毕 → 双臂跑(~1h)→ v2 判分 → 四门判读 → (全绿)人审 closure 质量+语气 delta → 呈报。
