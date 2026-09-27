"""内核会话状态(v1 内存化,00 §5.1/03 §4)。

03 §4 状态:preparing → first_question_ready/failed → dialogue ⇄ conflict(瞬态)
→ ready_to_confirm / needs_review(非终态,可回 dialogue)→ completed(终态,
summary 不可变)。会话只存在于内存,持久化是 M3 的事。Turn 携带 session 引用:
调用方把 start 返回的 turn.session 传给 reply/finish——三个函数即完整闭环。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from .completion import (
    CompletionEvidence,
    CompletionRejectionReason,
    diagnose_rejection,
)


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
    stuck: bool = False                # 卡点标记(R6;#382 P0-1 收口):学生本人明确 stuck 信号专属,
    #                                  # 系统侧异常(guard 降级/复读兜底等)只记 guard_events 不写此位
    steps: list[dict] = field(default_factory=list)   # 分步解(统一 open 求解):阶梯底稿 +
    # 数字校验基准(引用值须 ⊆ steps 的 value),随 FileSessionStore asdict 持久化。
    # #382 PR-C:每步带 provenance(analysis=trusted 题库切片 / model=untrusted 规划件)
    # ——deterministic reveal 只消费 analysis 步,随 asdict 全字段持久化(重启恢复后
    # 边界不丢)。
    hint_level: int = 0                # 阶梯揭示进度:学生卡住时揭示 steps 的第几级(0 起)
    completion_evidence: CompletionEvidence | None = None  # 当轮完成证据(#414 §二/§四,
    #                                  # B 段):turn-scoped/ephemeral——只对最新学生轮有效,
    #                                  # 每轮 reply() 重新生产覆盖(无命中即覆写 None,跨轮
    #                                  # 不复用);completed 迁移的必要授权(非充分)。
    #                                  # None=无证据:无 answer_spec 声明面的题(fail-closed)
    #                                  # 或本轮学生消息未命中六窄面。随 asdict 持久化。
    guard_events: list = field(default_factory=list)  # 护栏埋点(任务包1步1):命中的
    # 规则与被替换原文随会话落盘(FileSessionStore asdict 自动持久化),供兜底率度量
    session_id: str = field(default_factory=lambda: f"kernel_{uuid.uuid4().hex[:10]}")

    @property
    def finished(self) -> bool:
        return self.state in ("completed", "failed")

    @property
    def verified_signal(self) -> dict | None:
        """完成信号只读视图(#414 §五 generation 只读消费,C 段 accessor——任务书裁定
        放本文件,不进 kernel.py:kernel.py 预算 788/800 已冻结)。

        当轮 trusted CompletionEvidence 在场 → {"verified_complete": True,
        "evidence_turn_id": N};None = 无证据(prompt 侧「未注入」形态,§五
        「注入或未注入」)。评测重放/审查的只读消费面;生产 prompt 注入见
        prompting.completion_signal_fact——kernel 每轮已把判定原料(answer_spec
        声明面+学生本轮回答+对话记录)送进 prompt 装配,信号在装配侧由同一
        verifier 重演,与本视图恒等(tests/teaching/test_completion_signal_prompt.py
        钉死)。不含 canonical answer(§五:学生原文模型已有,塞答案=新
        answer-leak 面)。"""
        if self.completion_evidence is None:
            return None
        return {"verified_complete": True,
                "evidence_turn_id": self.completion_evidence.turn_id}

    @property
    def completion_rejection(self) -> CompletionRejectionReason | None:
        """C′(#423 终裁 2026-09-27)拒因只读视图:completion gate 拒绝路径的
        diagnostic/routing signal——**最新学生轮消息**经 diagnose_rejection 八
        条件全成立时在场(值匹配但 claim 形态未认证,#453 两类 FN 形态),
        turn_id=最新学生轮号。

        **零 authority(权限分级铁律)**:不触发状态迁移、不进任何判定口径;
        与 verified_signal(trusted 完成事实)权限等级不同、命名不复用(#448
        §五分界:那是「已认证完成事实」,这是「未认证但存在窄定义 completion
        candidate 的拒绝原因」)。唯一消费效果=回复路由(finish 拒绝文案 →
        restatement bridge;prompt 侧经 prompting 装配重演同一 diagnose_rejection,
        单一实现)。放本文件不进 kernel.py:kernel.py 预算 800/800 已冻结
        (verified_signal 同款先例)。不含 canonical answer(matched_value 是
        学生自己的话)。"""
        from .kernel import _answer_spec  # 懒加载:kernel 顶层 import session
        message = next((str(m.get("content") or "") for m in reversed(self.history)
                        if m.get("role") == "user"), "")
        return diagnose_rejection(
            _answer_spec(self.question), message,
            sum(1 for m in self.history if m.get("role") == "user"))


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
