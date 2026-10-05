"""#542 answer-leak 恢复梯子:数值掩码救不回后的确定性问句兜底。

Case 15 形态(M6-0 资格证据):句级泄漏(字母答案)→ 数值面干净(violations=∅)
→ `mask_numbers(reply, ∅)` 恒等空转 → 恢复漏斗退化为 PURE_BLOCK 硬停,学生面
断裂。本电池钉修复后的梯子(合同 #542):

    answer_leak → numeric mask → 安全返回 masked;
    不可修(空转/复检仍命中)→ 常量问句兜底(零模型)→ 同 `_guard_check` 复检;
    兜底安全 → 返回(mode=safe_fallback,additive);不安全 → PURE_BLOCK(末级不删)。

与 test_leak_gate_numeric 的分野:那边钉数值归因判据(哪类数字违规),这边钉
恢复漏斗的 rung 顺序与不降量——检测面同输入同命中、mask 成功路径逐字不变、
兜底零模型调用、unsafe 兜底仍 fail-closed、兜底常量过同一张检测脸。
"""

from __future__ import annotations

from edu_agent.agents.small_lecturer import (
    PURE_BLOCK,
    SAFE_FALLBACK_TEXT,
    reply,
    start,
)

from teachkit import FakeGateway

# 句级泄漏载体(Case 15 同构,通用形态非题目特例):字母答案,题面无数字 →
# 数值面恒干净 → 掩码恒空转。学生 B 图陈述给「1」合法来源(学生已说)。
LETTER_Q = {"text": "图中A、B、C三个图形里,a和b满足什么关系时互为倒数?",
            "answer": "C", "analysis": "", "knowledge_points": ["倒数"]}
LEARNER = {"grade": "六年级", "name": "小明"}
STUDENT_B = "B图线段a米、b米,总长1米,那是a+b=1,不是乘积。"
# 泄漏回复:「C图」含权威答案字母 +「答案」断言 cue,学生未说过 C → 句级命中;
# 数字 1 学生已说 → violations=∅ → mask 空转(探针 P1:mask_numbers(t,∅)≡t)。
LEAK_REPLY = ("你刚才说B图里a和b加起来是1,这说明它们不是互为倒数,因为倒数要满足"
              "乘积是1,对吧?那C图呢?你猜猜它为什么可能是答案?")
# 数值泄漏载体(mask 成功路径对照):答案数字可掩
NUMBER_Q = {"text": "鸡兔同笼,一共 8 只,26 只脚。鸡和兔各有多少只?",
            "answer": "鸡3只兔5只", "analysis": "", "knowledge_points": ["鸡兔同笼"]}
STEPS = [{"step": "先算鸡脚差", "value": "16"}, {"step": "再算兔脚差", "value": "10"},
         {"step": "兔的只数", "value": "5"}]


def _open(reply_text: str) -> dict:
    return {"reply": reply_text, "ready_to_confirm": False, "cited_numbers": [],
            "steps": []}


def _tutor(reply_text: str, ready: bool = False) -> dict:
    return {"reply": reply_text, "ready_to_confirm": ready, "cited_numbers": []}


def _leak_events(session) -> list[dict]:
    return [e for e in session.guard_events if e.get("guard") == "answer_leak"]


