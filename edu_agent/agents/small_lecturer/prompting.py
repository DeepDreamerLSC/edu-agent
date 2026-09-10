"""提示词装配(PR2,#45 资产 + 基线攻守图指导)。

system 消息 = SKILL.md 剪裁版(规则+教学边界,作为代码读入,不改其内容)
+ 年级风格指令(风格档案按年级选 profile) + 攻守图教学指令(基线报告 §3:
守擂台 first_question/grade_fit——题意确认与适龄表述钉死;攻免费区
socratic/pacing/summary/termination——苏格拉底追问、单步推进、收尾规范给足)。
用户消息 = _user_prompt 装配的结构化教学上下文(M3 PR2:题目段 = 题面 text +
参考答案 answer + 解析 analysis,教师侧专属——answer/analysis 永不出现在学生
可见回复中,由内核 _guard_output 以同款对照文本把关;knowledge_points 有值时
追加追问锚点段)。风格档案从 configs/ 读取
(数据随配置走,装配逻辑是代码)。模块名 prompting 避让包内 prompts/ 目录
(SKILL.md 所在,命名空间包优先于同名模块)。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[3]
SKILL_PATH = Path(__file__).resolve().parent / "prompts" / "SKILL.md"
STYLE_PROFILES_PATH = _REPO / "configs" / "small_lecturer_style_profiles.yaml"
# 年级知识点树(数据随配置走,装配逻辑是代码):年级 → 领域 → 模块 → 主题 → [四级知识点]。
KNOWLEDGE_TREE_PATH = _REPO / "configs" / "knowledge_points.json"

# 攻守图教学指令(基线报告 §3 的 prompt 形态)。守:首问质量/年级表达(老系统
# 1.82/1.73 的强项,不容失分);攻:追问/节奏/总结/判停(老系统 0.27–0.64 的
# 弱区,行为规范给足即免费得分)。
_TONE_DIRECTIVE = """\
【语气与回应基调(每轮遵守)】
- 用词简单、语气温暖亲切,像和大孩子聊天;偶尔可用一个表情符号活跃气氛,不过度。
- 学生信息里没有名字:不给学习者起名,也不拿题面里出现的人名称呼他(那是题目角色,
  不是学生),直接用「你」对话。
- 首问友好开场(问候+邀请一起看题),不点名、不直接报题。
- 每轮回复 = 一句贴合学生表现的回应 + 一个引导问题,**必须以问题结尾**——字数不够时
  砍类比、砍展开,引导问题永远不牺牲。长度软性上限:低年级(1-3)约 80 字、高年级(4-6)
  约 100 字、初中约 120 字;超了就拆到下一轮讲,不算违规。
- 回应基调与学生本轮的真实对错一致:答对→具体肯定他做对的那一步;答错→不空夸
  也不指责,平实接住、引导他再看条件;犹豫卡住→放慢安抚。措辞贴他刚说的内容,
  每轮自然变化。
"""


# 角色与解题方法框架(演示联调定稿):波利亚四阶段 + 苏格拉底式提问拆步骤依次引导;
# 两个方法论名称只住教师侧 prompt,学生侧对话永不出现。
_MISSION_DIRECTIVE = """\
【角色与解题方法】
你是学习指导老师,基于学习者提出的问题进行引导解答。
答题过程:用波利亚解题法(理解题意→拟定计划→执行计划→回顾)配合苏格拉底式
提问,把题目拆分成多个关键步骤知识点,依次逐个引导学习者想明白。
对话中不出现「波利亚」「苏格拉底」这两个词——方法用在引导里,不说方法名。"""

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
- 学生未答对也未确认时绝不结束;证据不足时宁可继续引导。

【输出契约(字段语义,非教学策略)】
reason 字段先用一句话写明:本轮打算如何引导学生自己想到下一步,不给出答案、不写出
答案数字;写完这句规划再写 reply。reason 是你的引导计划,学生只会看到 reply。
你输出的 JSON 里 ready_to_confirm=true 当且仅当:学生本轮已给出本题的正确最终答案,
或已明确表示理解并完成检验。只要终答未出或未检验,一律 false。"""

_SUMMARY_INSTRUCTION = """\
【总结要求】基于学生真实表达整理:点出方法、他的关键转折、仍需注意的一处;
不补写他未说过的标准解法,不宣告超出本题的掌握。"""

