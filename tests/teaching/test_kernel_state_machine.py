"""内核三函数契约与状态机转移(00 §5.1;03 §4 逐态)。

真 Gateway + FakeOpenAI 假上游(02 §6:零真实模型;tutor 走 json_strict=true
的 grammar 路径)。#54 口径:gateway.text 即已验证 JSON,内核直接解析——
假上游直接回合法 JSON 模拟 grammar 强制。剧本构造器与 Gateway 构造收拢在
tests/fixtures/teachkit.py(kernel_env 一处定义、多处引用)。
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import pytest
from fake_openai import Reply, completion

from edu_agent.agents.small_lecturer import (
    FIRST_QUESTION_COLLECT,
    SessionVersionConflict,
    TerminalStateError,
    finish,
    reply,
    start,
)
from edu_agent.gateway import GatewayError

from teachkit import kernel_env, open_json, tutor_json

# Gate B 段(#414 §四)改据:completed 迁移需当轮 CompletionEvidence——题面带
# answer_spec 声明面(测试本地;现网题库无此面,缺口留人审),学生轮「x=6」经
# equation_form 窄面命中即证据,完成断言语义不变。
QUESTION_TEXT = {"text": "解方程 3x+7=25,并说明每一步为什么这样做。",
                 "answer": "x=6", "answer_spec": {"answer_type": "equation_form"}}
# #382 PR-C:reveal 只回放 trusted(analysis)阶梯——卡壳/支持动作的测试面给题面挂
# analysis(与生产题库同源);模型 steps 仍照喂(证明入库与规划辅助不受边界影响)。
QUESTION = {"text": "解方程 3x+7=25,并说明每一步为什么这样做。",
            "answer": "x=6", "analysis": "两边同时减7得3x=18。再两边除以3得x=6。",
            "knowledge_points": []}
LEARNER = {"grade": "六年级"}


# ---------- start:Preparing → FirstQuestionReady / Failed ----------

def test_start_text_question_skips_vision(tmp_path):
    """纯文本题统一 open(一次调用);首问就绪且可见文本 = 固定模板(缺省 status → 采集档)。"""
    with kernel_env(tmp_path, [completion(open_json("题目要我们求什么?先说说已知条件。"))]) as (fake, gateway):
        turn = start(QUESTION_TEXT, LEARNER, gateway=gateway)
        assert turn.state == "first_question_ready" and turn.text == FIRST_QUESTION_COLLECT
        assert turn.session.guard_events == []
        assert turn.session is not None and turn.session.state == "first_question_ready"
        assert [r["model"] for r in fake.requests] == ["fake-model"]  # 统一 open:只有 tutor 一次(vision 分支跳过)


def test_start_image_untrusted_fails_closed_without_tutor(tmp_path):
    """Preparing → Failed:统一 open 判 acceptable=False 且纯图 → fail closed(不采信 reply/steps)。"""
    with kernel_env(tmp_path, [completion(open_json("不该被采信的首问", acceptable=False))]) as (fake, gateway):
        turn = start({"image": "file:photo-123"}, LEARNER, gateway=gateway)
        assert turn.state == "failed" and "题图" in turn.text
        assert len(fake.requests) == 1  # 一次统一 open,acceptable=False → 内核 fail closed
        with pytest.raises(TerminalStateError):  # Failed 终态:不可再推进(校验先于模型调用)
            reply(turn.session, "继续")


def test_start_image_trusted_proceeds_to_first_question(tmp_path):
    with kernel_env(tmp_path, [completion(open_json("我们先确认题意:这道题要我们求什么?"))]) as (fake, gateway):
        turn = start({"image": "file:photo-123"}, LEARNER, gateway=gateway)
        assert turn.state == "first_question_ready"
        assert len(fake.requests) == 1


def test_start_vision_infrastructure_error_bubbles(tmp_path):
    """GatewayError 按失败类型冒泡,内核不吞(00 §5.1)。"""
    with kernel_env(tmp_path, [Reply(status=500), Reply(status=500)]) as (fake, gateway):
        with pytest.raises(GatewayError) as excinfo:
            start({"image": "file:photo-x"}, LEARNER, gateway=gateway)
    assert excinfo.value.failure.value == "upstream_5xx"


# ---------- reply:Dialogue 自旋 / Conflict / ReadyToConfirm ----------

def test_reply_appends_history_and_increments_version(tmp_path):
    with kernel_env(tmp_path, [
        completion(open_json("题目要我们求什么?")),
        completion(tutor_json("很好,那两个量之间是什么关系?")),
    ]) as (fake, gateway):
        first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
        turn = reply(first.session, "我先两边同时减去7。", gateway=gateway)
        assert turn.state == "dialogue" and turn.session_version == 2
        assert first.session.history == [
            {"role": "user", "content": "我先两边同时减去7。"},
            {"role": "assistant", "content": "很好,那两个量之间是什么关系?"},
        ]


def test_reply_stale_version_conflicts_without_advancing(tmp_path):
    """Dialogue ⇄ Conflict(03 §4):旧 expected_session_version 不推进、不覆盖。"""
    with kernel_env(tmp_path, [completion(open_json("第一问?")), completion(tutor_json("第二问?"))]) as (fake, gateway):
        first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
        reply(first.session, "回答一", gateway=gateway)  # version 1 → 2
        with pytest.raises(SessionVersionConflict):
            reply(first.session, "旧页面重发", gateway=gateway, expected_session_version=1)
        assert first.session.session_version == 2  # 冲突不推进
        assert len(fake.requests) == 2              # 冲突不发模型调用


def test_reply_ready_signal_enters_ready_to_confirm(tmp_path):
    with kernel_env(tmp_path, [
        completion(open_json("第一问?")),
        completion(tutor_json("你已经说清了每一步的依据。", ready=True)),
    ]) as (fake, gateway):
        first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
        turn = reply(first.session, "我算出 x=6,并回代检验了。", gateway=gateway)
        assert turn.state == "ready_to_confirm" and turn.ready_to_confirm is True


# ---------- finish:Completed 不可变 / needs_review ----------

def test_finish_before_ready_returns_needs_review_without_model(tmp_path):
    """证据不足(00 §5.1):不调模型、确定性文案、不写 summary。"""
    with kernel_env(tmp_path, [completion(open_json("第一问?"))]) as (fake, gateway):
        first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
        summary = finish(first.session, gateway=gateway)
        assert summary.status == "needs_review" and "继续" in summary.text
        assert len(fake.requests) == 1            # 只有首问那一次,finish 未调模型
        assert first.session.summary is None and first.session.state == "first_question_ready"


def test_finish_ready_writes_immutable_summary(tmp_path):
    with kernel_env(tmp_path, [
        completion(open_json("第一问?")),
        completion(tutor_json("掌握了", ready=True)),
        completion(json.dumps({"summary": "你用等式性质解出 x=6,并回代检验。"}, ensure_ascii=False)),
        completion(json.dumps({"summary": "不该再次生成"}, ensure_ascii=False)),
    ]) as (fake, gateway):
        first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
        reply(first.session, "x=6,检验通过。", gateway=gateway)
        summary = finish(first.session, gateway=gateway)
        again = finish(first.session, gateway=gateway)  # completed 终态:幂等返回同一 Summary
        assert summary.status == "completed" and "x=6" in summary.text
        assert again == summary
        assert len(fake.requests) == 3               # 第二次 finish 不再调模型(不可变)
        with pytest.raises(TerminalStateError):      # Completed 终态:不可再 reply
            reply(first.session, "再问一句", gateway=gateway)


# ---------- 三函数契约(#54 后的 text 即已验证内容) ----------

def test_kernel_consumes_validated_text_directly(tmp_path):
    """#54 口径:gateway.text 即已验证 JSON(grammar/路线 1 归一),内核直接 json.loads
    不二次剥壳——带围栏输出经 gateway 归一后内核同样直解析。

    首问可见文本恒为固定模板(prompting.first_question_text),故解析成功的见证
    落在 Turn.state(模型产出照旧被 json.loads,不经二次剥壳)。"""
    fenced = "```json\n" + open_json("我们先确认题意。") + "\n```"
    fenced = "```json\n" + open_json("我们先确认题意。") + "\n```"
    with kernel_env(tmp_path, [completion(fenced), completion(tutor_json("第二问?", ready=True))]) as (fake, gateway):
        first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
        turn = reply(first.session, "知道了。", gateway=gateway)
        assert first.text == FIRST_QUESTION_COLLECT and turn.state == "ready_to_confirm"


def test_start_stores_steps_from_open_payload(tmp_path):
    """统一 open 的 steps 经 solver 校验(非法过滤)存进 session.steps,且逐条带
    provenance="model"(#382 PR-C:untrusted planning artifact 标记,reveal 不消费)。"""
    with kernel_env(tmp_path, [completion(open_json(
        "你先说说题目给了哪些条件?",
        steps=[{"step": "两边减7", "value": "18"},
               {"step": "", "value": "18"},      # 空 step → 过滤
               {"step": "除以3", "value": ""},   # 空 value → 过滤
               {"step": "得 x", "value": "6"}],
    ))]) as (fake, gateway):
        turn = start(QUESTION_TEXT, LEARNER, gateway=gateway)
        assert turn.session.steps == [{"step": "两边减7", "value": "18",
                                       "provenance": "model"},
                                      {"step": "得 x", "value": "6",
                                       "provenance": "model"}]


def test_reply_masks_method_names_in_teacher_prompt(tmp_path):
    """复讲阶段方法名脱敏(代喂窄规则方案②):教师侧解析/知识点里的方法名 → 「这种方法」,
    总结阶段(finish)不脱敏,由教师侧上下文恢复点名。"""
    with kernel_env(tmp_path, [completion(open_json("我们先确认题意。")),
                               completion(tutor_json("你来说说你的思路。"))]) as (fake, gateway):
        first = start({"text": "鸡兔同笼,共8只26脚", "answer": "鸡3只兔5只",
                       "analysis": "用假设法:先假设全是鸡,再按脚差求兔。",
                       "knowledge_points": ["鸡兔同笼", "假设法"]},
                      {"grade": "六年级"}, gateway=gateway)
        reply(first.session, "我先说说我的想法。", gateway=gateway)
        prompt = json.loads(fake.requests[1]["messages"][1]["content"])
        assert "假设法" not in prompt["题目"]["解析"]
        assert "这种方法" in prompt["题目"]["解析"]
        assert prompt["追问锚点"] == ["鸡兔同笼", "这种方法"]  # 方法名脱敏,概念名保留
        assert prompt["题目"]["参考答案"] == "鸡3只兔5只"      # 答案不脱敏(兜底/校验需要)


def test_reply_repairs_method_feed_and_keeps_open(tmp_path):
    """复讲轮代喂(输出侧兜底):学生给普通回答,tutor 回「你用的是假设法」→ **重生成**
    保留本轮引导语义(不再整轮换复讲模板),且 ready_to_confirm=False(不关对话,
    继续收集讲题内容)。

    学生消息必须是普通回答(非「都懂了」/卡住),否则会走理解/卡壳的确定性短路、不调模型,
    这条输出侧代喂分支就永远测不到(#109 P2-2)。"""
    with kernel_env(tmp_path, [
        completion(open_json("你先说说题目给了哪些条件?")),
        completion(tutor_json("你用的是假设法,对吧?", ready=True)),
        completion(tutor_json("这个思路可以,那这一步你打算先算哪一个?", ready=False)),
    ]) as (fake, gateway):
        first = start({"text": "鸡兔同笼,共8只26脚", "answer": "鸡3只兔5只",
                       "knowledge_points": ["假设法"]}, {"grade": "六年级"}, gateway=gateway)
        turn = reply(first.session, "我先说说我的想法。", gateway=gateway)
        assert turn.text == "这个思路可以,那这一步你打算先算哪一个?"  # 本轮引导语义保留
        assert turn.ready_to_confirm is False  # 不关对话,继续收集
        assert turn.session.stuck is False     # 重生成修好 = 非硬降级(不再连坐卡点)
        assert "假设法" not in turn.text


def test_reply_student_says_understood_routes_to_model(tmp_path):
    """Thin Kernel(#333 终裁):elicit 句族已删——「都懂了」走模型路径,由模型
    自然承接(讲思路引导归 Prompt/Model 面),零确定性干预。"""
    follow = tutor_json("很好,那你说说第一步从哪里开始?")
    with kernel_env(tmp_path, [completion(open_json("你先说说题目给了哪些条件?")),
                               completion(follow)]) as (fake, gateway):
        first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
        turn = reply(first.session, "都懂了。", gateway=gateway)
        assert turn.text == json.loads(follow)["reply"]  # 模型直通
        assert not any(e.get("branch") == "elicit" for e in turn.session.guard_events)


def test_reply_stuck_sets_flag_and_routes_to_model(tmp_path):
    """#3a-response(#500,deletion test 六门通过):学生说「我不太会」→ 置 stuck、
    该轮走模型路径(命中→置位→模型调用→非常量返回);模型 steps 照喂入库但不再被
    stuck 轮消费(#382 PR-C 的 reveal 消费面只在复读兜底)。"""
    follow = tutor_json("这一步你觉得卡在哪里?我们回到条件看看。")
    with kernel_env(tmp_path, [completion(open_json(
        "你先说说题目给了哪些条件?",
        steps=[{"step": "两边减7", "value": "18"}, {"step": "除以3", "value": "6"}],
    )), completion(follow)]) as (fake, gateway):
        first = start(QUESTION, LEARNER, gateway=gateway)
        assert first.session.stuck is False
        calls_before = len(fake.requests)
        turn = reply(first.session, "我不太会。", gateway=gateway)
        assert turn.session.stuck is True                # 命中 → 置位
        assert len(fake.requests) == calls_before + 1    # 该轮发生模型调用
        assert turn.text == json.loads(follow)["reply"]  # 模型直通(非常量返回)
        assert turn.ready_to_confirm is False            # 不关对话
        assert turn.session.hint_level == 0              # 阶梯不被 stuck 轮消耗


def test_reply_negative_huile_goes_stuck_not_understanding(tmp_path):
    """#109 P2-1:「我不会了」是卡住,不是「懂了」——不能触发请讲思路。#333 终裁起
    elicit 句族已删;#3a-response(#500):卡住轮改走模型路径(置 stuck)。

    回归:曾经 `会了` 命中 `不会了` 子串 → understanding 短路,错触发「从头讲讲思路」。"""
    follow = tutor_json("哪里卡住了?你说说目前的想法。")
    with kernel_env(tmp_path, [completion(open_json(
        "你先说说题目给了哪些条件?",
        steps=[{"step": "两边减7", "value": "18"}, {"step": "除以3", "value": "6"}],
    )), completion(follow)]) as (fake, gateway):
        first = start(QUESTION, LEARNER, gateway=gateway)
        turn = reply(first.session, "我不会了。", gateway=gateway)
        assert turn.session.stuck is True                # 判卡住(非「懂了」短路)
        assert turn.text == json.loads(follow)["reply"]  # 模型直通
        assert turn.ready_to_confirm is False
        assert "讲讲你的思路" not in turn.text


# ---------- #107 方案 A:题库解析切片优先(确定性阶梯,零模型) ----------

_ANALYSIS = ("先假设8只全是鸡,算出脚的总数8×2=16。再算实际脚数比假设多26-16=10只。"
             "然后每把一只鸡换成兔,脚数多4-2=2只。最后多出的脚数能换10÷2=5只兔,鸡有8-5=3只。")
_MODEL_STEPS = [{"step": "模型自拟第一步", "value": "111"}, {"step": "模型自拟第二步", "value": "222"}]


@contextmanager
def _start_with_question(tmp_path, question: dict, steps: list[dict]):
    with kernel_env(tmp_path, [completion(open_json("我们先看看题目条件?", steps=steps))]) as (fake, gateway):
        turn = start(question, {"grade": "六年级", "answer_status": "incorrect"}, gateway=gateway)
        yield turn


def test_analysis_ladder_takes_priority_over_model_steps(tmp_path):
    """题库带解析 → 阶梯来自**既定解析**(纯函数切片),不用模型当场生成的分步解;
    #382 PR-C:切片逐条带 provenance="analysis"(trusted 标记,reveal 只消费它)。"""
    question = {"text": "鸡和兔一共8只,26只脚,各多少?", "answer": "鸡3只兔5只",
                "analysis": _ANALYSIS, "knowledge_points": ["鸡兔同笼"]}
    with _start_with_question(tmp_path, question, _MODEL_STEPS) as turn:
        steps = turn.session.steps
        assert len(steps) == 4 and all("模型自拟" not in s["step"] for s in steps)
        assert [s["value"] for s in steps] == ["16", "10", "2", "3"]
        assert all(s["provenance"] == "analysis" for s in steps)
        assert steps[0]["step"].startswith("先假设8只全是鸡")
        # 末级 value 即终答兜底(_known_answer 同源)→ 解析的结论数字
        assert steps[-1]["value"] == "3"


def test_model_steps_kept_when_analysis_missing_or_unsliceable(tmp_path):
    """无解析 / 解析切不出 ≥2 步(纯叙述、无数字)→ 保持模型分步解不变(零回归);
    #382 PR-C:入库步带 provenance="model"(untrusted 标记,reveal 不消费——
    专项钉见 test_trusted_ladder_boundary.py)。"""
    no_analysis = {"text": "鸡和兔一共8只,26只脚,各多少?", "answer": "", "analysis": "",
                   "knowledge_points": []}
    narrative = {"text": "看题目说说你的想法。", "answer": "",
                 "analysis": "先读题。再想想要求什么。最后说说你的结论。", "knowledge_points": []}
    expected = [{"step": s["step"], "value": s["value"], "provenance": "model"}
                for s in _MODEL_STEPS]
    for question in (no_analysis, narrative):
        with _start_with_question(tmp_path, question, _MODEL_STEPS) as turn:
            assert turn.session.steps == expected


def test_analysis_ladder_is_revealed_on_repeat_fallback(tmp_path):
    """卡住/复读兜底揭示的下一级 = 解析切片(证明阶梯真的接上了揭示路径)。"""
    question = {"text": "鸡和兔一共8只,26只脚,各多少?", "answer": "鸡3只兔5只",
                "analysis": _ANALYSIS, "knowledge_points": []}
    repeated = FIRST_QUESTION_COLLECT   # 首问固定模板 = 第一轮被复读的上一轮文本
    with kernel_env(tmp_path, [
        completion(open_json(repeated, steps=_MODEL_STEPS)),
        completion(tutor_json(repeated)),      # 模型复读首问模板
        completion(tutor_json(repeated)),      # 重生成仍复读 → 兜底揭示下一级
    ]) as (fake, gateway):
        first = start(question, {"grade": "六年级", "answer_status": "incorrect"}, gateway=gateway)
        turn = reply(first.session, "嗯,我看看。", gateway=gateway)
        assert "先假设8只全是鸡" in turn.text        # 揭开的是题库解析的第一级
        assert turn.session.hint_level == 1
