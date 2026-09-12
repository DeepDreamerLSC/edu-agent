"""KernelSubject:runner 被测对象的内核实现(00 §8.4 阶段 3;#41 Subject 协议)。

M1 的被测对象是老系统适配器(legacy_adapter),M2 换成内核三函数——评测线
代码零改动(00 §8.4「被测对象换内核,runner 已抽象」)。内核经 gateway=None
注入口接 runner 的 gateway 实例(直调三函数,事实记录不断链);学生消息按
场景剧本(student_turns)逐轮推进,与适配器同口径。
"""

from __future__ import annotations

import time

from edu_agent.agents.small_lecturer import TerminalStateError, finish, reply, start
from edu_agent.gateway import Gateway, GatewayError

from .image_teaching import question_image_data_url
from .judge import ENV_FAILURES
from .runner import EnvironmentFailure


class KernelSubject:
    """小讲师内核作为被测对象:run_case 按剧本驱动 start→reply×N→finish。"""

    def __init__(self, gateway: Gateway) -> None:
        self.gateway = gateway

    name = "kernel-small-lecturer"

    @staticmethod
    def _question_payload(raw: object, feed_answer: bool = False) -> dict:
        """题面 → 内核 start() 入参:纯文本(旧)或 v1 图文(question.text + image)。

        v1 的 image(path+sha256)读文件、对账后转 data URL,内核 L380 直接消费。
        P 口径(#34 台账):answer/analysis/knowledge_points 默认不喂——内核与
        生产不同,看不到参考答案。`feed_answer=True` 是**显式测量断点**(#178
        条件对照帧用,按 #146 条件变更登记):仅喂 answer,让代喂/泄漏的数值
        口径可判;默认路径零漂移(断言钉在 tests/evals/test_kernel_subject.py)。
        """
        if isinstance(raw, str):
            return {"text": raw}
        if not isinstance(raw, dict):
            raise ValueError(f"question 必须是字符串或 dict,实际 {type(raw).__name__}")
        payload = {"text": raw.get("text", "")}
        if feed_answer and raw.get("answer"):
            payload["answer"] = str(raw["answer"])
        image = raw.get("image")
        if image is not None:
            payload["image"] = question_image_data_url(image)
        return payload

    def run_case(self, case: dict) -> dict:
        started = time.monotonic()
        question = self._question_payload(case["question"],
                                          feed_answer=bool(case.get("feed_answer")))
        learner = {"grade": case.get("grade", "")}
        if case.get("answer_status"):  # R6 首问策略分派信号(评测数据侧)
            learner["answer_status"] = case["answer_status"]
        turns: list[dict] = []
        try:
            first = start(question, learner, gateway=self.gateway)
            session = first.session
            turns.append({"student": "", "tutor": first.text,
                          "state": first.state, "elapsed_ms": 0})
            for student_message in case.get("student_turns", []):
                t0 = time.monotonic()
                turn = reply(session, student_message, gateway=self.gateway)
                turns.append({"student": student_message, "tutor": turn.text,
                              "state": turn.state,
                              "elapsed_ms": int((time.monotonic() - t0) * 1000)})
                if turn.state == "ready_to_confirm":
                    break  # 掌握证据充分,余下剧本轮次不再发(判停语义)
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
        }
