"""tutor 请求上限参数化回归钉(有界修复:start-only budget)。

截断归因(REQUEST-LIMIT OWNED):kernel `_invoke` 旧硬编码 max_tokens=800 是
small_lecturer 全部 tutor 调用的单点输出上限;open-solve 单调用四合一
(acceptable/transcription/steps/reply)对 bank 6a61bd8d(live-distributive 冻结案
bbb155e3/5062d4d9)需求 >800,8303 忠实执行请求上限 → finish_reason=length 截断。

修复口径(逐字):`_invoke` 增加默认参数 max_tokens=800(其余调用点字节等价),
仅 start() 的 open 调用显式传 open 专用上限。冻结探针(修复后 stem @ 4bc71c93,
8303 真跑):1200 → finish_reason=stop、749 completion tokens、OPEN_SCHEMA 四件套
齐 → 冻结 1200。两根钉:

- start 的统一 open 调用 max_tokens == 1200(冻结值逐字钉,防回归);
- reply 调用 max_tokens == 800(默认参数,reply 路径字节等价)。

零网络、确定性(FakeGateway 对象注入)。judge 面(judge.py max_tokens=900)属
另一族,不在本钉范围。
"""

from __future__ import annotations

from edu_agent.agents.small_lecturer import reply, start
from teachkit import FakeGateway

QUESTION = {"text": "三段路分别长82米、88米、94米,这三段总长是多少米?",
            "answer": "264米", "analysis": "", "knowledge_points": ["加法"]}
LEARNER = {"grade": "六年级"}
OPEN_PAYLOAD = {"acceptable": True, "transcription": "", "steps": [], "reply": "你想怎么算?"}
REPLY_PAYLOAD = {"reply": "先算82加88,你说下一步?", "ready_to_confirm": False,
                 "cited_numbers": []}


def test_start_open_call_uses_frozen_open_budget():
    """start 统一 open 调用 = 冻结上限 1200(探针双门:stop + OPEN_SCHEMA 四件套齐)。"""
    gateway = FakeGateway(tutor_payloads=[dict(OPEN_PAYLOAD)])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)

    assert turn.state == "first_question_ready"
    assert len(gateway.requests) == 1                       # 统一 open 一次
    assert gateway.requests[0]["max_tokens"] == 1200        # 冻结值逐字钉


def test_reply_call_keeps_default_budget_800():
    """reply 走默认上限 800:有界修复只动 start 的 open 调用,reply 路径字节等价。"""
    gateway = FakeGateway(tutor_payloads=[dict(OPEN_PAYLOAD), dict(REPLY_PAYLOAD)])
    turn = start(dict(QUESTION), dict(LEARNER), gateway=gateway)
    turn = reply(turn.session, "然后呢?", gateway=gateway)

    assert len(gateway.requests) == 2                       # open + reply,零额外调用
    assert gateway.requests[0]["max_tokens"] == 1200        # start open(冻结值)
    assert gateway.requests[1]["max_tokens"] == 800         # reply(默认,不变)
