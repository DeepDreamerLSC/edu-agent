"""GEPA 驱动脚本(spike 管线验证 + #256 长跑)。

用法:
  python -m edu_agent.evals.gepa_driver <output_dir> [--rounds N] [--batch-size K]
  python -m edu_agent.evals.gepa_driver <output_dir> --paired [--rounds N]
  长跑(#256):--train-corpus v2 --max-calls 1624 --rounds 6(默认 resume,
  checkpoint.json 在 output_dir 即续跑;预算 facts 实测硬限,#284 tier-2)
"""

import argparse
import json
from pathlib import Path

from edu_agent.evals import gepa_loop, paired_loop, GepaConfig
from edu_agent.evals.image_teaching import load_scenarios, to_cases
from edu_agent.gateway import Gateway, load_registry


def main():
    parser = argparse.ArgumentParser(description="GEPA spike 驱动")
    parser.add_argument("output_dir", type=Path, help="输出目录")
    parser.add_argument("--rounds", type=int, default=2, help="轮数")
    parser.add_argument("--batch-size", type=int, default=4, help="批次大小(配对模式忽略)")
    parser.add_argument("--max-calls", type=int, default=100, help="预算上限(calls)")
    parser.add_argument("--paired", action="store_true", help="配对实验模式(全案例不重采样)")
    parser.add_argument("--train-corpus", choices=["image", "v2"], default="image",
                        help="训练池:image=v1 8 案(spike);v2=corpus-round-v2 93 案(#256 长跑)")
    parser.add_argument("--no-resume", action="store_true", help="忽略 checkpoint 从头跑")
    parser.add_argument("--two-knobs", action="store_true",
                        help="双旋钮搜索空间(elicit+support,#304 头部可达族,选项 A)")
    args = parser.parse_args()
    
    # 加载 train cases (从 scenario 语料取,有 student_turns/steps)
    if args.train_corpus == "v2":
        # #256 长跑池:corpus-round-v2 全 93 案(cases.jsonl 每行一案,含 question/
        # student_turns/grade/reference_answer 的 case 形态)。held-out 4 帧在独立
        # 文件(math_gold_b2_heldout),corpus_round 显式路径加载——本驱动不传不可见。
        train_cases = [json.loads(line) for line in
                       (Path("edu_agent/evals/artifacts/corpus-round-v2/cases.jsonl")
                        ).read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        scenarios_path = Path("edu_agent/evals/datasets/small_lecturer_image_teaching_v1.json")
        scenarios = load_scenarios(scenarios_path)
        train_cases = to_cases(scenarios)[:20]  # v1 只有 8 个 scenario,[:20] 实际取全量 8 案
    
    # 初始 elicit 模板
    initial_template = "我们从头把思路串一遍——先说说你第一步算了什么、为什么这样算。"
    
    # 加载 gateway
    gateway = Gateway(load_registry(Path("configs/models.yaml")))
    
    try:
        config = GepaConfig(
            rounds=args.rounds,
            batch_size=args.batch_size,
            max_calls=args.max_calls,
            two_knobs=args.two_knobs,
        )
        
        if args.paired:
            # 配对实验模式
            print(f"GEPA paired experiment: rounds={config.rounds}, max_calls={config.max_calls}")
            print(f"Train cases: {len(train_cases)} (all, no resampling)")
            print(f"Initial template: {initial_template[:50]}...")
            
            reports = paired_loop(
                cases=train_cases,
                initial_template=initial_template,
                config=config,
                gateway=gateway,
                output_dir=args.output_dir,
            )
            
            print(f"\n完成: {len(reports)} 轮")
            
            # 输出 paired-report
            paired_report_path = args.output_dir / "paired-report.json"
            if paired_report_path.exists():
                paired_summary = json.loads(paired_report_path.read_text(encoding="utf-8"))
                print(f"Budget: {paired_summary['budget']}")
                print(f"Mean Δ: {paired_summary['mean_delta']:.2f}")
                print(f"Verdict: {paired_summary['verdict']}")
        else:
            # 常规 GEPA 模式
            print(f"GEPA spike: rounds={config.rounds}, batch_size={config.batch_size}, max_calls={config.max_calls}")
            print(f"Train cases: {len(train_cases)} (from scenario corpus with student_turns)")
            print(f"Initial template: {initial_template[:50]}...")
            
            population, scores, reports = gepa_loop(
                train_cases=train_cases,
                initial_template=initial_template,
                config=config,
                gateway=gateway,
                output_dir=args.output_dir,
                resume=not args.no_resume,
            )
            
            print(f"\n完成: population={len(population.candidates)}, rounds={len(reports)}")
            print(f"Accepted variants: {sum(1 for r in reports if r['accepted'])}")
            
            # 输出 summary
            summary_path = args.output_dir / "summary.json"
            if summary_path.exists():
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                print(f"Budget: {summary['budget']}")
        
    finally:
        gateway.close()


if __name__ == "__main__":
    main()
