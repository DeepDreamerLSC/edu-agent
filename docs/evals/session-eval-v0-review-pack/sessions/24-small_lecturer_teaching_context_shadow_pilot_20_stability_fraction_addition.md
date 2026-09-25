# Session 24/64 — `small_lecturer_teaching_context_shadow_pilot_20_stability_fraction_addition`

## 运行注记
- 时长 13.5s;final_state: **needs_review**
- 构造性注记(pack 级,见 INDEX):本批场景未携带 answer_spec——依赖「无 spec→fail-closed」的完成/状态发现按 fixture-limited/non-attributable 标注

## Transcript(轮表:student / tutor / 轮末 state)
**t0** student: (首问)
    tutor: 你好同学,这道题你的答案是什么呀?讲讲你的思路吧!
    state: first_question_ready

**t1** student: 我能不能直接把分子和分母分别相加？
    tutor: 你刚才说想把分子和分母分别相加，能说说你是怎么想到这个办法的吗？比如，你有没有想过为什么分母不能直接加？
    state: dialogue

**t2** student: 直接算成十二分之四好像不对，因为每一份的大小不同。
    tutor: 你刚才说每一份的大小不同，这很关键！那如果想让它们变成相同大小的份，该怎么做呢？
    state: dialogue

**t3** student: 我把四分之三化成八分之六，再加八分之一。
    tutor: 你刚才说把四分之三化成八分之六，再加八分之一，这一步很聪明！因为这样两个分数就变成了相同分母，可以相加了，对吧？
    state: ready_to_confirm

**t4** student: 同分母后分子相加得到八分之七，分母仍然是8。
    tutor: 这一题的学习证据还不够,我们继续——你能说说目前想到的第一步吗?
    state: ready_to_confirm

## post-turn obs(六字段逐轮)
| i | state | sess_ver | hint | stuck | verified | ev_turn |
|---|---|---|---|---|---|---|
| 0 | first_question_ready | 1 | 0 | False | False | None |
| 1 | dialogue | 2 | 0 | False | False | None |
| 2 | dialogue | 3 | 0 | False | False | None |
| 3 | ready_to_confirm | 4 | 0 | False | False | None |
| 4 | ready_to_confirm | 5 | 0 | False | False | None |

## 标注区(首审盲填)
- failure family 候选(自由文本,可多个):
- 对应 5 类 property(1 evidence-re-ask / 2 state-transition / 3 hint-progression / 4 cross-turn-fact / 5 semantic-bucket;可多选/可 none):
- supporting turns(轮号):
- fixture-limited 标注(若发现依赖无 spec→fail-closed,写 yes):
- 其他注记: