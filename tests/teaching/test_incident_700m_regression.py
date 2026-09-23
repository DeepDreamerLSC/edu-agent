"""#382 PR-D:700m 生产事故冻结为 production regression(架构师总裁定 2026-09-20)。

事故正本:calibration-private/incident-20260920-700m-kernel-closing.md(逐轮表 +
尾部 GatewayError×2 / 同句重发×2)。冻结面 = 事故的四维度,断言即规格:

  · repeat/stuck 语义(P0-1 / PR-A):Tutor repeat / guard failure / regen /
    fallback / Gateway 一律不得写 session.stuck——系统状态 ≠ 学生状态;
  · 收束原子性(P0-2 / PR-B):任何模型/Gateway 调用抛异常后,本轮 Session
    必须保持调用前状态(history/state/summary/session_version/hint_level 全一致),
    同消息重试不得重复 history;
  · trusted ladder 边界(P0-3 / PR-C):非题库 analysis 来源(模型生成)的阶梯
    不得进 deterministic reveal;
  · 行为面「学生首答正确不被无端质疑」:教学行为属 Prompt/Model 层,§11 禁令
    明确本波不动——以 skip 标记占位,待 Prompt/Model 层修复后翻绿(不是永绿,
    翻绿即修复证据)。

另两条事故直接派生的度量口径(裁定 §执行序列 4):
  · Gateway failure turn 从 trajectory 指标排除(failed 轮不是教学轮);
  · 用户同句重发 ≠ 教学复读(infra 重试不进复读口径)。

本电池是**行为合同**,分两档(仓库 known_red 同款机制,先例 test_scenario_corpus):
  · 已修面(guard/Gateway 不置 stuck 的合规路径、analysis trusted 通道、两条
    度量口径):真实断言,基底即绿,永久防回归;
  · 待修面六条事故断言:原全部 `xfail(strict=True)`;PR-A/B 合入(main@82157c8)后
    PR-A/B/C 全合入(main@46ef6d9)后六条全转绿,全部翻标记(2026-09-20,断言本体一字未动)
    (基底 origin/main@27d8306 实测 6 红,红灯证据逐条落 PR 描述);PR-A/B/C
    合入后转绿 → XPASS(strict)把 CI 变红,**逼人翻掉标记**(known_red→guarded
    同款翻转),断言本体一字不动即恢复守卫。

与 PR-A/B/C 各自的单元回归互补——这里从**事故剧本**逐轮驱动(题库 6a61b3d4
逐字),任何一条面被未来改掉,本文件先红。
"""

from __future__ import annotations

import pytest

from edu_agent.agents.small_lecturer import _is_repeat, reply, start
from edu_agent.evals import _tutor_turns
from edu_agent.gateway import FailureType, GatewayError

from teachkit import FakeGateway

# ---------------------------------------------------------------------------
# 事故题面(题库 6a61b3d4 逐字):answer 含 A/B/山顶三处气温;analysis 只有
# 方法叙述无海拔数字(_analysis_steps 切不出 ≥2 步 → 阶梯只能来自模型生成,
# 这正是事故里「A处海拔是500米」读图错误的来源,见事故转录第 6 轮)。
# ---------------------------------------------------------------------------
QUESTION_700M = {
    "text": "海拔每升高100m，气温平均下降3/5℃。图中A处、B处和山顶的气温大约分别是多少？",
    "answer": "A处气温约25.8℃，B处气温约24℃，山顶气温约22.8℃。",
    "analysis": "先由图读出大致海拔，再按每升高100m下降3/5℃计算。",
    "knowledge_points": [],
}
GRADE = "六年级"

# 模型生成的错误阶梯(事故实录形态:A 处海拔被读成 500 米;B 1000 米)。
# 末级 value=25.8 触答案焦点 → 过 _store_steps 外题阶梯门(该门只拦「整副不触
# 焦点」,拦不住「触焦点但读图错误」——权威源问题正是 PR-C 的修面)。
MODEL_LADDER_WRONG_500M = [
    {"step": "从图中读出A处海拔是500米", "value": "500"},
    {"step": "B处海拔是1000米,山顶是1200米", "value": "1200"},
    {"step": "A处气温:27-500/100×3/5=25.8℃", "value": "25.8"},
]

