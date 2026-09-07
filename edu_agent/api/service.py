"""合作方接口会话语义(00 §5.2 复用清单;#48 partner_endpoints 的行为面)。

内核铁律(C 线):真内核由 B 线在 edu_agent/agents/small_lecturer 实现,本模块
只依赖 Kernel 协议(三个公开函数签名,00 §5.1),经构造注入——api 不 import
agents 包。Turn/Summary 的 duck 字段假设:.text(str)/.ready_to_confirm(bool)/
.status("completed"|"needs_review")。
错误码映射按 #48 快照集合:401、409 QUESTION_SOURCE_PINNED /
SKILL_SESSION_CONFLICT / TEACHING_CONTEXT_PRELOAD_NOT_READY(兼容保留,新链路
同步出首问预期不再触发)、503。
"""

from __future__ import annotations

import uuid
from typing import Protocol

from edu_agent.store import Conversation, MemoryConversationStore

SKILL_ID = "small_lecturer_coaching"
SKILL_VERSION = "2026-09-migration-v1"  # #45 SKILL.md 剪裁版的版本串


class ApiError(Exception):
    """合作方错误(老仓库 AppError 形态:code/message/status)。"""

    def __init__(self, status_code: int, code: str | None, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class Kernel(Protocol):
    """B 线内核的三个公开函数(00 §5.1);C 线经注入使用,不动 agents 包。"""

    def start(self, question: dict, learner: dict) -> object: ...
    def reply(self, session: object, student_message: str) -> object: ...
    def finish(self, session: object) -> object: ...


class ConversationService:
    def __init__(self, store: MemoryConversationStore, kernel: Kernel) -> None:
        self.store = store
        self.kernel = kernel

    # ---------- open(幂等键,同键同 Attempt) ----------

    def open(self, question_id: str, idempotency_key: str, learner: dict) -> dict:
        if not idempotency_key:
            raise ApiError(422, None, "idempotency_key 必填(00 §5.2:请求只有 idempotency_key)")
        existing = self.store.find_by_idempotency(idempotency_key)
        if existing is not None:
            if existing.question_id != question_id:
                # 00 §5.2 约定 2:题目在会话内固定,不能中途换题
                raise ApiError(409, "QUESTION_SOURCE_PINNED", "同一幂等键已固定另一道题,新建学习会话")
            return self._open_response(existing)
        try:
            turn = self.kernel.start({"question_id": question_id}, learner)
        except ApiError:
            raise
        except Exception as error:  # 内核/模型基础设施故障 → 503(合同表)
            raise ApiError(503, None, f"服务暂不可用:{type(error).__name__}") from error
        conversation = Conversation(
            conversation_id=f"conv_{uuid.uuid4().hex[:12]}",
            question_id=question_id,
            attempt_id=f"attempt_{uuid.uuid4().hex[:12]}",
            skill_session_id=f"skill_session_{uuid.uuid4().hex[:12]}",
            session_version=1,
            state="first_question_ready",
            first_question=str(getattr(turn, "text", "")),
            extras={"learner": learner},
        )
        conversation = self.store.create(conversation, idempotency_key)
        return self._open_response(conversation)

    @staticmethod
    def _open_response(conversation: Conversation) -> dict:
        # 00 §5.2:conversation、skill_session_id、session_version、first_question_ready、retry_after_ms
        return {
            "conversation": {"conversation_id": conversation.conversation_id,
                             "question_id": conversation.question_id,
                             "attempt_id": conversation.attempt_id},
            "skill_session_id": conversation.skill_session_id,
            "session_version": conversation.session_version,
            "first_question_ready": True,   # 新链路同步出首问(PR2 保持字段语义)
            "retry_after_ms": 0,
        }

    # ---------- refresh(返回首问与新 session_version;两形态同一语义) ----------

    def refresh(self, skill_session_id: str) -> dict:
        conversation = self.store.find_by_skill_session(skill_session_id)
        if conversation is None:
            raise ApiError(404, None, "skill_session 不存在")
        return {
            "first_question": conversation.first_question,
            "session_version": conversation.session_version,
        }

    # ---------- messages(多轮 + confirm) ----------

    def send(self, conversation_id: str, body: dict) -> dict:
        conversation = self._conversation_or_404(conversation_id)
        if conversation.state == "completed":
            raise ApiError(409, "SKILL_SESSION_CONFLICT", "会话已完成,重开需新幂等键")
        action = (body.get("input") or {}).get("interaction_action")
        if action == "confirm":
            return self._confirm(conversation)
        return self._dialogue_turn(conversation, body)

    def _dialogue_turn(self, conversation: Conversation, body: dict) -> dict:
        payload = body.get("input") or {}
        if payload.get("skill_session_id") not in (None, conversation.skill_session_id):
            raise ApiError(404, None, "skill_session 不属于该会话")
        expected = payload.get("expected_session_version")
        if expected is not None and expected != conversation.session_version:
            # 00 §5.2 约定 3:旧版本 409,不静默覆盖新一轮诊断
            raise ApiError(409, "SKILL_SESSION_CONFLICT",
                           "会话版本过期,读取最新 interaction 后由学生决定是否重发")
        content = body.get("content") or payload.get("student_response") or ""
        if not str(content).strip():
            raise ApiError(422, None, "content/student_response 不能为空")
        history = conversation.extras.setdefault("history", [])
        try:
            turn = self.kernel.reply(self._kernel_session(conversation), str(content))
        except ApiError:
            raise
        except Exception as error:
            raise ApiError(503, None, f"服务暂不可用:{type(error).__name__}") from error
        reply_text = str(getattr(turn, "text", ""))
        history.append({"role": "user", "content": str(content)})
        history.append({"role": "assistant", "content": reply_text})
        ready = bool(getattr(turn, "ready_to_confirm", False))
        conversation.session_version += 1
        conversation.state = "ready_to_confirm" if ready else "dialogue"
        conversation.first_question = conversation.first_question or reply_text
        self.store.update(conversation)
        return self._message_response(conversation, reply_text)

    def _confirm(self, conversation: Conversation) -> dict:
        if conversation.state != "ready_to_confirm":
            # 证据不足:finish 语义返回 needs_review,不写 summary(00 §5.2 结束行)
            try:
                summary = self.kernel.finish(self._kernel_session(conversation))
            except ApiError:
                raise
            except Exception as error:
                raise ApiError(503, None, f"服务暂不可用:{type(error).__name__}") from error
            status = getattr(summary, "status", "needs_review")
            if status != "completed":
                return {"ready_to_confirm": False, "status": "needs_review"}
        if conversation.summary is None:
            conversation.summary = {"status": "completed"}  # 不可变:completed 后只读
            conversation.state = "completed"
            self.store.update(conversation)
        return {
            "ready_to_confirm": True,
            "status": "completed",
            "summary": conversation.summary,
            "session_version": conversation.session_version,
        }

    def _message_response(self, conversation: Conversation, text: str) -> dict:
        # skill_interaction/v1 最小信封(PR2 按 contracts schema 装配全量)
        return {
            "assistant_message": {"content": text},
            "skill_interaction": {
                "schema_version": "skill_interaction/v1",
                "skill_session_id": conversation.skill_session_id,
                "skill_id": SKILL_ID,
                "skill_version": SKILL_VERSION,
                "session_version": conversation.session_version,
                "kind": "input_request",
                "state": conversation.state,
            },
            "session_version": conversation.session_version,
        }

    # ---------- 内部 ----------

    def _kernel_session(self, conversation: Conversation) -> dict:
        """内核会话的最小投影(v1 内存态;B 线内核的 Session 形态就绪后对齐)。"""
        return {
            "question_id": conversation.question_id,
            "history": conversation.extras.setdefault("history", []),
            "state": conversation.state,
        }

    def _conversation_or_404(self, conversation_id: str) -> Conversation:
        conversation = self.store.get(conversation_id)
        if conversation is None:
            raise ApiError(404, None, "会话不存在")
        return conversation