# 首问策略分派(老系统 opening_strategy.py 语义;教学弧线 2026-09-08 人定:
# 正确→直接问不懂处,懂了→学生复讲;错误→采集错误答案→诊断思路→苏格拉底纠错→复讲)。
OPENING_HINT_CORRECT = (
    "这道题学生已做对。首问只做一件事:直接问学生这道题还有没有不懂的地方,"
    "此轮不要提「讲一遍」;不绕弯、不铺垫、不重新教。"
    "学生说都懂了之后,再请学生自己把解题思路从头讲一遍——他讲你听,"
    "复讲提问只问「你当时是怎么想的、先算了什么」;"
    "复讲提问里禁止出现任何方法名(「假设法」「方程法」等)和答案数字——"
    "方法与结论必须从他嘴里讲出来,他讲完你再点名方法予以肯定;"
    "只在卡住或讲错的地方补一个引导问题。"
)
OPENING_HINT_INCORRECT = (
    "这道题学生未做对。学生自己不知道错在哪,按教学弧线依次推进,不跳步:"
    "①首问 = 一句简短友好的开场(问候、陪学生一起看这道题,语气温暖不施压),"
    "紧接着采集他现在的作答——按题型自然地问:选择题问他选了哪个选项,"
    "计算或解答题问他算出的答案是什么——只采集不评判,不暗示对错;"
    "②追问他这个答案或选项是怎么想出来的,听他的思路;"
    "③引导他对照题目条件,自己找出卡点和错在哪一步;"
    "④苏格拉底式一步步追问修正,直到他自己说出正确答案;"
    "⑤确认他懂了之后,请他把这道题从头到尾讲一遍——他讲你听,"
    "复讲提问禁方法名与答案数字,方法和结论由他自己讲出来,他讲完你再点名方法;"
    "只在他卡住或讲错的地方补一个引导问题。"
)
OPENING_HINT_UNANSWERED = "这道题学生尚未作答。首问引导学生从第一步开始思考。"

_OPENING_HINTS = {
    "correct": OPENING_HINT_CORRECT,
    "incorrect": OPENING_HINT_INCORRECT,
    "unanswered": OPENING_HINT_UNANSWERED,
}


def opening_hint(answer_status: str | None) -> str:
    """learner.answer_status → 首问策略提示;unknown/缺省返回空串(不加提示)。"""
    return _OPENING_HINTS.get(answer_status or "", "")


def _user_prompt(question: dict, extra: dict | None = None) -> str:
    """tutor user 消息装配(M3 PR2):题目段 = 题面 + 参考答案 + 解析(教师侧专属)。

    answer/analysis 只住教师侧 prompt;学生可见面由内核 _guard_output 用同款
    对照文本把关(答案/解析出现在回复中即拦截)。knowledge_points 有值时追加
    追问锚点段(苏格拉底追问的出题点,一行 if);题图引用不进 prompt——tutor
    是文本模型,图意经 vision 转写进题面。"""
    subject = {"题面": str(question.get("text") or "")}
    if question.get("answer"):
        subject["参考答案"] = str(question["answer"])
    if question.get("analysis"):
        subject["解析"] = str(question["analysis"])
    points = question.get("knowledge_points") or []
    context = {"题目": subject, **({"追问锚点": points} if points else {}), **(extra or {})}
    return json.dumps(context, ensure_ascii=False)


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


@lru_cache(maxsize=1)
def _knowledge_tree() -> dict:
    """年级 → 领域 → 模块 → 主题 → [四级知识点] 四层知识树(数据文件读入)。

    缺文件/损坏返回空 dict,不崩——知识树是增强信号,读不到就退化为无年级依据。"""
    try:
        data = json.loads(KNOWLEDGE_TREE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def grade_grounding(grade: str, knowledge_points: list | None) -> str:
    """年级 + 题目知识点 → 该年级知识树上可依据的知识点文本(开题 steps 年级恰当化)。

    按题目 knowledge_points 精确命中主题名或子知识点,取该主题的四级清单;
    未命中(无年级 / 该年级无树 / 无匹配)返回空串,不注入、不扰动现有弧线。"""
    band = _knowledge_tree().get(str(grade or "").strip(), {})
    if not isinstance(band, dict) or not band:
        return ""
    pts = {str(x) for x in (knowledge_points or []) if x}
    if not pts:
        return ""
    matched: list[str] = []
    for modules in band.values():
        if not isinstance(modules, dict):
            continue
        for topics in modules.values():
            if not isinstance(topics, dict):
                continue
            for topic, leaves in topics.items():
                leaves = leaves if isinstance(leaves, list) else []
                if topic in pts or any(lf in pts for lf in leaves):
                    detail = "、".join(str(v) for v in leaves if v) if leaves else ""
                    matched.append(f"{topic}:{detail}" if detail else str(topic))
    return "；".join(dict.fromkeys(matched))


def system_prompt(grade: str = "") -> str:
    """start/reply 共用 system 消息:角色与方法框架 + SKILL 剪裁版 + 年级风格
    + 攻守图教学指令 + 语气指令(稳定段,cache 友好;每轮变化的只有对话内容)。"""
    return (f"{_MISSION_DIRECTIVE}\n\n{skill_rules()}\n\n{style_directives(grade)}"
            f"\n\n{TACTICS}\n\n{_TONE_DIRECTIVE}")


def summary_system_prompt(grade: str = "") -> str:
    """finish 总结路径的 system 消息。"""
    return f"{skill_rules()}\n\n{style_directives(grade)}\n\n{_SUMMARY_INSTRUCTION}"
