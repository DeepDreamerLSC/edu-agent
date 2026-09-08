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

import hashlib
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Protocol

from edu_agent.store import Conversation, FileSessionStore, MemoryConversationStore

SKILL_ID = "small_lecturer_coaching"
SKILL_VERSION = "2026-09-migration-v1"  # #45 SKILL.md 剪裁版的版本串

# M3 PR6:内核态 → 合作方 attempt_state 词汇(老系统 learning_dialogue 口径,
# #34 基线实录出现 collecting_inputs/ready_to_confirm/completed);马尾梯直读映射。
_ATTEMPT_STATES = {
    "preparing": "preparing",
    "first_question_ready": "collecting_inputs",
    "dialogue": "collecting_inputs",
    "ready_to_confirm": "ready_to_confirm",
    "needs_review": "needs_review",
    "completed": "completed",
    "failed": "failed",
}
EXPECTED_ROUNDS = 5  # 预期轮次:v1 常数默认(基线/评测典型 5 回合),不建跟踪机制
# 00 §5.2 合同只实现 confirm 与普通对话(null);老通用面的其余 action 明确拒收
# (M3 全景 B4:一个 if/else,不是工作流引擎)。
SUPPORTED_ACTIONS = frozenset({None, "confirm"})
UNSUPPORTED_ACTIONS = frozenset({
    "activate", "submit_inputs", "diagnose", "pause", "resume", "restart", "cancel", "refresh",
})


