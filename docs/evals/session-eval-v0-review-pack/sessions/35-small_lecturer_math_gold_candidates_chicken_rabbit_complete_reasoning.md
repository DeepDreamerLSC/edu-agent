# Session 35/64 — `small_lecturer_math_gold_candidates_chicken_rabbit_complete_reasoning`

## 运行注记
- 时长 14.4s;final_state: **needs_review**
- 构造性注记(pack 级,见 INDEX):本批场景未携带 answer_spec——依赖「无 spec→fail-closed」的完成/状态发现按 fixture-limited/non-attributable 标注

## Transcript(轮表:student / tutor / 轮末 state)
**t0** student: (首问)
    tutor: 你好同学,这道题你的答案是什么呀?讲讲你的思路吧!
    state: first_question_ready

**t1** student: 假设全是鸡会有16只脚，比实际少10只。
    tutor: 你刚才说假设全是鸡会有16只脚，比实际少10只——这一步很聪明，你是怎么想到用‘假设全是鸡’来算的？
    state: dialogue

**t2** student: 每换成一只兔多2只脚，所以有5只兔、3只鸡。
    tutor: 你刚才说每换成一只兔多2只脚，所以有5只兔、3只鸡——这一步推理很到位，能完整讲清怎么从差值推出兔的数量吗？
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