"""Trusted Completion Gate B 段:Kernel transition gate(#414 设计件 v3.1 §四/§五)。

断言即规格(gateway 对象注入,零网络零端口)。五必测+红灯演练:
① 无 evidence 的 completed 迁移被拒(含题库无 answer_spec 声明面的 fail-closed
   形态——现网全量题库即此形态,缺口清单见 PR 描述留人审);
② 有 evidence 且其他条件满足 → 迁移允许(裸答案「25.8度」/声明式「答案是6」/
   选项字母「B」——干净正例,不碰 #416 收窄中的输入语法边界);
③ 有 evidence 但其他条件不满足 → 仍不迁移(必要非充分,§一:evidence 不是
   状态跳转器,ready_to_confirm 等既有条件照旧);
④ stale turn evidence 不授权(§二 turn-scoped/ephemeral);
⑤ summary/模型文本路径无法创造 evidence(§二不可构造面:LLM 输出/summary/
   guard 事件/教师转述均无构造权)。

测试题的 answer_spec 是**测试本地声明面**(B 段组装方契约的输入形态);现网
题库(partner 263/snapshot/seed/外部 6846)answer 均为纯字符串、无此声明面——
kernel 对缺声明面一律 fail-closed(①-a 钉死),不由 answer 字面猜类型。
"""

from __future__ import annotations

from dataclasses import replace

from edu_agent.agents.small_lecturer import (
    CompletionEvidence,
    EvidenceProvenance,
    LearnerSession,
    _answer_spec,
    _completion_authorized,
    finish,
    reply,
    start,
)
from edu_agent.store import FileSessionStore

from teachkit import FakeGateway


# ---------- 测试题(干净正例;answer_spec = 测试本地声明面) ----------

# numeric_with_unit:单位「度」在温度族(维度安全 token 相等),裸答案+单位形态
TEMPERATURE_Q = {
    "text": "海拔每升高100m,气温平均下降3/5℃。A处气温大约是多少?",
    "answer": "25.8度",
    "answer_spec": {"answer_type": "numeric_with_unit"},
    "analysis": "", "knowledge_points": [],
}
# numeric_with_unit:无单位答案,声明式模板「答案是6」形态
CANDY_Q = {
    "text": "小明有一些糖,给了同学3颗后还剩3颗,他原有多少颗糖?",
    "answer": "6",
    "answer_spec": {"answer_type": "numeric_with_unit"},
    "analysis": "", "knowledge_points": [],
}
# choice_letter:题面选项字母表 = letter_choices 声明(合法集)
CHOICE_Q = {
    "text": "下面哪个数是质数? A.9 B.11 C.15 D.21",
    "answer": "B",
    "answer_spec": {"answer_type": "choice_letter",
                    "letter_choices": ["A", "B", "C", "D"]},
    "analysis": "", "knowledge_points": [],
}
# 复合题(多槽):设计 §三红线——不造 spec、任何局部槽命中不构造 evidence
CHICKEN_Q = {
    "text": "鸡和兔一共 8 只,共有 26 只脚。鸡和兔各有多少只?",
    "answer": "鸡3只,兔5只", "analysis": "", "knowledge_points": [],
}


def _open(text):
    return {"reply": text, "acceptable": True, "steps": []}


def _tutor(text, ready=False):
    return {"reason": "引导学生", "reply": text, "ready_to_confirm": ready,
            "cited_numbers": []}


def _gate_rejections(session):
    return [event for event in session.guard_events
            if event.get("branch") == "completion_gate_rejected"]


# ---------- ① 无 evidence 的 completed 迁移被拒 ----------

def test_finish_rejected_without_spec_declaration():
    """①-a 题库 schema 缺 answer_spec 声明面(现网全量题库形态)→ 无法组装
    spec → 无 evidence → completed 迁移被拒:学生确实说出了答案值、模型也判停,
    门照样拒(fail-closed,确定性)。session 保持 ready_to_confirm、零模型调用、
    埋点 completion_gate_rejected 带轮号。"""
    gateway = FakeGateway([_open("这道题要我们求什么?"),
                           _tutor("我们把思路理清楚了。", ready=True)])
    question = dict(TEMPERATURE_Q)
    question.pop("answer_spec")            # 缺声明面 = 现网题库形态
    session = start(question, {"grade": "六年级"}, gateway=gateway).session
    turn = reply(session, "25.8度", gateway=gateway)
    assert turn.state == "ready_to_confirm" and turn.ready_to_confirm is True
    assert session.completion_evidence is None
    requests_before = len(gateway.requests)
    summary = finish(session, gateway=gateway)
    assert summary.status == "needs_review" and "继续" in summary.text
    assert session.state == "ready_to_confirm" and not session.finished
    assert len(gateway.requests) == requests_before   # 拒绝先于 summary 模型调用
    assert _gate_rejections(session) == [{"branch": "completion_gate_rejected", "turn": 1}]


