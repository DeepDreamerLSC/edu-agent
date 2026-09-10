#!/usr/bin/env python3
"""#101 双臂评测盲判:四指标 schema,judge 单遍(temperature=0,mlx_27b,同夜评口径)。

用法:.venv/bin/python scripts/arc_eval_judge.py --out <共享 artifacts 目录>

盲判纪律(p8):
  · 送进模型的 system/user 内容**不含**臂标签、分支名、commit、工作树路径;
    case id 用 base_id 的 sha256 前 12 位,重复序号保留(便于配对,不含臂信息)。
  · 臂只出现在输出路径 …/<caliber>/<arm>/judge-scores/ 上。
  · 每份 transcript 独立调用,不把两臂并列给模型比较。
规格与 schema 原文见 docs/evals/teaching-arc-eval-v1.md §5。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
from edu_agent.gateway import Gateway, ModelRequest, load_registry  # noqa: E402

# response_schema 原文(pre-registration §5,一字不改)
SCHEMA = {
    "type": "object",
    "properties": {
        "first_question": {
            "type": "object",
            "properties": {"applicable": {"type": "boolean"}, "compliant": {"type": "boolean"},
                           "evidence": {"type": "string"}},
            "required": ["applicable", "compliant", "evidence"],
        },
        "collect_not_judge": {
            "type": "object",
            "properties": {"applicable": {"type": "boolean"}, "compliant": {"type": "boolean"},
                           "evidence": {"type": "string"}},
            "required": ["applicable", "compliant", "evidence"],
        },
        "restate": {
            "type": "object",
            "properties": {"asked": {"type": "boolean"}, "delivered": {"type": "boolean"},
                           "evidence": {"type": "string"}},
            "required": ["asked", "delivered", "evidence"],
        },
        "feeding": {
            "type": "object",
            "properties": {"fed": {"type": "boolean"},
                           "quotes": {"type": "array", "items": {"type": "string"}},
                           "evidence": {"type": "string"}},
            "required": ["fed", "quotes", "evidence"],
        },
    },
    "required": ["first_question", "collect_not_judge", "restate", "feeding"],
}

SYSTEM_PROMPT = """\
你是小学数学教学对话评审。你会看到一段「小讲师(教师)」与「学生」的对话和题目信息。
只按下面四条规则判定,不评价其他方面,不推测这段对话来自哪个系统或版本。

【对话形态】messages 里 user=学生、assistant=教师;若第一条是 assistant,那条就是「首问」
(学生还没开口);末尾可能有一条 assistant,是「总结」。

【规则1 首问合规 first_question】只看「首问」那一条 assistant 消息。
 · 学生作答状态=correct(本题已做对):compliant=true 当且仅当 首问**只问**学生「还有没有不懂的地方」,
   且不出现复讲指令(「讲一遍」「复述」「说说你的思路」「你是怎么想的」等),
   且不重新讲解本题、不评判对错。
 · 学生作答状态=incorrect(本题未做对):compliant=true 当且仅当 首问 = 一句友好开场 +
   采集学生当前的作答(选择题问他选了哪个选项;计算/解答题问他算出的答案是什么),
   且不出现对错评判、不直接纠正、不给出答案。
 · 学生作答状态=unknown:applicable=false(无法判定)。

【规则2 采集不评判 collect_not_judge】仅当 学生作答状态=incorrect 时 applicable=true,否则 false。
 compliant=true 当且仅当 教师确实采集到了学生的作答(问出选项/答案),且在该轮及紧随的回应中
 未对该作答作任何对错判定或纠正(无「对/错/不对/正确/错误/其实/应该」类判定)。

【规则3 复讲 restate】asked=教师是否在任一轮明确请学生复讲或讲解题思路;
 delivered=在该请求之后,学生确实讲出了自己的解题过程。只看这两件事是否发生。

【规则4 方法名代喂 feeding】fed=true 当且仅当 教师的任一轮或总结中出现:
 (a) 任何方法名(「假设法」「方程法」「代入法」「消元法」「画图法」「列表法」「枚举法」
     「比例法」「转化法」「数形结合」「移项」「通分」「约分」「公式法」);或
 (b) 本题参考答案的数值,而学生尚未说出这个数。
 quotes 逐字抄录命中的原句(可多条);未命中 fed=false、quotes=[]。
 例外:学生自己已经讲出方法之后,教师点名方法予以肯定,不算代喂;
 代喂指学生还没讲出方法或答案时,教师先说了。

