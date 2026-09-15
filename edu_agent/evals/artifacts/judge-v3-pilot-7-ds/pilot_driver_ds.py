"""#253 引擎 A/B:ds-as-judge × 同 7 案。

底座 = task/253-judge-prompt-v3-pilot(件 1-4 补丁);引擎经 models.yaml 现成的
judge_independent 角色 → deepseek_chat 直评(无备选,不碰冻结配置);输入 =
judge-v3-pilot-7/judge-cases.jsonl 存档逐字复用(完全隔离引擎变量);
max_tokens=900 / temperature=0 / 单调用结构不变(route-1 内部修复属单调用结构)。

纪律:API 调用数以 7 为上限(facts 行计数,超限即停报);失败不重试不救参;
输出原样落盘;judger_sha256(v3 指纹,与 mlx 先导同码)随产物记录。
"""
import json
import shutil
import sys
from pathlib import Path

from edu_agent.evals import judge_transcript, judger_sha256
from edu_agent.gateway import Gateway, GatewayError, load_registry

SRC = Path(__file__).resolve().parent
# 自含复算:输入读本工件目录;输出/facts 落 /tmp(不写仓内)。需 DEEPSEEK_API_KEY。
CASES_FILE = Path(__file__).resolve().parent / "judge-cases.jsonl"
OUT_DIR = Path("/tmp/pilot7-ds-rerun")
FACTS = Path("/tmp/pilot7-ds-rerun-facts")
API_CAP = 7  # 派单上限;超限即停报

cases = [json.loads(line) for line in CASES_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
assert len(cases) == 7, len(cases)
shutil.rmtree(FACTS, ignore_errors=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)


def api_calls() -> int:
    """facts 行数 = 实际 API 调用数(每次 attempt 一行)。"""
    return sum(1 for f in sorted(FACTS.glob("model_calls-*.jsonl"))
               for line in f.read_text(encoding="utf-8").splitlines() if line.strip())


gateway = Gateway(load_registry(Path("configs/models.yaml")), facts_dir=str(FACTS))
rows, breach = [], None
try:
    for case in cases:
        cid = case["id"]
        try:
            row = judge_transcript(gateway, case, role="judge_independent")
        except GatewayError as exc:
            row = {"error": f"{type(exc).__name__}: {exc}"[:500],
                   "raw_output": getattr(exc, "output", None)}
        rows.append({"case_id": cid, **row})
        n = api_calls()
        print(f"[done] {cid[:66]} verdict={row.get('verdict') or 'ERROR'} "
              f"mi={row.get('math_integrity')} leaked={row.get('answer_leaked')} "
              f"(API 调用累计 {n}/{API_CAP})", flush=True)
        if n > API_CAP:
            breach = f"API 调用超限:{n} > {API_CAP}(停余案,原样报回)"
            break
finally:
    gateway.close()

(OUT_DIR / "judge-scores.jsonl").write_text(
    "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
(OUT_DIR / "judger.sha256").write_text(judger_sha256() + "\n", encoding="utf-8")
errors = [r["case_id"] for r in rows if "error" in r]
print(f"\n完成 {len(rows)}/7 案 → {OUT_DIR};judger_sha256={judger_sha256()};"
      f"API 调用总数 {api_calls()}")
if errors:
    print(f"失败(不重试):{errors}", file=sys.stderr)
if breach:
    print(breach, file=sys.stderr)
    sys.exit(2)
if errors:
    sys.exit(1)
