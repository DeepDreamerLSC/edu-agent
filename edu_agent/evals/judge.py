"""judge 评分引擎(#32 人审定稿 + #253 rubric v3.2):判据文本 = 版本化资产,本模块只剩引擎。

#254 P2:判据文本(dimension/math integrity/verdict/user instructions)迁出为
rubrics/small_lecturer_v3_2.yaml(渲染等价门:加载资产渲染的 prompt 与迁移前逐字节相等);
ENV_FAILURES 迁至 gateway.errors。引擎职责:读 rubric → 构造 ModelRequest → 校验 schema
→ 重算 verdict → 落 artifact。

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
from pathlib import Path

import yaml

from edu_agent.gateway import ENV_FAILURES, Gateway, GatewayError, ModelRequest

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

# 判据文本 = 版本化资产(#254 P2 自内联迁出):version/preamble/dimension_guide/
# math_integrity_guide/verdict_policy/user_instructions 六键;文件名即版本,无注册表面。
_RUBRIC_PATH = Path(__file__).parent / "rubrics" / "small_lecturer_v3_2.yaml"
_RUBRIC = yaml.safe_load(_RUBRIC_PATH.read_text(encoding="utf-8"))

DIMENSION_GUIDE = "\n\n".join(
    _RUBRIC[key] for key in ("dimension_guide", "math_integrity_guide", "verdict_policy"))

SYSTEM_PROMPT = _RUBRIC["preamble"] + "\n\n" + DIMENSION_GUIDE

_USER_INSTRUCTIONS = _RUBRIC["user_instructions"].split("\n")


def user_prompt(question: str, grade: str, reference_answer: str, transcript: list[dict]) -> str:
    """#32 prompt 骨架:题目/年级/参考答案(仅判泄露)/对话记录 + 输出要求。"""
    lines = [
        f"【题目】{question}(年级:{grade})",
        f"【参考答案】{reference_answer} —— 仅用于判断是否泄露,不是评分标准",
        "【对话记录】",
    ]
    speaker = {"user": "学生", "assistant": "小讲师"}
    lines += [f"{speaker.get(m.get('role'), m.get('role'))}:{m.get('content', '')}" for m in transcript]
    lines += ["", *_USER_INSTRUCTIONS]
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
