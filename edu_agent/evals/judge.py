"""judge 评分器(#32 人审定稿 + #253 rubric v2):六维教学 schema 组 prompt,经 gateway 调用。

维度与分值结构照 #32 定稿原文实现,不发明维度;#253 后 verdict 本地重算含:
泄露一票否决(fail)、math_integrity 硬门(0=fail、1=封顶 review)、六维阈值
(pass ≥10 无 0 分、review 7-9 或有 0 分维度、fail <7)。math_integrity 为独立
字段,不计入六维总分 /12(DIMENSIONS 元组不变)。模型输出同样带 verdict 字段
(schema 要求),但阈值算术不托付给模型。
结构化输出走路线 1(gateway response_schema:schema 进 prompt + 本地校验 +
schema_violation 一次修复重试)。披露义务(#32):凡含 judge 分数的报告必须标注
judge 模型与版本——judge_model 字段随每次评分结果落盘。
"""

from __future__ import annotations

import json

from edu_agent.gateway import FailureType, Gateway, GatewayError, ModelRequest

from .runner import EnvironmentFailure

# judge 输出 JSON Schema(#32 定稿 + #253 rubric v2;路线 1:附 prompt,本地校验)。
SCHEMA = {
    "type": "object",
    "properties": {
        "first_question": {"type": "integer", "minimum": 0, "maximum": 2},
        "socratic_followup": {"type": "integer", "minimum": 0, "maximum": 2},
        "grade_fit": {"type": "integer", "minimum": 0, "maximum": 2},
        "pacing": {"type": "integer", "minimum": 0, "maximum": 2},
        "summary_mastery": {"type": "integer", "minimum": 0, "maximum": 2},
        "termination": {"type": "integer", "minimum": 0, "maximum": 2},
        "answer_leaked": {"type": "boolean"},
        # #253 P3:数学正确性硬门,独立字段不计入六维总分(fail-closed,无默认值)
        "math_integrity": {"enum": [0, 1, 2]},
        "evidence": {
            "type": "object",
            "properties": {
                "first_question": {"type": "string"},
                "socratic_followup": {"type": "string"},
                "grade_fit": {"type": "string"},
                "pacing": {"type": "string"},
                "summary_mastery": {"type": "string"},
                "termination": {"type": "string"},
                # 引用对应学生/导师轮次原文,并说明为何属于 0/1/2
                "math_integrity": {"type": "string"},
                # #253 v3:引首泄句原文(未泄露则引学生先给终答原句),幻影否决可诊断
                "answer_leaked": {"type": "string"},
            },
            "required": [
                "first_question", "socratic_followup", "grade_fit",
                "pacing", "summary_mastery", "termination", "math_integrity",
                "answer_leaked",
            ],
        },
        "verdict": {"enum": ["pass", "review", "fail"]},
    },
    "required": [
        "first_question", "socratic_followup", "grade_fit", "pacing",
        "summary_mastery", "termination", "answer_leaked", "math_integrity",
        "evidence", "verdict",
    ],
}

DIMENSIONS = (
    "first_question",
    "socratic_followup",
    "grade_fit",
    "pacing",
    "summary_mastery",
    "termination",
)

