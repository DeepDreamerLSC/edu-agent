"""老系统适配器合同(00 §8.2 阶段 1-2):对着假老系统服务器验证流程驱动、恢复路径与
fresh 学生池轮换;以及适配器 × EvalRunner 的集成(失败分类与 checkpoint)。

真实环境的行为结论见 docs/evals/spike-legacy-adapter.md(实测);这里只测适配器逻辑。
"""

from __future__ import annotations

import json
import socket
import threading

import pytest
from fake_legacy import FakeLegacy

from edu_agent.evals import (
    EnvironmentFailure,
    EvalRunner,
    LegacyAdapter,
    RunnerConfig,
    morning_summary,
)

CASE = {"question_id": "6a695a01", "student_turns": ["12", "3", "我讲完了"]}


@pytest.fixture
def pool_file(tmp_path, monkeypatch):
    path = tmp_path / "pool.json"
    path.write_text(json.dumps({"students": [
        {"account": "cap_student_a", "password": "pool-secret-a", "role": "student"},
        {"account": "cap_student_b", "password": "pool-secret-b", "role": "student"},
        {"account": "cap_teacher_c", "password": "pool-secret-c", "role": "teacher"},
    ]}), encoding="utf-8")
    monkeypatch.setenv("EDU_LEGACY_STUDENT_POOL", str(path))
    return path


def test_idempotency_keys_are_stable_across_runs(pool_file):
    # 中断续跑安全:同 case 两次执行(哪怕服务端已提交过部分回合)产生同一幂等键序列,
    # 服务端按键幂等返回已提交结果,不会判并发更新 409(阶段 2 试跑实测的续跑缺口)
    keys_per_run = []
    for _ in range(2):
        fake = FakeLegacy(["回复一", "回复二", "完成"]).start()
        adapter = LegacyAdapter(base_url=fake.url)
        adapter.run_case({"id": "stable-case", "question_id": "q", "student_turns": ["1", "2", "3"]})
        fake.stop()
        keys_per_run.append([r["body"]["idempotency_key"]
                             for r in fake.requests if r["path"].endswith("/messages/stream")])
    assert keys_per_run[0] == keys_per_run[1]
    assert len(set(keys_per_run[0])) == 3  # 回合间互不重键
    assert keys_per_run[0][0].endswith(":t0")


def test_resume_skips_committed_turns(pool_file):
    """审查 P1 复现形态:服务端已有已提交回合(t0),续跑不得重发——重发同回合
    会因版本推进被判并发更新 409(稳定幂等键只救孤儿生成)。恢复响应是对齐权威:
    跳过已提交回合、从 t1 续发、transcript 回填已提交内容。
    """
    fake = FakeLegacy(["t1 的讲解", "t2 的讲解"], preset_committed=1).start()
    adapter = LegacyAdapter(base_url=fake.url)
    transcript = adapter.run_case({"id": "stable-case", "question_id": "q",
                                   "student_turns": ["1", "2", "3"]})
    fake.stop()
    stream = [r for r in fake.requests if r["path"].endswith("/messages/stream")]
    # 只发 t1/t2,绝不重发已提交的 t0(重发即 409,实测三连)
    assert [r["body"]["idempotency_key"][-3:] for r in stream] == [":t1", ":t2"]
    assert stream[0]["body"]["input"]["expected_session_version"] == 4  # 恢复响应的已推进版本
    assert stream[0]["body"]["content"] == "2"  # 第 2 个学生回合
    # transcript 完整:首问 + 回填的 t0 + 新发的 t1/t2
    assert [t["student"] for t in transcript["turns"]] == ["", "已提交回答1", "2", "3"]
    assert transcript["turns"][1]["tutor"] == "已提交讲解1"
    assert transcript["final_state"] == "completed"


def test_full_flow_drives_dialogue_to_terminal(pool_file):
    fake = FakeLegacy(["12个圆片,平均分成4份,每份几个?", "对!每份3个。", "你讲完了,确认结束?"]).start()
    adapter = LegacyAdapter(base_url=fake.url)
    transcript = adapter.run_case(CASE)
    fake.stop()
    assert transcript["question_id"] == "6a695a01"
    assert transcript["attempt_id"] == "qat_fake"
    assert transcript["final_state"] == "completed"
    assert [t["student"] for t in transcript["turns"]] == ["", "12", "3", "我讲完了"]
    assert transcript["turns"][0]["tutor"] == "先看看图上有几个圆片?"
    assert transcript["login_ms"] >= 0 and transcript["open_ms"] >= 0  # 各段延迟入档
    # 流式请求带幂等键与 session_version(实测契约)
    stream = [r for r in fake.requests if r["path"].endswith("/messages/stream")]
    assert all(r["body"]["idempotency_key"] and r["body"]["client_turn_id"] for r in stream)
    assert stream[0]["body"]["input"]["expected_session_version"] == 3
    assert stream[1]["body"]["input"]["expected_session_version"] == 4
    open_request = next(r for r in fake.requests if r["path"].endswith("/open"))
    assert open_request["body"]["idempotency_key"]


def test_eval_identity_headers_sent_when_configured(pool_file, monkeypatch):
    # 可信评测身份:EDU_LEGACY_EVAL_TOKEN 设置时,认证请求带内部服务头(prompt_lab 归属题必需)
    monkeypatch.setenv("EDU_LEGACY_EVAL_TOKEN", "eval-secret-token")
    fake = FakeLegacy(["回复一", "完成"]).start()
    adapter = LegacyAdapter(base_url=fake.url)
    adapter.run_case({"id": "c1", "question_id": "q", "student_turns": ["1", "2"]})
    fake.stop()
    authed = [h for h in fake.captured_headers if h.get("Authorization")]
    assert authed and all(
        h.get("X-Internal-Service-Id") == "small_lecturer_dialogue_eval"
        and h.get("X-Internal-Service-Token") == "eval-secret-token"
        for h in authed
    )


