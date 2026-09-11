"""首问固定模板回归钉(实测缺陷:首问直接把答案报出来)。

改动口径:首问**可见文本**由内核 `start()` 覆盖为 `prompting.first_question_text`
的确定性模板(head + tail 组装,五条文案定稿):
- head 两选一:转录读出内容 → 图像招呼语 + 半句复述;纯文字题/读不出内容 → 纯文字招呼语;
- tail:正确档一套(文字/图像共用);采集档——图像题恒用**统一那句**,文字题按**题型**
  分选择题/非选择题(`_is_multiple_choice`,纯规则零模型调用)。
不再采信模型生成的 reply 文本;模型调用照旧(steps/transcription 仍被采信)。既有两条
确定性分支优先级不变:纯图题 fail-closed(`FAIL_CLOSED_TEXT`)与图文题 acceptable=false
且 reply 留空(`kernel._OPENING_FALLBACK`)。零真实模型(假上游)。
"""

from __future__ import annotations

import re

import pytest
from fake_openai import FakeOpenAI, completion

from edu_agent.agents.small_lecturer import (
    FIRST_QUESTION_COLLECT,
    FIRST_QUESTION_COLLECT_CHOICE,
    FIRST_QUESTION_CORRECT,
    HEAD_IMAGE_PREFIX,
    HEAD_TEXT,
    TAIL_COLLECT_CHOICE,
    TAIL_COLLECT_IMAGE,
    TAIL_COLLECT_OPEN,
    TAIL_CORRECT,
    first_question_text,
    start,
)

from test_kernel_state_machine import kernel_gateway, open_json

# 实测缺陷同款题:当时的首问写成「…记作(5,12),(3,10)表示10排3号,对吗?」——
# 两个空的答案都给了。题面数字(8/6/12/5/3/10)与答案数字同源,故文字档用「无数字」兜底。
# 题面无可选项 → 文字·采集走**非选择题**那句。
GRID_QUESTION = {
    "text": "8排6号记作(6,8),那么12排5号记作(  ,  );(3,10)表示(  )排(  )号。",
    "answer": "(5,12);(3,10)表示3排10号",
    "analysis": "先看排与号的顺序:第一个数表示排,第二个数表示号。",
    "knowledge_points": ["数对"],
}
LEARNER = {"grade": "五年级"}
# 假上游照常返回「会泄露答案的首问」:模板覆盖必须把它挡在学生面之外
LEAKING_REPLY = "12排5号记作(5,12),(3,10)表示10排3号,对吗?"
# 干净回复(无任何数字):图像档用例只想验模板组装,不额外触发答案泄露护栏
CLEAN_REPLY = "我们一起看看题目给了哪些条件,好吗?"
_DIGIT = re.compile(r"\d")

# 选择题(题面带 4 个选项标记 A. B. C. D.)→ 文字·采集走**选择题**那句
CHOICE_QUESTION = {
    "text": "下列各数中最大的是(  )。A. 3.14  B. 22/7  C. 3.1415  D. 3.142",
    "answer": "B. 22/7",
}
# 带图的选择题:图像档采集句**统一**,不因题面有选项而改句
CHOICE_IMAGE_QUESTION = {**CHOICE_QUESTION, "image": "file:photo-choice-1"}
CHOICE_TRANSCRIPTION = "下列各数中最大的是(  )。"
CHOICE_BRIEF = "下列各数中最大的是(  )"      # 13 字,未触 16 字上限

# 带图题(应用题,vision 读出头半句):复述只取半句「小明有8本书」(首个逗号之前)。
# 答案「10本」的结论数字 1/0 既不在题面也不在复述里 → 「答案独有数字」非空,
# 分档回归钉不空转(网格题的答案数字全来自题面,那一差集恒为空)。
IMAGE_WORD_QUESTION = {
    "text": "小明有8本书,借出3本后又买了5本,现在有多少本?",
    "image": "file:photo-word-1",
    "answer": "10本",
    "knowledge_points": ["加减混合"],
}
WORD_TRANSCRIPTION = "小明有8本书,借出3本。"
WORD_BRIEF = "小明有8本书"                    # 半句复述:首个逗号之前的 6 字
IMAGE_ONLY_QUESTION = {"image": "file:photo-only-1"}   # 纯图题(无题面文字)


