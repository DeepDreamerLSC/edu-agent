"""M3 PR2(vision 接线 + answer/analysis 进 prompt)教学合同测试。

断言即规格:vision 三字段 schema 的四分支(acceptable+transcription /
not_acceptable / 纯图题走转写 / 纯文本题跳过);泄露护栏对照文本扩到
answer/analysis(教师侧看得见,学生侧永不出现);题目段与追问锚点段装配。
零真实模型(假上游)。
"""

from __future__ import annotations

import json

from fake_openai import FakeOpenAI, completion

from edu_agent.agents.small_lecturer import SAFE_FALLBACK_TEXT, start

from test_kernel_state_machine import LEARNER, kernel_gateway, tutor_json, vision_json

QUESTION_WITH_ANSWER = {
    "text": "解方程 3x+7=25,并说明每一步为什么这样做。",
    "answer": "x=6",
    "analysis": "先在等式两边同时减去7，得到3x=18；再同时除以3，得到x=6。",
    "knowledge_points": ["简易方程"],
}


def tutor_user_prompt(requests: list, index: int = 0) -> dict:
    """取第 index 次 tutor 请求的 user 消息(内核装配的 JSON 上下文)。

    messages[1] = 内核 user 消息;末条是路线 1 追加的 schema 指令(gateway 装配)。"""
    return json.loads(requests[index]["messages"][1]["content"])


# ---------- vision 四分支 ----------

