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
import re
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
- 表扬须指向学生刚说的具体内容(哪一步、哪个想法对);禁「这一步很准!」式
  固定口头禅空夸——同一句夸奖不许每轮复读。
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

# incorrect 弧线第②步(**逐轮**)提示:首问完成采集后,紧随的那一轮只追问思路。
# 缺口实测(#165 WS4 第 5 条;F 口径 20 例「采集不评判」= 4/20):弧线提示只在首问注入,
# 后续轮次没有步骤指引 → 模型从①采集直接跳到③纠正,把②「追问他怎么想的」跳过,
# 于是「采集轮 + 紧随回应」窗口内出现对错判定/纠正(judge 原句:「但分数加法不能这样算哦」
# 「这一步很准!」「借出的书要从总数里去掉」)。本提示只改**那一轮**的措辞取向,
# 不动任何判据/基线,也不新增模板(仍是模型生成)。
_DIAGNOSE_TURN_HINT = (
    "【弧线第②步 · 这一轮只做一件事】学生刚说出他的作答。请**只追问他是怎么想出来的**"
    "(例如「你是怎么想到这一步的?」),听他把思路讲完:"
    "这一轮**不要判定对错**(不出现「对/很准/真棒/不能这样算」这类评价)、"
    "**不要纠正**、**不要给反例或下一步**。"
)

# 第③步(**找卡点**)提示:实测定为**不用**——把不评判窗口从「只第②轮」扩到②+③ 后,
# F 口径「采集不评判」反而 8/20 → 4/20(判词显示判定后移、且两例被复讲引导接走)。
# 按数据回退到只覆盖第②轮;此处只留结论,不留常量(避免死代码)。

_OPENING_HINTS = {
    "correct": OPENING_HINT_CORRECT,
    "incorrect": OPENING_HINT_INCORRECT,
    "unanswered": OPENING_HINT_UNANSWERED,
}

# 首问固定模板(head/tail 组装,五条文案逐字定稿)。上面的 OPENING_HINT_* 只是拼进 user
# 消息的**策略提示**,模型可以违抗——实测首问直接把答案报出来(题「8排6号记作(6,8),那么
# 12排5号记作(,);(3,10)表示()排()号」的首问写成「…记作(5,12),(3,10)表示10排3号,对吗?」,
# 两个空的答案都给了)。故首问**可见文本**由内核 start() 覆盖为确定性模板:不含答案数字、
# 不含方法名,答案只能从学生嘴里出来;模型调用照旧(仍产出 steps/transcription)。
# head 两选一:**真·带图**(question.image 非空)且读出半句 → 图像招呼语 + 半句复述
# + 识题确认句(IMAGE_BRIEF_CONFIRM,#180 ③);其余(纯文字题 / 图像题没读出内容)
# → 纯文字招呼语(不出现「…这道题:。」残句,也不插确认)。
# tail 三选一:正确档一套(文字/图像共用);采集档——图像题恒用统一那句(不按题型分),
# 文字题按题型分选择题/非选择题(见 `_is_multiple_choice`)。
HEAD_TEXT = "你好同学,"
HEAD_IMAGE_PREFIX = "你好同学,我看到你发的题啦,我们一起看看:"   # 后面接半句复述 + 识题确认句
# 图像档识题确认(#180 ③ 试点):复述来自模型转录,可能读错题(#180 实锤一例把剩余 3/8
# 读成 5/8)→ 复述后紧跟「对吗?」式确认,让学生在第 0 轮就能纠正,而不是教错整场。
IMAGE_BRIEF_CONFIRM = "我读得对吗?"
TAIL_CORRECT = "这道题你做对啦,真棒!还有哪里不太明白吗?"
TAIL_COLLECT_CHOICE = "请问这道题你选了什么呀?讲讲你的思路吧!"
TAIL_COLLECT_OPEN = "请问你算出的答案是多少呀?讲讲你的思路吧!"
TAIL_COLLECT_IMAGE = "这道题你的答案是什么呀?讲讲你的思路吧!"
# 完成表达追问(#178 判停分析→PR-2):学生说「算出来了」但没带答案数字 → 确定性追问,
# 把判停闸要的结论数字采上来(中性措辞:只采集、不判对错、不预设掌握)。
ASK_FINAL_ANSWER = "你算出的是多少?把答案说出来,我们对一对。"

# 定稿可见文本的文字题两档(常量形式,供测试与调用方逐字对照):
FIRST_QUESTION_COLLECT = HEAD_TEXT + TAIL_COLLECT_OPEN              # 文字·采集·非选择题
FIRST_QUESTION_COLLECT_CHOICE = HEAD_TEXT + TAIL_COLLECT_CHOICE    # 文字·采集·选择题
FIRST_QUESTION_CORRECT = HEAD_TEXT + TAIL_CORRECT                   # 文字/图像·正确档(文字 head)

# 复述(transcription → brief)的确定性口径:取「半句」——首个逗号或句末标点之前,
# strip 后 4–16 字(超 16 字截到 16 字加「…」)。
_BRIEF_MIN_CHARS = 4
_BRIEF_MAX_CHARS = 16
_BRIEF_ELLIPSIS = "…"
_BRIEF_CUTS = ("。", "!", "?", ".", "！", "？", ",", "，")

# 选择题标记(纯规则,零模型调用):字母 + 选项标点,含全角 ＡＢＣＤ 与全角标点(、．)）。
_OPTION_MARK_RE = re.compile(r"[A-DＡ-Ｄ]\s*[.、．)）]")


