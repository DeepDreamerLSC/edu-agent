"""#253 路 B extract-only spike:三案 ×2 独立抽取(flash,6 调用)。

预注册门命题(跑前钉死,见 artifacts/…/README):
- C40:「方程两边同时除以(同一非零数)3 会破坏等式平衡」(规则,假)
- 编造51:「八分之一(可)变成十二分之一」(等值转换,假)
- C11:「(小讲师声称)学生刚才说了三份加一份」(归因,假;学生实说「占两份,再加一份,共三份」)
抽取层 ≠ 判据层:judge.py 零改动(指纹 af93e564 不动);本驱动为新层 spike,
max_tokens 1600(spike 参数,披露);schema 走 Gateway 路线 1(平台自带一次修复)。
"""
import json
import shutil
import sys
from pathlib import Path

from edu_agent.evals import judger_sha256
from edu_agent.gateway import Gateway, GatewayError, load_registry
from edu_agent.gateway.request import ModelRequest

cases_file, out_dir, facts_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
used_before = int(sys.argv[4])
assert judger_sha256() == "af93e5645086f6f02c0fcd303550adedf5a4004b3d8f69359999d481df85d3a8"
cases = [json.loads(l) for l in Path(cases_file).read_text(encoding="utf-8").splitlines() if l.strip()]
shutil.rmtree(facts_dir, ignore_errors=True)
out_dir.mkdir(parents=True, exist_ok=True)

SYSTEM = (
    "你是数学教学对话的命题抽取器(只抽取,不评判真假)。任务:通读师生对话,"
    "抽取小讲师(assistant)实际说出或明确暗示的每一条独立数学命题,输出显式分解的命题清单。"
    "抽取范围:①数值命题(某数等于某数);②等值/转换命题(某分数/单位/形式可化为另一形式);"
    "③公式或规则命题(运算性质、等式性质、某做法的后果,如「两边同时除以某数会/不会怎样」);"
    "④归因命题(小讲师声称学生说过/做过某内容,如「你刚才说…」——把被声称的内容显式化为命题)。"
    "每条命题给:(a)quote=小讲师原话逐字引文;(b)proposition=独立、可判真假的陈述句"
    "(把引文中的数学内容显式化,如「三分之二等于六分之四」「等式两边同时加上相同的数,等式仍然成立」);"
    "(c)kind=数值|等值|转换|公式|规则|归因。"
    "不遗漏规则类与归因类命题;不评判真假;不把学生自己的话单独作为命题"
    "(学生的话只在归因命题的引文中出现)。"
)
SCHEMA = {
    "type": "object",
    "properties": {
        "propositions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quote": {"type": "string"},
                    "proposition": {"type": "string"},
                    "kind": {"type": "string", "enum": ["数值", "等值", "转换", "公式", "规则", "归因"]},
                },
                "required": ["quote", "proposition", "kind"],
            },
        }
    },
    "required": ["propositions"],
}


def facts_count():
    n = 0
    for f in sorted(Path(facts_dir).glob("model_calls-*.jsonl")):
        n += sum(1 for l in f.read_text(encoding="utf-8").splitlines() if l.strip())
    return n


def render(case):
    lines = [f"题目:{case['question']}", "", "对话:"]
    for m in case["messages"]:
        who = "学生" if m["role"] == "user" else "小讲师"
        lines.append(f"{who}:{m['content']}")
    return "\n".join(lines)


gateway = Gateway(load_registry(Path("configs/models.yaml")), facts_dir=str(facts_dir))
rows = []
try:
    for case in cases:
        cid = case["id"]
        try:
            resp = gateway.invoke(ModelRequest(
                role="judge_independent",
                messages=[{"role": "system", "content": SYSTEM},
                          {"role": "user", "content": render(case)}],
                response_schema=SCHEMA,
                session_id=f"extract-{cid[:40]}",
                max_tokens=1600,
                temperature=0.0,
            ))
            content = resp.text
            try:
                parsed = json.loads(content)
                props = parsed.get("propositions", [])
                err = None
            except json.JSONDecodeError as exc:
                props, err = [], f"JSONDecodeError: {exc}"
            rows.append({"case_id": cid, "propositions": props, "parse_error": err,
                         "raw_output": content if err else None})
            print(f"{cid[:58]} 抽取 {len(props)} 条命题 parse_error={err} (调用累计 {used_before + facts_count()})", flush=True)
        except GatewayError as exc:
            rows.append({"case_id": cid, "propositions": [], "parse_error": f"{type(exc).__name__}: {exc}"[:400]})
            print(f"{cid[:58]} GatewayError: {str(exc)[:100]} (调用累计 {used_before + facts_count()})", flush=True)
finally:
    gateway.close()

(out_dir / "extractions.jsonl").write_text(
    "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
print(f"\n完成 {len(rows)}/{len(cases)} → {out_dir};本批调用 {facts_count()}")