# 学生首答(事故第 1 轮,完整正确含推理:「A在700米…降了6/5度…25.8度」)。
STUDENT_FIRST_CORRECT = "这道题我会：A在700米，降了6/5度，所以A处是25.8度。"
# 被质疑后的重申(事故第 5 轮:复读触发器点亮的那句)。
STUDENT_RESTATE_AFTER_DOUBT = "700米气温降了6/5度。"
# 孩子纠正导师(事故第 7 轮)。
STUDENT_CORRECTS_TUTOR = "你读的不对，A在700米，B在1000米。"

# 事故尾部实录:同一句经 App 重发两次 + GatewayError×2(用户重发,非新教学轮)。
GATEWAY_SENTENCE = "高200米，然后27-6/5是25.8度"


def _open_payload(reply_text: str, steps: list[dict]) -> dict:
    return {"acceptable": True, "transcription": "", "steps": steps, "reply": reply_text}


def _tutor_payload(reply_text: str, ready: bool = False) -> dict:
    return {"reply": reply_text, "ready_to_confirm": ready, "cited_numbers": []}


class ExplodingGateway(FakeGateway):
    """tutor 剧本耗尽至 `explode_remaining` 时抛 GatewayError(环境类
    upstream_5xx,事故实录「出错了: 服务暂不可用:GatewayError」)——半提交
    现场注入器;vision 角色与耗尽前的调用照常出牌。"""

    def __init__(self, tutor_payloads: list[dict], explode_remaining: int) -> None:
        super().__init__(tutor_payloads=tutor_payloads)
        self.explode_remaining = explode_remaining
        self.gateway_errors = 0

    def invoke(self, request):
        if (request.role == "tutor"
                and len(self.tutor_queue) == self.explode_remaining):
            self.gateway_errors += 1
            raise GatewayError(FailureType.UPSTREAM_5XX, "服务暂不可用")
        return super().invoke(request)


def _session_after_first_exchange(gateway: FakeGateway):
    """start + 学生首答 + 导师追问(事故第 1-2 轮形态)。"""
    first = start(dict(QUESTION_700M), {"grade": GRADE}, gateway=gateway)
    session = first.session
    reply(session, STUDENT_FIRST_CORRECT, gateway=gateway)
    return session


# =========================================================================== #
# 维度一(P0-1 / PR-A):repeat / stuck 语义污染
# =========================================================================== #


def test_tutor_repeat_fallback_never_marks_student_stuck():
    """事故链冻结:Tutor 复读(重生成仍复读 → 阶梯揭示兜底)是**系统状态**,
    不得写 session.stuck——错误的 stuck 会把零调用收束变成依赖 Gateway 的收束
    (reliability 不变量)。红灯证据:基底 kernel.py `_repeat_refine` 在 reveal
    兜底后置 `session.stuck = True`(2026-09-20 基底实测红)。"""
    from edu_agent.agents.small_lecturer import FIRST_QUESTION_COLLECT

    gateway = FakeGateway(tutor_payloads=[
        _open_payload(FIRST_QUESTION_COLLECT, MODEL_LADDER_WRONG_500M),
        _tutor_payload(FIRST_QUESTION_COLLECT),   # 模型复读首问模板
        _tutor_payload(FIRST_QUESTION_COLLECT),   # 重生成仍复读 → 揭示兜底
    ])
    session = _session_after_first_exchange(gateway)
    turn = reply(session, STUDENT_RESTATE_AFTER_DOUBT, gateway=gateway)
    assert session.stuck is not True, (
        "Tutor repeat 的 reveal 兜底是系统状态,不得污染学生卡点标记(P0-1)")


def test_guard_hard_degradation_never_marks_student_stuck():
    """护栏硬降级(答案泄露纯 block)是 tutor 质量问题,不是学生卡住——
    系统状态 ≠ 学生状态(guard_events 已记系统异常,不占学生状态位)。
    红灯证据:基底 `_record_event` 在 mode=blocked 时置 `session.stuck = True`
    (kernel.py L441,2026-09-20 基底实测红)。前导零「022.8」形态检得出、
    掩不掉(词边界护体)→ round-2 纯 block,同 test_leak_gate_numeric ④口径。"""
    # 前导零泄露句:答案焦点 22.8(山顶)以「022.8」出现 → PURE_BLOCK 硬降级
    leak_reply = "山顶气温是022.8度,直接记住这个数就行。"
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("这道题你怎么想?先说说看。", MODEL_LADDER_WRONG_500M),
        _tutor_payload(leak_reply),
        _tutor_payload(leak_reply),  # 重生成仍泄露 → 纯 block 硬降级
    ])
    session = _session_after_first_exchange(gateway)
    blocked = [e for e in session.guard_events if e.get("mode") == "blocked"]
    assert blocked, "前置自检:泄露句必须走纯 block 硬降级路径(否则本用例空转)"
    assert session.stuck is not True, (
        "guard failure 的硬降级是系统状态,不得写学生卡点标记(P0-1)")


def test_gateway_error_never_marks_student_stuck():
    """GatewayError 冒泡路径不得顺手置 stuck(系统故障 ≠ 学生卡住)。"""
    gateway = ExplodingGateway(
        tutor_payloads=[
            _open_payload("这道题你怎么想?先说说看。", MODEL_LADDER_WRONG_500M),
            _tutor_payload("那你是怎么从500米27℃推到700米的?"),
        ],
        explode_remaining=0,  # 剧本耗尽:首答之后的 tutor 调用即 GatewayError
    )
    session = _session_after_first_exchange(gateway)
    with pytest.raises(GatewayError):
        reply(session, STUDENT_RESTATE_AFTER_DOUBT, gateway=gateway)
    assert session.stuck is not True, "Gateway 故障不得写学生卡点标记(P0-1)"


def test_student_own_stuck_signal_still_marks_stuck():
    """合法路径保留:学生本人明确 stuck 信号(「我不会」)仍置 stuck——
    PR-A 删的是系统写入,不是学生信号通道。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("这道题你怎么想?先说说看。", MODEL_LADDER_WRONG_500M),
    ])
    session = _session_after_first_exchange(gateway)
    reply(session, "我不会", gateway=gateway)
    assert session.stuck is True


# =========================================================================== #
# 维度二(P0-2 / PR-B):收束失败原子性
# =========================================================================== #


def test_gateway_error_on_close_leaves_session_untouched():
    """事故尾部冻结(原始形态,700m 题=三槽复合答案):ready 态 + 学生终述 →
    收束路径 finish() 调 Gateway 抛错 → 本轮 Session 必须保持调用前状态
    (history/state/summary/session_version/hint_level 逐字段一致)。红灯证据:
    基底 `_close_on_final_statement` 先 append 学生消息再 finish(kernel.py
    L212),GatewayError 冒泡后 history 已多一条半提交(2026-09-20 基底实测红)。

    Gate B 段(#414 §四)改据:completed 迁移需当轮 CompletionEvidence,700m 题
    answer 为三槽复合(A/B/山顶三值,§三红线:多槽整体不判定)→ 无 evidence →
    finish 在 **Gateway 调用之前**被门拒(确定性,零模型调用),爆炸位不再触达:
    原子性回归的机制面(GatewayError 回滚)由 test_kernel_restate.py 同款测试
    以 eligible 门题(answer_spec 声明面)承接;本测改钉事故题的新契约——
    收束被门拒、session 保持 ready_to_confirm、零 Gateway 消耗、埋点在案。"""
    final_statement = "所以A处是25.8度，B处24度，山顶22.8度，都算出来了。"
    gateway = ExplodingGateway(
        tutor_payloads=[
            _open_payload("这道题你怎么想?先说说看。", MODEL_LADDER_WRONG_500M),
            # 第二次 tutor 调用:模型判 ready(收束前置态)
            _tutor_payload("你把三处气温都说出来了。", ready=True),
        ],
        explode_remaining=0,  # 剧本耗尽:若无门,收束 finish 的 Gateway 调用会抛错
    )
    first = start(dict(QUESTION_700M), {"grade": GRADE}, gateway=gateway)
    session = first.session
    confirmed = reply(session, STUDENT_CORRECTS_TUTOR, gateway=gateway)
    assert confirmed.state == "ready_to_confirm"
    requests_before = len(gateway.requests)
    turn = reply(session, final_statement, gateway=gateway)   # 不再抛 GatewayError
    assert turn.state == "ready_to_confirm" and not session.finished
    assert session.state == "ready_to_confirm" and session.summary is None
    assert len(gateway.requests) == requests_before           # 门先于 Gateway(零消耗)
    assert any(event.get("branch") == "completion_gate_rejected"
               for event in session.guard_events)


def test_user_resend_after_gateway_error_no_duplicate_history():
    """事故尾部直接冻结(原始形态):同一句重发不得重复 history——半提交的
    history 里躺着未回应的学生消息,重试再 append 一条即双记(事故实录:同句
    在 App 界面出现两次)。

    Gate B 段(#414 §四)改据:700m 题=三槽复合 → 无当轮 evidence → 收束被门
    拒于 Gateway 之前,重发不再撞 GatewayError(见上测改据);本测改钉事故题的
    新契约——每次重发是**完整提交的干净轮**(user+assistant 成对、version+1,
    无半提交),零 Gateway 消耗,门埋点逐轮在案。GatewayError 半提交回滚的原
    机制面由 test_kernel_restate.py 以 eligible 门题承接。"""
    final_statement = "所以A处是25.8度，B处24度，山顶22.8度，都算出来了。"
    gateway = ExplodingGateway(
        tutor_payloads=[
            _open_payload("这道题你怎么想?先说说看。", MODEL_LADDER_WRONG_500M),
            _tutor_payload("你把三处气温都说出来了。", ready=True),
        ],
        explode_remaining=0,
    )
    first = start(dict(QUESTION_700M), {"grade": GRADE}, gateway=gateway)
    session = first.session
    reply(session, STUDENT_CORRECTS_TUTOR, gateway=gateway)
    requests_before = len(gateway.requests)
    version_before = session.session_version
    for _ in range(2):  # 事故实录形态:同句重发 ×2(现被门确定性拒,零 Gateway)
        turn = reply(session, final_statement, gateway=gateway)
        assert turn.state == "ready_to_confirm"
    user_contents = [m["content"] for m in session.history if m["role"] == "user"]
    assistant_count = sum(1 for m in session.history if m["role"] == "assistant")
    # 每次重发一条 user 必配一条 assistant(成对完整提交,无半提交双记)
    assert user_contents.count(final_statement) == 2
    assert assistant_count == len(user_contents)
    assert session.session_version == version_before + 2
    assert len(gateway.requests) == requests_before           # 门先于 Gateway
    assert sum(1 for event in session.guard_events
               if event.get("branch") == "completion_gate_rejected") == 2


# =========================================================================== #
# 维度三(P0-3 / PR-C):reveal 权威源边界
# =========================================================================== #


def test_model_generated_ladder_never_reaches_deterministic_reveal():
    """事故第 6 轮冻结:reveal 说「A处海拔是500米」——题库 analysis 无海拔
    数字(question_image=null),该阶梯只能来自 start() 模型生成;模型生成
    ladder = untrusted planning artifact,不得进 deterministic reveal。
    红灯证据:基底 `_reveal_stuck_hint` 无 provenance 消费全部 steps
    (2026-09-20 基底实测红:揭示文本含「500米」)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("这道题你怎么想?先说说看。", MODEL_LADDER_WRONG_500M),
    ])
    session = _session_after_first_exchange(gateway)
    turn = reply(session, "我不会", gateway=gateway)  # 学生明确 stuck → 揭示路径
    assert "500" not in turn.text, (
        f"模型生成的阶梯(读图错误 500米)进入 deterministic reveal:「{turn.text}」"
        "——非 trusted(题库 analysis)来源不得 reveal(P0-3)")


