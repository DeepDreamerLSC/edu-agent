# Session 31/64 — `small_lecturer_teaching_context_shadow_pilot_20_stability_rectangle_perimeter`

## 运行注记
- 时长 18.7s;final_state: **needs_review**
- 构造性注记(pack 级,见 INDEX):本批场景未携带 answer_spec——依赖「无 spec→fail-closed」的完成/状态发现按 fixture-limited/non-attributable 标注

## Transcript(轮表:student / tutor / 轮末 state)
**t0** student: (首问)
    tutor: 你好同学,这道题你的答案是什么呀?讲讲你的思路吧!
    state: first_question_ready

**t1** student: 我把8乘5算成40厘米。
    tutor: 你刚才说把8乘5算成40厘米，能说说你是怎么想到这一步的吗？比如，你是不是觉得长方形的周长就是长乘宽？
    state: dialogue

**t2** student: 40算的是面积，不是周长。
    tutor: 你刚才说40算的是面积，不是周长，这说明你已经知道长乘宽是求面积的，那周长呢？周长是围绕长方形一圈的长度，你猜猜怎么算？
    state: dialogue

**t3** student: 周长要把四条边加起来，也就是8加5加8加5。
    tutor: 你刚才说周长要把四条边加起来，也就是8加5加8加5，这一步很对！那接下来，你打算怎么算这四个数的和呢？
    state: dialogue

**t4** student: 可以写成括号8加5括号乘2，结果是26厘米。
    tutor: 你刚才说可以写成括号8加5括号乘2，结果是26厘米，这方法很聪明，把重复加法变成乘法，算得又快又准！
    state: ready_to_confirm

## post-turn obs(六字段逐轮)
| i | state | sess_ver | hint | stuck | verified | ev_turn |
|---|---|---|---|---|---|---|
| 0 | first_question_ready | 1 | 0 | False | False | None |
| 1 | dialogue | 2 | 0 | False | False | None |
| 2 | dialogue | 3 | 0 | False | False | None |
| 3 | dialogue | 4 | 0 | False | False | None |
| 4 | ready_to_confirm | 5 | 0 | False | False | None |

## 标注区(首审盲填)
- failure family 候选(自由文本,可多个):
- 对应 5 类 property(1 evidence-re-ask / 2 state-transition / 3 hint-progression / 4 cross-turn-fact / 5 semantic-bucket;可多选/可 none):
- supporting turns(轮号):
- fixture-limited 标注(若发现依赖无 spec→fail-closed,写 yes):
- 其他注记: