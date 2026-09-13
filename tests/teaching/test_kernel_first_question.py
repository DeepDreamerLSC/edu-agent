"""首问固定模板回归钉(实测缺陷:首问直接把答案报出来)。

改动口径(#235 定稿):首问**可见文本**由内核 `start()` 覆盖为
`prompting.first_question_text` 的确定性模板——**3 句固定文案**,首问内容一致性
不随题源/题型/图像变形:
- correct 档(文字/图像共用);采集档按 `question["image"]` 分 head(带图 → 固定
  图像招呼语「我看到你发的题啦」,零提取零分支);选择题统一用「答案是什么」句
  (题型分流与半句复述机器已整体撤除,#235:47% 题面会采出无信息量短语)。
不再采信模型生成的 reply 文本;模型调用照旧(steps/transcription 仍被采信)。
kernel 的 transcription 回填 question.text 保留(纯图题题面来源)。既有两条确定性
分支优先级不变:纯图题 fail-closed(`FAIL_CLOSED_TEXT`)与图文题 acceptable=false
且 reply 留空(`kernel._OPENING_FALLBACK`)。零真实模型(假上游)。
"""

from __future__ import annotations

import re

import pytest
from fake_openai import FakeOpenAI, completion

from edu_agent.agents.small_lecturer import (
    FIRST_QUESTION_COLLECT,
    FIRST_QUESTION_COLLECT_IMAGE,
    FIRST_QUESTION_CORRECT,
    HEAD_IMAGE,
    HEAD_TEXT,
    TAIL_COLLECT,
    TAIL_CORRECT,
    first_question_text,
    start,
)
from teachkit import kernel_gateway, open_json

# 实测缺陷同款题:当时的首问写成「…记作(5,12),(3,10)表示10排3号,对吗?」——
# 两个空的答案都给了。题面数字(8/6/12/5/3/10)与答案数字同源,故文字档用「无数字」兜底。
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

# 选择题(题面带 4 个选项标记 A. B. C. D.)→ 采集档**统一**那句(#235:题型分流撤除)
CHOICE_QUESTION = {
    "text": "下列各数中最大的是(  )。A. 3.14  B. 22/7  C. 3.1415  D. 3.142",
    "answer": "B. 22/7",
}
# 带图题(应用题):首问不再复述题面 → 图像档同样零数字
IMAGE_WORD_QUESTION = {
    "text": "小明有8本书,借出3本后又买了5本,现在有多少本?",
    "image": "file:photo-word-1",
    "answer": "10本",
    "knowledge_points": ["加减混合"],
}
WORD_TRANSCRIPTION = "小明有8本书,借出3本。"
IMAGE_ONLY_QUESTION = {"image": "file:photo-only-1"}   # 纯图题(无题面文字)


def _opening(tmp_path, learner: dict, question: dict | None = None,
             reply_text: str = LEAKING_REPLY, **open_kwargs):
    """走公开路径取首问(假上游 + 真 Gateway),并返回 (turn, fake)。"""
    fake = FakeOpenAI([completion(open_json(reply_text, **open_kwargs))]).start()
    gateway = kernel_gateway(fake.url, tmp_path)
    try:
        return start(dict(question or GRID_QUESTION), learner, gateway=gateway), fake
    finally:
        gateway.close()


# ---------- #235 定稿:3 句固定文案(不复述、不确认,逐字钉) ----------

@pytest.mark.parametrize("status", ["incorrect", "unanswered", "unknown", None])
def test_unified_collect_text_question(tmp_path, status):
    """文字题采集档 = 固定一句(选择题/非选择题同句),不含复述片段与识题确认。"""
    learner = {**LEARNER, **({"answer_status": status} if status else {})}
    turn, fake = _opening(tmp_path, learner)
    fake.stop()
    assert turn.state == "first_question_ready"
    assert turn.text == FIRST_QUESTION_COLLECT
    assert turn.text == "你好同学,这道题你的答案是什么呀?讲讲你的思路吧!"   # #235 定稿逐字
    assert turn.text == HEAD_TEXT + TAIL_COLLECT
    assert turn.session.first_question == FIRST_QUESTION_COLLECT  # 记录面与可见面同源
    assert _DIGIT.search(turn.text) is None
    assert "我读得对吗" not in turn.text          # 识题确认撤除
    assert "我们一起看看" not in turn.text        # 旧图像前缀(我们一起看看:)不残留
    assert "小明有8本书" not in turn.text         # 复述片段不出现(题面/转录都不进首问)


