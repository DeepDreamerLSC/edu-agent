"""KernelSubject:runner 被测对象的内核实现(00 §8.4 阶段 3;#41 Subject 协议)。

M1 的被测对象是老系统适配器(legacy_adapter),M2 换成内核三函数——评测线
代码零改动(00 §8.4「被测对象换内核,runner 已抽象」)。内核经 gateway=None
注入口接 runner 的 gateway 实例(直调三函数,事实记录不断链);学生消息按
场景剧本(student_turns)逐轮推进,与适配器同口径。
"""

from __future__ import annotations

import time

from edu_agent.agents.small_lecturer import TerminalStateError, finish, reply, start
from edu_agent.gateway import ENV_FAILURES, Gateway, GatewayError

from .image_teaching import question_image_data_url
from .runner import EnvironmentFailure
from .scenario_corpus import select_branch


class KernelSubject:
    """小讲师内核作为被测对象:run_case 按剧本驱动 start→reply×N→finish。"""

    def __init__(self, gateway: Gateway) -> None:
        self.gateway = gateway

    name = "kernel-small-lecturer"

    @staticmethod
    def _question_payload(raw: object, reference: dict | None = None) -> dict:
        """题面 → 内核 start() 入参:纯文本(旧)或 v1 图文(question.text + image)。

        parity 口径(#333 方向修正单 2026-09-19 裁①):对齐生产 question_source
        resolve() 契约——answer/analysis/knowledge_points 照喂(question 字段优先,
        缺口由场景 reference_answer 的 value/steps 补),内核与生产同看权威答案;
        旧 P 口径(#34 默认不喂+feed_answer 断点)作废,测试钉同步改。
        """
        if isinstance(raw, str):
            return {"text": raw}
        if not isinstance(raw, dict):
            raise ValueError(f"question 必须是字符串或 dict,实际 {type(raw).__name__}")
        payload = {"text": raw.get("text", "")}
        reference = reference or {}
        answer = raw.get("answer") or reference.get("value")
        if answer:
            payload["answer"] = str(answer)
        analysis = raw.get("analysis") or ";".join(
            str(s) for s in reference.get("steps") or [])
        if analysis:
            payload["analysis"] = str(analysis)
        if raw.get("knowledge_points"):
            payload["knowledge_points"] = list(raw["knowledge_points"])
        image = raw.get("image")
        if image is not None:
            payload["image"] = question_image_data_url(image)
        return payload

    def run_case(self, case: dict) -> dict:
        started = time.monotonic()
        question = self._question_payload(case["question"],
                                          case.get("reference_answer"))
        learner = {"grade": case.get("grade", "")}
        # parity 裁①:answer_status 恒有(生产由 answer_correct 映射;评测缺省
        # 补 incorrect——切片学生均未达正确终态,与生产 no-progress 主弧一致)
        learner["answer_status"] = case.get("answer_status") or "incorrect"
        turns: list[dict] = []
        try:
            first = start(question, learner, gateway=self.gateway)
            session = first.session
            turns.append({"student": "", "tutor": first.text,
                          "state": first.state, "elapsed_ms": 0})
            # 学生消息两种取法共用一个循环体:线性剧本(student_turns 固定序列)
            # 或 v2 分支剧本(steps——每轮按导师上一句选分支,#178 跟随器)。
            tutor_text = first.text
            pending_steps = list(case.get("steps") or [])
            linear_turns = iter(case.get("student_turns", []))
            while True:
                if pending_steps:
                    step = pending_steps.pop(0)
                    student_message = select_branch(step["branches"], tutor_text)["student_response"]
                else:
                    student_message = next(linear_turns, None)
                    if student_message is None:
                        break
                t0 = time.monotonic()
                turn = reply(session, student_message, gateway=self.gateway)
                turns.append({"student": student_message, "tutor": turn.text,
                              "state": turn.state,
                              "elapsed_ms": int((time.monotonic() - t0) * 1000)})
                tutor_text = turn.text
                if turn.state == "completed":
                    break  # 终态才断:ready 后客户端仍会发消息(产线实录 444a/2c85
                    # ——close-loop-fix 复现的正是 ready 后续轮;剧本有轮就发)
            summary = finish(session, gateway=self.gateway)
            final_state = summary.status
            summary_text = summary.text
        except GatewayError as error:
            if error.failure in ENV_FAILURES:
                raise EnvironmentFailure(str(error)) from error
            raise  # 内容类失败:重跑改变不了,runner 记台账
        except TerminalStateError as error:  # 剧本推进与状态机不符(如 fail closed)
            raise ValueError(f"内核状态机拒绝推进:{error}") from error
        return {
            "question_id": case.get("id", ""),
            "final_state": final_state,
            "turns": turns,
            "summary": summary_text,
            "total_ms": int((time.monotonic() - started) * 1000),
            "learner": learner,
            "guard_events": getattr(session, "guard_events", []),  # 兜底率度量(任务包1步1)
            # #238 件 B:tutor 调用的 facts join 键(facts.edu.session_id);judge 侧
            # 天然是 "judge-{case_id}",两侧合齐后报告层可拆 primary-only 口径。
            "session_id": session.session_id,
        }