# 六维度完整定义(#32 定稿;#253 rubric v2:P1 一票否决条款/第 5 维/独立硬门段/verdict 段
# 四块判据文本逐字采自人批草案),嵌 system 消息。
DIMENSION_GUIDE = """\
【六维度定义与打分标准(每维 0/1/2 三档)】

1. 首问质量与答案泄露(first_question):学生提出问题后,小讲师的第一轮讲解是否切题、是否直接给出完整答案。
   2=切题引入,用问题/铺垫引导思路,未泄露终答;讲解结构清晰(先确认题意/给关键概念)
   1=切题但讲解含糊或直接给关键步骤,泄露了大部分推理(学生不需自己思考即可得答案)
   0=直接给出完整终答(数值/结论)答非所问,或第一轮就自问自答完成教学
   **一票否决:终答泄露。** 在学生尚未主动给出**该终答或与该终答等价的答案**之前,小讲师主动给出了完整终答(数值或结论)→ `answer_leaked=true`,`verdict=fail`。
   学生已经主动给出该终答或等价终答——包括以疑问形式提出候选答案——以后,小讲师对**该同一答案**进行确认、纠正说明、复述或在总结中引用,不属于终答泄露;其处理是否正确、是否过度、是否符合教学节奏,仍分别按 `math_integrity`、引导追问、节奏等判据评价。
   **学生只提出了错误候选答案,并不会因此获得正确终答的豁免**:若正确终答此前尚未由学生给出,小讲师随后直接给出该正确终答,仍按终答泄露评价。
   仅当输入中存在明确的"授权披露"事实时,设计内允许的终答披露才不按非法泄露处理;Judge 不得自行猜测某次披露是否属于 kernel 的 bottom-out。

2. 追问的苏格拉底性(socratic_followup):学生答错/卡住后,追问是否以引导性问题推进,而非重复讲解或直接纠正。
   2=追问指向学生的具体错误点,逐步缩小范围,给学生思考空间
   1=有追问但泛化(如「再想想」)或急于给提示,引导链断裂
   0=直接给答案/重复原话/无关追问

3. 年级表达适配(grade_fit):语言、术语、例子是否匹配学生年级。
   2=词汇与句式符合该年级课标,术语先解释后使用,例子贴近生活
   1=个别超纲术语未解释,或表达偏幼稚
   0=明显超纲(如给六年级用方程组)或表达混乱

4. 追问节奏(pacing):单轮信息量与轮次推进是否适度,不灌输出不拖沓。
   2=每轮一个明确目标,信息量适中;学生答对即推进,答错即换角度
   1=偶发长篇大论或原地打转(连续 2 轮同一提示)
   0=一次性倾倒全部讲解,或 3 轮以上无实质推进

5. 总结与掌握判断(summary_mastery):
   `2` = 有实质方法总结,并明确指向**学生本人的**关键学习证据或转折,同时给出与该证据一致、有根据的掌握判断。
   `1` = 存在部分实质总结,但缺学生本人的关键学习证据,或掌握判断缺乏依据;仅有"你真棒、继续保持"等泛化鼓励也属于此档。
   `0` = 没有实质总结直接结束,或掌握判断明显与学生实际表现矛盾。
   **注:**总结中复述学生已经给出的答案不因复述本身扣分,也不属于终答泄露;"注意事项"等补充内容可以作为额外证据,但不能替代对学生实际学习证据和掌握状态的判断。
   summary_mastery 评 2 时,须在 evidence 中引用学生本人实际说出或做出该关键内容的那一轮原文;若总结声称的学生理解在对话中找不到学生本人的对应轮次(该内容实为小讲师所给,或学生从未实际说出/做出),该声称不得作为学生本人关键学习证据,该维度最高评 1。

6. 终止行为(termination):何时结束对话——学生未掌握就终止、掌握后拖堂,都算失败。
   2=学生给出正确终答(或明确表示懂了)后自然收尾;多次失败后按策略升级提示再收尾
   1=终止时学生状态未明(既未答对也未确认)但提前结束
   0=学生已答对仍强行继续,或第一轮失败即终止

**【数学正确性把关(`math_integrity`,独立字段,不计入六维总分)】**评价小讲师是否正确处理学生的关键数学结论与关键推理,并且自身没有引入会改变解题结论或方法的实质性错误数学事实。

`2` = 能正确区分最终结论与关键推理:学生结论与推理正确时正确确认;学生结论错误时识别错误并合理引导检查;学生结论正确但推理有误时**保留正确结论,同时指出推理问题**;小讲师自身未引入实质性错误数学事实。

`1` = 漏过学生一个影响解题的数学错误,但未明确正向强化该错误,也未主动教授错误结论、错误规则或错误方法。

`0` = 出现任一严重数学把关失败:明确肯定了错误的关键数学结论或错误方法;否定了正确结论并教授错误内容;小讲师自身引入了会改变解题结论或方法的实质性错误数学事实。

**边界说明:**对一个包含错误的完整方法表述给予整体性肯定,应判 `0`;若小讲师明确只肯定其中一个局部正确片段,同时明确指出其余部分仍需检查或修正,不因该局部肯定本身判 `0`。
豁免只适用于陈述本身为真、仅措辞不够精确的情况。小讲师陈述的数学事实本身为假(数值、转换、公式、规则任一错误,如声称八分之一等于十二分之一、或称等式两边同除非零数会破坏平衡)时,无论后续对话是否跟进该陈述、无论最终答案是否碰巧正确,均属『引入错误数学事实』,判 0。

**0 分**:学生把坐标两个分量互换,小讲师仍称"这一步很准";学生最终结论 `2/3 × 6 = 4` 正确、但中间推理有误,小讲师没有保留正确结论,反而总结称"结果才是 2,而不是 4";学生把圆面积错误表述为"半径 × 3.14",小讲师复述该完整方法并称"这个想法很对";小讲师自身编造了错误的分母运算、错误公式或其他会改变解题结果/方法的数学事实;小讲师把学生原话转述成实质内容不同的说法并据此推进(如学生说『占两份,再加一份,共三份』,导师转述为『你刚才说三份加一份』)——转述后的陈述在数学上错误或与学生实际所说不符,属引入错误数学事实。
**2 分**:学生答错,小讲师指出错误并引导其自行检查;学生答案正确但推理错误,小讲师保留正确答案,同时纠正推理;学生某个局部步骤正确,小讲师只确认该局部正确点,并明确继续检查其余部分。

【verdict 阈值】
终答泄露一票否决:`answer_leaked=true` → `fail`。
数学正确性硬门:`math_integrity=0` → `fail`;`math_integrity=1` 时,最终 `verdict` 至多为 `review`。
六维总分规则保持不变:总分 `>=10` 且六维中无 `0` 分 → `pass`;总分 `7-9` 或六维中存在 `0` 分 → `review`;总分 `<7` → `fail`。
`math_integrity` 不计入六维总分 `/12`。"""

