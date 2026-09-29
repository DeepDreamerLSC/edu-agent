#!/usr/bin/env python3
"""D6/D7 gold 消费运行器(matched-surface;#464 终裁 5892600320)。

- 模型边界只过 user_prompt(adapter 已渲染);SYSTEM_PROMPT/S2_SCHEMA/
  max_tokens 16384/temp 0 随引擎冻结件零改动(镜像 s2_judge_transcript);
- 身份链:git/rubric 冻结(head -n -1 口径)/prompt 资产/cases(含 pack+gold
  派生)/models 配置/judge_primary 双字段;resume 须身份全等(P0-6 同款);
- 模型身份门(P0-2/P0-4 同款):judge_model 单值 ∧ == 预注册 primary,
  任一不满足 → 整轮 VOID,不进任何对照;
- 无期望值打分:与 human gold 的一致/分歧矩阵是独立分析步,不在本运行器;
- 本轮仅云臂(Flash×2 / GLM×1);本地臂重启前须先修 #241 flag 的 Mac 侧落点。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from edu_agent.evals import EnvironmentFailure, EvalRunner, RunnerConfig
from edu_agent.evals.s2_judge import S2_SCHEMA, SYSTEM_PROMPT, _strip_code_fence
from edu_agent.gateway import (ENV_FAILURES, Gateway, GatewayError,
                               ModelRequest, load_registry)

_REPO = Path(__file__).resolve().parents[1]
_ROLE = "judge"


class MatchedSurfaceSubject:
    """被测对象:matched-surface 案(user_prompt 已渲染)→ 引擎同款请求。"""

    def __init__(self, gateway: Gateway) -> None:
        self.gateway = gateway

    def run_case(self, case: dict) -> dict:
        request = ModelRequest(
            role=_ROLE,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": case["user_prompt"]},
            ],
            response_schema=S2_SCHEMA,
            session_id=f"d6d7-gold-{case['case_id']}",
            # 16384:M1 control 容量适配(#459);与引擎冻结件逐字一致
            max_tokens=16384,
            temperature=0,
        )
        try:
            response = self.gateway.invoke(request)
        except GatewayError as error:
            if error.failure in ENV_FAILURES:
                raise EnvironmentFailure(str(error)) from error
            raise
        payload = json.loads(_strip_code_fence(response.text))
        return {"s2a": payload["s2a"], "s2b": payload["s2b"],
                "judge_model": response.model}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rubric_head_sha(rubric: Path) -> str:
    """冻结件 head -n -1 口径 sha(rubric 被改即变值,旧 run 随之拒绝续跑)。"""
    head = "".join(rubric.read_text(encoding="utf-8").splitlines(keepends=True)[:-1])
    return hashlib.sha256(head.encode()).hexdigest()


def _identity(models_yaml: Path, cases: Path, rubric: Path,
              prompt_asset: Path, registry) -> dict:
    role = registry.role(_ROLE)
    return {
        "git_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=_REPO, capture_output=True,
            text=True, check=True,
        ).stdout.strip(),
        "rubric_freeze_sha": _rubric_head_sha(rubric),
        "prompt_asset_sha": _sha(prompt_asset),
        "cases_sha": _sha(cases),
        "models_yaml_sha": _sha(models_yaml),
        # P0-4 双字段:id 仅追溯,不与 response.model 比;model 才是比较基准
        "judge_primary_id": role.primary,
        "judge_primary_model": registry.model(role.primary).name,
    }


def _resume_gate(run_dir: Path, identity: dict) -> None:
    """P0-6 同款:进 resume 前身份须全等,不等即拒。"""
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        return
    stored = json.loads(manifest_path.read_text(encoding="utf-8")).get("identity")
    if stored != identity:
        diff = [key for key in sorted(set(stored or {}) | set(identity))
                if (stored or {}).get(key) != identity.get(key)]
        sys.exit(f"resume 拒绝(P0-6):identity 不一致({', '.join(diff)}),"
                 "请新开 run 目录。")


def _model_gate(run_dir: Path, rows: list[dict], identity: dict) -> dict:
    """P0-2/P0-4 同款:judge_model 单值 ∧ == primary;否则整轮 VOID。"""
    results = {}
    for path in sorted((run_dir / "results").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        results[record["case_id"]] = record
    ok = {row["case_id"] for row in rows
          if results.get(row["case_id"], {}).get("status") == "ok"}
    models = {results[c]["transcript"]["judge_model"] for c in ok}
    valid = (len(models) == 1 and len(ok) > 0
             and next(iter(models)) == identity["judge_primary_model"])
    exposed_ok = sum(1 for r in rows if r["answer_exposed"] and r["case_id"] in ok)
    return {"ok": len(ok), "total": len(rows), "models": sorted(models),
            "model_gate": "ok" if valid else "VOID",
            "answer_exposed_ok": exposed_ok}


def main() -> int:
    parser = argparse.ArgumentParser(description="D6/D7 gold 消费运行器")
    parser.add_argument("--cases", required=True, type=Path,
                        help="matched-surface cases jsonl(d6d7_matched_surface.py 产出)")
    parser.add_argument("--artifacts-root", required=True, type=Path)
    parser.add_argument("--run-dir", type=Path, default=None,
                        help="续跑既有 run 目录(先过 identity 全等门)")
    args = parser.parse_args()

    rubric = _REPO / "docs/evals/s2-judge-rubric-v0.1.md"
    prompt_asset = _REPO / "edu_agent/evals/rubrics/s2_judge_v0_1.yaml"
    models_yaml = Path(os.environ.get("EDU_MODELS_YAML")
                       or _REPO / "configs" / "models.yaml")
    registry = load_registry(models_yaml)
    identity = _identity(models_yaml, args.cases, rubric, prompt_asset, registry)
    if args.run_dir is not None:
        _resume_gate(args.run_dir, identity)

    rows = [json.loads(line) for line in
            args.cases.read_text(encoding="utf-8").strip().splitlines()]
    args.artifacts_root.mkdir(parents=True, exist_ok=True)

    flag = Path(f"/tmp/edu-agent-batch/d6d7-gold-consume.{os.getpid()}")
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text(f"d6d7-gold-consume pid={os.getpid()}\n", encoding="utf-8")
    try:
        gateway = Gateway(registry, facts_dir=os.environ.get("EDU_FACTS_DIR") or "facts")
        try:
            runner = EvalRunner(MatchedSurfaceSubject(gateway), RunnerConfig(),
                                runs_root=args.artifacts_root)
            run_dir = runner.run(args.cases, rows,
                                 run_dir=args.run_dir, identity=identity)
        finally:
            gateway.close()
    finally:
        flag.unlink(missing_ok=True)

    gate = _model_gate(run_dir, rows, identity)
    report = run_dir / "report.md"
    report.write_text(
        f"# D6/D7 gold 消费(matched-surface)\n\n"
        f"- ok {gate['ok']}/{gate['total']};answer_exposed_ok {gate['answer_exposed_ok']}/5\n"
        f"- judge_model 集合:{json.dumps(gate['models'], ensure_ascii=False)}\n"
        f"- 模型身份门:{gate['model_gate']}"
        f"{'(任一不满足即整轮 VOID,不进对照)' if gate['model_gate'] == 'VOID' else ''}\n"
        f"- judge_primary_model:{identity['judge_primary_model']}\n",
        encoding="utf-8")
    print(f"run 目录:{run_dir}")
    print(f"ok {gate['ok']}/{gate['total']};模型身份门 {gate['model_gate']};"
          f"报告:{report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
