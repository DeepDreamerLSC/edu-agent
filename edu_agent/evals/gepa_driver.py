"""GEPA spike 驱动脚本:小配置跑一轮,验证管线通不通 + 产出工件。

用法:python -m edu_agent.evals.gepa_driver <output_dir> [--rounds N] [--batch-size K]
"""

import argparse
import json
from pathlib import Path

from edu_agent.evals import gepa_loop, GepaConfig
from edu_agent.gateway import Gateway, load_registry


def main():
    parser = argparse.ArgumentParser(description="GEPA spike 驱动")
    parser.add_argument("output_dir", type=Path, help="输出目录")
    parser.add_argument("--rounds", type=int, default=2, help="轮数")
    parser.add_argument("--batch-size", type=int, default=4, help="批次大小")
    parser.add_argument("--max-calls", type=int, default=100, help="预算上限(calls)")
    args = parser.parse_args()
    
    # 加载 train cases (从 93 案工件取前 20 个)
    cases_file = Path("edu_agent/evals/artifacts/judge-v3.2-rescore-93/judge-cases.jsonl")
    train_cases = []
    for i, line in enumerate(cases_file.read_text(encoding="utf-8").splitlines()):
        if i >= 20:
            break
        if line.strip():
            train_cases.append(json.loads(line))
    
    # 初始 elicit 模板
    initial_template = "我们从头把思路串一遍——先说说你第一步算了什么、为什么这样算。"
    
    # 加载 gateway
    gateway = Gateway(load_registry(Path("configs/models.yaml")))
    
    try:
        config = GepaConfig(
            rounds=args.rounds,
            batch_size=args.batch_size,
            max_calls=args.max_calls,
        )
        
        print(f"GEPA spike: rounds={config.rounds}, batch_size={config.batch_size}, max_calls={config.max_calls}")
        print(f"Train cases: {len(train_cases)}")
        print(f"Initial template: {initial_template[:50]}...")
        
        population, scores, reports = gepa_loop(
            train_cases=train_cases,
            initial_template=initial_template,
            config=config,
            gateway=gateway,
            output_dir=args.output_dir,
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
