# Session 38/64 — `small_lecturer_math_gold_candidates_fraction_addition_complete_reasoning`

## 运行注记
- 时长 12.6s;final_state: **needs_review**
- 构造性注记(pack 级,见 INDEX):本批场景未携带 answer_spec——依赖「无 spec→fail-closed」的完成/状态发现按 fixture-limited/non-attributable 标注

## Transcript(轮表:student / tutor / 轮末 state)
**t0** student: (首问)
    tutor: 你好同学,这道题你的答案是什么呀?讲讲你的思路吧!
    state: first_question_ready

**t1** student: 先把三分之一通分成六分之二。
    tutor: 你想到把三分之一变成六分之二，是基于什么想法呀？比如分母从□变成6，分子怎么变？
    state: dialogue

**t2** student: 六分之二加六分之一等于六分之三，也就是二分之一。
    tutor: 你算出六分之二加六分之一等于六分之三，没错！但为什么分母从□变成6时，分子要变成□呢？比如把一个苹果平均分成□份，每份是□/□，如果再平均分成□份，每份是□/6，那□/□等于多少个□/6？
    state: dialogue

## post-turn obs(六字段逐轮)
| i | state | sess_ver | hint | stuck | verified | ev_turn |
|---|---|---|---|---|---|---|
| 0 | first_question_ready | 1 | 0 | False | False | None |
| 1 | dialogue | 2 | 0 | False | False | None |
| 2 | dialogue | 3 | 0 | False | False | None |

## 标注区(首审盲填)
- failure family 候选(自由文本,可多个):
- 对应 5 类 property(1 evidence-re-ask / 2 state-transition / 3 hint-progression / 4 cross-turn-fact / 5 semantic-bucket;可多选/可 none):
- supporting turns(轮号):
- fixture-limited 标注(若发现依赖无 spec→fail-closed,写 yes):
- 其他注记: