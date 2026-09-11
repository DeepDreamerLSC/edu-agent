"""内核三函数契约与状态机转移(00 §5.1;03 §4 逐态)。

真 Gateway + FakeOpenAI 假上游(02 §6:零真实模型;tutor 走 json_strict=true
的 grammar 路径,vision 独立角色)。#54 口径:gateway.text 即已验证 JSON,
内核直接解析——假上游直接回合法 JSON 模拟 grammar 强制。
"""

from __future__ import annotations

import json

import pytest
from fake_openai import FakeOpenAI, Reply, completion

from edu_agent.agents.small_lecturer import (
    SessionVersionConflict,
    TerminalStateError,
    finish,
    reply,
    start,
)
from edu_agent.gateway import (
    Gateway,
    GatewayError,
    ModelConfig,
    ModelRegistry,
    ProviderConfig,
    RoleConfig,
)

QUESTION_TEXT = {"text": "解方程 3x+7=25,并说明每一步为什么这样做。"}
LEARNER = {"grade": "六年级"}


def tutor_json(reply_text: str, ready: bool = False,
               cited_numbers: list[float] | None = None) -> str:
    # reason 首位(#146 M1):镜像真模型 grammar 输出的字段序;内核不读该值(规划装置)
    return json.dumps({"reason": "先引导学生自己想到下一步", "reply": reply_text,
                       "ready_to_confirm": ready,
                       "cited_numbers": cited_numbers or []}, ensure_ascii=False)


def vision_json(acceptable: bool, reason: str = "", transcription: str = "") -> str:
    """M3 PR2:vision 响应三字段(schema required 三键),假上游照 schema 出牌。"""
    return json.dumps({"acceptable": acceptable, "reason": reason,
                       "transcription": transcription}, ensure_ascii=False)


def open_json(reply_text: str, *, acceptable: bool = True, transcription: str = "",
              steps: list[dict] | None = None) -> str:
    """统一 open schema(任务包2步4):一次调用产出 转写 + 分步解 + 首问。"""
    return json.dumps({
        "acceptable": acceptable,
        "transcription": transcription,
        "steps": steps or [],
        "reply": reply_text,
    }, ensure_ascii=False)


def kernel_gateway(facts_dir, tutor_url: str, vision_url: str | None = None) -> Gateway:
    """tutor(json_strict=true,grammar 路径)+ 可选 vision 角色指向假上游。"""
    providers = {"fake_tutor": ProviderConfig("fake_tutor", tutor_url, None, True)}
    models = {"m": ModelConfig("m", "fake_tutor", "fake-model")}
    roles = {"tutor": RoleConfig(
        name="tutor", primary="m", fallback=None, json_strict=True,
        concurrency=2, first_token_timeout_s=2.0, total_timeout_s=5.0,
        max_attempts=2, backoff_base_ms=1, backoff_cap_ms=8,
    )}
    if vision_url is not None:
        providers["fake_vision"] = ProviderConfig("fake_vision", vision_url, None, True)
        models["v"] = ModelConfig("v", "fake_vision", "fake-vision")
        roles["vision"] = RoleConfig(
            name="vision", primary="v", fallback=None, json_strict=True,
            concurrency=2, first_token_timeout_s=2.0, total_timeout_s=5.0,
            max_attempts=2, backoff_base_ms=1, backoff_cap_ms=8,
        )
    return Gateway(ModelRegistry(providers=providers, models=models, roles=roles), facts_dir)


# ---------- start:Preparing → FirstQuestionReady / Failed ----------

