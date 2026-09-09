"""FileSessionStore 合同(M3 PR6:文件就是 v1 的 store,additive-only)。

roundtrip 相等、重启恢复(写文件→新实例→读文件→session 可用)、旧文件缺新字段
按 dataclass 默认值补齐(不迁移不删字段);service 注入后内核回合自动落盘。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from edu_agent.agents.small_lecturer import LearnerSession, Summary
from edu_agent.api import FileSessionStore, build_service


def sample_session(**overrides) -> LearnerSession:
    session = LearnerSession(
        question={"text": "解方程 3x+7=25", "answer": "x=6"},
        learner={"grade": "五年级", "answer_status": "correct"},
        history=[{"role": "user", "content": "两边减 7。"},
                 {"role": "assistant", "content": "为什么两边能同时减?"}],
    )
    session.state = "ready_to_confirm"
    session.session_version = 4
    session.stuck = True
    session.summary = Summary(text="你完整讲清楚了。", status="completed",
                              session_version=4)
    for key, value in overrides.items():
        setattr(session, key, value)
    return session


# ---------- 保存→加载→roundtrip 相等 ----------

def test_save_load_roundtrip_equality(tmp_path):
    store = FileSessionStore(tmp_path)
    session = sample_session()
    store.save(session)
    assert (tmp_path / f"{session.session_id}.json").exists()  # data/sessions/{id}.json 布局
    restored = store.load(session.session_id)
    assert restored == session  # dataclass 逐字段相等(含 Summary 重建)
    assert restored.summary == session.summary and restored.stuck is True


def test_save_load_without_summary(tmp_path):
    store = FileSessionStore(tmp_path)
    session = sample_session(summary=None, stuck=False)
    store.save(session)
    assert store.load(session.session_id) == session
    assert store.load(session.session_id).summary is None


def test_load_missing_returns_none(tmp_path):
    assert FileSessionStore(tmp_path).load("kernel_no_such") is None


# ---------- 重启恢复:写文件→新实例→读文件→session 可用 ----------

def test_restart_recovery_with_new_store_instance(tmp_path):
    first = FileSessionStore(tmp_path)
    session = sample_session()
    first.save(session)

    second = FileSessionStore(tmp_path)  # 进程重启后的新实例
    recovered = second.load(session.session_id)
    assert recovered == session          # 字段完整
    assert recovered.finished is False   # 恢复的是可用 session,行为 property 正常
    recovered.history.append({"role": "user", "content": "继续"})
    assert recovered.session_version + 1 == 5  # 可继续内核流转(version 推进合法)


def test_startup_scan_load_all_sorted(tmp_path):
    FileSessionStore(tmp_path).save(sample_session())
    FileSessionStore(tmp_path).save(sample_session())  # 第二个 session(新 session_id)
    sessions = FileSessionStore(tmp_path).load_all()
    assert len(sessions) == 2 and all(s.state == "ready_to_confirm" for s in sessions)
    assert FileSessionStore(tmp_path / "void").load_all() == []  # 目录不存在 → 空表


def test_corrupt_file_is_skipped_not_fatal(tmp_path):
    """审查 P2 回归:一个半截 JSON(进程写入中途被杀的伴生产物)只被隔离跳过,
    不炸整个启动扫描。"""
    good = sample_session()
    FileSessionStore(tmp_path).save(good)
    (tmp_path / "kernel_broken.json").write_text('{"question": {"text": "半截', encoding="utf-8")
    (tmp_path / "kernel_stray.tmp").write_text("{}", encoding="utf-8")  # 非会话后缀也不入扫
    sessions = FileSessionStore(tmp_path).load_all()
    assert [s.session_id for s in sessions] == [good.session_id]


def test_save_is_atomic_no_tmp_left_behind(tmp_path):
    """save = tmp+os.replace(#31 同款):落盘即完整,目录里不留 .tmp 半成品。"""
    store = FileSessionStore(tmp_path)
    session = sample_session()
    store.save(session)
    store.save(session)  # 覆盖写同样原子
    assert sorted(p.name for p in tmp_path.iterdir()) == [f"{session.session_id}.json"]
    assert store.load(session.session_id) == session


def test_unknown_field_is_skipped_not_fatal(tmp_path):
    """P1-4 回归:文件带未知字段(字段改名/回滚遗留)→ LearnerSession(**data) 抛
    TypeError,应同半截 JSON 一样隔离跳过,不炸整个启动扫描(与 docstring 承诺一致)。"""
    good = sample_session()
    bad = sample_session()
    FileSessionStore(tmp_path).save(good)
    FileSessionStore(tmp_path).save(bad)
    path = tmp_path / f"{bad.session_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["renamed_field"] = "x"  # 回滚改名遗留的未知字段
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    sessions = FileSessionStore(tmp_path).load_all()
    assert [s.session_id for s in sessions] == [good.session_id]


def test_additive_only_old_file_loads_with_defaults(tmp_path):
    """旧文件缺新增字段 → dataclass 默认值补齐,不迁移不删字段(additive-only)。"""
    store = FileSessionStore(tmp_path)
    session = sample_session()
    store.save(session)
    path = tmp_path / f"{session.session_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["stuck"]          # 模拟该字段加入之前的旧文件
    del data["summary"]
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    restored = store.load(session.session_id)
    assert restored.stuck is False and restored.summary is None
    assert restored.state == "ready_to_confirm" and restored.history == session.history


# ---------- service 注入:内核回合后落盘 ----------

@dataclass
class StubTurn:
    text: str
    session: object = None
    ready_to_confirm: bool = False


class ReplayKernel:
    """带真 LearnerSession 的最小内核桩:start/reply/finish 推进 session 状态。"""

    def __init__(self):
        self.session = None

    def start(self, question: dict, learner: dict) -> StubTurn:
        self.session = LearnerSession(question=question, learner=learner)
        self.session.state = "first_question_ready"  # 同真内核:start 后首问就绪
        return StubTurn("首问", session=self.session)

    def reply(self, session: LearnerSession, student_message: str) -> StubTurn:
        session.state = "ready_to_confirm"
        session.session_version += 1
        session.history.append({"role": "user", "content": student_message})
        return StubTurn("好", session=session, ready_to_confirm=True)

    def finish(self, session: LearnerSession) -> StubTurn:
        session.state = "completed"
        return StubTurn("完成", session=session)


def test_service_persists_kernel_session_after_turns(tmp_path):
    service = build_service(ReplayKernel(), sessions=FileSessionStore(tmp_path))
    opened = service.open("q-1", "idem-store-1", learner={})
    session = service._conversation_or_404(
        opened["conversation"]["conversation_id"]).extras["kernel_session"]
    path = tmp_path / f"{session.session_id}.json"
    assert path.exists() and json.loads(path.read_text(encoding="utf-8"))["state"] \
        == "first_question_ready"
    service.send(opened["conversation"]["conversation_id"], {
        "content": "两边减 7。",
        "input": {"skill_session_id": opened["skill_session_id"],
                  "expected_session_version": opened["session_version"]}})
    restored = FileSessionStore(tmp_path).load(session.session_id)  # 新实例读回
    assert restored.state == "ready_to_confirm" and restored.session_version == 2


def test_service_without_session_store_is_noop():
    service = build_service(ReplayKernel())  # 未注入 sessions:空操作,行为不变
    opened = service.open("q-1", "idem-store-2", learner={})
    assert opened["first_question_ready"] is True
