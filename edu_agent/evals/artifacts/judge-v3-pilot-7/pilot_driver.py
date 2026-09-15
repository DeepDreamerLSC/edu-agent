"""#253 v3 先导 7 案:存档输入逐字复用 × v3 提示词补丁 → 单遍 judge(mlx_27b)。

纪律:只跑这 7 案;失败不重试(route-1 内部修复属单调用结构,不算重试);
输出原样落盘;judger_sha256(v3 指纹)随产物记录。
"""
import json
import sys
from pathlib import Path

from edu_agent.evals import judge_transcript, judger_sha256
from edu_agent.gateway import Gateway, GatewayError, load_registry

# 自含复算:输入读本工件目录,输出落 /tmp/pilot7-rerun(不写仓内)
CASES_FILE = Path(__file__).resolve().parent / "judge-cases.jsonl"
OUT_DIR = Path("/tmp/pilot7-rerun")

cases = [json.loads(line) for line in CASES_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
OUT_DIR.mkdir(parents=True, exist_ok=True)

gateway = Gateway(load_registry(Path("configs/models.yaml")))
rows = []
try:
    for case in cases:
        cid = case["id"]
        try:
            row = judge_transcript(gateway, case)
        except GatewayError as exc:
            row = {"error": f"{type(exc).__name__}: {exc}"[:500],
                   "raw_output": getattr(exc, "output", None)}
        rows.append({"case_id": cid, **row})
        got = row.get("verdict") or "ERROR"
        print(f"[done] {cid[:70]} verdict={got} mi={row.get('math_integrity')} "
              f"leaked={row.get('answer_leaked')}", flush=True)
finally:
    gateway.close()

(OUT_DIR / "judge-scores.jsonl").write_text(
    "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
(OUT_DIR / "judger.sha256").write_text(judger_sha256() + "\n", encoding="utf-8")
errors = [r["case_id"] for r in rows if "error" in r]
print(f"\n完成 {len(rows)} 案 → {OUT_DIR};judger_sha256={judger_sha256()}")
if errors:
    print(f"失败(不重试):{errors}", file=sys.stderr)
    sys.exit(1)
