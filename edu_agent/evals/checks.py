r"""对话质量回归网 check 注册表(#185 短板固化;#178 讲题打磨的判据底座)。

网不是第二套门:不拦内核输出,只把「已知短板」复算成红/绿。每条 check 是纯函数
`(check, case, result) -> (ok, detail)`:
- `check`:场景里声明的那条条目(`{"name": ..., **参数, "note": ...}`)——声明式参数
  住在条目里,故签名在任务书 `(case, result)` 基础上前插 check 条目本身(纯函数性不变);
- `case`:场景 dict(题面/终答/剧本——判定输入);
- `result`:`Subject.run_case` 的对话记录(turns / final_state / ...)。

`detail` 必须指名到具体数字/状态(失败可定位,不写「质量不佳」这类空话)。
零模型、零内核 import:网与被测物解耦,数字抽取口径 = ASCII 数字段(整数/小数,
分数按两个数字计),独立复算。**加一条新 check = 在此加一个函数并进 REGISTRY**,
不改其它任何文件。

## 判定力边界(已知且已钉死,见 test_ascii_digit_boundary_is_pinned)

只认 ASCII 数字段 ⇒ 终答的**等价表达**不在此口径内:中文数字「五分之四」、分数
形态「1/4」「12/5」、百分数「80%」、中文序数「第十三次」全部漏判。本 corpus 恰是
小数×分数题集,这个边界是**具体的**:tutor 若用分数形态揭示小数终答,网会绿。
补等价归一(分数/百分数/中文数字 → 小数)时改 `_numbers` 一处 + 同步钉边测试。

`_NUMBER_RE` 是本仓库第 9 份同口径正则(numeric.py ×4、kernel.py ×3、
arc_eval_metrics.py ×1)——**刻意重复、勿合并**:网要的就是与内核
(`_reply_numbers`)独立的 oracle。实测依据(#185 取证):泄漏文本「…第13次必形成…」
里内核 `_reply_numbers` 把「第\s*\d+」当序数剥掉、据不到 13,而网的 `_numbers`
看得到——正因为不共享口径,网抓到了内核自己看不见的形态。合并会让网静默继承
内核的盲区(若将来有人补全 numeric.py 的中文数字能力,这张网**不会**自动跟进,
需手动同步——代价写在这里,不藏着)。
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