def test_eval_identity_headers_survive_401_renewal(pool_file, monkeypatch):
    # 审查点名:401 重登录后的重发请求仍带评测头(open 后撤销 token 的实战形态)
    monkeypatch.setenv("EDU_LEGACY_EVAL_TOKEN", "eval-secret-token")
    fake = FakeLegacy(["重试成功后的回复"], revoke_token_after_open=True).start()
    adapter = LegacyAdapter(base_url=fake.url)
    transcript = adapter.run_case({"id": "c3", "question_id": "q", "student_turns": ["1", "2"]})
    fake.stop()
    assert fake.login_count == 2  # 初始登录 + 401 后重登录
    assert transcript["final_state"] == "completed"
    authed = [h for h in fake.captured_headers if h.get("Authorization")]
    assert all(
        h.get("X-Internal-Service-Id") == "small_lecturer_dialogue_eval"
        and h.get("X-Internal-Service-Token") == "eval-secret-token"
        for h in authed
    )


def test_eval_identity_headers_absent_without_token(pool_file, monkeypatch):
    monkeypatch.delenv("EDU_LEGACY_EVAL_TOKEN", raising=False)
    fake = FakeLegacy(["回复一", "完成"]).start()
    adapter = LegacyAdapter(base_url=fake.url)
    adapter.run_case({"id": "c2", "question_id": "q", "student_turns": ["1", "2"]})
    fake.stop()
    assert all("X-Internal-Service-Id" not in h for h in fake.captured_headers)


def test_student_pool_rotates_and_is_stable_per_case(pool_file):
    # 教师账号被过滤;student_index 显式分配:批内不同 index 不同学生,同 index 续跑同学生
    fake = FakeLegacy(["下一问", "很好,结束"]).start()
    adapter = LegacyAdapter(base_url=fake.url)
    base = {"question_id": "q", "student_turns": ["1", "2"]}
    adapter.run_case({"id": "case-1", "student_index": 0, **base})
    adapter.run_case({"id": "case-1", "student_index": 0, **base})  # 续跑重入:同学生
    adapter.run_case({"id": "case-2", "student_index": 1, **base})  # 批内下一学生
    adapter.run_case({"id": "case-3", **base})  # 无 index:case_id 稳定哈希兜底
    fake.stop()
    logins = [r["body"]["account"] for r in fake.requests if r["path"] == "/api/auth/login"]
    assert set(logins) <= {"cap_student_a", "cap_student_b"}  # teacher 不进池
    assert logins[0] == logins[1] == "cap_student_a"
    assert logins[2] == "cap_student_b"
    assert logins[3] in {"cap_student_a", "cap_student_b"}


def test_token_expired_mid_case_renews_and_retries(pool_file):
    # open 后撤销 token:后续请求 401 → 适配器重登录重试,流程不中断(spike 边界三验)
    fake = FakeLegacy(["重试成功后的回复"], revoke_token_after_open=True).start()
    adapter = LegacyAdapter(base_url=fake.url)
    transcript = adapter.run_case({"id": "c", "question_id": "q", "student_turns": ["3", "好的"]})
    fake.stop()
    assert fake.login_count == 2  # 初始登录 + 401 后重登录
    assert transcript["final_state"] == "completed"
    assert transcript["turns"][1]["tutor"] == "重试成功后的回复"


def test_stream_error_event_is_environment_failure(pool_file):
    # 第 3 个请求 = login/open 之后的首次流式回合(refresh 已不在批跑路径)
    fake = FakeLegacy(["不该到达"], stream_error_on_turn=3).start()
    adapter = LegacyAdapter(base_url=fake.url)
    with pytest.raises(EnvironmentFailure, match="流式错误事件"):
        adapter.run_case({"id": "c", "question_id": "q", "student_turns": ["3"]})
    fake.stop()


def test_unreachable_host_is_environment_failure(pool_file):
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


def test_missing_pool_env_is_environment_failure(tmp_path, monkeypatch):
    monkeypatch.delenv("EDU_LEGACY_STUDENT_POOL", raising=False)
    adapter = LegacyAdapter()
    with pytest.raises(EnvironmentFailure, match="EDU_LEGACY_STUDENT_POOL"):
        adapter.run_case(CASE)


def test_runner_integration_checkpoint_and_classification(pool_file, tmp_path):
    """适配器 × EvalRunner(#31):ok 入 checkpoint、环境失败重试后仍败入台账,续跑只补后者。"""
    fake = FakeLegacy(["第一问", "很好,完成"]).start()
    ok_cases = [{"id": f"ok-{i}", "question_id": "q", "student_turns": ["1", "2"]}
                for i in range(2)]
    config = RunnerConfig(concurrency=2, env_retry_attempts=1,
                          backoff_base_s=0.01, backoff_cap_s=0.02)
    runner = EvalRunner(LegacyAdapter(base_url=fake.url), config, tmp_path / "runs")
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text("\n".join(json.dumps(c) for c in ok_cases) + "\n", encoding="utf-8")
    run_dir = runner.run(dataset, ok_cases)
    results = {p.stem: json.loads(p.read_text(encoding="utf-8"))
               for p in (run_dir / "results").glob("*.json")}
    assert {r["status"] for r in results.values()} == {"ok"}
    assert all(r["transcript"]["final_state"] == "completed" for r in results.values())
    assert "全部 2 条完成" in morning_summary(run_dir)
    fake.stop()
