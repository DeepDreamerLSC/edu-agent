"""GEPA 反思编辑器族(#310 预算拆分自 gepa.py:单文件 800 行上限,02 §2)。

四个编辑器共享同一纪律:单次 gateway 调用、lint 不过保留父代(零退化)、
失败帧浓缩前 5 进 prompt。gepa.py 经 import 重导出,patch 目标与公共 API 不变。
"""

from __future__ import annotations

from edu_agent.gateway import Gateway, GatewayError, ModelRequest


_EDITOR_PROMPT = """你是一个提示词编辑器。当前 elicit 模板:
---
{current}
---

失败案例摘要(共 {n_failures} 个):
{failure_summary}

任务:生成改进版本,保持核心意图(引导学生从头讲思路、先说第一步),但调整措辞以降低失败率。
约束:
- 长度 30-100 字(中文);
- 必须包含「思路」「第一步」或等价引导词;
- 不要围栏、不要解释,只输出改进后的模板文本。"""


def edit_template(current: str, failure_frames: list[dict], gateway: Gateway,
                  role: str = "judge_independent") -> str:
    """一次 gateway 调用:当前模板 + 失败帧浓缩 → 变体;带 lint。
    
    Lint:必须保住核心引导词(「思路」「第一步」),防进化出废模板。
    角色:judge_independent(DeepSeek 直评,spike 复用,不加新角色)。
    三键裁决(2026-09-17,PM sha256=d7256fcc631e69e7)保留:编辑器非判分,
    走 judge_independent 属设计内(用户已追认);判分入口默认已改 "judge"
    (本地 mlx_27b 主选),judge_independent 留 #32 平行评分用途。
    """
    failure_summary = "\n".join(
        f"- {f['case_id']}: {f['kind']} — {f['detail'][:100]}"
        for f in failure_frames[:5]  # 浓缩前 5 个失败
    ) if failure_frames else "(无失败案例)"
    
    prompt = _EDITOR_PROMPT.format(current=current, n_failures=len(failure_frames), failure_summary=failure_summary)
    
    request = ModelRequest(
        role=role,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        temperature=0.7,
    )
    
    try:
        response = gateway.invoke(request)
        variant = response.text.strip().strip("`").strip()
    except GatewayError:
        return current  # 编辑失败,保守保留当前
    
    # Lint
    if len(variant) < 30 or len(variant) > 100:
        return current
    if "思路" not in variant and "第一步" not in variant and "从头" not in variant:
        return current
    if variant == current:
        return current
    
    return variant


_SUPPORT_EDITOR_PROMPT = """你是一个提示词编辑器。当前「卡壳支持」问句模板:
---
{current}
---
失败案例摘要(共 {n_failures} 个):
{failure_summary}

任务:生成改进版本,保持核心意图(学生卡住时把这一步拆成最小的一个小问题、只问不揭示、
不含答案数字),但调整措辞以降低失败率。约束:
- 长度 20-70 字(中文);
- 必须是问句且以问号结尾;
- 不出现任何数字或方法名;
- 不要围栏、不要解释,只输出改进后的模板文本。"""


_NR_EDITOR_PROMPT = """你是一个提示词编辑器。当前复讲引导模板:
---
{current}
---
以下案例被评审判为 review(学习证据不足,无法确认掌握):
{failure_summary}

任务:调整模板措辞(必须与当前版本不同,不得原样返回),让学生复讲时更容易给出**可判定的回答**——明确请他说出
具体步骤、算式或结论(而不是"说说想法"这类开放邀请),使评审能据以判定。
约束:
- 长度 30-100 字(中文);
- 必须包含「思路」「第一步」或「算式/步骤」等价引导词;
- 不要围栏、不要解释,只输出改进后的模板文本。"""


def edit_template_nr(current: str, failure_frames: list[dict], gateway: Gateway,
                      role: str = "judge_independent") -> str:
    """needs_review 靶向编辑(收敛#2 选项①准备件):与 edit_template 同 lint 同角色,
    唯一差异是指令瞄准 nr 维——让复讲引导产出可判定证据,而非更讨喜的开放邀请。"""
    failure_summary = "\n".join(
        f"- {f['case_id']}: {f['kind']} — {f['detail'][:100]}"
        for f in failure_frames[:5]
    ) if failure_frames else "(无失败案例)"
    prompt = _NR_EDITOR_PROMPT.format(current=current, failure_summary=failure_summary)
    try:
        response = gateway.invoke(ModelRequest(
            role=role, messages=[{"role": "user", "content": prompt}],
            max_tokens=200, temperature=0.7))
        variant = response.text.strip().strip("`").strip()
    except GatewayError:
        return current
    linted = _lint_common(variant, current, 30, 100, ("思路", "第一步", "算式", "步骤"))
    return variant if linted is not None else current


def _lint_common(variant: str, current: str, floor: int, cap: int,
                 keywords: tuple[str, ...]) -> str | None:
    """共享 lint:长度窗、关键词、非退化;不合规返回 None(调用方保留父代)。"""
    if variant == current or not (floor <= len(variant) <= cap):
        return None
    if not any(word in variant for word in keywords):
        return None
    return variant


def edit_support_hint(support: str, failure_frames: list[dict], gateway: Gateway,
                      role: str = "judge_independent") -> str:
    """「卡壳支持」问句编辑(双旋钮的 support 分支):lint 不过保留父代。"""
    failure_summary = "\n".join(
        f"- {f['case_id']}: {f['kind']} — {f['detail'][:100]}"
        for f in failure_frames[:5]
    ) if failure_frames else "(无失败案例)"
    prompt = _SUPPORT_EDITOR_PROMPT.format(
        current=support, n_failures=len(failure_frames), failure_summary=failure_summary)
    try:
        response = gateway.invoke(ModelRequest(
            role=role, messages=[{"role": "user", "content": prompt}],
            max_tokens=160, temperature=0.7))
        raw = response.text.strip().strip("`").strip()
    except GatewayError:
        return support
    linted = _lint_common(raw, support, 20, 70, ("?", "?"))
    return linted if linted is not None else support


def edit_two_knobs(
    elicit: str, support: str, round_idx: int,
    failure_frames: list[dict], gateway: Gateway,
    editors=None,
) -> tuple[str, str]:
    """双旋钮编辑(#256 阶段 2 选项 A 搜索空间):偶代编辑 elicit、奇代编辑 support。

    单次 gateway 调用(编辑器预算 1 call/代不变);被编辑旋钮拿失败帧反馈,
    另一旋钮原样保留。lint 失败保留父代(与 edit_template 同纪律)。
    editors=(elicit编辑器, support编辑器);None 时晚绑定默认对(保持可 patch)。
    """
    if editors is None:
        editors = (edit_template, edit_support_hint)
    elicit_editor, support_editor = editors
    if round_idx % 2 == 0:
        return elicit_editor(elicit, failure_frames, gateway), support
    return elicit, support_editor(support, failure_frames, gateway)
