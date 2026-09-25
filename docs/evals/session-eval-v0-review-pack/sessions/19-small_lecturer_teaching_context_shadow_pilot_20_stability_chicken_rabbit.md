# Session 19/64 — `small_lecturer_teaching_context_shadow_pilot_20_stability_chicken_rabbit`

## 运行注记
- 时长 23.3s;final_state: **needs_review**
- 构造性注记(pack 级,见 INDEX):本批场景未携带 answer_spec——依赖「无 spec→fail-closed」的完成/状态发现按 fixture-limited/non-attributable 标注

## Transcript(轮表:student / tutor / 轮末 state)
**t0** student: (首问)
    tutor: 你好同学,这道题你的答案是什么呀?讲讲你的思路吧!
    state: first_question_ready

**t1** student: 我还不知道怎么同时算两种动物。
    tutor: 你说到‘还不知道怎么同时算两种动物’，这说明你正在想怎么把鸡和兔的脚数联系起来。你能说说，你看到‘8只动物’和‘26只脚’这两个数字时，第一反应是想到什么办法呢？
    state: dialogue

**t2** student: 可以先假设8只全是鸡，这样有16只脚。
    tutor: 你想到假设8只全是鸡，有16只脚，这个想法很棒！那现在脚数差了26 - 16 = 10只，每只兔子比鸡多2只脚，这10只脚差能换几只兔子呢？
    state: dialogue

**t3** student: 实际比16只多10只，每把一只鸡换成兔会多2只脚。
    tutor: 你刚才说‘每把一只鸡换成兔会多2只脚’，这说明你已经知道替换的规律了！那10只脚差能换几只兔子呢？
    state: dialogue

**t4** student: 所以兔有10除以2等于5只，鸡有3只，检查5乘4加3乘2等于26。
    tutor: 你刚才说兔有5只、鸡有3只，还验证了5×4+3×2=26，这说明你已经完整地用替换法解出了这道题！
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