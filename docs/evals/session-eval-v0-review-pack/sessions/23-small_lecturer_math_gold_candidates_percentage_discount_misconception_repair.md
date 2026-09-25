# Session 23/64 — `small_lecturer_math_gold_candidates_percentage_discount_misconception_repair`

## 运行注记
- 时长 10.5s;final_state: **needs_review**
- 构造性注记(pack 级,见 INDEX):本批场景未携带 answer_spec——依赖「无 spec→fail-closed」的完成/状态发现按 fixture-limited/non-attributable 标注

## Transcript(轮表:student / tutor / 轮末 state)
**t0** student: (首问)
    tutor: 你好同学,这道题你的答案是什么呀?讲讲你的思路吧!
    state: first_question_ready

**t1** student: 八折就是减去8元，所以是192元。
    tutor: 你刚才说八折是减去8元，能说说你是怎么从‘八折’想到要减8元的吗？
    state: dialogue

**t2** student: 折扣表示百分比，不是直接减去折数对应的元数。八折是原价的百分之八十，200乘0.8，应该是160元。
    tutor: 你刚才说八折是原价的□%，用200乘0.8得到160元，这个思路完全对！那我们再确认一下，如果原价是□元，八折后是多少？
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