def test_start_text_question_skips_vision_branch(tmp_path):
    """纯文本题跳过 vision:只有 tutor 一次调用。"""
    fake = FakeOpenAI([completion(tutor_json("题目要我们求什么?"))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start({"text": "解方程 3x+7=25"}, LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.state == "first_question_ready"
    assert [r["model"] for r in fake.requests] == ["fake-model"]  # vision 未被调


def test_start_image_acceptable_with_transcription_proceeds(tmp_path):
    """分支①:vision acceptable+transcription → 放行进 tutor,首问照常。"""
    vision = FakeOpenAI([completion(vision_json(True, "单题清晰", "解方程 3x+7=25。"))]).start()
    tutor = FakeOpenAI([completion(tutor_json("我们先确认题意:这道题要我们求什么?"))]).start()
    gateway = kernel_gateway(tmp_path, tutor.url, vision_url=vision.url)
    turn = start({"text": "鸡兔同笼,共 10 头 26 足。", "image": "file:photo-1"},
                 LEARNER, gateway=gateway)
    gateway.close()
    vision.stop()
    tutor.stop()
    assert turn.state == "first_question_ready"
    assert len(vision.requests) == 1 and len(tutor.requests) == 1


def test_start_image_not_acceptable_fails_closed(tmp_path):
    """分支②:vision not_acceptable → fail closed,不调 tutor。"""
    vision = FakeOpenAI([completion(vision_json(False, "疑似多题混入", ""))]).start()
    tutor = FakeOpenAI([completion(tutor_json("不该被调用"))]).start()
    gateway = kernel_gateway(tmp_path, tutor.url, vision_url=vision.url)
    turn = start({"image": "file:photo-2"}, LEARNER, gateway=gateway)
    gateway.close()
    vision.stop()
    tutor.stop()
    assert turn.state == "failed" and "题图" in turn.text
    assert len(tutor.requests) == 0


def test_start_image_travels_as_multimodal_part_not_text(tmp_path):
    """题图经 ModelRequest.images 走 image_url 内容块;文本消息不携带图片引用
    (多模态接线回归:此前 file_id 被拼进 JSON 文本,模型从未见过图)。"""
    vision = FakeOpenAI([completion(vision_json(True, "单题清晰", ""))]).start()
    tutor = FakeOpenAI([completion(tutor_json("题图清晰,先读题。"))]).start()
    gateway = kernel_gateway(tmp_path, tutor.url, vision_url=vision.url)
    start({"text": "鸡兔同笼,共 10 头 26 足。", "image": "data:image/png;base64,QUJD"},
          LEARNER, gateway=gateway)
    gateway.close()
    vision.stop()
    tutor.stop()
    messages = vision.requests[0]["messages"]
    parts = messages[0]["content"]
    assert isinstance(parts, list) and [p["type"] for p in parts] == ["text", "image_url"]
    assert parts[1]["image_url"]["url"] == "data:image/png;base64,QUJD"
    assert "QUJD" not in parts[0]["text"]  # 图片引用不进文本


def test_vision_task_carries_explicit_criteria(tmp_path):
    """判定标准随任务下发:解不出/题干歧义不影响 acceptable——修复 8B 模型
    自创标准把可解题当不可接受(题库实测误杀 6/12)。"""
    vision = FakeOpenAI([completion(vision_json(True, "单题清晰", ""))]).start()
    tutor = FakeOpenAI([completion(tutor_json("先读题。"))]).start()
    gateway = kernel_gateway(tmp_path, tutor.url, vision_url=vision.url)
    start({"image": "data:image/png;base64,QUJD"}, LEARNER, gateway=gateway)
    gateway.close()
    vision.stop()
    tutor.stop()
    task_text = vision.requests[0]["messages"][0]["content"][0]["text"]
    assert "多道独立题目" in task_text and "不影响 acceptable" in task_text


def test_text_question_with_rejected_image_degrades_to_text_teaching(tmp_path):
    """图文题(题库命中,权威文答在题面)vision 拒图 → 降级纯文教学,不终态;
    fail-closed 只留给无文字兜底的纯图题。"""
    vision = FakeOpenAI([completion(vision_json(False, "图文不清", ""))]).start()
    tutor = FakeOpenAI([completion(tutor_json("我们先看已知条件。"))]).start()
    gateway = kernel_gateway(tmp_path, tutor.url, vision_url=vision.url)
    turn = start({"text": "鸡兔同笼,共 8 头 26 足。", "answer": "鸡3只,兔5只",
                  "image": "data:image/png;base64,QUJD"}, LEARNER, gateway=gateway)
    gateway.close()
    vision.stop()
    tutor.stop()
    assert turn.state == "first_question_ready"
    assert len(tutor.requests) == 1  # 照常教学(题面文答是权威,图只是辅助)


def test_start_image_only_question_fills_transcription_as_text(tmp_path):
    """分支③:纯图题(question.text 为空)的可信转写回填题面——进 tutor prompt
    与泄露护栏对照,且不改调用方入参。"""
    vision = FakeOpenAI([completion(vision_json(True, "单题清晰", "解方程 3x+7=25,求 x。"))]).start()
    tutor = FakeOpenAI([completion(tutor_json("我们先确认题意:这道题要我们求什么?"))]).start()
    gateway = kernel_gateway(tmp_path, tutor.url, vision_url=vision.url)
    question = {"image": "file:photo-3"}
    turn = start(question, LEARNER, gateway=gateway)
    gateway.close()
    vision.stop()
    tutor.stop()
    assert turn.state == "first_question_ready"
    assert turn.session.question["text"] == "解方程 3x+7=25,求 x。"
    assert question == {"image": "file:photo-3"}  # 调用方入参不被改写
    prompt = tutor_user_prompt(tutor.requests)
    assert prompt["题目"]["题面"] == "解方程 3x+7=25,求 x。"


# ---------- 题目段:answer/analysis 教师侧 + 追问锚点 ----------

def test_user_prompt_carries_answer_analysis_and_anchor(tmp_path):
    """题目段 = 题面 + 参考答案 + 解析(教师侧);knowledge_points 有值进锚点段。"""
    fake = FakeOpenAI([completion(tutor_json("题目要我们求什么?"))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    start(dict(QUESTION_WITH_ANSWER), LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    prompt = tutor_user_prompt(fake.requests)
    assert prompt["题目"]["题面"] == QUESTION_WITH_ANSWER["text"]
    assert prompt["题目"]["参考答案"] == "x=6"
    assert prompt["题目"]["解析"] == QUESTION_WITH_ANSWER["analysis"]
    assert prompt["追问锚点"] == ["简易方程"]


def test_user_prompt_omits_anchor_when_knowledge_points_absent(tmp_path):
    """knowledge_points 空值不进 prompt(锚点段不加键)。"""
    fake = FakeOpenAI([completion(tutor_json("第一问?"))]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    start({"text": "解方程 3x+7=25", "answer": "x=6", "analysis": "两边先减 7。"},
          LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    assert "追问锚点" not in tutor_user_prompt(fake.requests)


# ---------- 泄露护栏:对照文本扩到 answer/analysis ----------

def test_reply_containing_answer_text_is_intercepted(tmp_path):
    """answer 文本出现在回复中 → 拦截(答案不许从教师侧漏到学生侧)。"""
    leak = tutor_json("答案是 x=6。你能说说为什么吗?")
    fake = FakeOpenAI([completion(leak)]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start(dict(QUESTION_WITH_ANSWER), LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.text == SAFE_FALLBACK_TEXT
    assert "x=6" not in turn.text


def test_reply_copying_analysis_solution_path_is_intercepted(tmp_path):
    """解析的解法路径被复制进回复 → 拦截(grounded_solution_path_disclosure 同款)。"""
    leak = tutor_json("先在等式两边同时减去7，得到3x=18；再同时除以3，得到x=6。听懂了吗?")
    fake = FakeOpenAI([completion(leak)]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start(dict(QUESTION_WITH_ANSWER), LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.text == SAFE_FALLBACK_TEXT


def test_clean_socratic_reply_passes_with_answer_reference_present(tmp_path):
    """普通苏格拉底问句不受教师侧对照文本影响(窄判定,不误伤)。"""
    clean = tutor_json("题目要我们求什么?先说说你读到了哪些条件。")
    fake = FakeOpenAI([completion(clean)]).start()
    gateway = kernel_gateway(tmp_path, fake.url)
    turn = start(dict(QUESTION_WITH_ANSWER), LEARNER, gateway=gateway)
    gateway.close()
    fake.stop()
    assert turn.text == "题目要我们求什么?先说说你读到了哪些条件。"