def test_sentence_leak_mask_noop_returns_safe_fallback_question():
    """①句级泄漏(掩码空转):兜底问句返回、PURE_BLOCK 消失、检测事件与修复前
    一致(同 rule_ids/original/regenerated,观测事件 violation_sources 同空——检测
    面不变的钉);处置 mode 由 blocked → safe_fallback(additive)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("你先说说每个图里a和b的关系?"),
        _tutor(LEAK_REPLY),
    ])
    turn = start(dict(LETTER_Q), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, STUDENT_B, gateway=gateway)

    assert turn.text == SAFE_FALLBACK_TEXT            # 兜底问句达学生面
    assert turn.text != PURE_BLOCK                    # PURE_BLOCK 断裂消失
    # 检测面不变:处置事件仍是同一次命中(rule_ids/original 逐字,仅 mode 迁移)
    events = _leak_events(turn.session)
    assert len(events) == 1                           # 兜底本身未再命中(⑥的留痕半)
    event = events[0]
    assert event["rule_ids"] == ["grounded_answer_disclosure"]
    assert event["original"] == LEAK_REPLY
    assert event["regenerated"] is False
    assert event["mode"] == "safe_fallback"
    observed = [e for e in turn.session.guard_events if e.get("branch") == "model"][0]
    assert observed["violation_sources"] == []        # 数值归因口径同修复前
    assert turn.session.stuck is not True             # #382:系统处置不写学生卡点


def test_mask_success_path_unchanged_fallback_not_preempting():
    """②mask 成功路径回归:可掩形态逐字走掩码臂(mode=masked、结构保形、终答数字
    不可见)——兜底 rung 不抢占可修案(#542 G3 第一负向)。"""
    gateway = FakeGateway(tutor_payloads=[
        {"reply": "先看题面说的 8 只、26 只脚,你打算先算什么?",
         "ready_to_confirm": False, "cited_numbers": [], "steps": STEPS},
        _tutor("对,答案就是鸡 3 只、兔 5 只。"),
    ])
    turn = start(dict(NUMBER_Q), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)

    assert turn.text == "对,答案就是鸡 □ 只、兔 □ 只。"   # 掩码输出逐字不变
    assert _leak_events(turn.session)[-1]["mode"] == "masked"
    assert "3" not in turn.text and "5" not in turn.text


def test_unsafe_fallback_still_pure_blocks(monkeypatch):
    """③unsafe fallback fail-closed:测试内注入会触警的兜底文本(含答案字母 +
    断言 cue)→ 同一 guard 复检拦下 → PURE_BLOCK 仍是末级 rung(硬停语义不删)。"""
    monkeypatch.setattr("edu_agent.agents.small_lecturer.kernel.SAFE_FALLBACK_TEXT",
                        "答案就是C,你记住它。")
    gateway = FakeGateway(tutor_payloads=[
        _open("你先说说每个图里a和b的关系?"),
        _tutor(LEAK_REPLY),
    ])
    turn = start(dict(LETTER_Q), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, STUDENT_B, gateway=gateway)

    assert turn.text == PURE_BLOCK
    event = _leak_events(turn.session)[-1]
    assert event["mode"] == "blocked"                 # 末级处置照记
    assert event["rule_ids"] == ["grounded_answer_disclosure"]  # 检测面同源
    assert turn.session.stuck is not True


def test_fallback_and_block_add_zero_model_calls():
    """④零新模型调用:兜底与硬停路径的 gateway 请求数 = 剧本消费(open+reply 各一),
    无任何重生成/复述补救调用(CF-1 确定性恢复,#542 Hard Invariants 4)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("你先说说每个图里a和b的关系?"),
        _tutor(LEAK_REPLY),
    ])
    turn = start(dict(LETTER_Q), dict(LEARNER), gateway=gateway)
    reply(turn.session, STUDENT_B, gateway=gateway)
    assert len(gateway.requests) == 2                 # 零新增模型调用


def test_safe_fallback_constant_passes_same_guard():
    """⑥兜底常量安全证:SAFE_FALLBACK_TEXT 作为 tutor 输出经同一 `_guard_output`
    检测面零拦截(无 answer_leak 事件、原文直通)——兜底返回值与普通输出过同一张
    脸(常量来自仓内既有 SAFE_FALLBACK_TEXT 族,feeds_method 模板臂同源)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open("你先说说每个图里a和b的关系?"),
        _tutor(SAFE_FALLBACK_TEXT),
    ])
    turn = start(dict(LETTER_Q), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, STUDENT_B, gateway=gateway)

    assert turn.text == SAFE_FALLBACK_TEXT            # 检测面判干净,原样直通
    assert _leak_events(turn.session) == []