def test_finish_rejected_when_student_missed_answer():
    """①-b 声明面在场但本轮学生答错值(24度≠25.8度)→ 无 evidence → 拒。"""
    gateway = FakeGateway([_open("这道题要我们求什么?"),
                           _tutor("我们把思路理清楚了。", ready=True)])
    session = start(dict(TEMPERATURE_Q), {"grade": "六年级"},
                    gateway=gateway).session
    reply(session, "24度", gateway=gateway)
    assert session.completion_evidence is None
    summary = finish(session, gateway=gateway)
    assert summary.status == "needs_review" and session.state == "ready_to_confirm"
    assert _gate_rejections(session)


def test_close_on_final_statement_blocked_without_evidence():
    """①-c 终述收束路径同门:复合题(无 spec,§三红线:多槽整体不判定)+ 学生
    终述(数字焦点命中,_is_final_statement 通过)→ 不 completed——Turn 状态
    如实 ready_to_confirm,session 不落终态;incorrect 档下 finish 本会调模型
    总结,被门先拦(请求数不增)。"""
    gateway = FakeGateway([_open("你现在觉得鸡和兔各有多少只?"),
                           _tutor("我们把思路理清楚了。", ready=True)])
    session = start(dict(CHICKEN_Q), {"grade": "六年级", "answer_status": "incorrect"},
                    gateway=gateway).session
    confirmed = reply(session, "兔有10除以2等于5只,鸡有3只。", gateway=gateway)
    assert confirmed.state == "ready_to_confirm"
    requests_before = len(gateway.requests)
    turn = reply(session, "所以鸡有3只,兔有5只,验算3乘2加5乘4等于26只脚。",
                 gateway=gateway)
    assert turn.state == "ready_to_confirm" and not session.finished
    assert session.state == "ready_to_confirm" and session.summary is None
    assert len(gateway.requests) == requests_before   # 收束未消费模型调用
    assert _gate_rejections(session) == [{"branch": "completion_gate_rejected", "turn": 2}]


# ---------- ② 有 evidence 且其他条件满足 → 迁移允许 ----------

def test_finish_completes_with_bare_answer_evidence():
    """②-a 裸答案+单位「25.8度」→ 当轮 evidence;ready + correct + 无卡点 →
    零调用模板 completed(既有迁移条件照旧——门只放行,不自行触发)。"""
    gateway = FakeGateway([_open("这道题要我们求什么?"),
                           _tutor("我们把思路理清楚了。", ready=True)])
    session = start(dict(TEMPERATURE_Q),
                    {"grade": "六年级", "answer_status": "correct"},
                    gateway=gateway).session
    turn = reply(session, "25.8度", gateway=gateway)
    assert turn.state == "ready_to_confirm"
    evidence = session.completion_evidence
    assert evidence is not None and evidence.turn_id == 1
    assert evidence.answer_type == "numeric_with_unit"
    assert evidence.provenance.ground_truth_ref == "25.8度"
    summary = finish(session, gateway=gateway)
    assert summary.status == "completed" and session.state == "completed"
    assert len(gateway.requests) == 2            # open + reply;finish 零调用
    assert not _gate_rejections(session)         # 放行路径零埋点(只记拒绝)


def test_finish_completes_with_claim_template_evidence():
    """②-b 声明式模板「答案是6」(白名单句法形态)→ evidence → completed。"""
    gateway = FakeGateway([_open("这道题要我们求什么?"),
                           _tutor("我们把思路理清楚了。", ready=True)])
    session = start(dict(CANDY_Q),
                    {"grade": "三年级", "answer_status": "correct"},
                    gateway=gateway).session
    reply(session, "答案是6", gateway=gateway)
    assert session.completion_evidence is not None
    assert session.completion_evidence.provenance.matched_span == "6"
    assert finish(session, gateway=gateway).status == "completed"