def _opening(tmp_path, learner: dict, question: dict | None = None,
             reply_text: str = LEAKING_REPLY, **open_kwargs):
    """走公开路径取首问(假上游 + 真 Gateway),并返回 (turn, fake)。"""
    fake = FakeOpenAI([completion(open_json(reply_text, **open_kwargs))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    try:
        return start(dict(question or GRID_QUESTION), learner, gateway=gateway), fake
    finally:
        gateway.close()


# ---------- 文字档 · 采集(按题型分流) ----------

@pytest.mark.parametrize("status", ["incorrect", "unanswered", "unknown", None])
def test_non_correct_arcs_get_collect_template(tmp_path, status):
    """非 correct 弧线(含缺省/unknown)+ 题面无选项 → 非选择题采集句,且不含任何数字。"""
    learner = {**LEARNER, **({"answer_status": status} if status else {})}
    turn, fake = _opening(tmp_path, learner)
    fake.stop()
    assert turn.state == "first_question_ready"
    assert turn.text == FIRST_QUESTION_COLLECT
    # 文字档可见文本逐字钉死(与定稿一字不差)
    assert turn.text == "你好同学,请问你算出的答案是多少呀?讲讲你的思路吧!"
    assert turn.text == HEAD_TEXT + TAIL_COLLECT_OPEN
    assert turn.session.first_question == FIRST_QUESTION_COLLECT  # 记录面与可见面同源
    assert _DIGIT.search(turn.text) is None


def test_choice_question_gets_choice_collect_template(tmp_path):
    """题面带 A. B. C. D. 四个选项标记 → 选择题采集句。"""
    turn, fake = _opening(tmp_path, LEARNER, question=CHOICE_QUESTION)
    fake.stop()
    assert turn.text == FIRST_QUESTION_COLLECT_CHOICE
    assert turn.text == "你好同学,请问这道题你选了什么呀?讲讲你的思路吧!"
    assert turn.text == HEAD_TEXT + TAIL_COLLECT_CHOICE
    assert _DIGIT.search(turn.text) is None


def test_fullwidth_option_marks_are_recognised(tmp_path):
    """全角选项字母 + 全角标点(Ａ． B、)同样算选项标记。"""
    question = {"text": "下面哪个是对的? Ａ． 三 B、 四"}
    turn, fake = _opening(tmp_path, LEARNER, question=question)
    fake.stop()
    assert turn.text == FIRST_QUESTION_COLLECT_CHOICE


def test_single_option_mark_is_not_choice(tmp_path):
    """只出现**一个**选项标记 → 不判选择题(走非选择题采集句)。"""
    question = {"text": "下面哪个是对的? A. 三"}
    turn, fake = _opening(tmp_path, LEARNER, question=question)
    fake.stop()
    assert turn.text == FIRST_QUESTION_COLLECT


def test_choice_answer_is_secondary_signal(tmp_path):
    """题面信号不足时,answer 的选项标记(形如「A. (2,7)」)作次要信号 → 选择题句。"""
    question = {"text": "这道题应该选哪个?", "answer": "A. (2,7)"}
    turn, fake = _opening(tmp_path, LEARNER, question=question)
    fake.stop()
    assert turn.text == FIRST_QUESTION_COLLECT_CHOICE


# ---------- 正确档(文字/图像共用同一句) ----------

def test_correct_arc_gets_affirmative_template(tmp_path):
    """显式做对 → 正确档文案;同样不含任何数字。"""
    turn, fake = _opening(tmp_path, {**LEARNER, "answer_status": "correct"})
    fake.stop()
    assert turn.text == FIRST_QUESTION_CORRECT
    assert turn.text == "你好同学,这道题你做对啦,真棒!还有哪里不太明白吗?"
    assert turn.text == HEAD_TEXT + TAIL_CORRECT
    assert _DIGIT.search(turn.text) is None


def test_correct_arc_ignores_question_type(tmp_path):
    """正确档不按题型分:选择题做对也是同一句(题面有选项也不加「选了什么」)。"""
    turn, fake = _opening(tmp_path, {**LEARNER, "answer_status": "correct"},
                          question=CHOICE_QUESTION)
    fake.stop()
    assert turn.text == FIRST_QUESTION_CORRECT
    assert "选了什么" not in turn.text


# ---------- 图像档:head = 图像招呼语 + 半句复述 ----------

@pytest.mark.parametrize("status, tail", [
    (None, TAIL_COLLECT_IMAGE), ("incorrect", TAIL_COLLECT_IMAGE),
    ("unanswered", TAIL_COLLECT_IMAGE), ("correct", TAIL_CORRECT),
])
def test_image_question_head_restates_half_sentence_and_keeps_tier_tail(tmp_path, status, tail):
    """带图题 + 转录读出内容 → 首问 = HEAD_IMAGE_PREFIX + 半句复述 + 「。」 + 对应档 tail。"""
    learner = {**LEARNER, **({"answer_status": status} if status else {})}
    turn, fake = _opening(tmp_path, learner, question=IMAGE_WORD_QUESTION,
                          reply_text=CLEAN_REPLY, transcription=WORD_TRANSCRIPTION)
    fake.stop()
    assert turn.text == f"{HEAD_IMAGE_PREFIX}{WORD_BRIEF}。{tail}"
    assert turn.text.startswith(HEAD_IMAGE_PREFIX)     # 图像招呼语打头
    assert WORD_BRIEF in turn.text                     # 含半句复述(贴住学生发的那道题)
    assert turn.text.endswith(tail)                    # 以对应档 tail 结尾
    assert turn.session.first_question == turn.text    # 记录面与可见面同源


def test_image_collect_sentence_is_uniform_even_with_options(tmp_path):
    """图像档采集句**统一**:题面带 A. B. C. D. 也不改句(图像档不判题型)。"""
    turn, fake = _opening(tmp_path, LEARNER, question=CHOICE_IMAGE_QUESTION,
                          reply_text=CLEAN_REPLY, transcription=CHOICE_TRANSCRIPTION)
    fake.stop()
    assert turn.text == f"{HEAD_IMAGE_PREFIX}{CHOICE_BRIEF}。{TAIL_COLLECT_IMAGE}"
    assert "选了什么" not in turn.text and "算出的答案" not in turn.text


@pytest.mark.parametrize("status, expected", [
    (None, FIRST_QUESTION_COLLECT), ("incorrect", FIRST_QUESTION_COLLECT),
    ("unanswered", FIRST_QUESTION_COLLECT), ("correct", FIRST_QUESTION_CORRECT),
])
def test_text_question_never_uses_image_head_even_with_transcription(tmp_path, status, expected):
    """部署实测修正(#182,线上题 6a61a8da):**纯文字题**下模型也会把 transcription 填成
    一句废话(实测「你先别急。」)→ 绝不能用「transcription 非空」当"带图"判据;
    文字题永远用 HEAD_TEXT,且那句废话既不进 head 也不进复述。"""
    learner = {**LEARNER, **({"answer_status": status} if status else {})}
    turn, fake = _opening(tmp_path, learner, reply_text=CLEAN_REPLY, transcription="你先别急。")
    fake.stop()
    assert turn.text == expected
    assert turn.text.startswith(HEAD_TEXT)
    assert "我看到你发的题啦" not in turn.text
    assert "你先别急" not in turn.text


def test_image_question_prefers_question_text_over_transcription(tmp_path):
    """带图题 + 题面非空 → 半句**优先取题面**,转录(可能是一句废话)不参与复述。"""
    turn, fake = _opening(tmp_path, LEARNER, question=IMAGE_WORD_QUESTION,
                          reply_text=CLEAN_REPLY, transcription="这是一段无关的转录废话。")
    fake.stop()
    assert turn.text == f"{HEAD_IMAGE_PREFIX}{WORD_BRIEF}。{TAIL_COLLECT_IMAGE}"
    assert "废话" not in turn.text


def test_image_only_question_also_restates_transcription(tmp_path):
    """纯图题(question.text 为空)读出了转写 → 题面确无内容,才用转录当半句来源。"""
    turn, fake = _opening(tmp_path, LEARNER, question=IMAGE_ONLY_QUESTION,
                          reply_text=CLEAN_REPLY, transcription=WORD_TRANSCRIPTION)
    fake.stop()
    assert turn.text == f"{HEAD_IMAGE_PREFIX}{WORD_BRIEF}。{TAIL_COLLECT_IMAGE}"
    assert turn.session.question["text"] == WORD_TRANSCRIPTION  # 转写仍回填题面


@pytest.mark.parametrize("question, transcription", [
    (IMAGE_ONLY_QUESTION, ""), (IMAGE_ONLY_QUESTION, "   "),
    (IMAGE_ONLY_QUESTION, "好"), (IMAGE_ONLY_QUESTION, "嗯。"),
    # 题面非空但本身太短(不足 4 字)→ 也不拿转录顶上(题面优先);图像档退回文字档
    ({"text": "好。", "image": "file:photo-short-1"}, WORD_TRANSCRIPTION),
])
def test_no_readable_brief_falls_back_to_text_head(tmp_path, question, transcription):
    """读不出半句(转录空/过短,或题面本身太短)→ 退回纯文字档,不出「…这道题:。」残句。

    退回时一律用**非选择题**那句(图像题读不出内容 → 与「评测口径无 answer」同归非选择)。"""
    turn, fake = _opening(tmp_path, LEARNER, question=question,
                          reply_text=CLEAN_REPLY, transcription=transcription)
    fake.stop()
    assert turn.text == HEAD_TEXT + TAIL_COLLECT_OPEN
    assert turn.text == FIRST_QUESTION_COLLECT
    assert HEAD_IMAGE_PREFIX not in turn.text and ":" not in turn.text


def test_long_brief_is_capped_at_16_chars_with_ellipsis(tmp_path):
    """长半句(边界前 > 16 字)→ 复述截到 16 字并以「…」结尾(纯图题走转录这条来源)。"""
    long_text = "鸡兔同笼共有头八个脚二十六只问笼中各有多少只鸡和兔"   # 24 字,内部无逗号/句末标点
    turn, fake = _opening(tmp_path, LEARNER, question=IMAGE_ONLY_QUESTION,
                          reply_text=CLEAN_REPLY, transcription=long_text)
    fake.stop()
    brief = turn.text[len(HEAD_IMAGE_PREFIX):-len("。" + TAIL_COLLECT_IMAGE)]
    assert brief.endswith("…")
    assert brief[:-1] == long_text[:16]              # 截断位置确定
    assert len(brief[:-1]) <= 16                     # 上限 16 字(省略号另计)


def test_brief_rules_boundaries():
    """半句截断计数边界(公开函数直接钉):逗号/句末标点谁更早取谁;16 字上限;
    不足 4 字不复述;先 strip。半句来源走**纯图题**(题面为空 → 只能用转录)。"""
    pure_image = {"image": "file:photo-boundary"}
    keep15 = "一二三四五六七八九十一二三四五"           # 15 字
    keep16 = keep15 + "六"                            # 16 字
    keep17 = keep16 + "七"                            # 17 字
    assert first_question_text(None, transcription=keep15, question=pure_image) == (
        f"{HEAD_IMAGE_PREFIX}{keep15}。{TAIL_COLLECT_IMAGE}")
    assert first_question_text(None, transcription=keep16, question=pure_image) == (
        f"{HEAD_IMAGE_PREFIX}{keep16}。{TAIL_COLLECT_IMAGE}")     # 16 字不加省略号
    assert first_question_text(None, transcription=keep17, question=pure_image) == (
        f"{HEAD_IMAGE_PREFIX}{keep16}…。{TAIL_COLLECT_IMAGE}")    # 17 字截到 16 + 「…」
    # 首个逗号优先:逗号(,)比句末标点(。)更早 → 取逗号(全角逗号同款)
    for text in ("先算乘法,再算加法。结果是几", "先算乘法，再算加法。", "先算乘法,再算加法,"):
        assert first_question_text(None, transcription=text, question=pure_image) == (
            f"{HEAD_IMAGE_PREFIX}先算乘法。{TAIL_COLLECT_IMAGE}")
    # 句末标点更早 → 取句末标点
    assert first_question_text(None, transcription="先算乘法。再算加法,然后呢",
                               question=pure_image) == (
        f"{HEAD_IMAGE_PREFIX}先算乘法。{TAIL_COLLECT_IMAGE}")
    # 首尾空白先 strip
    assert first_question_text(None, transcription="  先算乘法。", question=pure_image) == (
        f"{HEAD_IMAGE_PREFIX}先算乘法。{TAIL_COLLECT_IMAGE}")
    # 不足 4 字 → 不复述,退回纯文字档(非选择题句)
    for too_short in ("好。", "先算。", "先算乘。"):
        assert first_question_text(None, transcription=too_short,
                                   question=pure_image) == HEAD_TEXT + TAIL_COLLECT_OPEN


def test_image_gate_and_brief_source_priority():
    """两条硬规则(部署实测修正 #182):①**不带图** → 永远 HEAD_TEXT(哪怕转录很长);
    ②**带图** → 半句优先取题面,仅当题面为空(真·纯图题)才用转录。"""
    long_trans = "鸡兔同笼共有头八个脚二十六只问笼中各有多少只鸡和兔"
    # ① 不带图:图像 head 与复述一律不出现
    assert first_question_text(None, transcription=long_trans,
                               question={"text": "解方程 3x+7=25。"}) == (
        HEAD_TEXT + TAIL_COLLECT_OPEN)
    assert first_question_text(None, transcription=long_trans, question=None) == (
        HEAD_TEXT + TAIL_COLLECT_OPEN)
    # ② 带图 + 题面非空 → 取题面(无关转录不参与)
    assert first_question_text(None, transcription="你一定要加油哦。", question={
        "text": "小明有8本书,借出3本后又买了5本,现在有多少本?", "image": "file:x"}) == (
        f"{HEAD_IMAGE_PREFIX}小明有8本书。{TAIL_COLLECT_IMAGE}")
    # ③ 带图 + 题面为空 → 才用转录
    assert first_question_text(None, transcription="小明有8本书,借出3本。",
                               question={"image": "file:x"}) == (
        f"{HEAD_IMAGE_PREFIX}小明有8本书。{TAIL_COLLECT_IMAGE}")


# ---------- 答案泄露:分档回归钉 ----------

def test_text_opening_carries_no_digits_at_all(tmp_path):
    """文字档回归钉:head 是纯文字招呼语 → 首问零数字(题面/答案一个都不出现);
    采集档与正确档、非选择题与选择题都钉。"""
    answer_digits = set(_DIGIT.findall(str(GRID_QUESTION["answer"]))) | set(
        _DIGIT.findall(str(CHOICE_QUESTION["answer"])))
    assert answer_digits  # 题目本身带数字答案,断言才有意义
    for question in (GRID_QUESTION, CHOICE_QUESTION):
        for status in ("correct", "incorrect", None):
            learner = {**LEARNER, **({"answer_status": status} if status else {})}
            turn, fake = _opening(tmp_path, learner, question=question)
            fake.stop()
            assert not (answer_digits & set(_DIGIT.findall(turn.text))), f"{status}"
            assert _DIGIT.search(turn.text) is None, f"{status}"


def test_image_opening_carries_no_answer_only_digits(tmp_path):
    """图像档回归钉:复述题面必然带题面数字,故只钉「答案独有数字」= 答案数字集 −
    **题面**数字集,一个都不许出现(半句来自题面,故不再看转录)。

    应用题「10本」的 1/0 不在题面里 → 差集 {"1","0"} 非空,这条钉不空转
    (网格题那一差集为空、断言必然通过,故不拿它当唯一见证)。"""
    word_only = set(_DIGIT.findall(str(IMAGE_WORD_QUESTION["answer"]))) - set(
        _DIGIT.findall(IMAGE_WORD_QUESTION["text"]))
    assert word_only == {"1", "0"}   # 非空,下面的断言才有约束力
    turn, fake = _opening(tmp_path, LEARNER, question=IMAGE_WORD_QUESTION,
                          reply_text=CLEAN_REPLY, transcription=WORD_TRANSCRIPTION)
    fake.stop()
    assert turn.text == f"{HEAD_IMAGE_PREFIX}{WORD_BRIEF}。{TAIL_COLLECT_IMAGE}"
    assert _DIGIT.search(turn.text) is not None             # 首问确实带数字(非空断言)
    assert not (word_only & set(_DIGIT.findall(turn.text)))


# ---------- 既有分支与调用面不受影响 ----------

def test_model_call_still_made_and_steps_stored(tmp_path):
    """首问文本固定 ≠ 不调模型:模型照常被调一次,steps 仍由 solver 校验入库。"""
    steps = [{"step": "先写排", "value": "12"}, {"step": "再写号", "value": "5"}]
    turn, fake = _opening(tmp_path, LEARNER, steps=steps)
    fake.stop()
    assert len(fake.requests) == 1                  # 统一 open 一次,照旧
    assert turn.session.steps == steps              # 阶梯底稿仍采信模型产出
    assert turn.text == FIRST_QUESTION_COLLECT      # 但可见文本是模板


def test_pure_image_unacceptable_still_fails_closed(tmp_path):
    """既有分支优先:纯图题 acceptable=false → fail closed(不被模板/转录复述改写)。"""
    turn, fake = _opening(tmp_path, LEARNER, question={"image": "file:photo-1"},
                          reply_text="不该被采信的首问", transcription="解方程 3x+7=25。",
                          acceptable=False)
    fake.stop()
    assert turn.state == "failed" and "题图" in turn.text


def test_image_question_with_empty_reply_keeps_opening_fallback(tmp_path):
    """既有分支优先:图文题 acceptable=false 且 reply 留空 → 仍走 kernel._OPENING_FALLBACK
    (即便转录读出了内容,也不被 head 组装改写)。"""
    question = {"text": "鸡兔同笼,共 8 头 26 足。", "image": "data:image/png;base64,QUJD"}
    turn, fake = _opening(tmp_path, LEARNER, question=question, reply_text="",
                          transcription="鸡兔同笼,共 8 头 26 足。", acceptable=False)
    fake.stop()
    assert turn.state == "first_question_ready"
    assert turn.text == "我们先看看这道题,你能说说题目给了哪些条件吗?"  # kernel._OPENING_FALLBACK