def test_start_text_question_skips_vision(tmp_path):
    """纯文本题统一 open(一次调用);首问就绪,Turn 携带 session 供后续调用。"""
    fake = FakeOpenAI([completion(open_json("题目要我们求什么?先说说已知条件。"))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.state == "first_question_ready" and turn.text == "题目要我们求什么?先说说已知条件。"
    assert turn.session is not None and turn.session.state == "first_question_ready"
    assert len(fake.requests) == 1  # 统一 open:只有 tutor 一次


def test_start_image_untrusted_fails_closed_without_tutor(tmp_path):
    """Preparing → Failed:统一 open 判 acceptable=False 且纯图 → fail closed(不采信 reply/steps)。"""
    fake = FakeOpenAI([completion(open_json("不该被采信的首问", acceptable=False))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start({"image": "file:photo-123"}, LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.state == "failed" and "题图" in turn.text
    assert len(fake.requests) == 1  # 一次统一 open,acceptable=False → 内核 fail closed
    with pytest.raises(TerminalStateError):  # Failed 终态:不可再推进(校验先于模型调用)
        reply(turn.session, "继续")


def test_start_image_trusted_proceeds_to_first_question(tmp_path):
    fake = FakeOpenAI([completion(open_json("我们先确认题意:这道题要我们求什么?"))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start({"image": "file:photo-123"}, LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.state == "first_question_ready"
    assert len(fake.requests) == 1


def test_start_vision_infrastructure_error_bubbles(tmp_path):
    """GatewayError 按失败类型冒泡,内核不吞(00 §5.1)。"""
    fake = FakeOpenAI([Reply(status=500), Reply(status=500)]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    with pytest.raises(GatewayError) as excinfo:
        start({"image": "file:photo-x"}, LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    assert excinfo.value.failure.value == "upstream_5xx"


# ---------- reply:Dialogue 自旋 / Conflict / ReadyToConfirm ----------

def test_reply_appends_history_and_increments_version(tmp_path):
    fake = FakeOpenAI([
        completion(open_json("题目要我们求什么?")),
        completion(tutor_json("很好,那两个量之间是什么关系?")),
    ]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    turn = reply(first.session, "我先两边同时减去7。", gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.state == "dialogue" and turn.session_version == 2
    assert first.session.history == [
        {"role": "user", "content": "我先两边同时减去7。"},
        {"role": "assistant", "content": "很好,那两个量之间是什么关系?"},
    ]


def test_reply_stale_version_conflicts_without_advancing(tmp_path):
    """Dialogue ⇄ Conflict(03 §4):旧 expected_session_version 不推进、不覆盖。"""
    fake = FakeOpenAI([completion(open_json("第一问?")), completion(tutor_json("第二问?"))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    reply(first.session, "回答一", gateway=gateway)  # version 1 → 2
    with pytest.raises(SessionVersionConflict):
        reply(first.session, "旧页面重发", gateway=gateway, expected_session_version=1)
    gateway.close()
    fake.stop()
    assert first.session.session_version == 2  # 冲突不推进
    assert len(fake.requests) == 2              # 冲突不发模型调用


def test_reply_ready_signal_enters_ready_to_confirm(tmp_path):
    fake = FakeOpenAI([
        completion(open_json("第一问?")),
        completion(tutor_json("你已经说清了每一步的依据。", ready=True)),
    ]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    turn = reply(first.session, "我算出 x=6,并回代检验了。", gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.state == "ready_to_confirm" and turn.ready_to_confirm is True


# ---------- finish:Completed 不可变 / needs_review ----------

def test_finish_before_ready_returns_needs_review_without_model(tmp_path):
    """证据不足(00 §5.1):不调模型、确定性文案、不写 summary。"""
    fake = FakeOpenAI([completion(open_json("第一问?"))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    summary = finish(first.session, gateway=gateway)
    gateway.close()
    fake.stop()
    assert summary.status == "needs_review" and "继续" in summary.text
    assert len(fake.requests) == 1            # 只有首问那一次,finish 未调模型
    assert first.session.summary is None and first.session.state == "first_question_ready"


def test_finish_ready_writes_immutable_summary(tmp_path):
    fake = FakeOpenAI([
        completion(open_json("第一问?")),
        completion(tutor_json("掌握了", ready=True)),
        completion(json.dumps({"summary": "你用等式性质解出 x=6,并回代检验。"}, ensure_ascii=False)),
        completion(json.dumps({"summary": "不该再次生成"}, ensure_ascii=False)),
    ]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    reply(first.session, "x=6,检验通过。", gateway=gateway)
    summary = finish(first.session, gateway=gateway)
    again = finish(first.session, gateway=gateway)  # completed 终态:幂等返回同一 Summary
    gateway.close()
    fake.stop()
    assert summary.status == "completed" and "x=6" in summary.text
    assert again == summary
    assert len(fake.requests) == 3               # 第二次 finish 不再调模型(不可变)
    with pytest.raises(TerminalStateError):      # Completed 终态:不可再 reply
        reply(first.session, "再问一句", gateway=gateway)


# ---------- 三函数契约(#54 后的 text 即已验证内容) ----------

def test_kernel_consumes_validated_text_directly(tmp_path):
    """#54 口径:gateway.text 即已验证 JSON(grammar/路线 1 归一),内核直接 json.loads
    不二次剥壳——带围栏输出经 gateway 归一后内核同样直解析。"""
    fenced = "```json\n" + open_json("我们先确认题意。") + "\n```"
    fake = FakeOpenAI([completion(fenced), completion(tutor_json("第二问?", ready=True))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    turn = reply(first.session, "知道了。", gateway=gateway)
    gateway.close()
    fake.stop()
    assert first.text == "我们先确认题意。" and turn.state == "ready_to_confirm"


def test_start_stores_steps_from_open_payload(tmp_path):
    """统一 open 的 steps 经 solver 校验(非法过滤)存进 session.steps(阶梯底稿)。"""
    fake = FakeOpenAI([completion(open_json(
        "你先说说题目给了哪些条件?",
        steps=[{"step": "两边减7", "value": "18"},
               {"step": "", "value": "18"},      # 空 step → 过滤
               {"step": "除以3", "value": ""},   # 空 value → 过滤
               {"step": "得 x", "value": "6"}],
    ))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.session.steps == [{"step": "两边减7", "value": "18"},
                                  {"step": "得 x", "value": "6"}]


def test_reply_masks_method_names_in_teacher_prompt(tmp_path):
    """复讲阶段方法名脱敏(代喂窄规则方案②):教师侧解析/知识点里的方法名 → 「这种方法」,
    总结阶段(finish)不脱敏,由教师侧上下文恢复点名。"""
    fake = FakeOpenAI([completion(open_json("我们先确认题意。")),
                       completion(tutor_json("你来说说你的思路。"))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start({"text": "鸡兔同笼,共8只26脚", "answer": "鸡3只兔5只",
                   "analysis": "用假设法:先假设全是鸡,再按脚差求兔。",
                   "knowledge_points": ["鸡兔同笼", "假设法"]},
                  {"grade": "六年级"}, gateway=gateway)
    reply(first.session, "我先说说我的想法。", gateway=gateway)
    gateway.close()
    fake.stop()
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
    fake = FakeOpenAI([
        completion(open_json("你先说说题目给了哪些条件?")),
        completion(tutor_json("你用的是假设法,对吧?", ready=True)),
        completion(tutor_json("这个思路可以,那这一步你打算先算哪一个?", ready=False)),
    ]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start({"text": "鸡兔同笼,共8只26脚", "answer": "鸡3只兔5只",
                   "knowledge_points": ["假设法"]}, {"grade": "六年级"}, gateway=gateway)
    turn = reply(first.session, "我先说说我的想法。", gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.text == "这个思路可以,那这一步你打算先算哪一个?"  # 本轮引导语义保留
    assert turn.ready_to_confirm is False  # 不关对话,继续收集
    assert turn.session.stuck is False     # 重生成修好 = 非硬降级(不再连坐卡点)
    assert "假设法" not in turn.text


def test_reply_student_says_understood_triggers_elicit_without_model(tmp_path):
    """学生说「都懂了」→ 确定性请学生讲思路(不调模型),不 confirm、不报答案。"""
    fake = FakeOpenAI([completion(open_json("你先说说题目给了哪些条件?"))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start(QUESTION_TEXT, LEARNER, gateway=gateway)
    calls_before = len(fake.requests)  # start 那次
    turn = reply(first.session, "都懂了。", gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.text == ("很好,你已经懂了。那请你从头讲讲你的思路——"
                         "先说说你第一步算了什么、为什么这样算。")
    assert turn.ready_to_confirm is False  # 不关对话
    assert len(fake.requests) == calls_before  # 「都懂了」这轮零模型调用


def test_reply_stuck_reveals_next_step_with_varied_lead(tmp_path):
    """学生说「我不太会」→ 揭示下一级阶梯(确定性),开场用轮换模板避免固定前缀生硬。"""
    fake = FakeOpenAI([completion(open_json(
        "你先说说题目给了哪些条件?",
        steps=[{"step": "两边减7", "value": "18"}, {"step": "除以3", "value": "6"}],
    ))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start({"text": "解方程 3x+7=25", "answer": "x=6"}, LEARNER, gateway=gateway)
    calls_before = len(fake.requests)
    turn = reply(first.session, "我不太会。", gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.text == "我们从这里入手:两边减7。你接着算下一步。"
    assert turn.ready_to_confirm is False  # 不关对话
    assert len(fake.requests) == calls_before  # 零模型调用


def test_reply_negative_huile_goes_stuck_not_understanding(tmp_path):
    """#109 P2-1:「我不会了」是卡住,不是「懂了」——不能触发请讲思路,要揭示下一级阶梯。

    回归:曾经 `会了` 命中 `不会了` 子串 → understanding 短路,错触发「从头讲讲思路」。"""
    fake = FakeOpenAI([completion(open_json(
        "你先说说题目给了哪些条件?",
        steps=[{"step": "两边减7", "value": "18"}, {"step": "除以3", "value": "6"}],
    ))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start({"text": "解方程 3x+7=25", "answer": "x=6"}, LEARNER, gateway=gateway)
    turn = reply(first.session, "我不会了。", gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.text == "我们从这里入手:两边减7。你接着算下一步。"  # 揭示阶梯,非请讲
    assert turn.ready_to_confirm is False
    assert "讲讲你的思路" not in turn.text


# ---------- #107 方案 A:题库解析切片优先(确定性阶梯,零模型) ----------

_ANALYSIS = ("先假设8只全是鸡,算出脚的总数8×2=16。再算实际脚数比假设多26-16=10只。"
             "然后每把一只鸡换成兔,脚数多4-2=2只。最后多出的脚数能换10÷2=5只兔,鸡有8-5=3只。")
_MODEL_STEPS = [{"step": "模型自拟第一步", "value": "111"}, {"step": "模型自拟第二步", "value": "222"}]


def _start_with_question(tmp_path, question: dict, steps: list[dict]):
    fake = FakeOpenAI([completion(open_json("我们先看看题目条件?", steps=steps))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start(question, {"grade": "六年级", "answer_status": "incorrect"}, gateway=gateway)
    gateway.close()
    fake.stop()
    return turn


def test_analysis_ladder_takes_priority_over_model_steps(tmp_path):
    """题库带解析 → 阶梯来自**既定解析**(纯函数切片),不用模型当场生成的分步解。"""
    question = {"text": "鸡和兔一共8只,26只脚,各多少?", "answer": "鸡3只兔5只",
                "analysis": _ANALYSIS, "knowledge_points": ["鸡兔同笼"]}
    turn = _start_with_question(tmp_path, question, _MODEL_STEPS)
    steps = turn.session.steps
    assert len(steps) == 4 and all("模型自拟" not in s["step"] for s in steps)
    assert [s["value"] for s in steps] == ["16", "10", "2", "3"]
    assert steps[0]["step"].startswith("先假设8只全是鸡")
    # 末级 value 即终答兜底(_known_answer 同源)→ 解析的结论数字
    assert steps[-1]["value"] == "3"


def test_model_steps_kept_when_analysis_missing_or_unsliceable(tmp_path):
    """无解析 / 解析切不出 ≥2 步(纯叙述、无数字)→ 保持模型分步解不变(零回归)。"""
    no_analysis = {"text": "鸡和兔一共8只,26只脚,各多少?", "answer": "", "analysis": "",
                   "knowledge_points": []}
    narrative = {"text": "看题目说说你的想法。", "answer": "",
                 "analysis": "先读题。再想想要求什么。最后说说你的结论。", "knowledge_points": []}
    for question in (no_analysis, narrative):
        turn = _start_with_question(tmp_path, question, _MODEL_STEPS)
        assert turn.session.steps == _MODEL_STEPS


def test_analysis_ladder_is_revealed_on_repeat_fallback(tmp_path):
    """卡住/复读兜底揭示的下一级 = 解析切片(证明阶梯真的接上了揭示路径)。"""
    question = {"text": "鸡和兔一共8只,26只脚,各多少?", "answer": "鸡3只兔5只",
                "analysis": _ANALYSIS, "knowledge_points": []}
    repeated = "兔子有几只呢?"
    fake = FakeOpenAI([
        completion(open_json(repeated, steps=_MODEL_STEPS)),
        completion(tutor_json(repeated)),      # 模型复读首问
        completion(tutor_json(repeated)),      # 重生成仍复读 → 兜底揭示下一级
    ]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    first = start(question, {"grade": "六年级", "answer_status": "incorrect"}, gateway=gateway)
    turn = reply(first.session, "嗯,我看看。", gateway=gateway)
    gateway.close()
    fake.stop()
    assert "先假设8只全是鸡" in turn.text        # 揭开的是题库解析的第一级
    assert turn.session.hint_level == 1
