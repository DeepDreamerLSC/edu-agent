#!/usr/bin/env python3
"""D6/D7 gold 消费运行器(matched-surface;#464 终裁 5892600320;#485 冻结审 P0×2)。

- 模型边界只过 user_prompt(adapter 已渲染);SYSTEM_PROMPT 逐字保留为前缀 +
  **系统级执行附录**(_SYSTEM_ADDENDUM,只判锚轮——前轮仅 need/authorization/
  trajectory 上下文;sha 入身份链);S2_SCHEMA/max_tokens 16384/temp 0 随引擎
  冻结件零改动(镜像 s2_judge_transcript);
- 硬门(#485 复审 5356022635):①frozen cases——与代码钉死 FROZEN_CASES_SHA256
  比对拒跑(不收自报);②preflight 恰 30/case_id 唯一/answer_exposed 恰 5;
  ③结束门四条件合取 ok==total==30 ∧ exposed_ok==5 ∧ model_gate==ok;
- 身份链:git/rubric 冻结(head -n -1 口径)/prompt 资产/cases/addendum/models
  配置/judge_primary 双字段;指纹构造走公共 helper(#490 M0 表第③项),
  resume 须身份全等(#490 M3 起由公共层 strict_identity 承载;模型身份比较走公共
  compare_models,VOID 处置留本脚本);
- 无期望值打分:与 human gold 的一致/分歧矩阵是独立分析步,不在本运行器;
- 本轮仅云臂(Flash×2 / GLM×1);本地臂重启前须先修 #241 flag 的 Mac 侧落点。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from edu_agent.evals import (
    EnvironmentFailure,
    EvalRunner,
    ResumeMismatch,
    RunnerConfig,
    compare_models,
    file_sha256,
    git_head_sha,
    head_sha256,
)
from edu_agent.evals.s2_judge import S2_SCHEMA, SYSTEM_PROMPT, _strip_code_fence
from edu_agent.gateway import (ENV_FAILURES, Gateway, GatewayError,
                               ModelRequest, load_registry)

_REPO = Path(__file__).resolve().parents[1]
_ROLE = "judge"

# P0-2(#485 复审 5356022635):cases 冻结门在版本化代码里钉死,不收调用者自报 sha
FROZEN_CASES_SHA256 = "71069ca8dca305ef2ae0cb07153bbc1d478ae09dfa123a852870899cbbbe1437"

# P0-1 系统级执行附录(#485 冻结审;复审 5356022635 收紧为只判锚轮):冻结
# SYSTEM_PROMPT 的输入描述是「除对话记录外你没有其他材料」,且其输出合同为全案
# 聚合口径——无附录则 judge 无视题面(B-1a 断输入),且可能把前轮自身 failure
# 聚合进最终 verdict。附录由 adapter 持有并版本化(sha 入身份链);资产本体
# 逐字保留为前缀,不改任何判据语义。
_SYSTEM_ADDENDUM = """【matched-surface 执行附录(adapter v0.1)】本次输入形态与上述判据的对接约定:
- 【题面】(及可选【年级】)行为给定材料的组成部分,可用于需要题面的判定(如 B-1a 层次识别);题面原文可能附带 answer 字段,按题面原文对待。
- 【对话记录】为逐轮原文;本次窗口截止于判定锚,锚后轮不存在。
- 【判定锚】行指定唯一判定对象:锚轮学生话语 × 锚轮 Tutor 回应。只判锚轮;前轮只作为 need / authorization / trajectory 上下文,不得把前轮自身 failure 作为本案成立证据。
- 除以上材料外无其他信息;姿态不变:判定不能闭合 → unsure,不强行归边。"""


class MatchedSurfaceSubject:
    """被测对象:matched-surface 案(user_prompt 已渲染)→ 引擎同款请求+系统级附录。"""

    def __init__(self, gateway: Gateway) -> None:
        self.gateway = gateway
        self.name = "d6d7-gold-matched"

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


def _addendum_sha() -> str:
    """执行附录 sha(身份链审计锚:附录变则旧 run 拒续跑)。"""
    return hashlib.sha256(_SYSTEM_ADDENDUM.encode()).hexdigest()


def _system_content() -> str:
    """系统消息 = 冻结 SYSTEM_PROMPT 逐字前缀 + 执行附录(P0-1)。"""
    return f"{SYSTEM_PROMPT}\n\n{_SYSTEM_ADDENDUM}"


def _identity(models_yaml: Path, cases: Path, rubric: Path,
              prompt_asset: Path, registry) -> dict:
    role = registry.role(_ROLE)
    return {
        # 指纹构造走公共 helper(#490 M0 表第③项):文件字节/rubric 冻结
        # (head -n -1)/git HEAD 三面;addendum/字段集与键名仍由本专项声明
        "git_sha": git_head_sha(_REPO),
        "rubric_freeze_sha": head_sha256(rubric),
        "prompt_asset_sha": file_sha256(prompt_asset),
        "cases_sha": file_sha256(cases),
        "addendum_sha256": _addendum_sha(),
        "models_yaml_sha": file_sha256(models_yaml),
        # P0-4 双字段:id 仅追溯,不与 response.model 比;model 才是比较基准
        "judge_primary_id": role.primary,
        "judge_primary_model": registry.model(role.primary).name,
    }


def _model_gate(run_dir: Path, rows: list[dict], identity: dict) -> dict:
    """P0-2/P0-4 同款:judge_model 单值 ∧ == primary;否则整轮 VOID。

    身份比较走公共 compare_models(#490 M2);observed 提取(仅 ok 行的
    transcript.judge_model)、VOID 措辞与结束门处置留本脚本。"""
    results = {}
    for path in sorted((run_dir / "results").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        results[record["case_id"]] = record
    ok = {row["case_id"] for row in rows
          if results.get(row["case_id"], {}).get("status") == "ok"}
    comparison = compare_models(
        (results[c]["transcript"]["judge_model"] for c in ok),
        identity["judge_primary_model"])
    exposed_ok = sum(1 for r in rows if r["answer_exposed"] and r["case_id"] in ok)
    return {"ok": len(ok), "total": len(rows),
            "models": comparison.observed_models,
            "model_gate": "ok" if comparison.matched else "VOID",
            "answer_exposed_ok": exposed_ok}


def _preflight(rows: list[dict]) -> str | None:
    """P0-2 模型调用前硬门:恰 30 案 / case_id 唯一 / answer_exposed 恰 5。"""
    if len(rows) != 30:
        return f"cases 必须恰 30 案,实得 {len(rows)}"
    ids = [row["case_id"] for row in rows]
    if len(set(ids)) != len(ids):
        return "case_id 必须唯一"
    exposed = sum(1 for row in rows if row["answer_exposed"])
    if exposed != 5:
        return f"answer_exposed 必须恰 5,实得 {exposed}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="D6/D7 gold 消费运行器")
    parser.add_argument("--cases", required=True, type=Path,
                        help="matched-surface cases jsonl(d6d7_matched_surface.py 产出)")
    parser.add_argument("--artifacts-root", required=True, type=Path)
    parser.add_argument("--run-dir", type=Path, default=None,
                        help="续跑既有 run 目录(#490 M3:公共层 strict identity 全等门)")
    args = parser.parse_args()

    # P0-2 硬门①(复审收紧):frozen cases——与代码钉死的 FROZEN_CASES_SHA256
    # 比对,不符即拒跑;不收调用者自报 sha(指纹口径走公共 file_sha256)
    actual_sha = file_sha256(args.cases)
    if actual_sha != FROZEN_CASES_SHA256:
        sys.exit(f"cases 冻结门:sha256 与代码钉死值不符"
                 f"(钉死 {FROZEN_CASES_SHA256[:16]}…,实际 {actual_sha[:16]}…)"
                 "——拒绝运行。")

    rubric = _REPO / "docs/evals/s2-judge-rubric-v0.1.md"
    prompt_asset = _REPO / "edu_agent/evals/rubrics/s2_judge_v0_1.yaml"
    models_yaml = Path(os.environ.get("EDU_MODELS_YAML")
                       or _REPO / "configs" / "models.yaml")
    registry = load_registry(models_yaml)
    identity = _identity(models_yaml, args.cases, rubric, prompt_asset, registry)

    rows = [json.loads(line) for line in
            args.cases.read_text(encoding="utf-8").strip().splitlines()]
    # P0-2 硬门(模型调用前):恰 30 / case_id 唯一 / answer_exposed 恰 5
    if problem := _preflight(rows):
        sys.exit(f"preflight 硬门:{problem}——拒绝运行。")
    args.artifacts_root.mkdir(parents=True, exist_ok=True)

    flag = Path(f"/tmp/edu-agent-batch/d6d7-gold-consume.{os.getpid()}")
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text(f"d6d7-gold-consume pid={os.getpid()}\n", encoding="utf-8")
    try:
        gateway = Gateway(registry, facts_dir=os.environ.get("EDU_FACTS_DIR") or "facts")
        try:
            runner = EvalRunner(MatchedSurfaceSubject(gateway), RunnerConfig(),
                                runs_root=args.artifacts_root)
            # P0-6(#490 M3):resume 同一性门由公共层承载——strict 下 stored/current
            # identity 须全等,且先于 dataset/config/subject 三面(迁移前顺序不变)
            run_dir = runner.run(args.cases, rows, run_dir=args.run_dir,
                                 identity=identity, strict_identity=True)
        finally:
            gateway.close()
    except ResumeMismatch as exc:
        sys.exit(f"resume 拒绝(P0-6):{exc}")
    finally:
        flag.unlink(missing_ok=True)

    gate = _model_gate(run_dir, rows, identity)
    # P0-2 结束门(复审收紧,四条件合取):ok == total == 30 ∧ exposed_ok == 5
    # ∧ model_gate == ok;任一不满足即非零退出,不进任何对照
    complete = (gate["ok"] == 30 and gate["total"] == 30
                and gate["answer_exposed_ok"] == 5
                and gate["model_gate"] == "ok")
    report = run_dir / "report.md"
    report.write_text(
        f"# D6/D7 gold 消费(matched-surface)\n\n"
        f"- 结束门:ok {gate['ok']}/{gate['total']}"
        f"{'(COMPLETE)' if complete else '(INCOMPLETE——不进对照)'};"
        f"answer_exposed_ok {gate['answer_exposed_ok']}/5;"
        f"模型身份门 {gate['model_gate']}\n"
        f"- judge_model 集合:{json.dumps(gate['models'], ensure_ascii=False)}\n"
        f"- judge_primary_model:{identity['judge_primary_model']}\n"
        f"- addendum_sha256:{identity['addendum_sha256']}\n",
        encoding="utf-8")
    print(f"run 目录:{run_dir}")
    print(f"ok {gate['ok']}/{gate['total']};exposed_ok "
          f"{gate['answer_exposed_ok']}/5;模型身份门 {gate['model_gate']};"
          f"报告:{report}")
    if not complete:
        sys.exit("结束门:ok/total/exposed_ok/model_gate 四条件任一不满足"
                 "——续跑补齐后重验;不进对照。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
