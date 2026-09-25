# Session 26/64 — `small_lecturer_math_gold_candidates_triangle_area_complete_reasoning`

## 运行注记
- 时长 13.3s;final_state: **needs_review**
- 构造性注记(pack 级,见 INDEX):本批场景未携带 answer_spec——依赖「无 spec→fail-closed」的完成/状态发现按 fixture-limited/non-attributable 标注

## Transcript(轮表:student / tutor / 轮末 state)
**t0** student: (首问)
    tutor: 你好同学,这道题你的答案是什么呀?讲讲你的思路吧!
    state: first_question_ready

**t1** student: 三角形面积等于底乘高再除以2。
    tutor: 你刚才说面积等于底乘高再除以2，那你是怎么想到要除以2的？比如，如果用两个这样的三角形拼成一个平行四边形，面积会怎么算？
    state: dialogue

**t2** student: 10乘6除以2等于30平方厘米。
    tutor: 你算出10乘6除以2等于30平方厘米，这个结果是对的，而且你解释了为什么除以2，真棒！那我们再想想，如果换一个底和高，比如底是□厘米、高是□厘米，面积会是多少？
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