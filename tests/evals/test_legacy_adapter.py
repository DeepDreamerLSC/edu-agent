"""老系统适配器雏形合同(00 §8.2 阶段 1):对着假老系统服务器验证流程驱动与恢复路径。

真实环境的行为结论见 docs/evals/spike-legacy-adapter.md(实测);这里只测适配器逻辑。
"""

from __future__ import annotations

import socket
import threading

import pytest
from fake_legacy import FakeLegacy

from edu_agent.evals import EnvironmentFailure, LegacyAdapter

CASE = {"question_id": "6a695a01", "student_turns": ["12", "3", "我讲完了"]}


@pytest.fixture
def credentials(monkeypatch):
    monkeypatch.setenv("EDU_LEGACY_ACCOUNT", "cap_student_1")
    monkeypatch.setenv("EDU_LEGACY_PASSWORD", "not-a-real-secret")


def test_full_flow_drives_dialogue_to_terminal(tmp_path, credentials):
    fake = FakeLegacy(["12个圆片,平均分成4份,每份几个?", "对!每份3个。你讲完了,确认结束?"]).start()
    adapter = LegacyAdapter(base_url=fake.url)
    transcript = adapter.run_case(CASE)
    fake.stop()
    assert transcript["question_id"] == "6a695a01"
    assert transcript["attempt_id"] == "qat_fake"
    assert transcript["final_state"] == "completed"
    # 首问(open 返回)+ 3 个学生回合
    assert [t["student"] for t in transcript["turns"]] == ["", "12", "3", "我讲完了"]
    assert transcript["turns"][0]["tutor"] == "先看看图上有几个圆片?"
    assert transcript["turns"][-1]["state"] == "completed"
    assert transcript["total_ms"] >= 0
    # 流式请求带幂等键与 session_version(实测契约)
    stream = [r for r in fake.requests if r["path"].endswith("/messages/stream")]
    assert all(r["body"]["idempotency_key"] and r["body"]["client_turn_id"] for r in stream)
    assert stream[0]["body"]["input"]["expected_session_version"] == 3
    assert stream[1]["body"]["input"]["expected_session_version"] == 4
    # open 走幂等键(00 §4.2)
    open_request = next(r for r in fake.requests if r["path"].endswith("/open"))
    assert open_request["body"]["idempotency_key"]


def test_token_expired_mid_case_renews_and_retries(credentials):
    # open 后撤销 token:后续请求 401 → 适配器重登录重试,流程不中断(spike 边界三验)
    fake = FakeLegacy(["重试成功后的回复"], revoke_token_after_open=True).start()
    adapter = LegacyAdapter(base_url=fake.url)
    transcript = adapter.run_case({"question_id": "q", "student_turns": ["3", "好的"]})
    fake.stop()
    assert fake.login_count == 2  # 初始登录 + 401 后重登录
    assert transcript["final_state"] == "completed"
    assert transcript["turns"][1]["tutor"] == "重试成功后的回复"


def test_stream_error_event_is_environment_failure(credentials):
    # 第 4 个请求 = login/open/refresh 之后的首次流式回合
    fake = FakeLegacy(["不该到达"], stream_error_on_turn=4).start()
    adapter = LegacyAdapter(base_url=fake.url)
    with pytest.raises(EnvironmentFailure, match="流式错误事件"):
        adapter.run_case({"question_id": "q", "student_turns": ["3"]})
    fake.stop()


def test_unreachable_host_is_environment_failure(credentials):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(4)

    def refuse_all():
        while True:
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            conn.close()

    threading.Thread(target=refuse_all, daemon=True).start()
    adapter = LegacyAdapter(base_url=f"http://127.0.0.1:{listener.getsockname()[1]}")
    with pytest.raises(EnvironmentFailure):
        adapter.run_case(CASE)
    listener.close()


def test_missing_credentials_is_environment_failure(tmp_path, monkeypatch):
    monkeypatch.delenv("EDU_LEGACY_ACCOUNT", raising=False)
    monkeypatch.delenv("EDU_LEGACY_PASSWORD", raising=False)
    adapter = LegacyAdapter()
    with pytest.raises(EnvironmentFailure, match="EDU_LEGACY_ACCOUNT"):
        adapter.run_case(CASE)
