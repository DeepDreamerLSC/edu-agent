"""#382 PR-C:reveal 权威源边界(trusted ladder boundary,事故 20260920 P0-3)。

事故形态(700m 温度题,产线实录):该题 analysis 无海拔数字 → 错误阶梯(「A处
海拔是500米」)来自**模型生成** → `_reveal_stuck_hint` 忠实回放 = 脚手架读图
错误,孩子当场纠正。总裁定(2026-09-20):trusted ladder = 题库 analysis 确定性
切片;model-generated ladder = untrusted planning artifact,只帮规划不得进
deterministic reveal;无 trusted ladder → safe guiding question(不硬编码题目
话术,禁令§11)。

断言即规格(公开面驱动 start/reply + FakeGateway,与 test_kernel_restate 同款):
  · provenance 标记:`_store_steps` 入库步 = model,`_analysis_steps` 切片 = analysis;
  · model 阶梯不揭示:卡壳/复读兜底 → `_UNTRUSTED_LADDER_HINT`,记
    {branch: reveal_untrusted},hint_level 不动,模型阶梯数字不上学生面;
  · analysis 阶梯照常揭示(trusted 回放不变);
  · 规划辅助不受边界影响:模型 steps 值仍进 `_drift_sources` 允许集/答案兜底
    (模型阶梯保留规划辅助,deterministic reveal 只此一门收紧);
  · 持久化:provenance 随 FileSessionStore asdict 落盘,重启恢复后边界不丢。
"""

from __future__ import annotations

from edu_agent.agents.small_lecturer import (
    _UNTRUSTED_LADDER_HINT,
    reply,
    start,
)
from edu_agent.api import FileSessionStore

from teachkit import FakeGateway

# 无 analysis 的题面(700m 事故形态:题库解析无该题关键数字,错误阶梯只能来自模型)
QUESTION_NO_ANALYSIS = {"text": "看图,A、B两地的海拔各是多少米?", "answer": "",
                        "analysis": "", "knowledge_points": []}
# 模型生成的错误阶梯(事故形态:数字与图不符——A 实为 700,阶梯写 500)
MODEL_LADDER = [
    {"step": "从图中读出A处海拔是500米", "value": "500"},
    {"step": "每100米降0.6度,算温差", "value": "1.2"},
]
LEARNER = {"grade": "五年级", "answer_status": "incorrect"}


def _open_payload(reply_text: str, steps: list[dict]) -> dict:
    return {"acceptable": True, "transcription": "", "steps": steps, "reply": reply_text}


def _tutor_payload(reply_text: str, ready: bool = False) -> dict:
    return {"reply": reply_text, "ready_to_confirm": ready, "cited_numbers": []}


# ---------- provenance 标记(写入面) ----------


