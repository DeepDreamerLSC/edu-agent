# Session 15/64 — `small_lecturer_teaching_context_shadow_pilot_20_stability_average`

## 运行注记
- 时长 14.4s;final_state: **needs_review**
- 构造性注记(pack 级,见 INDEX):本批场景未携带 answer_spec——依赖「无 spec→fail-closed」的完成/状态发现按 fixture-limited/non-attributable 标注

## Transcript(轮表:student / tutor / 轮末 state)
**t0** student: (首问)
    tutor: 你好同学,这道题你的答案是什么呀?讲讲你的思路吧!
    state: first_question_ready

**t1** student: 我能不能把最高分和最低分加起来除以2？
    tutor: 你想到用最高分和最低分加起来除以2，是想用一种更简单的方式吗？能说说你是怎么想到这个方法的吗？
    state: dialogue

**t2** student: 这样刚好是88，但我不确定是不是通用方法。
    tutor: 你发现最高分和最低分加起来除以2正好是88，这很巧！但平均分是所有分数的总和除以个数，你能说说为什么这个方法在这里刚好成立吗？
    state: dialogue

**t3** student: 平均数应该用三次总分除以次数，先算82加88加94等于264。
    tutor: 你已经知道平均分是总分除以次数，现在只要把264除以3，就能得到最终答案了，对吗？
    state: ready_to_confirm

**t4** student: 264除以3等于88，所以平均分是88分。
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