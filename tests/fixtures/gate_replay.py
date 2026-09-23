"""Gate 回归重放驱动(Trusted Completion Gate C 段,#414 §六.1;02 §6
tests/fixtures:tests/evals 两文件共享的确定性基础设施,不计测试比分子)。

零模型零网络:内核三函数(start/reply/finish)经对象注入 FakeGateway 驱动,
tutor 输出按剧本出牌(确定性),学生消息照录 corpus replay_input。重放协议
镜像生产客户端动力学:

- **finish-at-ready**:tutor 置 ready_to_confirm 的轮,客户端随即发起 confirm
  (finish)——§二「verified 后同轮终局」的交互形态;被门拒(needs_review)
  则剧本继续(444a/2c85 实录:答过还得再答),剧本尽头再试一次 finish;
- **tutor ready 剧本**:锚定 corpus 编译期登记的终答轮(expected.gate_evidence
  的 student_turn_index——轨迹事实,非期望终态),负向案锚末轮(镜像原失败
  形态:无终答而判停/收束——门必须有机会拦);分支案逐路径枚举,末轮 ready;
- **answer_spec 注入**:gate_a_probe 登记的 ADVISORY 建议规格作为题库声明面
  注入 question(组装契约在 kernel._answer_spec,composite 即 fail-closed)。

测量的量:终态(completed/needs_review)、逐轮 evidence 轮位、门拒绝埋点数、
summary 文本。期望对账(pass/divergence)与归因登记在
tests/evals/test_gate_regression_replay.py——冻结期望面是测量仪器,本驱动
只产数不改期望。
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from edu_agent.agents.small_lecturer import finish, reply, start

from teachkit import FakeGateway

# 剧本 tutor 文案:相邻轮结构迥异(_is_repeat 阈 0.85,天干后缀单字之差仍判
# 复读→重生成→多耗 payload,实测踩过)、无 ASCII 数字(防泄露护栏掩码/
# PURE_BLOCK)、无方法词(防代喂)、无字母(防选择面干扰)。确定性、可复算。
_TUTOR_LINES = (
    "我们先把题目读一遍,你来说说已知条件。",
    "这一步你打算怎么入手?讲讲你的想法。",
    "嗯,我们再往下推进一小步看看。",
    "很好,接下来换你来算这一段。",
    "我们把刚才那句话理清楚,你来试试。",
    "再往下算算看,把过程说出来。",
    "离结果不远了,你说说接下来求什么。",
    "换个角度想想,这道题问的到底是什么?",
    "你的思路有道理,我们验证一下看看。",
    "最后一步了,你来收尾说结论。",
    "我们先停一停,回头看看题目给了什么。",
    "这一遍你自己完整讲讲,我听着。",
)


def _tutor_reply(index: int, trigger: str = "") -> str:
    """第 index 轮剧本 tutor 文案;trigger(分支路由锚)非空时前置——
    trigger 含题面数字(allowed 集)与字母(泄露护栏只查数字/短语,不查字母)。"""
    return f"{trigger}{_TUTOR_LINES[index % len(_TUTOR_LINES)]}"


@dataclass
class ReplayOutcome:
    """一案(或分支案一路径)的实测面。"""

    case_id: str
    final_state: str                      # completed | needs_review | failed
    evidence_turns: list[int] = field(default_factory=list)   # 1 起学生轮号
    gate_rejections: int = 0              # completion_gate_rejected 埋点数
    summary_text: str = ""
    path: str = ""                        # 分支案路径标签(线性案空)
    scripted_ready_turns: list[int] = field(default_factory=list)


def _payloads(count: int, ready_flags: set[int], triggers: list[str]) -> list[dict]:
    """gateway 剧本:open 一发 + 每模型轮一发(ready 按剧本)+ 末位总结安全网
    (answer_status=correct 且 32 案零 stuck 消息 → finish 恒走零调用模板,
    正常不消费;防队列错位才垫底)。"""
    payloads = [{"acceptable": True, "transcription": "", "steps": [],
                 "reply": "我们来看这道题。"}]
    for i in range(count):
        payloads.append({"reason": "引导", "reply": _tutor_reply(i, triggers[i]),
                         "ready_to_confirm": i in ready_flags, "cited_numbers": []})
    payloads.append({"summary": "你把这道题的关键思路讲清楚了,这一题完成。"})
    return payloads


def _drive(case_id: str, question: dict, messages: list[str],
           ready_flags: set[int], triggers: list[str] | None = None,
           learner: dict | None = None) -> ReplayOutcome:
    """finish-at-ready 协议驱动:evidence 逐轮记录;completed 即止(终态后
    剧本余轮按生产语义不可达——客户端 confirm 成功即会话结束)。learner 缺省
    为 32 案统一剧本(五年级/correct:finish 恒零调用模板,零 gateway 依赖);
    #423 五景用场景自带 grade/answer_status(短路前均被门拒,无总结消费)。
    path 由分支包装器按路径标签回填。"""
    triggers = triggers or [""] * len(messages)
    gateway = FakeGateway(_payloads(len(messages), ready_flags, triggers))
    session = start(question, learner or {"grade": "五年级",
                                           "answer_status": "correct"},
                    gateway=gateway).session
    outcome = ReplayOutcome(case_id=case_id, final_state="needs_review",
                            scripted_ready_turns=sorted(t + 1 for t in ready_flags))
    for message in messages:
        turn = reply(session, message, gateway=gateway)
        if session.verified_signal is not None:
            outcome.evidence_turns.append(session.verified_signal["evidence_turn_id"])
        if turn.state == "completed":
            outcome.final_state = "completed"        # 终述收束路径在 reply 内闭环
            break
        if turn.ready_to_confirm:                    # 客户端见 ready → confirm
            summary = finish(session, gateway=gateway)
            if summary.status == "completed":
                outcome.final_state = "completed"
                break
    else:
        summary = finish(session, gateway=gateway)   # 剧本尽头的最终 confirm 尝试
        outcome.final_state = summary.status
        outcome.summary_text = summary.text
    outcome.gate_rejections = sum(
        1 for event in session.guard_events
        if event.get("branch") == "completion_gate_rejected")
    return outcome


def replay_linear(case_id: str, question: dict, student_turns: list[str],
                  ready_flags: set[int], learner: dict | None = None) -> ReplayOutcome:
    """线性剧本重放(student_turns 固定序列,无分支路由锚)。"""
    return _drive(case_id, question, list(student_turns), ready_flags,
                  learner=learner)


def replay_branch_paths(case_id: str, question: dict,
                        steps: list[dict]) -> list[ReplayOutcome]:
    """分支剧本(v2 steps)全路径重放:每步每分支一路径;非兜底分支的路由锚
    (assistant_contains_any 首个触发词)注入**上一轮** tutor 文案(导师句路由
    下一步学生分支),兜底分支用中性文案——同一剧本实测各路径 evidence/终态。"""
    outcomes: list[ReplayOutcome] = []
    combos = itertools.product(*(range(len(step["branches"])) for step in steps))
    for combo in combos:
        messages: list[str] = []
        triggers = [""] * len(steps)
        labels: list[str] = []
        for step_index, (step, branch_index) in enumerate(zip(steps, combo,
                                                              strict=True)):
            branch = step["branches"][branch_index]
            labels.append(f"{step['id']}/{branch['id']}")
            messages.append(branch["student_response"])
            when = branch.get("when") or {}
            if (not when.get("fallback") and when.get("assistant_contains_any")
                    and step_index > 0):
                triggers[step_index - 1] = str(when["assistant_contains_any"][0])
        outcome = _drive(case_id, question, messages,
                         {len(messages) - 1}, triggers)
        outcome.path = "/".join(labels)
        outcomes.append(outcome)
    return outcomes


def scripted_ready_flags(case: dict) -> set[int]:
    """tutor ready 剧本(0 起轮号):**终答轮起持续 ready**(sticky)。

    - 锚轮 = expected.gate_evidence 为 dict 时取 student_turn_index(corpus 编译期
      登记的轨迹终答轮——轨迹事实,非期望终态);字符串 student_final_answer_turn
      取 gate_a_probe 登记的 evidence 轮(无可构造轮即张力案,退末轮);
      字符串 none(负向案)锚末轮——镜像原失败形态(判停/收束先于终答),
      给门留下必拦的完成企图;
    - 锚轮起**每一轮**都 ready:导师已认出终答,后续表态(复述/回执/摇摆后
      回正)不收回承认;客户端逐 ready 轮发起 confirm,首个 Gate 授权轮即
      completed——§二「verified 后同轮终局」的交互形态(2960 摇摆案:compile
      锚轮 t1 被「大概」不确定表达拒判,evidence 后置 t3=probe 登记在案,
      sticky-ready 使 t3 回正轮的 confirm 被授权,四锚语义成立)。
    分支案不走本函数(逐路径末轮 ready,见 replay_branch_paths)。"""
    ri = case["replay_input"]
    evidence = case["gate_a_probe"].get("evidence_turns") or []
    gate = case["expected"]["gate_evidence"]
    turns = len(ri.get("student_turns") or [])
    if isinstance(gate, dict):
        anchor = int(gate["student_turn_index"])
    elif "none" in str(gate):
        anchor = turns - 1
    else:
        anchor = min(evidence) if evidence else turns - 1
    return set(range(anchor, turns))


def gate_question(scenario: dict, spec: dict | None) -> dict:
    """corpus replay_input 的 scenario → 内核 start() 入参:题面(字符串或
    question dict——短板五景为 dict,自带 answer/analysis)+ answer_spec 声明面
    (ADVISORY 建议规格注入;组装契约 kernel._answer_spec,composite/未知类型
    即 None fail-closed)。"""
    raw = scenario["question"]
    if isinstance(raw, dict):
        question = {"text": str(raw.get("text") or ""),
                    "analysis": str(raw.get("analysis") or ""),
                    "knowledge_points": list(raw.get("knowledge_points") or [])}
        if raw.get("answer"):
            question["answer"] = str(raw["answer"])
    else:
        question = {"text": str(raw), "analysis": "", "knowledge_points": []}
    if isinstance(spec, dict) and spec.get("ground_truth"):
        question.setdefault("answer", str(spec["ground_truth"]))
    if isinstance(spec, dict):
        question["answer_spec"] = {
            "answer_type": spec.get("answer_type"),
            "ground_truth": spec.get("ground_truth"),
            **({"letter_choices": list(spec["letter_choices"])}
               if spec.get("letter_choices") else {}),
        }
    return question