def test_finish_completes_with_choice_letter_evidence():
    """②-c 选项字母「B」(letter_choices 声明的合法集内)→ evidence → completed。"""
    gateway = FakeGateway([_open("这道题要我们求什么?"),
                           _tutor("我们把思路理清楚了。", ready=True)])
    session = start(dict(CHOICE_Q),
                    {"grade": "五年级", "answer_status": "correct"},
                    gateway=gateway).session
    reply(session, "B", gateway=gateway)
    assert session.completion_evidence is not None
    assert session.completion_evidence.answer_type == "choice_letter"
    assert finish(session, gateway=gateway).status == "completed"


def test_close_on_final_statement_completes_with_current_turn_evidence():
    """②-d 终述收束正向锚:ready 态 + 终述(「所以答案是25.8度」)→ 当轮
    evidence → close 直接 completed,零模型调用(①-c 的镜像:同一收束路径,
    有当轮证据即放行——「verified 后同轮终局」,§二)。"""
    gateway = FakeGateway([_open("这道题要我们求什么?"),
                           _tutor("我们把思路理清楚了。", ready=True)])
    session = start(dict(TEMPERATURE_Q),
                    {"grade": "六年级", "answer_status": "correct"},
                    gateway=gateway).session
    confirmed = reply(session, "我算出来了", gateway=gateway)
    assert confirmed.state == "ready_to_confirm"
    requests_before = len(gateway.requests)
    turn = reply(session, "所以答案是25.8度", gateway=gateway)
    assert turn.state == "completed" and session.finished
    assert len(gateway.requests) == requests_before   # 收束零模型调用
    assert session.completion_evidence.turn_id == 2
    assert not _gate_rejections(session)


# ---------- ③ 必要非充分:evidence 不自行触发迁移 ----------

def test_evidence_alone_does_not_complete_without_ready_state():
    """③ 有 evidence 但模型判未讲清(ready_to_confirm=False)→ 正常 dialogue
    轮;finish 照旧 needs_review——evidence 不是状态跳转器(§一),门不把
    「有证据」放大成「完成」。"""
    gateway = FakeGateway([_open("这道题要我们求什么?"),
                           _tutor("我们再看看你的思路。", ready=False),
                           _tutor("你的思路讲清楚了。", ready=True)])
    session = start(dict(TEMPERATURE_Q), {"grade": "六年级"},
                    gateway=gateway).session
    turn = reply(session, "25.8度", gateway=gateway)
    assert turn.state == "dialogue" and session.completion_evidence is not None
    summary = finish(session, gateway=gateway)
    assert summary.status == "needs_review" and not session.finished
    assert not _gate_rejections(session)     # 未达 ready:既有路径拒绝,非门拒绝


def test_finish_state_gate_rejection_records_event():
    """state 门拒埋点(用户裁 2026-09-24 ①:observation 非 promotion gate):
    state≠ready_to_confirm 的 finish 走既有 needs_review——落 state_gate_rejected
    埋点(state 值+轮号),与 completion_gate_rejected 对称且可区分;纯观测,
    不进任何判定/PASS 口径。"""
    gateway = FakeGateway([_open("这道题要我们求什么?"),
                           _tutor("我们先看已知条件。", ready=False)])
    session = start(dict(TEMPERATURE_Q), {"grade": "六年级"}, gateway=gateway).session
    turn = reply(session, "我先想想。", gateway=gateway)
    assert turn.state == "dialogue"
    requests_before = len(gateway.requests)
    summary = finish(session, gateway=gateway)
    assert summary.status == "needs_review" and not session.finished
    assert session.state == "dialogue"
    assert len(gateway.requests) == requests_before   # 拒绝先于任何模型调用
    assert [event for event in session.guard_events
            if event.get("branch") == "state_gate_rejected"] == [
        {"branch": "state_gate_rejected", "state": "dialogue", "turn": 1}]
    assert not _gate_rejections(session)   # state 门与 completion 门两拒可分诊


# ---------- ④ turn-scoped:stale evidence 不授权 ----------

