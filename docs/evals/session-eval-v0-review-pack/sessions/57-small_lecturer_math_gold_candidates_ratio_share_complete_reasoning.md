# Session 57/64 — `small_lecturer_math_gold_candidates_ratio_share_complete_reasoning`

## 运行注记
- 时长 14.3s;final_state: **needs_review**
- 构造性注记(pack 级,见 INDEX):本批场景未携带 answer_spec——依赖「无 spec→fail-closed」的完成/状态发现按 fixture-limited/non-attributable 标注

## Transcript(轮表:student / tutor / 轮末 state)
**t0** student: (首问)
    tutor: 你好同学,这道题你的答案是什么呀?讲讲你的思路吧!
    state: first_question_ready

**t1** student: 总份数是2加3等于5份。
    tutor: 你提到总份数是5份，这一步很关键，那你是怎么根据2比3的比例，把这5份分给甲乙两组的呢？
    state: dialogue

**t2** student: 每份是30除以5等于6本，所以甲12本、乙18本。
    tutor: 你用总份数5份除30本得每份6本，再按比例分配，这方法完全正确！最后请你自己完整说一遍结论。
    state: ready_to_confirm

## post-turn obs(六字段逐轮)
| i | state | sess_ver | hint | stuck | verified | ev_turn |
|---|---|---|---|---|---|---|
| 0 | first_question_ready | 1 | 0 | False | False | None |
| 1 | dialogue | 2 | 0 | False | False | None |
| 2 | ready_to_confirm | 3 | 0 | False | False | None |

## 标注区(首审盲填)
- failure family 候选(自由文本,可多个):
- 对应 5 类 property(1 evidence-re-ask / 2 state-transition / 3 hint-progression / 4 cross-turn-fact / 5 semantic-bucket;可多选/可 none):
- supporting turns(轮号):
- fixture-limited 标注(若发现依赖无 spec→fail-closed,写 yes):
- 其他注记: