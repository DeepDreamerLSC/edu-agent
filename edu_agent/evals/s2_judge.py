"""S2 专项 Judge 引擎(#459 件二,宿主 B):独立 LLM pass,annotation-only,不耦合 verdict。

判据文本 = 冻结件 docs/evals/s2-judge-rubric-v0.1.md §2(冻结 sha256(v0.1)
`e381c331…`,head -n -1 口径);本模块只剩引擎:读资产 → 构造 ModelRequest → 落
judge_model 披露。小讲师 judge v3.2 / judge.py 一字不动(镜像其形态,不 import)。

V1–V5 全部下沉 S2_SCHEMA(gateway 路线 1:schema 进 prompt + 本地校验 + 一次修复
重试);invoke() 返回后零残余模型调用。P0-5:unsure 的两合法分支(marker 或
rationale 含 U-0)为冻结「或」语义,不得收成单支。P1-2:expected 永不进本模块
——s2_user_prompt 只接 messages。
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from edu_agent.gateway import ENV_FAILURES, Gateway, GatewayError, ModelRequest

from .runner import EnvironmentFailure

# 每轴输出契约(件一 §3 + P0-5 修订)。allOf 两条 if/then:
# V2 verdict=yes → supporting_turns 非空;V1 verdict=unsure → anyOf 两合法分支
# (boundary_markers 非空,或 rationale 含 U-0——冻结 rubric §3「或」语义)。
# V4 轮号格式 / V3 rationale 结构完整(minLength;不声称验证「回指原文」,
# 回指原文不可机器判定,属 GC 归因审查域)。
_AXIS_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"enum": ["yes", "no", "unsure"]},
        "supporting_turns": {
            "type": "array",
            "items": {"type": "string", "pattern": "^t[0-9]+$"},
        },
        "evidence_tags": {"type": "array", "items": {"type": "string"}},
        "boundary_markers": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string", "minLength": 1},
    },
    "required": [
        "verdict", "supporting_turns", "evidence_tags",
        "boundary_markers", "rationale",
    ],
    "allOf": [
        {
            "if": {"properties": {"verdict": {"const": "yes"}}},
            "then": {"properties": {"supporting_turns": {"minItems": 1}}},
        },
        {
            "if": {"properties": {"verdict": {"const": "unsure"}}},
            "then": {"anyOf": [
                {"properties": {"boundary_markers": {"minItems": 1}}},
                {"properties": {"rationale": {"pattern": "U-0"}}},
            ]},
        },
    ],
}

# V5 两轴恒在(X-1 双走;缺轴即 schema violation)
S2_SCHEMA = {
    "type": "object",
    "properties": {"s2a": _AXIS_SCHEMA, "s2b": _AXIS_SCHEMA},
    "required": ["s2a", "s2b"],
}

# prompt 资产 = 版本化资产(件二方案 §1):从冻结件 §2 提取;提取等价门在
# tests/evals/test_s2_judge.py(资产 system_prompt 与冻结件 §2 块逐字节相等)。
_RUBRIC_PATH = Path(__file__).parent / "rubrics" / "s2_judge_v0_1.yaml"
_RUBRIC = yaml.safe_load(_RUBRIC_PATH.read_text(encoding="utf-8"))

SYSTEM_PROMPT = _RUBRIC["system_prompt"]

_SPEAKER = {"user": "学生", "assistant": "小讲师"}

_USER_INSTRUCTIONS = [
    "【输出要求】两轴独立、并发双走、unsure 统一纪律(见系统指令)。",
    "只输出一个符合 Schema 的 JSON 对象,不要围栏、不要解释。",
]


def s2_user_prompt(messages: list[dict]) -> str:
    """user prompt 渲染(件一 §3 骨架):逐轮「学生(t1):…/小讲师(t1):…」。

    只接 messages(P1-2 泄露防火墙):expected 永不进本函数;轮号用消息自带
    turn 标签逐字保留(案卷存在共享编号与顺序编号两种约定,不可推导)。
    """
    lines = ["【对话记录】"]
    for message in messages:
        lines.append(f"{_SPEAKER[message['role']]}({message['turn']}):{message['content']}")
    lines += ["", *_USER_INSTRUCTIONS]
    return "\n".join(lines)


def _strip_code_fence(text: str) -> str:
    """剥 Markdown 代码围栏(与 gateway 路线 1 校验同款语义,幂等)。"""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    return stripped.strip()


def s2_judge_transcript(gateway: Gateway, case: dict, role: str = "judge",
                        session_id: str | None = None) -> dict:
    """评一条教学对话的 S2a/S2b 两轴标注(annotation-only;不参与任何 verdict 算术)。

    case 只消费 messages(P1-2);expected 在 battery 案对象上存在但从不进模型边界。
    """
    request = ModelRequest(
        role=role,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": s2_user_prompt(case["messages"])},
        ],
        response_schema=S2_SCHEMA,
        session_id=session_id or f"s2-judge-{case.get('case_id', case.get('id', '?'))}",
        # 16384:M1 control 容量适配(#459)——deepseek-flash 为思考型输出且思考长度
        # 方差大(同案实测 2518–7175),4000 截断 11/24;16384=最坏观测 2.2 倍余量。
        # mlx 输出 <1200 不受影响;判定/schema/prompt/identity 零改动,纯容量。
        max_tokens=16384,
        temperature=0,
    )
    response = gateway.invoke(request)
    # 路线 1 已校验并剥壳(response.text 为归一化后内容);同款剥壳幂等防御
    payload = json.loads(_strip_code_fence(response.text))
    return {
        "s2a": payload["s2a"],
        "s2b": payload["s2b"],
        "judge_model": response.model,  # 披露义务(#32):标注与模型绑定落盘
    }


class S2JudgeSubject:
    """runner 的被测对象形态(镜像 JudgeSubject):S2 标注作为可断点续跑的批任务。"""

    def __init__(self, gateway: Gateway, role: str = "judge", name: str | None = None) -> None:
        self.gateway = gateway
        self.role = role
        self.name = name or "s2-judge"

    def run_case(self, case: dict) -> dict:
        try:
            return s2_judge_transcript(self.gateway, case, role=self.role)
        except GatewayError as error:
            if error.failure in ENV_FAILURES:
                raise EnvironmentFailure(str(error)) from error
            raise  # schema_violation/truncated 等:内容失败,重跑改变不了