def test_stale_turn_evidence_does_not_authorize():
    """④ t1 学生说出答案(evidence=t1)但未 ready;t2 学生没再说答案 → t2 无
    evidence → finish 拒——t1 证据跨轮失效(§二 ephemeral);对照组:同样流程
    但 t2 重申答案 → 当轮证据成立 → completed。同一答案,不同轮,两个结局。"""
    # 对照组:t2 重申答案 → completed
    gateway = FakeGateway([_open("这道题要我们求什么?"),
                           _tutor("我们再看看你的思路。", ready=False),
                           _tutor("你的思路讲清楚了。", ready=True)])
    session = start(dict(TEMPERATURE_Q),
                    {"grade": "六年级", "answer_status": "correct"},
                    gateway=gateway).session
    reply(session, "25.8度", gateway=gateway)          # t1:evidence 在场,未 ready
    reply(session, "所以答案是25.8度", gateway=gateway)  # t2:重申 → 当轮新证据
    assert session.completion_evidence.turn_id == 2
    assert finish(session, gateway=gateway).status == "completed"
    # 实验组:t2 未再说答案 → t1 证据 stale → 拒
    gateway = FakeGateway([_open("这道题要我们求什么?"),
                           _tutor("我们再看看你的思路。", ready=False),
                           _tutor("你的思路讲清楚了。", ready=True)])
    session = start(dict(TEMPERATURE_Q),
                    {"grade": "六年级", "answer_status": "correct"},
                    gateway=gateway).session
    reply(session, "25.8度", gateway=gateway)          # t1:evidence
    ready = reply(session, "我做完啦", gateway=gateway)  # t2:无答案 → 覆写 None
    assert ready.state == "ready_to_confirm"
    assert session.completion_evidence is None
    summary = finish(session, gateway=gateway)
    assert summary.status == "needs_review" and session.state == "ready_to_confirm"
    assert _gate_rejections(session) == [{"branch": "completion_gate_rejected", "turn": 2}]


def test_completion_authorized_requires_current_turn_id():
    """④-b 门判据单钉(白盒,构造期注入,运行时 LLM/summary 无此构造权):
    turn_id ≠ 当前学生轮号的 evidence 恒不授权——跨轮 stale 的结构性防线,
    不依赖生产端覆写行为。"""
    evidence = CompletionEvidence(
        source="student", turn_id=1, answer_type="numeric_with_unit",
        verdict="matched", verifier="numeric_with_unit",
        provenance=EvidenceProvenance(ground_truth_ref="25.8度", matched_span="25.8度"))
    session = LearnerSession(question=TEMPERATURE_Q, learner={"grade": "六年级"})
    session.history = [{"role": "user", "content": "25.8度"},
                       {"role": "assistant", "content": "嗯"},
                       {"role": "user", "content": "我做完啦"},
                       {"role": "assistant", "content": "好"}]
    session.completion_evidence = evidence                     # t1 证据,t2 在场
    assert not _completion_authorized(session)
    session.completion_evidence = replace(evidence, turn_id=2)  # 当轮证据
    assert _completion_authorized(session)
    session.completion_evidence = None                          # 无证据
    assert not _completion_authorized(session)


# ---------- ⑤ 不可构造面:模型文本/summary 无构造权 ----------

def test_model_text_cannot_create_evidence():
    """⑤ 问句猜答(「是25.8度吗?」)不构成证据——value_match ≠ claim:数值
    出现(旧判停闸按数字包含豁免泄露)但学生未声明它为答案;tutor 回复原样
    引 25.8度 到学生可见面,ready=True → finish 仍拒,completion_evidence
    恒 None(§二:LLM 输出/教师转述无构造权)。"""
    gateway = FakeGateway([_open("这道题要我们求什么?"),
                           _tutor("对,就是25.8度,你算出来了。", ready=True)])
    session = start(dict(TEMPERATURE_Q), {"grade": "六年级"},
                    gateway=gateway).session
    turn = reply(session, "是25.8度吗?", gateway=gateway)
    assert turn.state == "ready_to_confirm"      # 模型判停照旧(生成层不知门)
    assert session.completion_evidence is None   # 问句形态:无证据
    summary = finish(session, gateway=gateway)
    assert summary.status == "needs_review" and session.state == "ready_to_confirm"
    assert _gate_rejections(session) == [{"branch": "completion_gate_rejected", "turn": 1}]


