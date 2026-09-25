# Session 28/64 — `small_lecturer_teaching_context_shadow_pilot_20_stability_speed`

## 运行注记
- 时长 13.7s;final_state: **needs_review**
- 构造性注记(pack 级,见 INDEX):本批场景未携带 answer_spec——依赖「无 spec→fail-closed」的完成/状态发现按 fixture-limited/non-attributable 标注

## Transcript(轮表:student / tutor / 轮末 state)
**t0** student: (首问)
    tutor: 你好同学,这道题你的答案是什么呀?讲讲你的思路吧!
    state: first_question_ready

**t1** student: 我不确定该用乘法还是除法。
    tutor: 你提到不确定用乘法还是除法，能说说你是怎么想到要选其中一个的吗？比如，如果题目问的是总路程，你会怎么算？
    state: dialogue

**t2** student: 题目是把180千米平均分到3小时里。
    tutor: 你说到‘平均分’，这很对！那如果把180千米平均分成3份，每份是多少？你猜猜这个‘每份’在题目里代表什么？
    state: dialogue

**t3** student: 所以用路程除以时间，180除以3。
    tutor: 你说到‘平均分’，这很对！用180除以3，就是把总路程平均分到每小时，这个思路完全正确，最后请你自己完整说一遍结论。
    state: ready_to_confirm

**t4** student: 结果是60，平均速度是每小时60千米。
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