SYSTEM_PROMPT = (
    "你是小学数学教学的评审,评估一段「小讲师」AI 与学生的对话。只依据给出的对话评分,"
    "不臆测对话之外的信息;拿不准的维度给低档并说明理由。\n\n" + DIMENSION_GUIDE
)


def user_prompt(question: str, grade: str, reference_answer: str, transcript: list[dict]) -> str:
    """#32 prompt 骨架:题目/年级/参考答案(仅判泄露)/对话记录 + 输出要求。"""
    lines = [
        f"【题目】{question}(年级:{grade})",
        f"【参考答案】{reference_answer} —— 仅用于判断是否泄露,不是评分标准",
        "【对话记录】",
    ]
    speaker = {"user": "学生", "assistant": "小讲师"}
    lines += [f"{speaker.get(m.get('role'), m.get('role'))}:{m.get('content', '')}" for m in transcript]
    lines += [
        "",
        "逐维度按 0/1/2 打分(标准见六维度定义)。evidence 引用关键原文作依据,可多句:summary_mastery 须覆盖总结中实际存在的各部分(方法/学生本人证据/掌握判断);math_integrity 须先逐条列出小讲师陈述的具体数学事实(数值、转换、公式)并标注对错——包括对话中未被跟进的陈述——再按判据定档;answer_leaked 引首次给出终答的原句,未泄露则引学生先给终答的原句。",
        "`answer_leaked`:判断小讲师是否在学生尚未主动给出**该终答或等价终答**之前,主动给出了完整终答(数值或结论性答案)。学生已先给出该同一终答(含疑问形式候选答案)后,小讲师的确认、纠正说明、复述或总结引用不算终答泄露。若学生先给出的只是错误候选答案,小讲师随后首次给出正确终答,仍应判定是否构成终答泄露。除非输入中明确提供授权披露事实,否则不要自行假定某次终答披露属于合法 bottom-out。",
        "verdict 按阈值规则给出。",
        "只输出一个符合 Schema 的 JSON 对象,不要围栏、不要解释。",
    ]
    return "\n".join(lines)


def _strip_code_fence(text: str) -> str:
    """剥 Markdown 代码围栏(gateway 路线 1 校验同款语义):包装噪声不算结构违规。"""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    return stripped.strip()


def verdict_from_scores(scores: dict[str, int], answer_leaked: bool, math_integrity: int) -> str:
    """#32 六维阈值 + #253 rubric v2 硬门,本地重算(算术不托付给模型)。

    math_integrity 无默认值(fail-closed):漏传直接 TypeError,禁止静默当 2。"""
    if answer_leaked or math_integrity == 0:
        return "fail"  # 一票否决 + 数学正确性硬门
    total = sum(scores[dim] for dim in DIMENSIONS)
    zeros = [dim for dim in DIMENSIONS if scores[dim] == 0]
    if total >= 10 and not zeros:
        verdict = "pass"
    elif total < 7:
        verdict = "fail"
    else:
        verdict = "review"
    if math_integrity == 1 and verdict == "pass":
        return "review"  # 1 分封顶 review
    return verdict


def judge_transcript(
    gateway: Gateway,
    case: dict,
    role: str = "judge",
    session_id: str | None = None,
) -> dict:
    """评一条教学对话,返回含六维分数、泄露标志、证据、verdict 与 judge 模型披露。"""
    transcript = case["messages"]
    request = ModelRequest(
        role=role,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt(
                case["question"], case.get("grade", ""), case.get("reference_answer", ""), transcript,
            )},
        ],
        response_schema=SCHEMA,
        session_id=session_id or f"judge-{case.get('id', '?')}",
        max_tokens=900,
        temperature=0,
    )
    response = gateway.invoke(request)
    # ModelResponse.text 保留模型原文(实测 DeepSeek 恒带 ```json 围栏);
    # 与 gateway 校验同款剥壳,解析的是同一份被路线 1 判合法的内容
    payload = json.loads(_strip_code_fence(response.text))
    scores = {dim: payload[dim] for dim in DIMENSIONS}
    # #253 P3:显式解析(fail-closed,缺失/非数值直接炸,不静默补 2)
    math_integrity = int(payload["math_integrity"])
    return {
        "scores": scores,
        "total": sum(scores.values()),
        "answer_leaked": bool(payload["answer_leaked"]),
        "math_integrity": math_integrity,
        "evidence": payload["evidence"],
        "verdict": verdict_from_scores(scores, bool(payload["answer_leaked"]), math_integrity),
        "judge_model": response.model,  # 披露义务(#32):分数与模型绑定落盘
    }


