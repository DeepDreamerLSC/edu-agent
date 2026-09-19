# 靶①材料留档:judge①案(合理复核圆半径)bottom-out 重复句样本

来源:靶② candidate 重放(#366);judge 4→1 疑降的直接证据;单案样本。
案:no-progress-control-reasonable-review;final=needs_review;judge=1(baseline 4)。

## bottom-out 句(连轮同句,模型轮被拦后护栏兜底文本)

1. 「这一步我们直接看结果:10 ÷ 2 = 5。你先记住它,我们回头再讲一遍为什么。」
2. 「这一步我们直接看结果:10 ÷ 2 = 5。你先记住它,我们回头再讲一遍为什么。」

## guard 埋点(该案模型路径,18 条)


## 归因(靶②判读 README 已记,此处靶①视角)

模型轮连续携带终答值 5(10÷2=5=answer)→answer_leak 拦截→兜底替换句
「这一步我们直接看结果:10 ÷ 2 = 5。你先记住它,我们回头再讲一遍为什么。」
**连轮同句**——护栏替换句族无轮换,梯烧尽后重复率 100%。
**靶①(收束模板×护栏接缝)的问题域**:替换句模板多样性/收束路径轮换,
需架构师通道(kernel 层);本档作靶①材料用。
- `{"branch": "model", "cited": [5.0, 10.0], "extracted": [5.0, 12.0], "violation_sources": [{"number": 5.0, "source": "answer"}, {"number": 12.0, "source": "hallucinated"}]`
- `{"branch": "model", "cited": [5.0, 10.0], "extracted": [], "violation_sources": [], "gate": "observed", "turn": 1}`
- `{"guard": "answer_leak", "rule_ids": ["source_value_disclosure:answer", "source_value_disclosure:hallucinated"], "original": "你用‘半径是直径的一半’这个关系算出了5厘米，这一步很到位！那如果直径换成12厘米，半径`
- `{"guard": "premature_confirm", "rule_ids": [], "original": "你用‘半径是直径的一半’这个关系算出了5厘米，这一步很到位！那如果直径换成12厘米，半径会是多少呢？", "regenerated": false, "turn": 1}`
- `{"branch": "model", "cited": [5.0, 10.0], "extracted": [2.0, 10.0], "violation_sources": [{"number": 2.0, "source": "answer"}], "gate": "blocked", "turn": 1}`
- `{"branch": "reveal", "hint_level": 1, "soften": "cut", "turn": 1}`
- `{"branch": "model", "cited": [5.0, 10.0], "extracted": [2.0, 10.0], "violation_sources": [{"number": 2.0, "source": "answer"}], "gate": "blocked", "turn": 2}`
- `{"branch": "model", "cited": [5.0, 10.0], "extracted": [2.0, 10.0], "violation_sources": [{"number": 2.0, "source": "answer"}], "gate": "blocked", "turn": 2}`
- `{"guard": "answer_leak", "rule_ids": ["source_value_disclosure:answer"], "original": "你讲得真好，用圆的半径定义说明了为什么10除以2就是半径，这一步很扎实！那我们最后再确认一下，半径到底是多少厘米？", "regenerated": false, "t`
- `{"guard": "premature_confirm", "rule_ids": [], "original": "你讲得真好，用圆的半径定义说明了为什么10除以2就是半径，这一步很扎实！那我们最后再确认一下，半径到底是多少厘米？", "regenerated": false, "turn": 2}`
- `{"branch": "model", "cited": [5.0, 10.0], "extracted": [2.0, 10.0], "violation_sources": [{"number": 2.0, "source": "answer"}], "gate": "blocked", "turn": 2}`
- `{"branch": "reveal", "hint_level": 1, "turn": 2}`
- `{"branch": "model", "cited": [2.0, 5.0, 10.0], "extracted": [2.0, 5.0, 10.0], "violation_sources": [{"number": 2.0, "source": "answer"}, {"number": 5.0, "source": "answer`
- `{"branch": "model", "cited": [2.0, 5.0, 10.0], "extracted": [2.0, 10.0], "violation_sources": [{"number": 2.0, "source": "answer"}], "gate": "blocked", "turn": 3}`
- `{"guard": "answer_leak", "rule_ids": ["source_value_disclosure:answer"], "original": "你用直径除以2算出半径是5厘米，这个思路完全对！我们再确认一下：直径10厘米，除以2就是半径，对吗？", "regenerated": false, "turn": 3`
- `{"guard": "premature_confirm", "rule_ids": [], "original": "你用直径除以2算出半径是5厘米，这个思路完全对！我们再确认一下：直径10厘米，除以2就是半径，对吗？", "regenerated": false, "turn": 3}`
- `{"branch": "model", "cited": [2.0, 5.0, 10.0], "extracted": [2.0, 10.0], "violation_sources": [{"number": 2.0, "source": "answer"}], "gate": "blocked", "turn": 3}`
- `{"branch": "reveal", "hint_level": 1, "turn": 3}`