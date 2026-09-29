#!/usr/bin/env python3
"""D6/D7 gold 消费运行器(matched-surface;#464 终裁 5892600320;#485 冻结审 P0×2)。

- 模型边界只过 user_prompt(adapter 已渲染);SYSTEM_PROMPT 逐字保留为前缀 +
  **系统级执行附录**(_SYSTEM_ADDENDUM,adapter 持有并版本化,sha 入身份链)——
  桥接冻结件「除对话记录外无其他材料」的输入描述与 matched 面(题面/锚框架行);
  S2_SCHEMA/max_tokens 16384/temp 0 随引擎冻结件零改动(镜像 s2_judge_transcript);
- 硬门(#485 P0-2):①frozen cases——--cases-sha 不符即拒跑;②30/30 完整性——
  不完整或模型身份门 VOID 均非零退出,不进任何对照;
- 身份链:git/rubric 冻结(head -n -1 口径)/prompt 资产/cases/addendum/models
  配置/judge_primary 双字段;resume 须身份全等(P0-6 同款);
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

# P0-1 系统级执行附录(#485 冻结审):冻结 SYSTEM_PROMPT 的输入描述是「除对话记录外
# 你没有其他材料」,与 matched 面(【题面】/【年级】/【判定锚】行)正面冲突——无附录
# 则 judge 按系统指令无视题面,B-1a 层次识别断输入。附录由 adapter 持有并版本化
# (sha 入身份链);资产本体逐字保留为前缀,不改任何判据语义。
_SYSTEM_ADDENDUM = """【matched-surface 执行附录(adapter v0.1)】本次输入形态与上述判据的对接约定:
- 【题面】(及可选【年级】)行为给定材料的组成部分,可用于需要题面的判定(如 B-1a 层次识别);题面原文可能附带 answer 字段,按题面原文对待。
- 【对话记录】为逐轮原文;本次窗口截止于判定锚,锚后轮不存在。
- 【判定锚】行指定本次判定的目标配对:锚轮学生话语 × 锚轮 Tutor 回应;两轴判定与 supporting turns 仍按系统指令执行,锚轮配对为主要判定对象。
- 除以上材料外无其他信息;姿态不变:判定不能闭合 → unsure,不强行归边。"""


class MatchedSurfaceSubject:
    """被测对象:matched-surface 案(user_prompt 已渲染)→ 引擎同款请求+系统级附录。"""

    def __init__(self, gateway: Gateway) -> None:
        self.gateway = gateway

    def run_case(self, case: dict) -> dict:
        request = ModelRequest(
            role=_ROLE,
            messages=[
                {"role": "system", "content": _system_content()},
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


def _addendum_sha() -> str:
    """执行附录 sha(身份链审计锚:附录变则旧 run 拒续跑)。"""
    return hashlib.sha256(_SYSTEM_ADDENDUM.encode()).hexdigest()


def _system_content() -> str:
    """系统消息 = 冻结 SYSTEM_PROMPT 逐字前缀 + 执行附录(P0-1)。"""
    return f"{SYSTEM_PROMPT}\n\n{_SYSTEM_ADDENDUM}"


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
        "addendum_sha256": _addendum_sha(),
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
    parser.add_argument("--cases-sha", required=True,
                        help="冻结 cases jsonl 的 sha256(P0-2 硬门:不符即拒跑)")
    parser.add_argument("--artifacts-root", required=True, type=Path)
    parser.add_argument("--run-dir", type=Path, default=None,
                        help="续跑既有 run 目录(先过 identity 全等门)")
    args = parser.parse_args()

    # P0-2 硬门①:frozen cases——sha 不符即拒跑,防任何未冻结输入进模型边界
    actual_sha = _sha(args.cases)
    if actual_sha != args.cases_sha:
        sys.exit(f"cases 硬门:sha256 不符(期望 {args.cases_sha[:16]}…,"
                 f"实际 {actual_sha[:16]}…)——拒绝运行,仅接受冻结 cases。")

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
    # P0-2 硬门②:30/30 完整性——不完整或模型身份门 VOID 均非零退出,不进任何对照
    complete = gate["ok"] == gate["total"] and gate["total"] > 0
    report = run_dir / "report.md"
    report.write_text(
        f"# D6/D7 gold 消费(matched-surface)\n\n"
        f"- 完整性:{gate['ok']}/{gate['total']}"
        f"{'(COMPLETE)' if complete else '(INCOMPLETE——不进对照)'};"
        f"answer_exposed_ok {gate['answer_exposed_ok']}/5\n"
        f"- judge_model 集合:{json.dumps(gate['models'], ensure_ascii=False)}\n"
        f"- 模型身份门:{gate['model_gate']}"
        f"{'(任一不满足即整轮 VOID,不进对照)' if gate['model_gate'] == 'VOID' else ''}\n"
        f"- judge_primary_model:{identity['judge_primary_model']}\n"
        f"- addendum_sha256:{identity['addendum_sha256']}\n",
        encoding="utf-8")
    print(f"run 目录:{run_dir}")
    print(f"ok {gate['ok']}/{gate['total']};模型身份门 {gate['model_gate']};"
          f"报告:{report}")
    if not complete:
        sys.exit("完整性硬门:ok < total——run 不完整,续跑补齐后重验;不进对照。")
    if gate["model_gate"] == "VOID":
        sys.exit("模型身份门 VOID——judge_model 非单值或不等于预注册 primary;"
                 "整轮作废,不进对照。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
