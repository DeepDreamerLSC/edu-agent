"""M7-1 Identity Spine v0(#545):guard 事件/facts 行/工件的三类 additive 身份字段。

**Trace owns ordering and lineage, not the meaning or authority of facts.**
Guard 仍拥有 rule_ids/decision;Gateway 仍拥有 model/runtime facts;Kernel 仍
拥有 state;Completion/Eval truth 不动。本模块只构造 join/order/reference,
不含任何判定语义;全部纯哈希/常量拼接,无 I/O、无异常面(instrumentation
失败不得改变 Product outcome——按构造成立,非 try/except 吞错)。

三类增量(全部 additive;旧工件缺字段时既有读取行为不变):
A. guard 事件被检对象身份——影子检测事件(branch=model)补
   ``role/phase/subject_id``;处置事件(_record_event 形态)再补
   ``output_id/effect``。id 形态 = ``sha256:<hex>``(**实际文本的 UTF-8 原字节**,
   不做 strip/lower/JSON 重序列化等归一化)或 ``const:<NAME>``(仓内确定性常量,
   如 const:PURE_BLOCK / const:SAFE_FALLBACK_TEXT,不散列常量文本直接点名)。
B. facts join 脊柱——``edu.turn`` = 该调用所属 Kernel turn(0 起,transcript
   下标,与 guard_events.turn 同口径;finish 总结调用 = 末轮+1)。调用唯一性
   仍靠既有 ``edu.call_id``(同 turn 多调用不碰撞);join 键 =
   (edu.session_id, edu.turn)。
C. 工件代码指纹——run_case result 行补 ``git_sha``(git 不可用/非仓库时 None,
   不伪造;与 corpus_round manifest identity.git_sha 同口径,不自建第二 truth)。

phase 闭集(检查发生面;被检对象身份的定语):
- ``model_reply_first_check``:模型回合回复首检(对应同 turn 的主调用)
- ``mask_recheck``:数值掩码文本复检(零模型调用)
- ``fallback_constant_recheck``:SAFE_FALLBACK_TEXT 常量复检(零模型调用)
- ``repair_recheck``:重生成文本复检(对应同 turn 的 repair 调用)
- ``post_method_check``:方法名代喂处置(feeds_method,首检在 reply 后处理)

effect 闭集(处置语义,#545 授权子集):NO_OP / MASK / REPLACE / BLOCK。

join 机械规则(消费侧,不读 kernel 源码):
1. (edu.session_id, edu.turn) 圈定一次轮内的全部调用与事件;
2. phase=model_reply_first_check 的 subject_id = 主调用产出的 reply 文本;
   phase=repair_recheck = repair 调用产出;mask/fallback 常量复检不对应任何
   调用(subject_id=const:* 或掩码文本即可机械判别);
3. 处置事件 output_id = 该 stage 输出文本身份;无进一步变异时等于
   sha256(transcript 该轮 tutor 可见文本)。

隐私(E6 逐字段):role/phase/effect=闭集枚举;subject_id/output_id=哈希或
常量名(不含正文);turn=整数;git_sha=commit hex。零新增 prompt/学生原文/
answer/analysis/图片面;处置事件 ``original`` 为既有字段,本轮不新增不扩大。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

PHASE_FIRST_CHECK = "model_reply_first_check"
PHASE_MASK_RECHECK = "mask_recheck"
PHASE_FALLBACK_RECHECK = "fallback_constant_recheck"
PHASE_REPAIR_RECHECK = "repair_recheck"
PHASE_POST_METHOD = "post_method_check"

EFFECTS = frozenset({"NO_OP", "MASK", "REPLACE", "BLOCK"})


def text_id(text: str) -> str:
    """实际被检文本的对象身份:sha256(UTF-8 原字节),零归一化。"""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def const_id(name: str) -> str:
    """仓内确定性常量的对象身份(不散列常量文本,直接点名)。"""
    return f"const:{name}"


def shadow_event(ctx, text: str, phase: str, extracted: list, sources: list,
                 subject_const: str | None = None) -> dict:
    """branch=model 影子检测事件:既有四字段语义不变 + role/phase/subject_id。

    gate 由违规面推导(violation_sources 非空 ⟺ blocked),与 kernel 原判定同源,
    不引入第二套判据。ctx 为 kernel._GuardContext(role/cited_numbers)。
    subject_const 在场时被检对象是仓内常量(如 SAFE_FALLBACK_TEXT 复检),
    身份用 const:<NAME>——消费侧无需常量原文即可机械判别。"""
    return {
        "branch": "model", "cited": ctx.cited_numbers,
        "extracted": extracted, "violation_sources": sources,
        "gate": "blocked" if sources else "observed",
        "role": ctx.role, "phase": phase,
        "subject_id": const_id(subject_const) if subject_const else text_id(text),
    }


@dataclass(frozen=True)
class Disposition:
    """处置事件身份面(调用点声明,构造收口本模块):regenerated/mode 语义与
    #165 WS4 原口径逐字不变;phase=判定该处置的检查面;output_id/effect 见
    模块合同。role 恒 tutor(护栏处置面当前只在 tutor 输出上)。"""

    mode: str | None
    phase: str
    output_id: str
    effect: str
    regenerated: bool = False


def spine_event(guard: str, rule_ids: list[str], original: str,
                spine: Disposition) -> dict:
    """处置事件:既有字段(guard/rule_ids/original/regenerated/mode)逐字不变
    + 身份字段(role/phase/subject_id/output_id/effect)。"""
    event = {"guard": guard, "rule_ids": rule_ids,
             "original": original, "regenerated": spine.regenerated}
    if spine.mode is not None:
        event["mode"] = spine.mode
    event["role"] = "tutor"
    event["phase"] = spine.phase
    event["subject_id"] = text_id(original)
    event["output_id"] = spine.output_id
    event["effect"] = spine.effect
    return event


# ---- 处置构造点(kernel `_guard_output`/feeds_method 四处置的脊柱接线)----

def masked_disposition(masked_text: str) -> Disposition:
    """数值掩码处置:mask 复检通过,输出=掩码文本(结构逐字保留)。"""
    return Disposition(mode="masked", phase=PHASE_MASK_RECHECK,
                       output_id=text_id(masked_text), effect="MASK")


def fallback_disposition() -> Disposition:
    """问句兜底处置(#542 rung):SAFE_FALLBACK_TEXT 复检通过,输出=常量。"""
    return Disposition(mode="safe_fallback", phase=PHASE_FALLBACK_RECHECK,
                       output_id=const_id("SAFE_FALLBACK_TEXT"), effect="REPLACE")


def blocked_disposition() -> Disposition:
    """纯 block 处置(末级 rung,fail-closed):输出=PURE_BLOCK 常量。"""
    return Disposition(mode="blocked", phase=PHASE_FALLBACK_RECHECK,
                       output_id=const_id("PURE_BLOCK"), effect="BLOCK")


def method_disposition(mode: str, repaired_text: str) -> Disposition:
    """feeds_method 处置:masked=脱敏文本 / regenerated=重生成文本 / template=常量。"""
    template = mode == "template"
    return Disposition(
        mode=mode, phase=PHASE_POST_METHOD, regenerated=not template,
        output_id=const_id("SAFE_FALLBACK_TEXT") if template else text_id(repaired_text),
        effect="MASK" if mode == "masked" else "REPLACE")