def test_model_steps_stored_with_model_provenance():
    """open-solve 的模型分步解照常入库(规划辅助),但逐条带 provenance="model"
    (untrusted planning artifact 标记)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你先说说从图里看到了什么?", [dict(s) for s in MODEL_LADDER])])
    turn = start(dict(QUESTION_NO_ANALYSIS), dict(LEARNER), gateway=gateway)
    assert turn.session.steps == [
        {"step": "从图中读出A处海拔是500米", "value": "500", "provenance": "model"},
        {"step": "每100米降0.6度,算温差", "value": "1.2", "provenance": "model"}]


def test_analysis_ladder_stored_with_analysis_provenance():
    """题库解析切片优先于模型分步解,逐条带 provenance="analysis"(trusted)。"""
    question = {"text": "鸡和兔一共 8 只,共有 26 只脚。鸡和兔各有多少只?",
                "answer": "鸡3只兔5只",
                "analysis": "先假设8只全是鸡,算出脚的总数8×2=16。再算实际脚数比"
                            "假设多26-16=10只。",
                "knowledge_points": []}
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你先说说题目给了哪些条件?", [dict(s) for s in MODEL_LADDER])])
    turn = start(dict(question), dict(LEARNER), gateway=gateway)
    assert all(s["provenance"] == "analysis" for s in turn.session.steps)
    assert [s["value"] for s in turn.session.steps] == ["16", "10"]


# ---------- model 阶梯不进 deterministic reveal(核心边界) ----------


def test_stuck_with_model_ladder_gives_safe_question_not_replay():
    """事故 700m 形态:无 analysis(切不出 trusted 阶梯)+ 模型阶梯(500/1.2 与
    图不符)→ 学生卡壳时 reveal **不回放**模型阶梯——safe guiding question,
    模型阶梯数字不上学生面,零模型调用。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你先说说从图里看到了什么?", [dict(s) for s in MODEL_LADDER])])
    first = start(dict(QUESTION_NO_ANALYSIS), dict(LEARNER), gateway=gateway)
    calls_before = len(gateway.requests)
    turn = reply(first.session, "我不太会。", gateway=gateway)
    assert turn.text == _UNTRUSTED_LADDER_HINT
    assert "500" not in turn.text and "1.2" not in turn.text  # 模型阶梯数字不达学生面
    assert turn.session.hint_level == 0                        # 阶梯不消耗
    assert turn.session.guard_events[-1]["branch"] == "reveal_untrusted"
    assert len(gateway.requests) == calls_before               # 确定性:零模型调用


def test_repeat_fallback_with_model_ladder_gives_safe_question():
    """复读兜底路径同受边界:模型复读 → 重生成仍复读 → 兜底不走 model 阶梯
    (事故链里的 reveal 重发点即此)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你好同学,这道题你的答案是什么呀?讲讲你的思路吧!",
                      [dict(s) for s in MODEL_LADDER]),
        _tutor_payload("你好同学,这道题你的答案是什么呀?讲讲你的思路吧!"),
        _tutor_payload("你好同学,这道题你的答案是什么呀?讲讲你的思路吧!"),
    ])
    first = start(dict(QUESTION_NO_ANALYSIS), dict(LEARNER), gateway=gateway)
    turn = reply(first.session, "嗯,我看看。", gateway=gateway)
    assert turn.text == _UNTRUSTED_LADDER_HINT
    assert "500" not in turn.text
    assert turn.session.guard_events[-1]["branch"] == "reveal_untrusted"


def test_repeated_stuck_with_model_ladder_stays_safe_and_consumes_nothing():
    """连续卡壳:model 阶梯恒不揭示(不因再次 stuck 解锁),hint_level 恒 0,
    reveal_untrusted 每轮在案(可度量)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你先说说从图里看到了什么?", [dict(s) for s in MODEL_LADDER])])
    first = start(dict(QUESTION_NO_ANALYSIS), dict(LEARNER), gateway=gateway)
    session = first.session
    for message in ("我不会做。", "还是不会。", "我完全不知道怎么做。"):
        turn = reply(session, message, gateway=gateway)
        assert turn.text == _UNTRUSTED_LADDER_HINT
        assert session.hint_level == 0
    untrusted = [e for e in session.guard_events
                 if e.get("branch") == "reveal_untrusted"]
    assert len(untrusted) == 3


# ---------- analysis 阶梯照常揭示(trusted 回放不变) ----------


def test_stuck_with_analysis_ladder_reveals_trusted_step():
    """对照:题库解析切得出 ≥2 步 → 卡壳照常揭示下一级 analysis 切片
    (trusted 回放,既有行为零回归)。"""
    question = {"text": "鸡和兔一共 8 只,共有 26 只脚。鸡和兔各有多少只?",
                "answer": "鸡3只兔5只",
                "analysis": "先假设8只全是鸡,算出脚的总数8×2=16。再算实际脚数比"
                            "假设多26-16=10只。",
                "knowledge_points": []}
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你先说说题目给了哪些条件?", [dict(s) for s in MODEL_LADDER])])
    first = start(dict(question), dict(LEARNER), gateway=gateway)
    turn = reply(first.session, "我不太会。", gateway=gateway)
    assert "先假设8只全是鸡" in turn.text       # 揭的是 analysis 切片
    assert "500" not in turn.text                # 模型阶梯仍在库但不被揭示
    assert first.session.hint_level == 1
    assert first.session.guard_events[-1]["branch"] == "reveal"