def test_summary_payload_never_consumed_without_evidence():
    """⑤-b/红灯演练:gateway 剧本里摆好「summary: 完成」的模型输出——门在
    summary 模型调用**之前**拒绝,剧本根本不被消费(模型输出无 transition
    authority;绕过 gate 直推 completed 的路径在此被结构性截断)。"""
    gateway = FakeGateway([_open("这道题要我们求什么?"),
                           _tutor("我们把思路理清楚了。", ready=True),
                           {"summary": "你完整解出了 A 处气温,完成。"}])
    session = start(dict(TEMPERATURE_Q), {"grade": "六年级"},
                    gateway=gateway).session
    reply(session, "我猜是二十多度", gateway=gateway)   # 未命中:无 evidence
    requests_before = len(gateway.requests)
    summary = finish(session, gateway=gateway)
    assert summary.status == "needs_review"
    assert len(gateway.requests) == requests_before   # summary 剧本未被消费
    assert session.state == "ready_to_confirm" and session.summary is None


# ---------- 组装方契约(fail-closed,§三 P1-①) ----------

def test_answer_spec_assembly_is_fail_closed():
    """组装契约白盒钉:无 answer_spec / 类型不在六窄面(复合/开放/未知)/
    ground_truth 空 → None;**不从 answer 字面猜类型**(true_false 类型来自
    schema 声明,非文字猜——「对」「B」「x=6」没有声明面就都不判)。"""
    assert _answer_spec({"text": "t", "answer": "25.8度"}) is None          # 缺声明面
    assert _answer_spec({"text": "t", "answer": "鸡3只兔5只",
                         "answer_spec": {"answer_type": "composite"}}) is None
    assert _answer_spec({"text": "t",
                         "answer_spec": {"answer_type": "numeric_with_unit"}}) is None
    spec = _answer_spec(dict(TEMPERATURE_Q))
    assert spec is not None and spec.answer_type == "numeric_with_unit"
    assert spec.ground_truth == "25.8度"          # 缺省回退 question["answer"]
    assert spec.aliases == () and spec.unit_optional is False
    assert _answer_spec(dict(CHOICE_Q)).letter_choices == ("A", "B", "C", "D")


def test_answer_spec_counting_unit_grants_unit_optional():
    """#416 C-3a(spec 组装侧,verifier 零改动):truth 单位 ∈ 计数单位封闭集
    {名只本人个棵张条辆件次岁页种块支间道门步} → unit_optional=True(计数
    单位语义下学生裸值可收,4248「36减24应该是12」形态);「分」不入集(度量
    歧义,维持裸 token 精确匹配);度量单位(度)与非单位答案不授权。"""
    counting = _answer_spec({"text": "t", "answer": "12名",
                             "answer_spec": {"answer_type": "numeric_with_unit",
                                             "ground_truth": "12名"}})
    assert counting is not None and counting.unit_optional is True
    minutes = _answer_spec({"text": "t", "answer": "90分",
                            "answer_spec": {"answer_type": "numeric_with_unit",
                                            "ground_truth": "90分"}})
    assert minutes is not None and minutes.unit_optional is False
    assert _answer_spec(dict(TEMPERATURE_Q)).unit_optional is False   # 度量单位
    assert _answer_spec(dict(CANDY_Q)).unit_optional is False         # 无单位答案


# ---------- 持久化往返(api 层跨进程 confirm 链路) ----------

def test_evidence_survives_store_roundtrip(tmp_path):
    """store 往返:reply 产证据落盘 → load 回类型化 CompletionEvidence →
    finish completed(service._rehydrate 后门不失效:重启后的 confirm 仍由
    当轮证据授权)。"""
    store = FileSessionStore(tmp_path)
    gateway = FakeGateway([_open("这道题要我们求什么?"),
                           _tutor("我们把思路理清楚了。", ready=True)])
    session = start(dict(TEMPERATURE_Q),
                    {"grade": "六年级", "answer_status": "correct"},
                    gateway=gateway).session
    reply(session, "25.8度", gateway=gateway)
    store.save(session)
    loaded = store.load(session.session_id)
    assert isinstance(loaded.completion_evidence, CompletionEvidence)
    assert loaded.completion_evidence == session.completion_evidence
    assert finish(loaded, gateway=gateway).status == "completed"
