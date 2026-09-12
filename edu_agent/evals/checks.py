"""对话质量回归网 check 注册表(#185 短板固化;#178 的判据底座)。

网不是第二套门:只把现实复算成红/绿,不拦内核输出。每条 check 是纯函数
`(check, case, result) -> (ok, detail)`,detail 指名到具体数字/状态;声明式参数
住在 check 条目里。零模型、零内核 import:`_NUMBER_RE` 刻意不与内核共享口径
(独立 oracle,实测抓到内核 `_reply_numbers` 剥掉的「第13次」序数形态)。
**加一条新 check = 加一个函数并进 REGISTRY**,不改其它任何文件。

# ponytail: 天花板 = ASCII 数字口径,分数/百分数/中文数字等价形态漏判(钉在
# test_ascii_digit_boundary_is_pinned);升级点 = _numbers 一处 + 同步钉边表,勿与内核合并。
"""

from __future__ import annotations

import re
from collections.abc import Callable

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

# 注册表类型:check 条目 + 场景 + 对话记录 → (是否通过, 失败详情)。
CheckFn = Callable[[dict, dict, dict], tuple[bool, str]]


class UnknownCheck(ValueError):
    """场景声明了未注册的 check 名(多半是拼写错误):加载即暴露,不静默跳过。"""


def _numbers(text: object) -> set[float]:
    """ASCII 数字段全集(整数/小数;与题面口径一致,分数按两个数字计)。"""
    return {float(match) for match in _NUMBER_RE.findall(str(text or ""))}


def _question_field(case: dict, key: str) -> str:
    question = case.get("question")
    return str((question.get(key) if isinstance(question, dict) else None) or "")


def _tutor_turns(result: dict) -> list[tuple[int, str]]:
    """(轮次下标, tutor 文本);下标与 result["turns"] 对齐(0 = 首问)。"""
    turns = result.get("turns") or []
    return [(index, str(turn.get("tutor") or "")) for index, turn in enumerate(turns)]


def text_excludes_answer_values(check: dict, case: dict, result: dict) -> tuple[bool, str]:
    """终答值不得出现在任何 tutor 轮文本(#149:阶梯揭示只给步骤不给终答)。

    合法披露路径(bottom-out / finish / 学生已陈述后的确认轮)由**用例设计**规避
    ——本 check 不内嵌内核策略(网不是第二套门);fail-open:终答取不到数字
    (文字/字母类答案)时不判,沿用判据底座的空集语义。**静默恒真通道已在
    loader 层关闭**:声明本 check 的用例,`question.answer` 取不到 ASCII 数字
    会被 scenario_corpus 拒绝(中文数字终答 → 改写 answer 或换 check,见
    test_loader_rejects_bad_data)。"""
    answer_values = _numbers(_question_field(case, "answer"))
    if not answer_values:
        return True, ""
    violations = [
        f"终答值 {value:g} 出现在 turns[{index}]:「{text}」"
        for index, text in _tutor_turns(result)
        for value in sorted(answer_values & _numbers(text))
    ]
    if violations:
        return False, ";".join(violations)
    return True, ""


def text_excludes_unauthorized_numbers(check: dict, case: dict, result: dict) -> tuple[bool, str]:
    """tutor 文本不得含允许集(题面数字 ∪ 学生实际已说数字)之外的数字。

    防误伤反例的判据(修泄漏不许修成「连题面数字都不敢提」);学生数字取
    result 里实际发出的轮次(reality,非剧本声明——判停后余轮未发的数字不算)。

    **可用前提(挂这条 check 前必读)**:本轮 tutor 不引入任何新数字——**含
    合法导出数字**。「把 2.8 写成分数 28/10」里的 28/10 是合法推导,但按本口径
    判无授权(假阳性);题面用中文数字时 ASCII 允许集为空,连题面数字都会被判
    泄漏。v1 里只有「纯引用题面数字」的解读轮(如用例③)适合挂;判断/计算轮
    别挂,等价形态归一进来后再放开。"""
    allowed = _numbers(_question_field(case, "text"))
    for turn in result.get("turns") or []:
        allowed |= _numbers(turn.get("student"))
    violations = []
    for index, text in _tutor_turns(result):
        unauthorized = sorted(_numbers(text) - allowed)
        if unauthorized:
            violations.append(
                f"无授权数字 {','.join(f'{value:g}' for value in unauthorized)}"
                f" 出现在 turns[{index}]:「{text}」")
    if violations:
        return False, ";".join(violations)
    return True, ""


def state_is_not(check: dict, case: dict, result: dict) -> tuple[bool, str]:
    """任何轮次的 state 不得等于 check["state"](如 ready_to_confirm:#149 判停闸)。"""
    banned = str(check.get("state") or "")
    for index, turn in enumerate(result.get("turns") or []):
        if str(turn.get("state") or "") == banned:
            return False, (f"turns[{index}] 的 state 为 {banned}"
                           f"(学生文本:「{turn.get('student')}」)")
    return True, ""


def finish_status(check: dict, case: dict, result: dict) -> tuple[bool, str]:
    """final_state 必须等于 check["status"](completed / needs_review / failed)。"""
    expected = str(check.get("status") or "")
    actual = str(result.get("final_state") or "")
    if actual != expected:
        return False, f"final_state 期望 {expected},实际 {actual}"
    return True, ""


REGISTRY: dict[str, CheckFn] = {
    "text_excludes_answer_values": text_excludes_answer_values,
    "text_excludes_unauthorized_numbers": text_excludes_unauthorized_numbers,
    "state_is_not": state_is_not,
    "finish_status": finish_status,
}


def run_check(check: dict, case: dict, result: dict) -> tuple[bool, str]:
    """按条目里的 name 派发到注册函数;未注册名抛 UnknownCheck(拼写错误即刻暴露)。"""
    name = str(check.get("name") or "")
    function = REGISTRY.get(name)
    if function is None:
        raise UnknownCheck(f"check 未注册:{name!r}(已注册:{sorted(REGISTRY)})")
    return function(check, case, result)