# 环境类失败(可补跑)与内容类失败(不补跑)的分界,映射自 01 §4 重试资格。
ENV_FAILURES = frozenset({
    FailureType.CONNECTION,
    FailureType.TIMEOUT_FIRST_TOKEN,
    FailureType.TIMEOUT_TOTAL,
    FailureType.RATE_LIMITED,
    FailureType.UPSTREAM_5XX,
})


class JudgeSubject:
    """runner 的被测对象形态:judge 评分作为一个可过夜、可断点续跑的批任务。"""

    def __init__(self, gateway: Gateway, role: str = "judge", name: str | None = None) -> None:
        self.gateway = gateway
        self.role = role
        self.name = name or f"judge-{role}"

    def run_case(self, case: dict) -> dict:
        try:
            return judge_transcript(self.gateway, case, role=self.role)
        except GatewayError as error:
            if error.failure in ENV_FAILURES:
                raise EnvironmentFailure(str(error)) from error
            raise  # schema_violation/truncated 等:内容失败,重跑改变不了


def sample_independent(case_ids: list[str]) -> list[str]:
    """#32 独立性保险抽样:排序后每 10 条取 1 条(确定性,约 10%)。"""
    return sorted(case_ids)[::10]


def _ok(payloads: list[dict]) -> dict[str, dict]:
    """case_id → 该 case 的 judge 评分载荷,只取 ok 行。"""
    return {row["case_id"]: row["transcript"] for row in payloads if row["status"] == "ok"}


def stability_report(primary: list[dict], repeat: list[dict], independent: list[dict]) -> dict:
    """双评一致性 + 独立性保险的分差档案(#32 必做项)。

    primary/repeat = 同批 case 主选 judge 评两次;independent = 抽样 case 的
    DeepSeek 平行评分。报告只描述分差,不设偏向阈值——系统性偏向的判定与切换
    (judge.primary 换 deepseek_chat)留人批,#32 明确不自行切回。
    """
    p, r, i = _ok(primary), _ok(repeat), _ok(independent)
    paired = sorted(set(p) & set(r))
    diffs = [abs(p[c]["total"] - r[c]["total"]) for c in paired]
    sampled = sorted(set(p) & set(i))
    signed = [p[c]["total"] - i[c]["total"] for c in sampled]
    return {
        "double": {
            "cases": len(paired),
            "max_abs_total_diff": max(diffs, default=0),
            "mean_abs_total_diff": round(sum(diffs) / len(diffs), 2) if diffs else None,
            "verdict_flips": sum(1 for c in paired if p[c]["verdict"] != r[c]["verdict"]),
            "dim_disagreements": {
                dim: sum(1 for c in paired if p[c]["scores"][dim] != r[c]["scores"][dim])
                for dim in DIMENSIONS
            },
        },
        "independent": {
            "sampled": len(sampled),
            "ids": sampled,
            "signed_total_diffs": {c: p[c]["total"] - i[c]["total"] for c in sampled},
            "mean_signed_diff": round(sum(signed) / len(signed), 2) if signed else None,
            "same_direction": bool(signed) and (all(d > 0 for d in signed) or all(d < 0 for d in signed)),
        },
    }


def stability_markdown(report: dict, judge_model: str | None) -> str:
    double, indep = report["double"], report["independent"]
    lines = [
        "# judge 稳定性档案(#32 双评一致性 + 10% 独立性保险)",
        "",
        f"- judge 模型(披露义务): {judge_model or '未知'}",
        f"- 双评: {double['cases']} case,总分最大分差 {double['max_abs_total_diff']},"
        f"平均 {double['mean_abs_total_diff']},verdict 翻转 {double['verdict_flips']} 例",
        f"- 维度分歧计数: {json.dumps(double['dim_disagreements'], ensure_ascii=False)}",
        f"- 独立评分(DeepSeek): 抽样 {indep['sampled']} case,"
        f"带符号平均分差(主选−独立) {indep['mean_signed_diff']},"
        f"全部同向 {indep['same_direction']}",
        "",
        "系统性偏向的判定与切回(judge.primary→deepseek_chat)留人批,不自行切回(#32)。",
    ]
    return "\n".join(lines) + "\n"


def any_judge_model(payloads: list[dict]) -> str | None:
    for row in payloads:
        if row["status"] == "ok":
            return row["transcript"].get("judge_model")
    return None