class ApiError(Exception):
    """合作方错误(老仓库 AppError 形态:code/message/status;details 可选)。"""

    def __init__(self, status_code: int, code: str | None, message: str,
                 details: dict | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


class Kernel(Protocol):
    """B 线内核的三个公开函数(00 §5.1);C 线经注入使用,不动 agents 包。"""

    def start(self, question: dict, learner: dict) -> object: ...
    def reply(self, session: object, student_message: str) -> object: ...
    def finish(self, session: object) -> object: ...


class ConversationService:
    def __init__(self, store: MemoryConversationStore, kernel: Kernel,
                 source=None, sessions: FileSessionStore | None = None,
                 image_resolver=None) -> None:
        self.store = store
        self.kernel = kernel
        self.source = source
        self.sessions = sessions  # M3 PR6:上下文保留,未注入时空操作
        self.image_resolver = image_resolver  # file_id → data URL(FileService.data_url)
        self._turn_cache: dict[str, dict] = {}  # 消息幂等:cache_key → 响应(不重调模型)

    # ---------- open(幂等键,同键同 Attempt) ----------

    def create(self, body: dict) -> dict:
        """会话入口(POST /api/conversations,统一 Open 字段子集,老系统文档 §5)。

        idempotency_key 必填(重试原样复用);external_question_id 走题源(未命中
        404 QUESTION_BANK_QUESTION_NOT_FOUND);question_text/question_image 为
        自由材料二选一(同传 422),题图空壳由内核 vision 处理;合同字段之外
        透传 learner(调用方字段优先)。幂等重试返回同一 conversation_id。"""
        idempotency_key = str(body.get("idempotency_key") or "")
        if not idempotency_key:
            raise ApiError(422, None, "idempotency_key 必填(重试原样复用)")
        text = body.get("question_text")
        image = body.get("question_image")
        if text and image:
            raise ApiError(422, "PREPARED_QUESTION_SOURCE_CONFLICT",
                           "question_text 与 question_image 不能同传(自由材料二选一)")
        learner = {k: v for k, v in body.items() if k not in (
            "idempotency_key", "external_question_id", "question_text", "question_image")}
        external_question_id = str(body.get("external_question_id") or "")
        if external_question_id:
            # 同题组合与统一 open 同款:题库文答为准,客户端题图合并
            payload = self.open(external_question_id, idempotency_key, learner,
                                merge_image=str(image or ""))
        elif text or image:
            material = {"text": str(text)} if text else {"image": str(image)}
            payload = self._open_material(material, learner, idempotency_key,
                                          external_question_id)
        else:
            raise ApiError(422, "PREPARED_QUESTION_SOURCE_MISSING",
                           "open 请求未提供任何题目来源(external_question_id/question_text/question_image)")
        conversation = self.store.find_by_idempotency(idempotency_key)
        return {
            "conversation_id": payload["conversation"]["conversation_id"],
            "skill_session_id": payload["skill_session_id"],
            "session_version": payload["session_version"],
            "first_question_ready": payload["first_question_ready"],
            "first_question": conversation.first_question if conversation else None,
            "retry_after_ms": payload["retry_after_ms"],
        }

    # ---------- 统一 Open(老系统文档 §5:POST /api/prepared-questions/open) ----------

    _CONTRACT_FIELDS = frozenset({"idempotency_key", "external_question_id", "question_image",
                                  "question_text", "answer_correct", "knowledge_points"})

    def open_unified(self, body: dict) -> dict:
        """统一 Open(§5):字段/长度/严格类型照老系统;组合规则:
        external_question_id+题图允许同传(同题组合);题库命中复用题干/答案/解析/
        知识点;未命中但有题图走 vision 转写;未命中无图 404
        QUESTION_BANK_QUESTION_NOT_FOUND;question_text 与任何来源混用 422。
        内核同步出首问:pending 恒 false,active_session 恒在(retry_after_ms=0)。"""
        idempotency_key = body.get("idempotency_key")
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128:
            raise ApiError(422, None, "idempotency_key 必填且长度 1~128(重试原样复用)")
        if "target_subquestion_id" in body:
            # 仅可信评测客户端可提交(文档错误码表;details 照 conflicting_fields 口径)
            raise ApiError(422, "PREPARED_QUESTION_TARGET_SUBQUESTION_FORBIDDEN",
                           "target_subquestion_id 仅可信评测客户端可提交",
                           details={"conflicting_fields": ["target_subquestion_id", "question_id"]})
        external_question_id = self._str_field(body, "external_question_id", 255)
        question_image = self._str_field(body, "question_image", 128)
        question_text = self._str_field(body, "question_text", 8000)
        if question_image and ("://" in question_image or question_image.startswith("data:")):
            raise ApiError(422, None, "question_image 只接受已上传 file_id,禁 URL/Base64")
        answer_correct = body.get("answer_correct")
        if "answer_correct" in body and answer_correct is not None \
                and not isinstance(answer_correct, bool):
            raise ApiError(422, None, "answer_correct 必须是严格 JSON boolean 或 null")
        knowledge_points = self._validated_knowledge_points(body.get("knowledge_points"))
        if question_text and (external_question_id or question_image):
            raise ApiError(422, "PREPARED_QUESTION_SOURCE_CONFLICT",
                           "question_text 不能与 external_question_id/question_image 混用",
                           details={"conflicting_fields": ["question_text", "question_image",
                                                           "external_question_id"]})
        learner = {k: v for k, v in body.items() if k not in self._CONTRACT_FIELDS}
        # PR-4:answer_correct → 内核 R6 首问策略信号。true/false 显式有值才映射
        # answer_status 并标 provenance=partner_open;null/省略不填(内核缺省 unknown,
        # provenance 缺省)。映射值由合同字段推导,覆写同名透传(服务端权威)。
        client_answer = "answer_correct" in body and answer_correct is not None
        if client_answer:
            learner = {**learner,
                       "answer_status": "correct" if answer_correct else "incorrect",
                       "answer_correct_provenance": "partner_open"}
        material = ({"text": question_text} if question_text
                    else {"image": question_image} if question_image else None)
        if material is not None and knowledge_points:
            # 非题库路径:客户端知识点作追问锚点(题库命中时以题源为准,忽略客户端值)
            material["knowledge_points"] = knowledge_points
        if not external_question_id and not material:
            raise ApiError(422, "PREPARED_QUESTION_SOURCE_MISSING",
                           "open 请求未提供任何题目来源(external_question_id/question_text/question_image)")
        bank_hit = False
        if external_question_id:
            try:
                # 同题组合(§5):题库文答为准,客户端题图 file_id 合并进题面
                payload = self.open(external_question_id, idempotency_key, learner,
                                    merge_image=question_image)
                bank_hit = True
            except ApiError as error:
                # 未命中但有题图 → vision 转写路径;未命中无图 → 404 照合同
                if error.code != "QUESTION_BANK_QUESTION_NOT_FOUND" or not material:
                    raise
                payload = self._open_material(material, learner, idempotency_key,
                                              external_question_id)
        else:
            payload = self._open_material(material, learner, idempotency_key, "")
        conversation = self.store.find_by_idempotency(idempotency_key)
        return {
            "external_question_id": external_question_id or None,
            "prepared_question_package_id": None,  # v1 题源(seed/snapshot)不带包 id
            "pending": False,  # 同步内核:首问已就绪,无需重放
            "answer_correct": answer_correct,
            # 客户端显式有值 > 题库来源 > 缺省 null(答案正确性的出处标记)
            "answer_correct_provenance": ("partner_open" if client_answer else
                                          "partner_question_bank" if bank_hit else None),
            "question": {
                "package_id": None,
                "active_session": {
                    "conversation": conversation.conversation_id,
                    "skill_session_id": conversation.skill_session_id,
                    "session_version": conversation.session_version,
                    "first_question_ready": True,
                    "retry_after_ms": 0,
                },
            },
        }

    @staticmethod
    def _str_field(body: dict, field: str, limit: int) -> str:
        value = body.get(field)
        if value is None:
            return ""
        if not isinstance(value, str) or len(value) > limit:
            raise ApiError(422, None, f"{field} 须为字符串且长度 ≤{limit}")
        return value

    @staticmethod
    def _validated_knowledge_points(raw) -> list:
        """knowledge_points:数组 ≤20,每项 {id?, name 必填}(照 §5 字段表)。"""
        if raw is None:
            return []
        if not isinstance(raw, list) or len(raw) > 20:
            raise ApiError(422, None, "knowledge_points 须为数组且长度 ≤20")
        for item in raw:
            if not isinstance(item, dict) or not str(item.get("name") or "").strip():
                raise ApiError(422, None, "knowledge_points 每项必须含非空 name")
        return raw

    def open(self, question_id: str, idempotency_key: str, learner: dict,
             *, merge_image: str = "") -> dict:
        if not idempotency_key:
            raise ApiError(422, None, "idempotency_key 必填(00 §5.2:请求只有 idempotency_key)")
        existing = self.store.find_by_idempotency(idempotency_key)
        if existing is not None:
            if existing.question_id != question_id:
                # 00 §5.2 约定 2:题目在会话内固定,不能中途换题
                raise ApiError(409, "QUESTION_SOURCE_PINNED", "同一幂等键已固定另一道题,新建学习会话")
            return self._open_response(existing)
        try:
            question, learner, detail = self._resolved(question_id, learner, merge_image)
        except KeyError as error:
            # 题源 KeyError = 题库未命中(老系统文档错误码表)
            raise ApiError(404, "QUESTION_BANK_QUESTION_NOT_FOUND",
                           f"服务端题库没有该题目:{question_id}") from error
        return self._start_conversation(question, learner, detail, question_id, idempotency_key)

    def _open_material(self, material: dict, learner: dict, idempotency_key: str,
                       question_id: str) -> dict:
        """自由材料入口(question_text/question_image):不走题源,题图空壳由内核 vision 处理。"""
        existing = self.store.find_by_idempotency(idempotency_key)
        if existing is not None:
            if existing.question_id != question_id:
                raise ApiError(409, "QUESTION_SOURCE_PINNED", "同一幂等键已固定另一道题,新建学习会话")
            return self._open_response(existing)
        return self._start_conversation(material, learner, None, question_id, idempotency_key)

    def _start_conversation(self, question: dict, learner: dict, detail: dict | None,
                            question_id: str, idempotency_key: str) -> dict:
        image = question.get("image")
        if image and self.image_resolver:
            # file_id → data URL(内核 vision 的多模态输入)。解析器只在生产装配注入
            # (serve_partner_api);未注入(测试/评测)原样透传。解析失败 = file_id
            # 不存在或未就绪,早期 422(不把坏引用送进模型层变 503)。
            resolved = self.image_resolver(str(image))
            if not resolved:
                raise ApiError(422, "FILE_NOT_READY",
                               f"question_image 文件不存在或尚未就绪:{image}")
            question = {**question, "image": resolved}
        try:
            turn = self.kernel.start(question, learner)
        except ApiError:
            raise
        except Exception as error:  # 内核/模型基础设施故障 → 503(合同表)
            raise ApiError(503, None, f"服务暂不可用:{type(error).__name__}") from error
        extras = {"learner": learner, "kernel_session": getattr(turn, "session", None),
                  "created_at": datetime.now(timezone.utc)
                  .isoformat().replace("+00:00", "Z")}
        if detail is not None:
            extras["question_detail"] = detail
        conversation = Conversation(
            conversation_id=f"conv_{uuid.uuid4().hex[:12]}",
            question_id=question_id,
            attempt_id=f"attempt_{uuid.uuid4().hex[:12]}",
            skill_session_id=f"skill_session_{uuid.uuid4().hex[:12]}",
            session_version=1,
            state="first_question_ready",
            first_question=str(getattr(turn, "text", "")),
            extras=extras,
        )
        conversation = self.store.create(conversation, idempotency_key)
        self._persist_session(conversation)
        return self._open_response(conversation)

    def _resolved(self, question_id: str, learner: dict,
                  merge_image: str = "") -> tuple[dict, dict, dict | None]:
        """题源解析(PR1):内核面最小化(text/image),答案/解析/考点存 extras 供 judge
        (不进学生面);出处走 answer_correct_provenance(审查 P1:answer_status 是正确性
        字段,由 answer_correct 映射填,题源不碰);调用方 learner 字段优先。
        M3 PR2 叠加:answer/analysis/knowledge_points 进内核面——教师侧 prompt 专用,
        学生可见面由内核护栏把关;extras 副本仍供 judge。
        merge_image:题库命中时客户端上传的题图 file_id(§5 同题组合)——文答以题源
        为准,题图用客户端的(与老系统"合作方传图"一致)。
        source 未注入时维持旧形态(ScriptedKernel 夹具路径)。"""
        if self.source is None:
            return {"question_id": question_id}, learner, None
        resolved = self.source.resolve(question_id)
        bank_image = resolved["image"]
        # 题库图引用统一为 file_id 字符串(快照 dict 形态取 file_id;内核/解析器只认 str)
        image_ref = bank_image.get("file_id") if isinstance(bank_image, dict) else bank_image
        question = {"question_id": question_id, "text": resolved["text"],
                    "image": merge_image or image_ref or None,
                    "answer": resolved["answer"],
                    "analysis": resolved["analysis"],
                    "knowledge_points": resolved["knowledge_points"]}
        provenance = resolved.get("answer_correct_provenance")
        if provenance:
            learner = {"answer_correct_provenance": provenance, **learner}
        learner = {"grade": resolved["grade"], **learner}
        detail = {k: resolved[k] for k in ("answer", "analysis", "knowledge_points")}
        return question, learner, detail

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
        # M3 全景 B3:interaction 信封 + assistant_message(首问就绪非空)+ agent_run
        # (恒 completed——同步架构,不建异步任务系统)
        return {
            "assistant_message": {"content": conversation.first_question},
            "skill_interaction": {
                "schema_version": "skill_interaction/v1",
                "skill_session_id": conversation.skill_session_id,
                "skill_id": SKILL_ID,
                "skill_version": SKILL_VERSION,
                "session_version": conversation.session_version,
                "kind": "input_request",
                "state": conversation.state,
            },
            "agent_run": {"id": f"agent_run_{conversation.attempt_id}",
                          "status": "completed"},
            "session_version": conversation.session_version,
        }

    # ---------- messages(多轮 + confirm) ----------

    def send(self, conversation_id: str, body: dict) -> dict:
        conversation = self._conversation_or_404(conversation_id)
        if conversation.state == "completed":
            raise ApiError(409, "SKILL_SESSION_CONFLICT", "会话已完成,重开需新幂等键")
        if body.get("skill_id") not in (None, SKILL_ID):
            raise ApiError(403, "SKILL_ID_INVALID", "skill_id 与本服务不匹配")
        action = (body.get("input") or {}).get("interaction_action")
        if action is not None and action not in SUPPORTED_ACTIONS:
            # M3 全景 B4:老通用面的 action 明确拒收——一个 if/else,不是工作流引擎
            raise ApiError(400, "UNSUPPORTED_ACTION",
                           f"interaction_action={action} 不在本合同内(仅 confirm/普通对话)")
        if action == "confirm":
            return self._confirm(conversation)
        return self._dialogue_turn(conversation, body)

    def _dialogue_turn(self, conversation: Conversation, body: dict) -> dict:
        payload = body.get("input") or {}
        if payload.get("skill_session_id") not in (None, conversation.skill_session_id):
            raise ApiError(404, None, "skill_session 不属于该会话")
        # 消息幂等(M3 全景 B4):message_idempotency_key + 会话 → 命中即原样返回
        # 已生成 Turn(不重调模型、不 version++)——在版本门之前判(网络重试的本义:
        # 首次已成功,重试不该被新版本门槛拦住)
        idem = body.get("message_idempotency_key")
        cache_key = ""
        if idem is not None:
            cache_key = hashlib.sha256(
                f"{conversation.conversation_id}|{idem}".encode("utf-8")).hexdigest()
            cached = self._turn_cache.get(cache_key)
            if cached is not None:
                return cached
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
        self._persist_session(conversation)
        response = self._message_response(conversation, reply_text)
        if cache_key:
            self._turn_cache[cache_key] = response
        return response

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
            self._persist_session(conversation)
        return {
            "ready_to_confirm": True,
            "status": "completed",
            "summary": conversation.summary,
            "session_version": conversation.session_version,
        }

    def _message_response(self, conversation: Conversation, text: str) -> dict:
        return {
            "assistant_message": {"content": text},
            "skill_interaction": self.interaction_envelope(conversation),
            "session_version": conversation.session_version,
        }

    @staticmethod
    def interaction_envelope(conversation: Conversation) -> dict:
        """skill_interaction/v1 全量信封(按 #48 edu_agent/contracts 的 schema 装配)。

        M3 PR6 运行时填充(马尾梯:直读既有状态,不建状态机/跟踪机制):
        attempt_state/progress 直读内核 session(无 session 的夹具内核回退
        conversation);kind/state/confirmation 跟随 conversation(响应面)。
        inputs/requirements/missing_input_ids 无多步输入流,恒空载。
        已知结构现状:confirm 在 ready 路径不调 kernel.finish(PR1 最小接线),
        内核 attempt 停在 ready_to_confirm——随 B 线 PR4 refresh 语义补齐对齐。
        """
        session = conversation.extras.get("kernel_session")
        attempt_state_source = str(getattr(session, "state", "") or conversation.state)
        kind = {"dialogue": "input_request", "first_question_ready": "input_request",
                "ready_to_confirm": "confirmation", "completed": "result",
                "preparing": "progress"}.get(conversation.state, "progress")
        confirmation = None
        if conversation.state == "ready_to_confirm":
            confirmation = {"ready_to_confirm": True, "completed": False}
        elif conversation.state == "completed":
            confirmation = {"ready_to_confirm": True, "completed": True}
        history = getattr(session, "history", None) or conversation.extras.get("history", [])
        envelope = {
            "schema_version": "skill_interaction/v1",
            "skill_session_id": conversation.skill_session_id,
            "skill_id": SKILL_ID,
            "skill_version": SKILL_VERSION,
            "session_version": conversation.session_version,
            "kind": kind,
            "state": conversation.state,
            "attempt_state": {"state": _ATTEMPT_STATES.get(
                attempt_state_source, attempt_state_source)},
            "inputs": [],
            "requirements": [],
            "missing_input_ids": [],
            "confirmation": confirmation,
            "progress": {"current_round": sum(1 for m in history if m.get("role") == "user"),
                         "expected_rounds": EXPECTED_ROUNDS},
            "result": conversation.summary,
        }
        return envelope

    # ---------- 内部 ----------

    def _persist_session(self, conversation: Conversation) -> None:
        """上下文保留(M3 PR6):内核回合后把 LearnerSession 落盘;未注入即空操作。"""
        session = conversation.extras.get("kernel_session")
        if self.sessions is not None and session is not None:
            self.sessions.save(session)

    def _kernel_session(self, conversation: Conversation) -> object:
        """真内核:open 时暂存的 LearnerSession 对象(内存态);
        夹具内核(无 session 对象):最小投影 dict。"""
        session = conversation.extras.get("kernel_session")
        if session is not None:
            return session
        return {
            "question_id": conversation.question_id,
            "history": conversation.extras.setdefault("history", []),
            "state": conversation.state,
        }

    def status(self, conversation_id: str) -> dict:
        """会话状态视图(GET /api/conversations/{id},M3 最后代码 PR)。"""
        conversation = self._conversation_or_404(conversation_id)
        return {
            "conversation_id": conversation.conversation_id,
            "state": conversation.state,
            "session_version": conversation.session_version,
            "question_id": conversation.question_id,
            "created_at": conversation.extras.get("created_at"),
            "turn_count": len(conversation.extras.get("history", [])),
        }

    def _conversation_or_404(self, conversation_id: str) -> Conversation:
        conversation = self.store.get(conversation_id)
        if conversation is None:
            raise ApiError(404, None, "会话不存在")
        return conversation
