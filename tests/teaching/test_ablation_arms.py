"""三臂消融门控(#333 Kernel 重新审判·协议 artifacts/kernel-retrial/§1)。

断言零模型(FakeGateway 对象注入,断言即规格):
  · C=默认原样:不 set 时生产语义逐字不变(既有 338 测试已钉,此处只验 set 后回归);
  · A=raw shadow:B类确定性覆写点(elicit/stuck/答案命中/答案收集/pc 闸/repeat/
    防复读)旁路到模型路径,检测只记 would_* 事件(additive 键),模型文本直通;
  · B=thin safety:B类全关(同旁路但不记 shadow);_guard_output 仅 answer_leak
    处置(泄漏类 regen/兜底照走),非泄漏护栏命中原文直通;
  · fail closed:A/B/C 之外 ValueError;
  · 恢复:set_ablation_arm("C") 后语义复原(测试隔离 fixture)。
"""

from __future__ import annotations

import pytest

from edu_agent.agents.small_lecturer import reply, set_ablation_arm, start

from teachkit import FakeGateway

CHICKEN_QUESTION = {"text": "鸡和兔一共 8 只,共有 26 只脚。鸡和兔各有多少只?说明思路。",
                    "answer": "鸡3只兔5只", "analysis": "", "knowledge_points": ["鸡兔同笼"]}
CHICKEN_STEPS = [{"step": "先算全部按鸡的脚数", "value": "16"},
                 {"step": "再算脚数差", "value": "10"}]


def _open_payload(reply_text: str) -> dict:
    return {"acceptable": True, "transcription": "", "steps": CHICKEN_STEPS, "reply": reply_text}


def _tutor_payload(reply_text: str, ready: bool = False) -> dict:
    return {"reply": reply_text, "ready_to_confirm": ready, "cited_numbers": []}


def _session(gateway: FakeGateway, answer_status: str = "incorrect") -> object:
    first = start(dict(CHICKEN_QUESTION),
                  {"grade": "六年级", "answer_status": answer_status}, gateway=gateway)
    return first.session


@pytest.fixture(autouse=True)
def _restore_arm_c():
    """测试隔离:每例结束回 C(模块级臂不泄漏到其他测试)。"""
    yield
    set_ablation_arm("C")


def test_set_ablation_arm_fail_closed():
    with pytest.raises(ValueError):
        set_ablation_arm("X")


def test_arm_c_stuck_branch_unchanged():
    """C 臂:stuck 信号走确定性支持(零模型调用)——生产语义锚。"""
    set_ablation_arm("C")
    gateway = FakeGateway(tutor_payloads=[_open_payload("你打算怎么入手?")])
    session = _session(gateway)
    calls = len(gateway.requests)
    turn = reply(session, "我不会,想不出来", gateway=gateway)
    assert len(gateway.requests) == calls            # 确定性支持:零模型调用
    assert turn.session.guard_events[-1]["branch"] == "reveal"  # 阶梯揭示埋点照旧


def test_arm_a_stuck_bypasses_to_model_with_would_reveal():
    """A 臂:stuck 分支旁路——模型路径接手,记 would_reveal,文本直通模型输出。"""
    set_ablation_arm("A")
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你打算怎么入手?"),
        _tutor_payload("我们看看题目里已知的总数是几只?"),
    ])
    session = _session(gateway)
    turn = reply(session, "我不会,想不出来", gateway=gateway)
    assert len(gateway.requests) == 2                # 模型被调用(A 臂旁路到模型路径)
    assert turn.text == "我们看看题目里已知的总数是几只?"   # 模型文本直通
    shadows = [e for e in turn.session.guard_events if "shadow" in e]
    assert any(e["shadow"] == "would_reveal" and e["rule"] == "stuck_hint" for e in shadows)



def test_arm_a_leak_shadow_records_would_block_and_passes_through():
    """A 臂:模型输出带终答 → answer_leak 只记 would_block,文本直通(不拦不改)。"""
    set_ablation_arm("A")
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你打算怎么入手?"),
        _tutor_payload("答案是鸡 3 只兔 5 只,你记一下。"),
    ])
    session = _session(gateway)
    turn = reply(session, "先算哪个数?", gateway=gateway)
    assert "鸡 3 只兔 5 只" in turn.text            # 泄漏文本直通(raw 不达真实学生)
    shadows = [e for e in turn.session.guard_events if "shadow" in e]
    assert any(e["shadow"] == "would_block" for e in shadows)


def test_arm_b_deterministic_branches_off():
    """B 臂:stuck/understanding 确定性分支全关——模型路径接手,无 shadow 事件。"""
    set_ablation_arm("B")
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你打算怎么入手?"),
        _tutor_payload("我们从脚数关系想想?"),
        _tutor_payload("那你讲讲思路?"),
    ])
    session = _session(gateway)
    turn1 = reply(session, "我不会,想不出来", gateway=gateway)
    assert turn1.text == "我们从脚数关系想想?"       # 模型直通
    turn2 = reply(session, "我明白了", gateway=gateway)
    assert turn2.text == "那你讲讲思路?"
    assert not any("shadow" in e for e in turn2.session.guard_events)  # B 臂不记 shadow


def test_arm_b_leak_masked_via_main_path():
    """Thin Kernel(#333):B 臂泄漏 = 主路径掩码(专用漏斗已删,B 与 C 同一安全面)
    ——结构保留数值→□,零模型零 regen,无 arm_b 专用埋点。"""
    set_ablation_arm("B")
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你打算怎么入手?"),
        _tutor_payload("答案是鸡 3 只兔 5 只,你记一下。"),
    ])
    session = _session(gateway)
    turn = reply(session, "先算哪个数?", gateway=gateway)
    assert turn.text == "答案是鸡 □ 只兔 □ 只,你记一下。"  # 确定性掩码
    events = [e for e in turn.session.guard_events if e.get("mode")]
    assert [e["mode"] for e in events] == ["masked"]
    assert not any("arm_b" in e for e in turn.session.guard_events)  # 专用漏斗退役