def test_no_trusted_ladder_falls_to_safe_guiding_question():
    """无 trusted ladder(本题 analysis 切不出 ≥2 步)→ 既有 safe guiding
    question 机制(NEEDS_REVIEW_TEXT),不硬编码温度题话术、不调 LLM 验 step。"""
    from edu_agent.agents.small_lecturer import NEEDS_REVIEW_TEXT

    gateway = FakeGateway(tutor_payloads=[
        _open_payload("这道题你怎么想?先说说看。", MODEL_LADDER_WRONG_500M),
    ])
    session = _session_after_first_exchange(gateway)
    turn = reply(session, "我不会", gateway=gateway)
    assert turn.text == NEEDS_REVIEW_TEXT or "海拔" not in turn.text


def test_analysis_ladder_remains_trusted_for_reveal():
    """trusted 通道不误伤:题库 analysis 切得出 ≥2 步时,卡住揭示照常回放
    (PR-C 只收窄来源,不禁机制本身)。"""
    question = {
        "text": "鸡和兔一共 8 只,共有 26 只脚。鸡和兔各有多少只?说明思路。",
        "answer": "鸡3只兔5只",
        "analysis": "假设全是鸡,8×2=16只脚。脚数差26-16=10。兔:10÷2=5只,鸡:8-5=3只。",
        "knowledge_points": ["鸡兔同笼"],
    }
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("你怎么想?", [{"step": "外题", "value": "99"}]),
        _tutor_payload("先看看脚数。"),
    ])
    first = start(dict(question), {"grade": GRADE}, gateway=gateway)
    session = first.session
    reply(session, "我先算了一部分。", gateway=gateway)
    turn = reply(session, "我不会", gateway=gateway)
    # analysis 阶梯优先于模型阶梯(start() L668-670):揭示句含 analysis 步文本
    assert "鸡" in turn.text or "脚" in turn.text, (
        f"analysis 来源的 trusted 阶梯应照常揭示,实际:「{turn.text}」")


# =========================================================================== #
# 维度四(行为面):学生首答正确不被无端质疑 —— 待 Prompt/Model 层(§11)
# =========================================================================== #


@pytest.mark.skip(reason="待 Prompt/Model 层(§11):教学行为面不在 Kernel 修面,"
                         "本波禁令禁止在正确性 PR 里顺带优化文案与分数;"
                         "Prompt/Model 质量波(执行序列 7)合入后翻绿")
def test_correct_first_answer_not_challenged_with_but():
    """事故第 4 轮冻结:「…但每100米降3/5℃,700米应该降多少呢?」——「但」字
    质疑本来正确的答案。学生首答(第 1 轮)已含完整正确推理,导师追问应引用
    学生的正确结论,不得以「但」转折质疑。属 Prompt/Model 行为面(动作选择/
    最新内容回应),Kernel 不修(§11:不在正确性 PR 里顺带优化文案分数)。"""
    gateway = FakeGateway(tutor_payloads=[
        _open_payload("这道题你怎么想?先说说看。", MODEL_LADDER_WRONG_500M),
        _tutor_payload("那你是怎么从500米27℃推到700米的?"),
        _tutor_payload("…但每100米降3/5℃,700米应该降多少呢?"),  # 事故原句
    ])
    session = _session_after_first_exchange(gateway)
    turn = reply(session, "A在500米上面两格,一格100米,所以700米。", gateway=gateway)
    assert "但" not in turn.text, "首答正确的学生不得被「但」字质疑"


# =========================================================================== #
# 度量口径一:Gateway failure turn 从 trajectory 指标排除
# =========================================================================== #