def test_unified_collect_image_question(tmp_path):
    """带图题采集档 = 固定图像招呼语 + 同一句采集(转录读出内容也不复述)。"""
    turn, fake = _opening(tmp_path, LEARNER, question=IMAGE_WORD_QUESTION,
                          reply_text=CLEAN_REPLY, transcription=WORD_TRANSCRIPTION)
    fake.stop()
    assert turn.text == FIRST_QUESTION_COLLECT_IMAGE
    assert turn.text == "你好同学,我看到你发的题啦,这道题你的答案是什么呀?讲讲你的思路吧!"
    assert turn.text == HEAD_IMAGE + TAIL_COLLECT
    assert turn.session.first_question == turn.text
    assert "我读得对吗" not in turn.text
    assert "小明有8本书" not in turn.text         # 半句复述撤除(题面优先/转录来源一并死)
    assert _DIGIT.search(turn.text) is None       # 不复述题面 → 图像档首问同样零数字


def test_unified_correct_question(tmp_path):
    """correct 档 = 固定一句(带图 + 转录也不变:正确档不因图像变形)。"""
    turn, fake = _opening(tmp_path, {**LEARNER, "answer_status": "correct"},
                          question=IMAGE_WORD_QUESTION, reply_text=CLEAN_REPLY,
                          transcription=WORD_TRANSCRIPTION)
    fake.stop()
    assert turn.text == FIRST_QUESTION_CORRECT
    assert turn.text == "你好同学,这道题你做对啦,真棒!还有哪里不太明白吗?"
    assert turn.text == HEAD_TEXT + TAIL_CORRECT
    assert _DIGIT.search(turn.text) is None
    assert "我读得对吗" not in turn.text and "小明有8本书" not in turn.text
    assert "我看到你发的题啦" not in turn.text    # 正确档恒用文字招呼语


def test_choice_question_gets_unified_collect_sentence(tmp_path):
    """选择题统一用「答案是什么」句(#235:题型分流撤除,带图选择题实测已用通用句)。"""
    turn, fake = _opening(tmp_path, LEARNER, question=CHOICE_QUESTION)
    fake.stop()
    assert turn.text == FIRST_QUESTION_COLLECT
    assert "选了什么" not in turn.text and "算出的答案" not in turn.text


def test_text_question_never_uses_image_head_even_with_transcription(tmp_path):
    """部署实测修正(#182,线上题 6a61a8da):**纯文字题**下模型也会把 transcription 填成
    一句废话(实测「你先别急。」)→ 带图判据只看 question["image"];文字题永远 HEAD_TEXT。"""
    turn, fake = _opening(tmp_path, LEARNER, reply_text=CLEAN_REPLY, transcription="你先别急。")
    fake.stop()
    assert turn.text == FIRST_QUESTION_COLLECT
    assert turn.text.startswith(HEAD_TEXT)
    assert "我看到你发的题啦" not in turn.text
    assert "你先别急" not in turn.text


def test_pure_function_three_fixed_texts():
    """公开函数直接钉 3 句:status/题型/转录怎么变,答案只在这 3 句里。"""
    image_q = {"image": "file:x"}
    for status in (None, "incorrect", "unanswered", "unknown"):
        assert first_question_text(status) == FIRST_QUESTION_COLLECT
        assert first_question_text(status, "很长的转录也不复述", image_q) == FIRST_QUESTION_COLLECT_IMAGE
    assert first_question_text("correct") == FIRST_QUESTION_CORRECT
    assert first_question_text("correct", "转录", image_q) == FIRST_QUESTION_CORRECT
    assert first_question_text("correct", question=CHOICE_QUESTION) == FIRST_QUESTION_CORRECT


def test_image_only_transcription_still_backfills_question_text(tmp_path):
    """kernel 的转录回填保留(#235:纯图题题面来源,另一用途)——首问不复述,
    但 session.question.text 仍被转录回填。"""
    turn, fake = _opening(tmp_path, LEARNER, question=IMAGE_ONLY_QUESTION,
                          reply_text=CLEAN_REPLY, transcription=WORD_TRANSCRIPTION)
    fake.stop()
    assert turn.text == FIRST_QUESTION_COLLECT_IMAGE   # 首问 = 3 句之带图采集
    assert "小明有8本书" not in turn.text              # 复述撤除
    assert turn.session.question["text"] == WORD_TRANSCRIPTION  # 回填保留(kernel)


# ---------- 答案泄露:分档回归钉 ----------

def test_text_opening_carries_no_digits_at_all(tmp_path):
    """文字档回归钉:head 是纯文字招呼语 → 首问零数字(题面/答案一个都不出现);
    采集档与正确档、网格题与选择题都钉。"""
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
    """既有分支优先:图文题 acceptable=false 且 reply 留空 → 仍走 kernel._OPENING_FALLBACK。"""
    question = {"text": "鸡兔同笼,共 8 头 26 足。", "image": "data:image/png;base64,QUJD"}
    turn, fake = _opening(tmp_path, LEARNER, question=question, reply_text="",
                          transcription="鸡兔同笼,共 8 头 26 足。", acceptable=False)
    fake.stop()
    assert turn.state == "first_question_ready"
    assert turn.text == "我们先看看这道题,你能说说题目给了哪些条件吗?"  # kernel._OPENING_FALLBACK