# ---------- 规划辅助不受边界影响(model 阶梯保留其辅助用途) ----------


def test_model_ladder_values_still_in_drift_allowed_set():
    """模型阶梯值照旧进数字守卫允许集(规划辅助保留):导师复述模型阶梯算过的
    中间值(500)不算幻觉——若边界误伤规划面,这句会被掩码。"""
    question = {"text": "看图,A、B两地的海拔各是多少米?说说你的想法。",
                "answer": "A是700米,B是1000米", "analysis": "", "knowledge_points": []}
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你先说说从图里看到了什么?", [dict(s) for s in MODEL_LADDER]),
        _tutor_payload("你刚才说A处海拔是500米,我们往下算。"),
    ])
    first = start(dict(question), dict(LEARNER), gateway=gateway)
    turn = reply(first.session, "A处海拔是500米。", gateway=gateway)
    assert "500" in turn.text                     # 模型阶梯值 = 合法来源
    assert turn.session.stuck is not True


def test_model_ladder_value_still_backstops_known_answer():
    """question.answer 缺失时 steps 末值照旧兜底 `_known_answer`(规划辅助保留):
    阶梯末值 1.2 入终答池 → 学生未述时导师引述照旧掩码。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你先说说从图里看到了什么?", [dict(s) for s in MODEL_LADDER]),
        _tutor_payload("温差是 1.2 度,对吧?"),
    ])
    first = start(dict(QUESTION_NO_ANALYSIS), dict(LEARNER), gateway=gateway)
    turn = reply(first.session, "我先看看图。", gateway=gateway)
    assert "1.2" not in turn.text                 # 末值兜底成终答 → 首次披露照掩
    assert any(e.get("guard") == "answer_leak" for e in turn.session.guard_events)


# ---------- 支持动作:giving 判据只对 trusted 阶梯成立 ----------


def test_support_guiding_not_triggered_by_model_ladder_values():
    """model 阶梯的 value 不做掌握度判据:学生说出模型阶梯的数字后卡壳,
    `_support_move` 不给 guiding_focus(恒 telling → 由 reveal 边界接管为
    safe question)——幻觉值不洗成教学信号。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你先说说从图里看到了什么?", [dict(s) for s in MODEL_LADDER])])
    first = start(dict(QUESTION_NO_ANALYSIS), dict(LEARNER), gateway=gateway)
    reply(first.session, "A处海拔是500米。", gateway=gateway)   # 「做出」模型阶梯第 1 级
    turn = reply(first.session, "我不会了。", gateway=gateway)  # 紧邻卡壳
    assert not any(e.get("branch") == "support"
                   for e in first.session.guard_events)          # 无 guiding_focus
    assert turn.text == _UNTRUSTED_LADDER_HINT                   # telling → 边界接管


# ---------- 持久化:provenance 随会话落盘,重启后边界不丢 ----------


def test_provenance_persists_through_file_store(tmp_path):
    """steps 的 provenance 字段随 FileSessionStore asdict 落盘并可恢复
    (重启恢复的会话 reveal 边界不回退)。"""
    store = FileSessionStore(tmp_path / "sessions")
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你先说说从图里看到了什么?", [dict(s) for s in MODEL_LADDER])])
    first = start(dict(QUESTION_NO_ANALYSIS), dict(LEARNER), gateway=gateway)
    store.save(first.session)
    restored = store.load(first.session.session_id)
    assert restored is not None
    assert all(s["provenance"] == "model" for s in restored.steps)  # 标记随盘
    turn = reply(restored, "我不太会。", gateway=gateway)            # 恢复会话照样守边界
    assert turn.text == _UNTRUSTED_LADDER_HINT
    assert restored.guard_events[-1]["branch"] == "reveal_untrusted"
