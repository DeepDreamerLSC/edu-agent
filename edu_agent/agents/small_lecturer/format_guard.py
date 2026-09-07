"""学生可见输出格式护栏(02 §6「格式降级:无 Markdown / LaTeX」;SKILL.md 第 11/12 条语义)。

面向学生的回复只输出纯文本;数学表达用 ×、÷、±、≤、≥、≠、√ 等可直接阅读的
符号(白名单,不算违规)。不向学生输出 Markdown 结构、美元符号公式边界或
LaTeX 反斜杠命令——老仓库此语义只存在于 SKILL 条款(prompt 层),无确定性
检测器与现成断言,本模块是其首次成文;无法安全转换的格式降级为重新说明提示
(转换器 M2 内核按需加,检测先行)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FORMAT_GUARD_POLICY_VERSION = "small_lecturer_format_guard/v1"

# SKILL.md 第 11 条:可直接阅读的数学符号(允许)
READABLE_MATH_SYMBOLS = "×÷±≤≥≠√"

_MARKDOWN_PATTERNS = (
    re.compile(r"(?:^|\n)\s{0,3}#{1,6}\s"),      # ATX 标题
    re.compile(r"(?:^|\n)\s*(?:[-*+]|\d+\.)\s"),  # 列表项
    re.compile(r"\*\*[^*\n]+\*\*"),               # 粗体
    re.compile(r"(?<!\*)\*[^*\n]+\*(?!\*)"),      # 斜体
    re.compile(r"`[^`\n]+`"),                     # 行内代码
    re.compile(r"\[[^\]\n]*\]\([^)\n]*\)"),       # 链接
)
_LATEX_COMMAND = re.compile(r"\\[A-Za-z]+")       # LaTeX 反斜杠命令(\frac 等)
_DOLLAR_BOUNDARY = re.compile(r"\$\$?[^$\n]+\$")  # $...$ / $$...$$ 公式边界


@dataclass(frozen=True)
class FormatGuardResult:
    reply: str
    ok: bool
    findings: tuple[str, ...]
    downgrade_prompt: str | None  # SKILL 12:无法安全转换 → 降级为重新说明提示


_DOWNGRADE_PROMPT = "这一段我换个说法重新讲,我们继续看这道题的下一步。"


def evaluate_student_visible_format(reply: str) -> FormatGuardResult:
    """检测学生可见文本的格式违规;数学符号白名单不触发。"""
    findings: list[str] = []
    if any(pattern.search(reply) for pattern in _MARKDOWN_PATTERNS):
        findings.append("markdown_structure")
    if _LATEX_COMMAND.search(reply):
        findings.append("latex_command")
    if _DOLLAR_BOUNDARY.search(reply):
        findings.append("dollar_formula_boundary")
    if not findings:
        return FormatGuardResult(reply, True, (), None)
    return FormatGuardResult(reply, False, tuple(findings), _DOWNGRADE_PROMPT)
