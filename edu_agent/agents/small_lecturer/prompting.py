"""提示词装配(PR2,#45 资产 + 基线攻守图指导)。

system 消息 = SKILL.md 剪裁版(规则+教学边界,作为代码读入,不改其内容)
+ 年级风格指令(风格档案按年级选 profile) + 攻守图教学指令(基线报告 §3:
守擂台 first_question/grade_fit——题意确认与适龄表述钉死;攻免费区
socratic/pacing/summary/termination——苏格拉底追问、单步推进、收尾规范给足)。
用户消息 = 结构化教学上下文(题目/学生/对话记录)。风格档案从 configs/ 读取
(数据随配置走,装配逻辑是代码)。模块名 prompting 避让包内 prompts/ 目录
(SKILL.md 所在,命名空间包优先于同名模块)。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[3]
SKILL_PATH = Path(__file__).resolve().parent / "prompts" / "SKILL.md"
STYLE_PROFILES_PATH = _REPO / "configs" / "small_lecturer_style_profiles.yaml"

# 攻守图教学指令(基线报告 §3 的 prompt 形态)。守:首问质量/年级表达(老系统
# 1.82/1.73 的强项,不容失分);攻:追问/节奏/总结/判停(老系统 0.27–0.64 的
# 弱区,行为规范给足即免费得分)。
TACTICS = """\
【教学策略(必须遵守)】
守——首问与年级表达(底线,不可失分):
- 首问只确认题目范围、目标或已知条件,绝不判断答案、不纠正解法、不给关键提示,更不给出终答。
- 词汇句式贴合学生年级:超纲术语必须先用一句话解释再用;例子用学生生活里的事物。

攻——追问、节奏、总结、判停(行为规范,逐条执行):
- 追问要指向学生上一轮的具体表述:引用他说过的词,针对其中的缺口提问(「你刚才说先减 7,为什么两边都能减?」),不说「再想想」这类空话。
- 每轮只推进一个最小认知步骤:先确认一个条件,再连一个关系,再验一步算;单轮不并做两步。
- 学生答对就推进,答错就换角度,不重复同一句提示超过一次。
- 学生给出正确终答或明确说懂了,才进入总结;总结要点出方法本身与学生回答里的关键转折,基于他真实说过的内容,不补写他没表达过的解法。
- 学生未答对也未确认时绝不结束;证据不足时宁可继续引导。"""

_SUMMARY_INSTRUCTION = """\
【总结要求】基于学生真实表达整理:点出方法、他的关键转折、仍需注意的一处;
不补写他未说过的标准解法,不宣告超出本题的掌握。"""


@lru_cache(maxsize=1)
def skill_rules() -> str:
    """SKILL.md 剪裁版全文(#45 迁入资产,原样读入不改动)。"""
    return SKILL_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _style_profiles() -> dict:
    return yaml.safe_load(STYLE_PROFILES_PATH.read_text(encoding="utf-8"))


def _grade_band(grade: str) -> str:
    """年级 → 风格档案 band(两字 token 先查:「初三」不能落进「三」的小学桶)。"""
    for token, band in (("初一", "junior_middle"), ("初二", "junior_middle"), ("初三", "junior_middle"),
                        ("七", "junior_middle"), ("八", "junior_middle"), ("九", "junior_middle"),
                        ("一", "primary_lower"), ("二", "primary_lower"), ("三", "primary_lower"),
                        ("四", "primary_upper"), ("五", "primary_upper"), ("六", "primary_upper")):
        if token in str(grade):
            return band
    return "neutral"


def style_directives(grade: str) -> str:
    """风格档案按年级选 profile,指令展开为文本(enforce 语义,02 §6 年级表达规则)。"""
    profiles = _style_profiles()["profiles"]
    profile = profiles.get(_grade_band(grade)) or profiles["neutral"]
    directives = profile["style_directives"]
    shape = {"acknowledgement_plus_one_question": "每轮回复 = 一句针对学生内容的确认 + 一个问题"}.get(
        directives["sentence_shape"], directives["sentence_shape"])
    length = {"short": "句子要短", "concise": "表达精炼", "standard": "表达完整"}.get(
        directives["sentence_length"], directives["sentence_length"])
    abstraction = {"concrete": "只用具体事物讲,不用抽象术语",
                   "term_with_concrete_anchor": "术语要配一个具体例子作锚点",
                   "abstract_reasoning": "可以进入抽象推理"}.get(
        directives["abstraction_level"], directives["abstraction_level"])
    return (f"【年级表达(学生年级:{grade or '未知'})】{shape};{length};{abstraction};"
            "鼓励要指向具体证据(「这一步你用对了等式性质」),不空泛表扬。")


def system_prompt(grade: str = "") -> str:
    """start/reply 共用 system 消息:SKILL 剪裁版 + 年级风格 + 攻守图教学指令。"""
    return f"{skill_rules()}\n\n{style_directives(grade)}\n\n{TACTICS}"


def summary_system_prompt(grade: str = "") -> str:
    """finish 总结路径的 system 消息。"""
    return f"{skill_rules()}\n\n{style_directives(grade)}\n\n{_SUMMARY_INSTRUCTION}"
