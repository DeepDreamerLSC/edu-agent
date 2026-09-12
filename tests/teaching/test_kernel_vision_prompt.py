"""M3 PR2(vision 接线 + answer/analysis 进 prompt)教学合同测试。

断言即规格:vision 三字段 schema 的四分支(acceptable+transcription /
not_acceptable / 纯图题走转写 / 纯文本题跳过);泄露护栏对照文本扩到
answer/analysis(教师侧看得见,学生侧永不出现);题目段与追问锚点段装配。
零真实模型(假上游);剧本构造器与 Gateway 构造收拢在 tests/fixtures/teachkit.py。
"""

from __future__ import annotations

import json

import pytest
from fake_openai import completion

from edu_agent.agents.small_lecturer import FIRST_QUESTION_COLLECT, start

from teachkit import kernel_env, open_json
from test_kernel_state_machine import LEARNER

QUESTION_WITH_ANSWER = {
    "text": "解方程 3x+7=25,并说明每一步为什么这样做。",
    "answer": "x=6",
    "analysis": "先在等式两边同时减去7，得到3x=18；再同时除以3，得到x=6。",
    "knowledge_points": ["简易方程"],
}


def tutor_user_prompt(requests: list, index: int = 0) -> dict:
    """取第 index 次 tutor 请求的 user 消息(内核装配的 JSON 上下文)。

    messages[1] = 内核 user 消息;末条是路线 1 追加的 schema 指令(gateway 装配)。
    多模态题(带图)时 content 是 [text, image_url] 块,取 text 块。"""
    content = requests[index]["messages"][1]["content"]
    if isinstance(content, list):
        content = content[0]["text"]
    return json.loads(content)


# ---------- vision 四分支 ----------
# 分支④(纯文本题跳过 vision,只调 tutor 一次)由
# test_kernel_state_machine.py::test_start_text_question_skips_vision 承担。

def test_start_image_acceptable_with_transcription_proceeds(tmp_path):
    """分支①:统一 open acceptable+transcription → 放行,首问照常。"""
    with kernel_env(tmp_path, [completion(open_json("我们先确认题意:这道题要我们求什么?",
                                                    acceptable=True, transcription="解方程 3x+7=25。"))]) as (fake, gateway):
        turn = start({"text": "鸡兔同笼,共 10 头 26 足。", "image": "file:photo-1"},
                     LEARNER, gateway=gateway)
        assert turn.state == "first_question_ready"
        assert len(fake.requests) == 1


def test_text_question_with_rejected_image_degrades_to_text_teaching(tmp_path):
    """图文题(题库命中,权威文答在题面)统一 open 判 unacceptable → 降级纯文教学,
    不终态;fail-closed 只留给无文字兜底的纯图题(该分支见
    test_kernel_state_machine.py::test_start_image_untrusted_fails_closed_without_tutor)。"""
    with kernel_env(tmp_path, [completion(open_json("我们先看已知条件。", acceptable=False))]) as (fake, gateway):
        turn = start({"text": "鸡兔同笼,共 8 头 26 足。", "answer": "鸡3只,兔5只",
                      "image": "data:image/png;base64,QUJD"}, LEARNER, gateway=gateway)
        assert turn.state == "first_question_ready"
        assert len(fake.requests) == 1  # 照常教学(题面文答是权威,图只是辅助)


def test_start_image_travels_as_multimodal_part_not_text(tmp_path):
    """题图经 ModelRequest.images 走 image_url 内容块;文本消息不携带图片引用
    (多模态接线回归:此前 file_id 被拼进 JSON 文本,模型从未见过图)。"""
    with kernel_env(tmp_path, [completion(open_json("题图清晰,先读题。"))]) as (fake, gateway):
        start({"text": "鸡兔同笼,共 10 头 26 足。", "image": "data:image/png;base64,QUJD"},
              LEARNER, gateway=gateway)
        messages = fake.requests[0]["messages"]
        parts = messages[1]["content"]  # [0]=system,[1]=user(统一 open)
        assert isinstance(parts, list) and [p["type"] for p in parts] == ["text", "image_url"]
        assert parts[1]["image_url"]["url"] == "data:image/png;base64,QUJD"
        assert "QUJD" not in parts[0]["text"]  # 图片引用不进文本