def test_gateway_failure_turns_excluded_from_trajectory_metrics():
    """事故尾部冻结:GatewayError 轮(failed turn)不是教学轮——turns_to_confirm
    等 trajectory 指标不得把「重发了 N 次」计入教学轮数(否则可靠性事故会
    污染教学质量指标)。口径钉死:transcript turns 里 tutor 回应为空的 failed
    轮不进 trajectory 分母(_tutor_turns 过滤空文本 = 指标消费侧同源判据)。"""
    # 模拟事故尾部形态的 transcript:正常轮 ×2 + Gateway 失败轮 ×2(无 tutor 文本)
    transcript = {
        "turns": [
            {"student": "", "tutor": "这道题你怎么想?", "state": "first_question_ready"},
            {"student": STUDENT_FIRST_CORRECT, "tutor": "你怎么推到700米的?",
             "state": "dialogue"},
            {"student": GATEWAY_SENTENCE, "tutor": "", "state": "failed"},   # GatewayError×1
            {"student": GATEWAY_SENTENCE, "tutor": "", "state": "failed"},   # 同句重发 ×2
        ],
        "final_state": "dialogue",
    }
    # 事故尾部冻结的度量合同:教学轮 = 有 tutor 回应的轮;Gateway failure 轮
    # (tutor 文本为空)不进 trajectory 指标。当前消费侧(_four_metrics 的
    # student_turn_counts / checks 的 _tutor_turns)如改口径把空回应轮计入,
    # 这里先红。
    teaching_turns = [(i, t) for i, t in _tutor_turns(transcript) if t.strip()]
    assert len(teaching_turns) == 2, (
        "Gateway failure turn(空 tutor 回应)必须从 trajectory 指标排除:"
        f"实际计入 {len(teaching_turns)} 轮")


# =========================================================================== #
# 度量口径二:用户重发不计教学复读
# =========================================================================== #


def test_user_resend_not_counted_as_teaching_repeat():
    """事故尾部冻结(§11 逐字:「禁止把 infra 用户重试记成教学复读」):
    GatewayError 后用户的同句重发是 infra 重试,不是学生在复读自己的答案
    ——复读检测(tutor 侧 _is_repeat / 学生侧 no-progress 诊断)都不得把它
    计成教学复读信号。"""
    # tutor 侧复读检测:两次 GatewayError 之间没有 tutor 输出,无 prev/new 对;
    # 重发成功后的 tutor 首句与「上一句成功的 tutor 输出」比较——学生重发本身
    # 不进 _is_repeat 的输入(它只看 tutor 输出)。钉死口径:
    # 学生同句重发(事故实录)不构成 tutor 复读判定输入:tutor 文本无重复即不触发
    assert _is_repeat("我们先看看这道题。", "你能说说题目给了哪些条件吗?") is False
    # 教学复读的正例仍然成立(tutor 自己复读):口径不因事故放宽
    assert _is_repeat("我们先看看这道题。", "我们先看看这道题。") is True


def test_resend_scenario_in_subject_not_double_counted():
    """端到端口径:KernelSubject 驱动的事故尾部(同句重发)在 GatewayError 下
    抛 EnvironmentFailure(环境类,不进内容失败)——重发轮不产 tutor turn,
    trajectory 里只留有回应的教学轮。"""
    from edu_agent.evals import EnvironmentFailure, KernelSubject

    case = {
        "id": "incident-700m-tail",
        "question": dict(QUESTION_700M),
        "grade": GRADE,
        "answer_status": "incorrect",
        "student_turns": [STUDENT_FIRST_CORRECT, GATEWAY_SENTENCE, GATEWAY_SENTENCE],
    }
    gateway = ExplodingGateway(
        tutor_payloads=[
            _open_payload("这道题你怎么想?先说说看。", MODEL_LADDER_WRONG_500M),
            _tutor_payload("你怎么推到700米的?"),
        ],
        explode_remaining=0,  # 剧本耗尽:GATEWAY_SENTENCE 轮 tutor 调用 → GatewayError
    )
    with pytest.raises(EnvironmentFailure):
        KernelSubject(gateway).run_case(case)
    # Gateway 环境失败整案标记,不把重发轮当作教学轮落进 transcript:
    # (EnvironmentFailure 冒泡即 run_case 不返回——turns 不含半提交轮。)
