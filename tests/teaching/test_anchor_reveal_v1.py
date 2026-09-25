"""#333 泄露网 V1 锚/终答测试面——三层测试之①②(裁定 c5717512971;PM 49255c5dba108a0b)。

①Q5 第二层四断言(首次 stuck 不给数值 / 再次 stuck 给当前级非终答锚 / 单步题
repeated stuck 仍不给 / 部件重叠仍不给)+ ②Q5 第一层边界对 C/D/F(support 零锚 /
ready_to_confirm 禁 / 答案不可判定 fail-closed)。种子 = 同目录 seeds-anchor-v1.json
(A-D/M/F 七对);走**公开面驱动**(start/reply + FakeGateway,与 test_kernel_restate
同款口径),steps 经 open payload 注入(种子里 steps 为合成 plan 步,已标注);
#382 PR-C 起 reveal 只消费 trusted(analysis)阶梯,故 `_drive` 同时由 steps 反解
analysis 注入题面(切片与种子 steps 同文同值,断言面零改)。92/93 泄漏=0 硬门 =
既有套件(test_answer_leak_guardrails + test_kernel_invariants)保持全绿,merge
blocker 口径见 docs/plan/07-leak-net-v1.md。

V1 授权面(裁定原文):终答数字永远 protected;中间步锚仅 deterministic reveal/telling
路径 × 仅当前 next step 的 value × anchor=value数字−answer_pool 非空且 ∩answer_pool=∅
× 仅 hint_level>0 且再次 stuck × ready_to_confirm 禁止;模型自由生成路径零例外。
埋点:reveal 事件 additive 键 `anchor_numbers`(Q6,只在授权轮写;未授权轮不加键)。
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from edu_agent.agents.small_lecturer import FIRST_QUESTION_COLLECT, reply, start

from teachkit import FakeGateway

SEEDS_PATH = (
    Path(__file__).resolve().parents[2]
    / "edu_agent" / "evals" / "artifacts" / "leak-net-v1-testface" / "seeds-anchor-v1.json"
)
SEEDS = {s["name"]: s for s in json.loads(SEEDS_PATH.read_text(encoding="utf-8"))["seeds"]}


def _open_payload(reply_text: str, steps: list[dict]) -> dict:
    return {"acceptable": True, "transcription": "", "steps": steps, "reply": reply_text}


def _tutor_payload(reply_text: str, ready: bool = False) -> dict:
    return {"reply": reply_text, "ready_to_confirm": ready, "cited_numbers": []}


def _drive(seed: dict, stuck_rounds: int, student_messages=None):
    """种子 → 会话弧:open 注入合成 steps(**model 阶梯,照常入库**)+ analysis
    (由 steps 反解,#382 PR-C 起 reveal 只消费 analysis 切片);每轮把上一轮学生
    可见文本喂给模型复读(复读→重生成仍复读→兜底揭示下一级,同 test_kernel_restate
    口径)。第 1 次 reveal = 首次 stuck(hint_level 0→1);第 2 次起 = 再次 stuck。
    student_messages:分轮学生消息(缺省每轮同句卡壳话姿)。"""
    fx = seed["session"]
    gateway = FakeGateway(tutor_payloads=[_open_payload(FIRST_QUESTION_COLLECT, [dict(s) for s in fx["steps"]])])
    question = {"text": fx["question"]["text"], "answer": fx["question"]["answer"],
                "analysis": (seed.get("analysis")
                             or _analysis_from_steps(fx["steps"])),
                "knowledge_points": []}
    first = start(question, dict(fx["learner"]), gateway=gateway)
    messages = ([student_messages] * stuck_rounds if isinstance(student_messages, str)
                else list(student_messages or ["嗯,我看看,还是不会。"] * stuck_rounds))
    prev, turn = FIRST_QUESTION_COLLECT, None
    for message in messages:
        gateway.tutor_queue.extend([_tutor_payload(prev), _tutor_payload(prev)])
        turn = reply(first.session if turn is None else turn.session, message, gateway=gateway)
        prev = turn.text
    return turn


def _reveal_events(turn) -> list[dict]:
    return [e for e in turn.session.guard_events if e.get("branch") == "reveal"]


# ---------- ① Q5 第二层四断言(PM 派单任务③) ----------


def test_first_stuck_gives_no_anchor_clause():
    """首次 stuck(hint_level 0→1)不给**数值锚**(V1 不放宽首次):
    Thin Kernel(#333)soften 收回已删——步文本中间结果(16)照示,锚子句
    (「这一步先算,得到」)不出现,终答部件(3/5)不上学生面。"""
    turn = _drive(SEEDS["A_anchor_legal_intermediate_not_answer"], stuck_rounds=1)
    assert "得到" not in turn.text                      # 锚子句缺席
    for value in ("3", "5"):                            # 终答部件(掩码面)
        assert value not in turn.text
    assert not _reveal_events(turn)[-1].get("anchor_numbers")


def test_restuck_gives_current_level_non_answer_anchor():
    """再次 stuck → 给**当前级非终答**锚(A 类:10 ∉ answer_pool{3,5}):
    Thin Kernel 中间结果(26-16)随步文本示出,锚只认当前级 value;
    5=终答部件不出现(掩码面)。"""
    turn = _drive(SEEDS["A_anchor_legal_intermediate_not_answer"], stuck_rounds=2)
    assert "10" in turn.text
    assert "5" not in turn.text
    assert _reveal_events(turn)[-1]["anchor_numbers"] == [10.0]  # Q6:additive 字段


def test_single_step_repeated_stuck_still_withholds():
    """单步题(value=终答)repeated stuck **仍不给**——唯一可锚级=终答,永无 value 锚
    (第 2 轮耗尽 → bottom-out 披露终答 = 设计内路径,不记锚)。"""
    for name in ("B_single_step_collision_stuck02", "B_single_step_collision_answerhit01"):
        turn = _drive(SEEDS[name], stuck_rounds=2)
        assert not any(e.get("anchor_numbers") for e in _reveal_events(turn))


def test_step_value_overlapping_answer_part_still_withholds():
    """step value 与 answer **部件**重叠仍不给锚(C 类多部件全保护,
    understanding_04:answer_pool={6,3},两级 value 均重叠 → 整梯无锚);
    Thin Kernel:终答部件 3 掩码(□),题面给定 6 照示。"""
    turn = _drive(SEEDS["M_multi_part_overlap_still_withheld"], stuck_rounds=2)
    assert not any(e.get("anchor_numbers") for e in _reveal_events(turn))
    assert "3" not in turn.text


# ---------- ② Q5 第一层边界对 C/D/F(七条件单面验证) ----------

# #382 PR-C:anchor 面钉 **trusted(analysis)阶梯**——V1 授权判据(value−answer_pool、
# 当前级、再次 stuck)只对权威阶梯有意义;合成 plan 步仍照喂(模型阶梯入库不回归),
# 但 reveal 只消费 analysis 切片。按种子 steps 文本反解成 analysis(每步一句),
# 使切片与种子 steps 同文同值,断言面零改。
def _analysis_from_steps(steps: list[dict]) -> str:
    return "。".join(str(s.get("step") or "") for s in steps) + "。"


def test_C_support_guiding_focus_gives_no_anchor():
    """C 非 telling 路径 → 零锚:学生上一轮复述了当前级数字(「脚数差是10」)→
    下一轮卡住走 guiding_focus 拆小问句(只问不揭示,#169 不含数字)——
    support 轮无 reveal 事件、无 anchor_numbers(此前轮的合法锚不受影响)。"""
    seed = SEEDS["C_support_guiding_focus_no_anchor"]
    turn = _drive(seed, stuck_rounds=3,
                  student_messages=["嗯,我看看,还是不会。", "哦,全部按鸡是16只脚,然后呢。", "还是不会。"])
    assert turn.session.guard_events[-1]["branch"] == "support"
    assert turn.session.guard_events[-1]["move"] == "guiding_focus"
    assert not any(ch.isdigit() for ch in turn.text)


def test_D_ready_state_demoted_by_stuck_anchor_resumes():
    """D ready_to_confirm → 禁(#333 七条件,kernel 保留防直接调用方)。公开流实证:
    学生卡壳信号先把确认态降回 dialogue(t2)→ re-stuck 锚按**当前态**授权——
    本测试钉住「state 检查读当前态」:若误用陈旧 ready 旗,t3 的合法锚会被错拦。
    ready 态与 re-stuck 在公开流互斥(卡壳即降态),防御条件由源读核验。"""
    seed = SEEDS["D_ready_to_confirm_blocks_anchor"]
    fx = seed["session"]
    gateway = FakeGateway(tutor_payloads=[_open_payload(FIRST_QUESTION_COLLECT, [dict(s) for s in fx["steps"]])])
    question = {"text": fx["question"]["text"], "answer": fx["question"]["answer"],
                "analysis": (seed.get("analysis")
                             or _analysis_from_steps(fx["steps"])),
                "knowledge_points": []}
    first = start(question, dict(fx["learner"]), gateway=gateway)
    # 轮1:学生自述答案 + 模型 ready → 合法确认态(test_kernel_restate 同款口径)
    gateway.tutor_queue.extend([_tutor_payload("我们把思路理清楚了。", ready=True)])
    turn1 = reply(first.session, "鸡3只,兔5只。", gateway=gateway)
    assert turn1.state == "ready_to_confirm"
    # 轮2/3:确认态下卡壳 → 降回 dialogue → 背板揭示第2级 → 锚按当前态授权
    gateway.tutor_queue.extend([_tutor_payload(turn1.text)] * 2)
    turn2 = reply(turn1.session, "嗯,我看看,还是不会。", gateway=gateway)
    assert turn2.session.state == "dialogue"  # 卡壳信号降态
    gateway.tutor_queue.extend([_tutor_payload(turn2.text)] * 2)
    turn3 = reply(turn2.session, "嗯,我看看,还是不会。", gateway=gateway)
    assert _reveal_events(turn3)[-1]["anchor_numbers"] == [10.0]


def test_F_answer_undeterminable_fail_closed():
    """F 答案侧不可判定(纯文字答案)→ 保守不给:answer_pool=∅ 时锚数字面无从
    验证保护,空 value 步不入梯(_store_steps 口径)→ 首轮耗尽 bottom-out,全程零锚。"""
    turn = _drive(SEEDS["F_answer_undeterminable_fail_closed"], stuck_rounds=2)
    assert not any(e.get("anchor_numbers") for e in _reveal_events(turn))


# ---------- ③ V1 锚不变量 property 化(v1-property-supplement;随机合成网格,
# 固定种子无新依赖;+四数字等价类定夺的确定性钉) ----------

_ALLOWED_EVENT_KEYS = {"branch", "hint_level", "turn", "soften", "dropped", "anchor_numbers"}


def _synth_seed(rng: random.Random) -> tuple[dict, set[float]]:
    """随机合成 A 形种子:题面数/终答数/阶梯值,重叠与非重叠都造(不变量与
    是否授权无关——锚无论何时出现都必须 ∩pool=∅ 且单数值)。#382 PR-C:step
    文本带该步数值(analysis 切片可承载 value;「第N步」三字短片会被切片弃)。
    B′(#441):步文本取系词断言形(先算这一步的结果是X,同 `_class_seed` 形态)
    ——「先把这一项算出结果 X」是操作叙述(「结果」=算出的宾语,B1 fail-closed
    弃锚,网格锚面退化为 0);property 的对象是**授权后**不变量,网格须保有
    非空锚面,弃锚面由 oracle(19 假)/mutation 测试钉。"""
    qnums = rng.sample(range(2, 60), 2)
    pool = rng.sample([n for n in range(2, 99) if n not in qnums], rng.choice([1, 2]))
    # 阶梯值避题面数、末级必触终答池(guard-provenance-fix ③ 门契约:模型阶梯
    # 须达答案焦点;非末级可撞池,重叠面进样本,不变量须在重叠下仍成立 P4)。
    # #382 PR-C:梯长 ≥2(analysis 切片 ≥2 片才成梯;单级形态由 B 种子钉)。
    ladder = [rng.choice([n for n in range(2, 99) if n not in qnums])
              for _ in range(rng.choice([2, 3]))]
    ladder[-1] = rng.choice(pool)
    steps = [{"step": f"先算这一步的结果是{v}", "value": str(v)} for v in ladder]
    answer = "、".join(f"{n}只" for n in pool)
    seed = {"session": {"question": {"text": f"一共 {qnums[0]} 只和 {qnums[1]} 只,问各多少?",
                                     "answer": answer},
                        "learner": {"grade": "四年级", "answer_status": "incorrect"},
                        "steps": steps}}
    return seed, {float(n) for n in pool}


def test_property_anchor_never_leaks_answer():
    """P1/P2/P3/P4 合一:任意(题面,终答,阶梯值,梯长)组合下——
    锚与终答数字集交恒空(fail-closed)/首次 stuck 零锚/锚恒为单数值/键只增不改。"""
    rng = random.Random(20260918)
    anchored = 0
    for i in range(120):
        seed, pool = _synth_seed(rng)
        turn = _drive(seed, stuck_rounds=2)
        events = _reveal_events(turn)
        assert events[0].get("anchor_numbers") is None, f"case{i}: 首次 stuck 不得带锚"
        for event in events[1:]:
            anchor = event.get("anchor_numbers")
            if anchor is not None:
                anchored += 1
                assert len(anchor) == 1, f"case{i}: 锚必须单数值,实得 {anchor}"
                assert not set(anchor) & pool, f"case{i}: 锚 {anchor} 撞终答池 {pool}"
    # 防网格退化空转(P3-nano③,reviewer 659c6ae9):锚面下限(B′ #441 网格改
    # 系词断言形后实测 57;网格/判据若改到不足此限,说明授权面样本萎缩——先查
    # 网格再动阈值)
    assert anchored >= 30, f"property 网格退化:仅 {anchored} 案有锚(<30)"


def test_property_anchor_audit_single_field():
    """P5 授权单字段审计:reveal 事件键集 ⊆ 既有键 ∪ {anchor_numbers}(Q6 只增不改,
    不造新事件类型);锚键出现 ⟺ 授权轮。"""
    rng = random.Random(20260919)
    for i in range(40):
        seed, _pool = _synth_seed(rng)
        turn = _drive(seed, stuck_rounds=2)
        for event in _reveal_events(turn):
            assert set(event) <= _ALLOWED_EVENT_KEYS, f"case{i}: 新键 {set(event) - _ALLOWED_EVENT_KEYS}"
            if "anchor_numbers" in event:  # 单方向:锚 ⟹ 非首次 stuck(授权 ⟸ 由 P1 网格+七种子钉)
                assert event["hint_level"] > 1, f"case{i}: 首次 stuck 带锚"


def _class_seed(answer: str, ladder: list[str]) -> dict:
    # #382 PR-C:显式给 analysis(等值类钉的 value 形态——「8组,余5人」「50%」
    #「-5」——含切片分隔符/符号,不经 step 文本反解,保 value 原样入梯)。
    steps = [{"step": f"第{i + 1}步:先处理这一项", "value": v} for i, v in enumerate(ladder)]
    analysis = "。".join(f"先算这一步的结果是{v}" for v in ladder) + "。"
    return {"session": {"question": {"text": "仓库里有 12 箱和 9 箱,问合计与余量。",
                                     "answer": answer},
                        "learner": {"grade": "四年级", "answer_status": "incorrect"},
                        "steps": steps},
            "analysis": analysis}


def test_gap_thousands_separator_normalized():
    """千分位(补):answer「1,000」归一池={1000},value「1000」撞池即禁——
    不归一则池={1,0} 与 {1000} 交空 → 锚漏终答(本测试=漏 vector 的关死钉)。
    #382 PR-C:analysis 切片取值即「1000」(纯数字),公开路径可复现。"""
    turn = _drive(_class_seed("共 1,000 千克", ["9", "1000"]), stuck_rounds=2)
    assert not any(e.get("anchor_numbers") for e in _reveal_events(turn))


def test_gap_multi_number_value_fail_closed():
    """单数值门槛(补):多位值「8组,余5人」={8,5} 渲染「得到 8、5」破相 → 禁
    (answer「35人」池={35} 本不撞,禁来自门槛非重叠)。#382 PR-C:analysis 切片
    取值恒单数字段,多位值形态只经会话直构可造——保 `_current_step_anchor_numbers`
    的单数值门槛钉(unit 面,同 test_property_invariants 直构口径)。"""
    from edu_agent.agents.small_lecturer import LearnerSession, _reveal_stuck_hint

    session = LearnerSession(
        question={"text": "仓库里有 12 箱和 9 箱,问合计与余量。", "answer": "共 35 人"},
        learner={"grade": "四年级", "answer_status": "incorrect"},
        steps=[{"step": "先算这一项", "value": "9", "provenance": "analysis"},
               {"step": "再算分组结果", "value": "8组,余5人", "provenance": "analysis"}])
    for _ in range(2):  # 首次 stuck 揭第 1 级;再次 stuck 到多位值级
        out = _reveal_stuck_hint(session)
    assert isinstance(out, str)
    assert not any(e.get("anchor_numbers") for e in session.guard_events
                   if e.get("branch") == "reveal")


def test_gap_percent_sign_conservative():
    """百分号(不补,回归钉):「50%」→{50} 双侧一致,撞池即禁(行为与 V1 合并版一致)。"""
    turn = _drive(_class_seed("占 50%", ["9", "50%"]), stuck_rounds=2)
    assert not any(e.get("anchor_numbers") for e in _reveal_events(turn))


def test_gap_negative_sign_blind():
    """负数(不补,回归钉):「-5」→{5} 符号双侧一致剔除,撞池即禁=保守正确。"""
    turn = _drive(_class_seed("变化 -5 度", ["9", "-5"]), stuck_rounds=2)
    assert not any(e.get("anchor_numbers") for e in _reveal_events(turn))