每条给一句 evidence(引用原句片段),不要空泛。只输出 JSON。"""


def anonymized_id(base_id: str, repeat: int) -> str:
    digest = hashlib.sha256(base_id.encode("utf-8")).hexdigest()[:12]
    return f"c{digest}r{repeat}"


def to_judge_case(row: dict, meta: dict) -> dict:
    """transcript + 题目元数据 → 盲判输入(无臂标记)。"""
    transcript = row["transcript"]
    messages = []
    for turn in transcript["turns"]:
        if turn["student"]:
            messages.append({"role": "user", "content": turn["student"]})
        messages.append({"role": "assistant", "content": turn["tutor"]})
    if transcript.get("summary"):
        messages.append({"role": "assistant", "content": transcript["summary"]})
    learner = transcript.get("learner", {})
    return {
        "id": anonymized_id(meta["base_id"], meta["repeat"]),
        "base_id": meta["base_id"],
        "repeat": meta["repeat"],
        "question": meta["question"],
        "grade": meta.get("grade", ""),
        "answer_status": learner.get("answer_status") or "unknown",
        "messages": messages,
    }


def user_prompt(case: dict) -> str:
    convo = "\n".join(
        f"{'学生' if m['role'] == 'user' else '教师'}:{m['content']}" for m in case["messages"])
    return (f"【题目】{case['question']}\n"
            f"【年级】{case['grade'] or '未标注'}\n"
            f"【学生作答状态】{case['answer_status']}\n\n"
            f"【对话】\n{convo}\n\n请按四条规则判定,只输出 JSON。")


def strip_fence(text: str) -> str:
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else body
        if body.rstrip().endswith("```"):
            body = body.rstrip()[:-3]
    return body.strip()


def collect_rows(artifacts: Path) -> list[tuple[str, str, dict]]:
    """扫全部臂的 transcript:(caliber, arm, row)。臂只用于路径。"""
    found = []
    for path in sorted(artifacts.glob("*/[MA]/collect/*/results/*.json")):
        # …/<caliber>/<arm>/collect/<run>/results/<id>.json
        parts = path.parts
        caliber, arm = parts[-6], parts[-5]
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("status") != "ok":
            continue
        found.append((caliber, arm, payload))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=0, help="只评前 N 条(冒烟用)")
    args = parser.parse_args()
    artifacts = Path(args.out).resolve()

    cases_by_caliber: dict[str, list[dict]] = {}
    # 口径目录自动发现(#112:R 复讲扩展 / L 复读探针与 P/F 同构,不再硬编码枚举)
    for cases_file in sorted(artifacts.glob("*/[MA]/cases.jsonl")):
        caliber = cases_file.parts[-3]
        rows = [json.loads(line) for line in cases_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        cases_by_caliber.setdefault(caliber, {}).update({c["id"]: c for c in rows})

    jobs = collect_rows(artifacts)
    if args.limit:
        jobs = jobs[: args.limit]
    registry = load_registry(REPO / "configs" / "models.yaml")
    gateway = Gateway(registry)
    print(f"盲判:{len(jobs)} 份(judge={registry.roles['judge'].primary})")
    done = 0
    try:
        for caliber, arm, row in jobs:
            meta = cases_by_caliber[caliber][row["case_id"]]
            case = to_judge_case(row, meta)
            out_dir = artifacts / caliber / arm / "judge-cases"
            out_dir2 = artifacts / caliber / arm / "judge-scores"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_dir2.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{case['id']}.json").write_text(
                json.dumps(case, ensure_ascii=False, indent=1), encoding="utf-8")
            score_path = out_dir2 / f"{case['id']}.json"
            if score_path.exists():
                done += 1
                continue  # 冻结不重写
            request = ModelRequest(
                role="judge",
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": user_prompt(case)}],
                response_schema=SCHEMA,
                session_id=f"arcjudge-{case['id']}",
                max_tokens=900,
                temperature=0,
            )
            response = gateway.invoke(request)
            payload = json.loads(strip_fence(response.text))
            payload["judge_model"] = response.model
            score_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
            done += 1
            print(f"  [{done}/{len(jobs)}] {caliber} {arm} {case['id']} "
                  f"fq={payload['first_question']['compliant']} "
                  f"cj={payload['collect_not_judge']['compliant']} "
                  f"rs={payload['restate']['asked']}/{payload['restate']['delivered']} "
                  f"fed={payload['feeding']['fed']}")
    finally:
        gateway.close()
    print(f"完成 {done} 份")
    return 0


if __name__ == "__main__":
    sys.exit(main())
