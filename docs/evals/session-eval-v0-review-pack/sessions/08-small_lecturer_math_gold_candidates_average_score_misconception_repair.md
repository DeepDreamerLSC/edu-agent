# Session 08/64 — `small_lecturer_math_gold_candidates_average_score_misconception_repair`

## 运行注记
- 时长 10.2s;final_state: **needs_review**
- 构造性注记(pack 级,见 INDEX):本批场景未携带 answer_spec——依赖「无 spec→fail-closed」的完成/状态发现按 fixture-limited/non-attributable 标注

## Transcript(轮表:student / tutor / 轮末 state)
**t0** student: (首问)
    tutor: 你好同学,这道题你的答案是什么呀?讲讲你的思路吧!
    state: first_question_ready

**t1** student: 用最高分减最低分，得到20分。
    tutor: 你提到用最高分减最低分得到20分，这一步你是怎么想到的？能说说你这样算的依据吗？
    state: dialogue

**t2** student: 平均数表示总量平均分成相同份数，要用总分除以次数。三次一共80加90加100等于270分，除以3，平均90分。
    tutor: 你刚才说总分270除以3等于90，这一步计算很准确，能再确认一下你为什么用加法求总分吗？
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