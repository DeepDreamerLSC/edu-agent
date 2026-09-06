#!/usr/bin/env python3
"""judge 批量评分 + 稳定性档案(#32 必做项:双评一致性 + 10% 独立性保险)。

读 cases JSONL(每行:id/question/grade/reference_answer/messages),三遍过
EvalRunner(断点续跑/失败台账/并发控制复用 runner 设施):
  pass1 主选 judge(mlx 27B,路线 1)、pass2 同模型重评(双评)、
  pass3 抽样 10% 走 judge_independent(DeepSeek 直评,独立性保险)。
产出 var 下的 stability.md(judge 稳定性档案首档;真实 transcripts 随适配器
到位后同一命令直接换输入文件)。DEEPSEEK_API_KEY 走环境变量,不进代码不进日志。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from edu_agent.evals import (
    EvalRunner,
    JudgeSubject,
    RunnerConfig,
    any_judge_model,
    load_results,
    sample_independent,
    stability_markdown,
    stability_report,
)
from edu_agent.gateway import Gateway, load_registry


def _resume_dir(root: Path) -> Path | None:
    """该 pass 已有的 run 目录(续跑);无则返回 None 交给 runner 自建。"""
    if not root.is_dir():
        return None
    existing = sorted(root.glob("cases-*"))
    return existing[-1] if existing else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, help="cases JSONL 路径")
    parser.add_argument("--out", default="var/judge-stability", help="输出根目录")
    args = parser.parse_args()

    cases_file = Path(args.cases)
    cases = [json.loads(line) for line in cases_file.read_text(encoding="utf-8").splitlines() if line]
    gateway = Gateway(load_registry(Path("configs/models.yaml")))
    config = RunnerConfig()  # 并发 2:judge 主选 27B mlx 的角色声明口径(models.yaml)
    out = Path(args.out)
    sampled = set(sample_independent([str(case.get("id")) for case in cases]))
    passes = {
        "pass1": (cases, "judge", "judge-primary"),
        "pass2": (cases, "judge", "judge-repeat"),
        "pass3": (
            [case for case in cases if str(case.get("id")) in sampled],
            "judge_independent",
            "judge-independent-deepseek",
        ),
    }
    try:
        dirs: dict[str, Path] = {}
        for name, (batch, role, subject_name) in passes.items():
            if not batch:
                print(f"{name}: 无 case,跳过")
                continue
            print(f"{name}: {len(batch)} case,role={role}")
            runner = EvalRunner(JudgeSubject(gateway, role=role, name=subject_name), config, out / name)
            dirs[name] = runner.run(cases_file, batch, run_dir=_resume_dir(out / name))
        report = stability_report(
            load_results(dirs["pass1"]),
            load_results(dirs["pass2"]),
            load_results(dirs.get("pass3", Path("-none-"))),
        )
    finally:
        gateway.close()
    markdown = stability_markdown(report, any_judge_model(load_results(dirs["pass1"])))
    out.mkdir(parents=True, exist_ok=True)
    (out / "stability.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
