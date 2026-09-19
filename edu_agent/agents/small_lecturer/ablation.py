"""三臂消融门控组件(#333 Kernel 重新审判;协议=evals/artifacts/kernel-retrial/)。

kernel.py 的伴生模块(02 §2 单文件预算:门控组件不进 kernel 本体):
  - 臂状态用容器变异(免 global 语句);C=生产默认,生产不注入恒为 C;
  - A=raw shadow(B类全旁路,检测记 would_* 不动作);B=thin(仅 answer_leak 处置);
  - 评测 runner 按臂串行设置(每臂一跑,无并发串臂)。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from edu_agent.agents.small_lecturer.kernel import LearnerSession

_STATE = {"arm": "C"}  # 容器变异免 global(suppression 预算)
_OFF = {"off": frozenset()}  # 二阶段 LOO 关闭集(默认空=现 C;生产零改动)


def set_ablation_arm(arm: str) -> None:
    """消融臂设置(仅评测 runner 调用;A/B/C 之外 fail closed)。"""
    if arm not in ("A", "B", "C"):
        raise ValueError(f"消融臂必须是 A/B/C,实际 {arm!r}")
    _STATE["arm"] = arm


def set_phase2_off(names) -> None:
    """二阶段 LOO 关闭集(仅评测 runner;协议 phase2-protocol-v1.md §2 词表)。"""
    allowed = {"repeat_regen", "repeat_fallback", "reveal_ladder", "premature_confirm",
               "confirm_rewrite", "soften_step", "bottomout_backboard"}
    bad = set(names) - allowed
    if bad:
        raise ValueError(f"未知机制名 {sorted(bad)};词表={sorted(allowed)}")
    _OFF["off"] = frozenset(names)


def mech_off(name: str) -> bool:
    """机制是否被二阶段关闭(C 臂门控点查询;A/B 臂不受 off 集影响)。"""
    return name in _OFF["off"]


def current_arm() -> str:
    return _STATE["arm"]


def shadow_event(session: "LearnerSession | None", kind: str, rule: str,
                 **extra) -> None:
    """A 臂 shadow 埋点(additive 新键 shadow/rule,不改既有键;M6 同口径读数)。"""
    if session is not None:
        session.guard_events.append({"shadow": kind, "rule": rule, **extra})


def arm_bypass(kind: str, rule: str, session: "LearnerSession | None") -> bool:
    """B类确定性覆写点统一问路:C=False(照原逻辑);A=记 would_* 后 True(旁路到
    模型路径);B=True(静默旁路)。"""
    if _STATE["arm"] == "C":
        return False
    if _STATE["arm"] == "A":
        shadow_event(session, kind, rule)
    return True


def guard_early(guard: str | None, session: "LearnerSession | None",
                rule_ids: list[str], violations, reply_text: str) -> str | None:
    """消融臂 guard 早退(协议 §1.3):A=检测照跑记 would_*,原文直通(不归一化/
    不重生成/不兜底);B=仅 answer_leak 走处置,其余(含无命中)原文直通。
    返回 None=C 臂照原漏斗逻辑。"""
    if _STATE["arm"] == "A":
        if guard is not None:
            shadow_event(session,
                         "would_block" if guard == "answer_leak" else "would_rewrite",
                         str(guard), rule_ids=rule_ids,
                         violations=sorted(violations or ()))
        return reply_text
    if _STATE["arm"] == "B" and guard != "answer_leak":
        return reply_text
    return None


# B 臂最小安全 regen(协议 §1.3 硬约束「只拒绝不重教」):critique 仅要求去除终答,
# 不注入教学话术;再命中 → 纯 block 安全句(非教学句)。
_SAFETY_REGEN_CRITIQUE = (
    "逐字保留原回复,仅将终答数值替换为□,不得改写其他任何词句。")
PURE_BLOCK = "这条回复包含题目终答,我不能直接给出。"


def _number_forms(number: float) -> list[str]:
    """数值 → 文本形态(整数/千分位/小数),掩码替换候选集。"""
    if float(number).is_integer():
        whole = str(int(number))
        return [whole] + ([f"{int(number):,}"] if len(whole) > 3 else [])
    return [str(number), f"{number:g}"]


def _mask_violations(text: str, violations) -> str:
    """确定性数值掩码(phase2bx 附录 A):违规数值→□;词边界防误伤(2025 里的
    20 不动,3.0 里的 3 不动——留待 regen 兜底)。"""
    for number in violations or ():
        for form in _number_forms(float(number)):
            text = re.sub(rf"(?<![\d.,]){re.escape(form)}(?![\d.,])", "□", text)
    return text


def arm_b_leak_funnel(ctx, session: "LearnerSession | None", rule_ids: list[str],
                      reply_text: str, violations, ready_to_confirm: bool) -> str:
    """B 臂 answer_leak 处置(phase2bx 附录 A 掩码版,联合变体安全面):round-1
    确定性数值掩码;不过判据→regen(critique=逐字保留);再命中→纯 block。
    check/regenerate 惰性导入 kernel(调用期无循环)。埋点 safety_mask/regen r1|2。"""
    from edu_agent.agents.small_lecturer.kernel import _guard_check, _regenerate
    session.guard_events.append({"arm_b": "safety_mask", "round": 1,
                                 "rule_ids": list(rule_ids)})
    event = session.guard_events[-1]  # 持引用:check 会追加自己的事件,[-1] 会漂移
    masked = _mask_violations(reply_text, violations)
    if masked != reply_text:
        guard, _r, _n, _v = _guard_check(ctx, masked, session, ready_to_confirm)
        if guard is None:
            return masked
        event["mode"] = "mask_failed"
    else:
        event["mode"] = "no_number_form"
    session.guard_events.append({"arm_b": "safety_regen", "round": 1,
                                 "rule_ids": list(rule_ids)})
    regenerated = _regenerate(ctx, session, reply_text,
                              _SAFETY_REGEN_CRITIQUE, ready_to_confirm)
    if regenerated is not None:
        return regenerated
    session.guard_events.append({"arm_b": "safety_regen", "round": 2,
                                 "rule_ids": list(rule_ids)})
    return PURE_BLOCK