def test_vision_task_carries_explicit_criteria(tmp_path):
    """判定标准随统一 open 任务下发:解不出/题干歧义不影响 acceptable——
    修复 8B 模型自创标准把可解题当不可接受(题库实测误杀 6/12)。"""
    with kernel_env(tmp_path, [completion(open_json("先读题。"))]) as (fake, gateway):
        start({"image": "data:image/png;base64,QUJD"}, LEARNER, gateway=gateway)
        content = fake.requests[0]["messages"][1]["content"]
        task_text = content[0]["text"] if isinstance(content, list) else content
        assert "多道独立题目" in task_text and "不影响 acceptable" in task_text


def test_start_image_only_question_fills_transcription_as_text(tmp_path):
    """分支③:纯图题(question.text 为空)的可信转写回填题面——进 tutor prompt
    与泄露护栏对照,且不改调用方入参。"""
    with kernel_env(tmp_path, [completion(open_json("我们先确认题意:这道题要我们求什么?",
                                                    acceptable=True, transcription="解方程 3x+7=25,求 x。"))]) as (fake, gateway):
        question = {"image": "file:photo-3"}
        turn = start(question, LEARNER, gateway=gateway)
        assert turn.state == "first_question_ready"
        assert turn.session.question["text"] == "解方程 3x+7=25,求 x。"  # 转写回填会话(后续轮/护栏对照)
        assert question == {"image": "file:photo-3"}  # 调用方入参不被改写


# ---------- 题目段:answer/analysis 教师侧 + 追问锚点 ----------

def test_user_prompt_carries_answer_analysis_and_anchor(tmp_path):
    """题目段 = 题面 + 参考答案 + 解析(教师侧);knowledge_points 有值进锚点段。"""
    with kernel_env(tmp_path, [completion(open_json("题目要我们求什么?"))]) as (fake, gateway):
        start(dict(QUESTION_WITH_ANSWER), LEARNER, gateway=gateway)
        prompt = tutor_user_prompt(fake.requests)
        assert prompt["题目"]["题面"] == QUESTION_WITH_ANSWER["text"]
        assert prompt["题目"]["参考答案"] == "x=6"
        assert prompt["题目"]["解析"] == QUESTION_WITH_ANSWER["analysis"]
        assert prompt["追问锚点"] == ["简易方程"]


def test_user_prompt_omits_anchor_when_knowledge_points_absent(tmp_path):
    """knowledge_points 空值不进 prompt(锚点段不加键)。"""
    with kernel_env(tmp_path, [completion(open_json("第一问?"))]) as (fake, gateway):
        start({"text": "解方程 3x+7=25", "answer": "x=6", "analysis": "两边先减 7。"},
              LEARNER, gateway=gateway)
        assert "追问锚点" not in tutor_user_prompt(fake.requests)


# ---------- 泄露护栏:对照文本扩到 answer/analysis ----------

@pytest.mark.parametrize("leak_reply,extra_forbidden", [
    # answer 文本出现在回复中 → 拦截(答案不许从教师侧漏到学生侧)
    ("答案是 x=6。你能说说为什么吗?", ()),
    # 解析的解法路径被复制进回复 → 拦截(grounded_solution_path_disclosure 同款)
    ("先在等式两边同时减去7，得到3x=18；再同时除以3，得到x=6。听懂了吗?", ("3x",)),
], ids=["answer_text", "analysis_solution_path"])
def test_reply_leaking_teacher_reference_is_intercepted(tmp_path, leak_reply, extra_forbidden):
    """教师侧对照文本泄露 → 拦截。

    首问可见文本恒为固定模板(prompting.first_question_text),故「拦截」由埋点 +
    模板不含答案数字共同见证,不再靠兜底句文本断言。"""
    with kernel_env(tmp_path, [completion(open_json(leak_reply))]) as (fake, gateway):
        turn = start(dict(QUESTION_WITH_ANSWER), LEARNER, gateway=gateway)
        assert turn.text == FIRST_QUESTION_COLLECT
        for token in ("x=6", *extra_forbidden):
            assert token not in turn.text
        assert [e["guard"] for e in turn.session.guard_events if e.get("guard")] == ["answer_leak"]


def test_clean_socratic_reply_passes_with_answer_reference_present(tmp_path):
    """普通苏格拉底问句不受教师侧对照文本影响(窄判定,不误伤):零护栏埋点。"""
    clean = open_json("题目要我们求什么?先说说你读到了哪些条件。")
    clean = open_json("题目要我们求什么?先说说你读到了哪些条件。")
    with kernel_env(tmp_path, [completion(clean)]) as (fake, gateway):
        turn = start(dict(QUESTION_WITH_ANSWER), LEARNER, gateway=gateway)
        assert [e for e in turn.session.guard_events if e.get("guard")] == []
        assert turn.text == FIRST_QUESTION_COLLECT
