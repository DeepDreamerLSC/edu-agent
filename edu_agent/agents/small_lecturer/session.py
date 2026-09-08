"""内核会话状态(v1 内存化,00 §5.1/03 §4)。

03 §4 状态:preparing → first_question_ready/failed → dialogue ⇄ conflict(瞬态)
→ ready_to_confirm / needs_review(非终态,可回 dialogue)→ completed(终态,
summary 不可变)。会话只存在于内存,持久化是 M3 的事。Turn 携带 session 引用:
调用方把 start 返回的 turn.session 传给 reply/finish——三个函数即完整闭环。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


class SessionVersionConflict(Exception):
    """03 §4 Conflict:调用方携带的 expected_session_version 过期(内核不推进,
    M3 api 层映射 409 SKILL_SESSION_CONFLICT)。"""


class TerminalStateError(Exception):
    """终态(failed/completed)后不可再推进教学流程。"""


@dataclass
class LearnerSession:
    question: dict                     # {"text": str} 或 {"image": ...}(00 §5.1)
    learner: dict                      # {"grade": "二年级", ...}(风格档案选型输入;
                                       #  可选 answer_status: correct/incorrect/unanswered)
    state: str = "preparing"
    session_version: int = 1
    history: list[dict] = field(default_factory=list)
    first_question: str | None = None
    summary: "Summary | None" = None   # completed 后不可变
    stuck: bool = False                # 卡点标记(R6):对话中出现被护栏替换的输出等未解决质量问题
    guard_events: list = field(default_factory=list)  # 护栏埋点(任务包1步1):命中的
    # 规则与被替换原文随会话落盘(FileSessionStore asdict 自动持久化),供兜底率度量
    session_id: str = field(default_factory=lambda: f"kernel_{uuid.uuid4().hex[:10]}")

    @property
    def finished(self) -> bool:
        return self.state in ("completed", "failed")


@dataclass(frozen=True)
class Turn:
    text: str
    session_version: int
    state: str                          # 03 §4 态;failed 即 fail closed 的首问结果
    ready_to_confirm: bool = False
    session: LearnerSession | None = None


@dataclass(frozen=True)
class Summary:
    text: str
    status: str                         # completed | needs_review(00 §5.1)
    session_version: int