def _is_multiple_choice(question: dict | None) -> bool:
    """选择题判定(首问文案分流用;纯规则,零模型调用,无第三方依赖)。

    **主信号 = 题面文本**(评测口径下 question 只有 {text, image}、没有 answer,用题面才能
    在两条路径上都生效):题面出现 ≥2 个选项标记(形如 A. / B、 / C． / D))即判选择题;
    题面信号不足时用 `answer`(形如「A. (2,7)」)作**次要**信号(它带选项标记即判选择题)。
    只有单个标记、或标记全无 → 非选择题。"""
    source = question or {}
    if len(_OPTION_MARK_RE.findall(str(source.get("text") or ""))) >= 2:
        return True
    return bool(_OPTION_MARK_RE.search(str(source.get("answer") or "")))


def _brief_transcription(transcription: str | None) -> str:
    """转录 → 首问里的半句复述短语(确定性,零依赖,纯字符串、零模型调用):
    取首个逗号或句末标点**之前**(谁更早取谁)→ strip → 上限 16 字(超出截到 16 字加「…」);
    不足 4 字视为没读出内容,返回空串(head 退回 HEAD_TEXT,不出「…这道题:。」残句)。"""
    text = str(transcription or "").strip()
    cut = min((text.index(ch) for ch in _BRIEF_CUTS if ch in text), default=len(text))
    brief = text[:cut].strip()
    if len(brief) < _BRIEF_MIN_CHARS:
        return ""
    if len(brief) > _BRIEF_MAX_CHARS:
        return brief[:_BRIEF_MAX_CHARS] + _BRIEF_ELLIPSIS
    return brief


def _text_collect_tail(question: dict | None) -> str:
    """纯文字档采集句:真·文字题按题型分流;图像题读不出内容而退回文字档 → 非选择题句
    (题型分流只服务文字题,图像档另有统一那句)。"""
    if (question or {}).get("image") is not None:
        return TAIL_COLLECT_OPEN
    return TAIL_COLLECT_CHOICE if _is_multiple_choice(question) else TAIL_COLLECT_OPEN


def _has_image(question: dict | None) -> bool:
    """是否**真·带图**:判据只看 `question["image"]`。

    实测教训(部署抓到,#182):**绝不能拿「transcription 非空」当"这题带图"的判据**——
    纯文字题下模型也会把 transcription 填上一句废话,于是文字题错用了图像档 head
    (线上题 6a61a8da:「你好同学,我看到你发的题啦,我们一起看看:你先别急。…」)。"""
    return (question or {}).get("image") is not None


def _brief_source(question: dict | None, transcription: str | None) -> str:
    """半句来源:**题面文本优先**(权威),仅当题面为空(真·纯图题)才退回转录。

    与 `_has_image` 同一教训:转录可能是一句与题目无关的废话,只有当题面本身没有内容
    (纯图题)时才不得不采信它。"""
    text = str((question or {}).get("text") or "").strip()
    return text or str(transcription or "")


def first_question_text(answer_status: str | None, transcription: str | None = None,
                        question: dict | None = None) -> str:
    """首问固定模板(head + tail 组装):显式做对 → 正确档(文字/图像共用同一句);其余
    (incorrect/unanswered/缺省/unknown)→ 采集档。口径依据 docs/plan/00-rewrite-plan.md:
    「false/null/省略→incorrect(unanswered 默认按做错,等价老系统 assumed_incorrect)」。
    head **只在真·带图且读出半句**时用图像招呼语(见 `_has_image` / `_brief_source`);
    采集档 tail 按题型/图像分流(见 `_is_multiple_choice` 与 `_text_collect_tail`)。
    为什么固定:同一段策略此前作为 prompt 提示被模型违抗过——实测首问直接报出答案数字。"""
    source = question or {}
    brief = _brief_transcription(_brief_source(source, transcription)) if _has_image(source) else ""
    if brief:
        tail = TAIL_CORRECT if answer_status == "correct" else TAIL_COLLECT_IMAGE
        # 半句复述后先识题确认(#180 ③):读错题学生第 0 轮即可纠正;brief 空已走文字档,不插。
        return f"{HEAD_IMAGE_PREFIX}{brief},{IMAGE_BRIEF_CONFIRM}{tail}"
    tail = TAIL_CORRECT if answer_status == "correct" else _text_collect_tail(source)
    return HEAD_TEXT + tail


def opening_hint(answer_status: str | None) -> str:
    """learner.answer_status → 首问策略提示;unknown/缺省返回空串(不加提示)。"""
    return _OPENING_HINTS.get(answer_status or "", "")


def diagnose_turn_hint(answer_status: str | None, reply_index: int) -> str:
    """incorrect 弧线第②步提示:**仅**「首问后的第一次回应」(reply_index=0)返回非空。

    实测依据(#165 WS4 第 5 条,F 口径「采集不评判」4/20 → 8/20):判词显示②「追问他
    怎么想的」被跳过(采集后直接判定/纠正)。只覆盖那一轮是**两版对照后的选择**:
    扩到②+③ 反而 4/20(判定后移 + 复讲引导接走两例)。非 incorrect 状态一律空串。
    """
    if answer_status == "incorrect" and reply_index == 0:
        return _DIAGNOSE_TURN_HINT
    return ""


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
