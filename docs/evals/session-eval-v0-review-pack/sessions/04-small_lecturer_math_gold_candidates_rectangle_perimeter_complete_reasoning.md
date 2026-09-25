# Session 04/64 — `small_lecturer_math_gold_candidates_rectangle_perimeter_complete_reasoning`

## 运行注记
- 时长 11.3s;final_state: **needs_review**
- 构造性注记(pack 级,见 INDEX):本批场景未携带 answer_spec——依赖「无 spec→fail-closed」的完成/状态发现按 fixture-limited/non-attributable 标注

## Transcript(轮表:student / tutor / 轮末 state)
**t0** student: (首问)
    tutor: 你好同学,这道题你的答案是什么呀?讲讲你的思路吧!
    state: first_question_ready

**t1** student: 周长是四条边的总长度，要用8加5再乘2。
    tutor: 你刚才说周长是四条边的总长度，那为什么要把8加5再乘2呢？这个乘2是怎么来的？
    state: dialogue

**t2** student: 8加5等于13，13乘2等于26厘米。
    tutor: 你算出13乘2等于26厘米，这一步是对的！那为什么周长要乘2呢？因为长方形有两条长边和两条宽边，所以8×2 + 5×2，或者(8+5)×2，都是在算两条边的总和。
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