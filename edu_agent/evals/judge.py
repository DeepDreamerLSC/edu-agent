"""judge 评分器(#32 人审定稿,00 §8.2 阶段 3):六维教学 schema 组 prompt,经 gateway 调用。

维度与分值结构照 #32 定稿原文实现,不发明维度;verdict 阈值(泄露一票否决、
pass ≥10 无 0 分、review 7-9 或有 0 分维度、fail <7)在本地重算——模型输出同样
带 verdict 字段(schema 要求),但阈值算术不托付给模型。
结构化输出走路线 1(gateway response_schema:schema 进 prompt + 本地校验 +
schema_violation 一次修复重试)。披露义务(#32):凡含 judge 分数的报告必须标注
judge 模型与版本——judge_model 字段随每次评分结果落盘。
"""

from __future__ import annotations

import json

from edu_agent.gateway import FailureType, Gateway, GatewayError, ModelRequest

from .runner import EnvironmentFailure

# judge 输出 JSON Schema(#32 定稿原文,一字不改;路线 1:附 prompt,本地校验)。
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
        "evidence": {
            "type": "object",
            "properties": {
                "first_question": {"type": "string"},
                "socratic_followup": {"type": "string"},
                "grade_fit": {"type": "string"},
                "pacing": {"type": "string"},
                "summary_mastery": {"type": "string"},
                "termination": {"type": "string"},
            },
            "required": [
                "first_question", "socratic_followup", "grade_fit",
                "pacing", "summary_mastery", "termination",
            ],
        },
        "verdict": {"enum": ["pass", "review", "fail"]},
    },
    "required": [
        "first_question", "socratic_followup", "grade_fit", "pacing",
        "summary_mastery", "termination", "answer_leaked", "evidence", "verdict",
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

# 六维度完整定义(#32 定稿),嵌 system 消息。
DIMENSION_GUIDE = """\
【六维度定义与打分标准(每维 0/1/2 三档)】

1. 首问质量与答案泄露(first_question):学生提出问题后,小讲师的第一轮讲解是否切题、是否直接给出完整答案。
   2=切题引入,用问题/铺垫引导思路,未泄露终答;讲解结构清晰(先确认题意/给关键概念)
   1=切题但讲解含糊或直接给关键步骤,泄露了大部分推理(学生不需自己思考即可得答案)
   0=直接给出完整终答(数值/结论)答非所问,或第一轮就自问自答完成教学
   一票否决:泄露完整终答 → 该维度 0 且 verdict=fail。

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

5. 总结与掌握判断(summary_mastery):结束时是否把方法讲清楚,并基于学生表现判断掌握程度,而非空泛鼓励。
   2=总结点出方法与学生的关键转折,给出有依据的掌握判断
   1=有总结但泛化(「你真棒,继续保持」),判断无依据
   0=无总结直接结束,或判断与学生实际表现矛盾

6. 终止行为(termination):何时结束对话——学生未掌握就终止、掌握后拖堂,都算失败。
   2=学生给出正确终答(或明确表示懂了)后自然收尾;多次失败后按策略升级提示再收尾
   1=终止时学生状态未明(既未答对也未确认)但提前结束
   0=学生已答对仍强行继续,或第一轮失败即终止

【verdict 阈值】泄露终答一票否决=fail;总分 ≥10 且无 0 分维度=pass;
总分 7-9 或有 0 分维度=review;总分 <7=fail。"""

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
        "逐维度按 0/1/2 打分(标准见六维度定义),每个维度在 evidence 里引用一句对话原文作依据。",
        "answer_leaked:小讲师是否在任何一轮给出了完整终答(数值或结论性答案)。",
        "verdict 按阈值规则给出。",
        "只输出一个符合 Schema 的 JSON 对象,不要围栏、不要解释。",
    ]
    return "\n".join(lines)


def verdict_from_scores(scores: dict[str, int], answer_leaked: bool) -> str:
    """#32 定稿阈值,本地重算(模型同字段仅作输出要求,算术不托付给它)。"""
    if answer_leaked:
        return "fail"  # 一票否决
    total = sum(scores[dim] for dim in DIMENSIONS)
    zeros = [dim for dim in DIMENSIONS if scores[dim] == 0]
    if total >= 10 and not zeros:
        return "pass"
    if total < 7:
        return "fail"
    return "review"


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
        max_tokens=600,
        temperature=0,
    )
    response = gateway.invoke(request)
    payload = json.loads(response.text)
    scores = {dim: payload[dim] for dim in DIMENSIONS}
    return {
        "scores": scores,
        "total": sum(scores.values()),
        "answer_leaked": bool(payload["answer_leaked"]),
        "evidence": payload["evidence"],
        "verdict": verdict_from_scores(scores, bool(payload["answer_leaked"])),
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
