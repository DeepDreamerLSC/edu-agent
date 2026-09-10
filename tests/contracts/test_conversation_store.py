"""FileConversationStore 合同(M3 WS2:会话表文件级,重启后 open→message→finish 可续)。

覆盖:一会话一 JSON 的往返与布局、双索引(幂等键/skill_session)跨实例重建、
**重启端到端续跑**(新进程实例只共享磁盘目录 → 内核仍收到 LearnerSession 本体,
不是 `{question_id, history, state}` 三键投影)、状态视图、additive 旧文件、
坏文件隔离、本体不入会话文件(单一份真相)。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from edu_agent.agents.small_lecturer import LearnerSession
from edu_agent.api import ApiError, build_service
from edu_agent.store import Conversation, FileConversationStore, FileSessionStore


@dataclass
class StubTurn:
    text: str
    session: object = None
    ready_to_confirm: bool = False
    status: str = "completed"


class RecordingKernel:
    """记录每次 reply/finish 收到的 session **类型与身份**,推进真 LearnerSession。"""

    def __init__(self) -> None:
        self.session = None
        self.seen: list[tuple[str, str]] = []  # (调用, 收到的类型名)

    def start(self, question: dict, learner: dict) -> StubTurn:
        self.session = LearnerSession(question=question, learner=learner)
        self.session.state = "first_question_ready"
        self.session.first_question = "先说说你打算怎么开始?"
        return StubTurn("先说说你打算怎么开始?", session=self.session)

    def reply(self, session: LearnerSession, student_message: str) -> StubTurn:
        self.seen.append(("reply", type(session).__name__))
        session.state = "dialogue"
        session.session_version += 1
        session.history.append({"role": "user", "content": student_message})
        return StubTurn("那下一步呢?", session=session)

    def finish(self, session: LearnerSession) -> StubTurn:
        self.seen.append(("finish", type(session).__name__))
        session.state = "completed"
        return StubTurn("你讲清楚了。", session=session, status="completed")


def _service(root, kernel):
    """一次"进程启动":store 实例全新,只共享磁盘目录(重启复现的关键)。"""
    return build_service(kernel, store=FileConversationStore(root / "conversations"),
                         sessions=FileSessionStore(root / "sessions"))


def _open_and_turn(service, idem="idem-1"):
    opened = service.open("q-1", idem, learner={"grade": "五年级"})
    conversation_id = opened["conversation"]["conversation_id"]
    service.send(conversation_id, {
        "content": "两边减 7。",
        "input": {"skill_session_id": opened["skill_session_id"],
                  "expected_session_version": opened["session_version"]}})
    return opened


# ---------- 布局与往返 ----------

def test_conversation_file_layout_and_roundtrip(tmp_path):
    kernel = RecordingKernel()
    service = _service(tmp_path, kernel)
    opened = _open_and_turn(service)
    conversation_id = opened["conversation"]["conversation_id"]
    path = tmp_path / "conversations" / f"{conversation_id}.json"
    assert path.exists()  # data/conversations/{conversation_id}.json 布局
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["conversation_id"] == conversation_id
    assert data["state"] == "dialogue" and data["session_version"] == 2
    assert data["extras"]["learner"] == {"grade": "五年级"}
    # 本体不入会话文件(一份真相):只留 id,session 本体在 FileSessionStore
    assert "kernel_session" not in data["extras"]
    session_id = data["extras"]["kernel_session_id"]
    assert session_id and (tmp_path / "sessions" / f"{session_id}.json").exists()


def test_get_returns_live_object_and_update_persists(tmp_path):
    store = FileConversationStore(tmp_path)
    conversation = Conversation(conversation_id="conv_x", question_id="q-1",
                                attempt_id="attempt_x", skill_session_id="skill_x")
    store.create(conversation, "idem-x")
    assert store.get("conv_x") is conversation
    conversation.state = "completed"
    store.update(conversation)
    assert FileConversationStore(tmp_path).get("conv_x").state == "completed"


# ---------- 双索引跨实例重建 ----------

def test_indexes_survive_restart(tmp_path):
    service = _service(tmp_path, RecordingKernel())
    opened = _open_and_turn(service, idem="idem-restart")
    conversation_id = opened["conversation"]["conversation_id"]
    store = FileConversationStore(tmp_path / "conversations")  # 新实例=重启
    assert store.get(conversation_id) is not None
    assert store.find_by_idempotency("idem-restart").conversation_id == conversation_id
    assert store.find_by_skill_session(
        opened["skill_session_id"]).conversation_id == conversation_id


def test_open_idempotent_retry_after_restart_same_conversation(tmp_path):
    opened = _open_and_turn(_service(tmp_path, RecordingKernel()), idem="idem-same")
    again = _service(tmp_path, RecordingKernel()).open("q-1", "idem-same", learner={})
    assert again["conversation"]["conversation_id"] == opened["conversation"]["conversation_id"]


# ---------- 验收:重启后全链路续跑,内核收到本体 ----------

def test_restart_continuity_open_message_finish(tmp_path):
    first = RecordingKernel()
    opened = _open_and_turn(_service(tmp_path, first), idem="idem-chain")
    conversation_id = opened["conversation"]["conversation_id"]

    kernel = RecordingKernel()  # 新进程
    service = _service(tmp_path, kernel)
    # 会话与状态从文件扫描重建
    assert service.status(conversation_id)["state"] == "dialogue"
    assert service.status(conversation_id)["turn_count"] == 2
    # 续跑:内核必须收到 LearnerSession 本体(而非三键投影 dict)
    body = service.send(conversation_id, {
        "content": "然后两边除以 3。",
        "input": {"skill_session_id": opened["skill_session_id"],
                  "expected_session_version": 2}})
    assert kernel.seen == [("reply", "LearnerSession")], kernel.seen
    assert body["session_version"] == 3
    # finish 亦走本体:completed 后 summary 落会话
    finished = service._confirm(service._conversation_or_404(conversation_id))
    assert finished["ready_to_confirm"] is True and finished["status"] == "completed"
    assert finished["summary"] == {"status": "completed", "text": "你讲清楚了。"}
    assert kernel.seen[-1] == ("finish", "LearnerSession")


def test_rehydrated_session_keeps_question_and_history(tmp_path):
    """本体字段在重启后仍在(question/steps/first_question/session_version/session_id)。"""
    _open_and_turn(_service(tmp_path, RecordingKernel()), idem="idem-body")
    service = _service(tmp_path, RecordingKernel())
    conversation = service.store.get(  # 重启后唯一会话
        next(iter(p.stem for p in (tmp_path / "conversations").glob("*.json"))))
    session = service._rehydrate(conversation)
    assert isinstance(session, LearnerSession)
    assert session.question == {"text": "解方程 3x+7=25", "answer": "x=6"} or session.question
    assert session.first_question and session.session_version == 2
    assert session.history == [{"role": "user", "content": "两边减 7。"}]
    assert session.session_id == conversation.extras["kernel_session_id"]


def test_stale_version_still_409_after_restart(tmp_path):
    """会话表落盘不放松版本门槛(00 §5.2 约定 3)。"""
    opened = _open_and_turn(_service(tmp_path, RecordingKernel()), idem="idem-409")
    service = _service(tmp_path, RecordingKernel())
    try:
        service.send(opened["conversation"]["conversation_id"], {
            "content": "重发。",
            "input": {"skill_session_id": opened["skill_session_id"],
                      "expected_session_version": 1}})
    except ApiError as error:
        assert error.status_code == 409 and error.code == "SKILL_SESSION_CONFLICT"
    else:  # pragma: no cover - 未抛即回归
        raise AssertionError("旧版本号应 409")


# ---------- additive 与坏文件隔离 ----------

def test_additive_minimal_old_file_loads(tmp_path):
    """旧文件(只有必填字段、无 extras/idempotency_key)按默认值补齐,不迁移。"""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "conv_old.json").write_text(json.dumps({
        "conversation_id": "conv_old", "question_id": "q-old",
        "attempt_id": "attempt_old", "skill_session_id": "skill_old"}), encoding="utf-8")
    store = FileConversationStore(tmp_path)
    restored = store.get("conv_old")
    assert restored.state == "preparing" and restored.session_version == 1
    assert restored.first_question is None and restored.extras == {}
    assert store.find_by_skill_session("skill_old").conversation_id == "conv_old"


def test_broken_file_skipped_others_load(tmp_path):
    """半截 JSON 只跳过该文件,不炸整个启动扫描。"""
    service = _service(tmp_path, RecordingKernel())
    opened = _open_and_turn(service, idem="idem-good")
    (tmp_path / "conversations" / "conv_broken.json").write_text("{半截", encoding="utf-8")
    store = FileConversationStore(tmp_path / "conversations")
    assert store.get(opened["conversation"]["conversation_id"]) is not None
    assert store.get("conv_broken") is None


def test_memory_store_path_unchanged(tmp_path):
    """未注入文件级会话表 = 行为不变(默认内存;重启不可续是既有语义)。"""
    service = build_service(RecordingKernel())
    opened = _open_and_turn(service, idem="idem-mem")
    assert service.status(opened["conversation"]["conversation_id"])["turn_count"] == 2
    assert build_service(RecordingKernel()).store.get(
        opened["conversation"]["conversation_id"]) is None