def test_arm_b_unmaskable_leak_pure_blocks():
    """Thin Kernel:B 臂不可掩形态(带修饰数字)→ 主路径纯 block(与 C 同一面),
    只拒绝不重教,置卡点。"""
    set_ablation_arm("B")
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你打算怎么入手?"),
        _tutor_payload("答案是鸡 3 只兔 05 只,你记一下。"),  # 05 前导零:检得出掩不掉
    ])
    session = _session(gateway)
    turn = reply(session, "先算哪个数?", gateway=gateway)
    assert "鸡 3 只兔 05 只" not in turn.text
    assert turn.text == "这条回复包含题目终答,我不能直接给出。"  # 纯 block:只拒绝不重教
    assert turn.session.stuck is True
    events = [e for e in turn.session.guard_events if e.get("mode")]
    assert [e["mode"] for e in events] == ["blocked"]



def test_arm_a_feeds_method_shadow():
    """A 臂:代喂命中记 would_rewrite(feeds_method),模型文本直通(协议 §1.2 #8)。"""
    set_ablation_arm("A")
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你打算怎么入手?"),
        _tutor_payload("我们用假设法:先假设全是鸡,再数脚数差?"),
    ])
    session = _session(gateway)
    turn = reply(session, "先算哪个数?", gateway=gateway)
    assert "假设法" in turn.text                       # A 臂代喂不处置,文本直通
    shadows = [e for e in turn.session.guard_events if "shadow" in e]
    assert any(e["shadow"] == "would_rewrite" and e["rule"] == "feeds_method"
               for e in shadows)


def test_arm_c_restore_after_ablation():
    """恢复语义:set 回 C 后 stuck 分支照走确定性支持。"""
    set_ablation_arm("A")
    set_ablation_arm("C")
    gateway = FakeGateway(tutor_payloads=[_open_payload("你打算怎么入手?")])
    session = _session(gateway)
    calls = len(gateway.requests)
    reply(session, "我不会,想不出来", gateway=gateway)
    assert len(gateway.requests) == calls            # 回 C:确定性支持零模型


# --- 二阶段 LOO 门控(phase2-protocol-v1.md §2;C 臂 + off 集,零模型) ---

def test_phase2_off_fail_closed_unknown_mech():
    from edu_agent.agents.small_lecturer import set_phase2_off
    with pytest.raises(ValueError):
        set_phase2_off(["bogus_mech"])


def test_phase2_repeat_regen_off_passes_repeat_through():
    """repeat_regen(+背板)关:复读不 regen 不兜底不背板,原文本直通(零 regen 调用)。"""
    from edu_agent.agents.small_lecturer import set_phase2_off
    set_ablation_arm("C")
    set_phase2_off(["repeat_regen", "bottomout_backboard"])
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你打算怎么入手?"),
        _tutor_payload("先算哪个数?"),
        _tutor_payload("先算哪个数?"),  # 与上轮同文本 → 复读
    ])
    session = _session(gateway)
    reply(session, "第一问", gateway=gateway)
    calls = len(gateway.requests)
    turn = reply(session, "再想想", gateway=gateway)
    assert len(gateway.requests) == calls + 1     # 只有一次模型调用,无 regen
    assert turn.text == "先算哪个数?"             # 原文直通(背板同关)
    set_phase2_off([])


def test_phase2_reveal_ladder_off_support_only():
    """reveal_ladder 关:stuck 落 _SUPPORT_HINT(只问不揭示),记 reveal_off。"""
    from edu_agent.agents.small_lecturer import set_phase2_off
    set_ablation_arm("C")
    set_phase2_off(["reveal_ladder"])
    gateway = FakeGateway(tutor_payloads=[_open_payload("你打算怎么入手?")])
    session = _session(gateway)
    turn = reply(session, "我不会,想不出来", gateway=gateway)
    assert "我们把这一步拆小" in turn.text          # _SUPPORT_HINT,无步内容
    assert any(e.get("branch") == "reveal_off" for e in turn.session.guard_events)
    set_phase2_off([])


def test_phase2_premature_confirm_off_passes_ready():
    """premature_confirm 关:模型 ready_to_confirm 直用,不重写(对照 C 臂闸下)。"""
    from edu_agent.agents.small_lecturer import set_phase2_off
    set_ablation_arm("C")
    set_phase2_off(["premature_confirm"])
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你打算怎么入手?"),
        _tutor_payload("那我们确认一下:鸡和兔一共是 8 只,对吗?", ready=True),
    ])
    session = _session(gateway)
    turn = reply(session, "先算哪个数?", gateway=gateway)
    assert turn.state == "ready_to_confirm"        # 闸不验,ready 直用
    assert not any(e.get("guard") == "premature_confirm"
                   for e in turn.session.guard_events)
    set_phase2_off([])


def test_phase2_off_reset_restores_c():
    """off 集清空后 C 语义复原(测试隔离)。"""
    from edu_agent.agents.small_lecturer import set_phase2_off
    set_ablation_arm("C")
    set_phase2_off(["reveal_ladder"])
    set_phase2_off([])
    gateway = FakeGateway(tutor_payloads=[_open_payload("你打算怎么入手?")])
    session = _session(gateway)
    turn = reply(session, "我不会,想不出来", gateway=gateway)
    assert turn.session.guard_events[-1]["branch"] == "reveal"  # 阶梯照走
