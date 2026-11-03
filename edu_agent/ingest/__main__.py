"""ingest 管线 CLI(08 §5:唯一驱动入口;质量检查只经 gate,不另设脚本)。

用法:python -m edu_agent.ingest render|ocr|segment|gate ...
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from edu_agent.ingest import get_engine, render_pdf, run_ocr, run_segment
from edu_agent.ingest.gate import run_gate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="edu_agent.ingest")
    sub = parser.add_subparsers(dest="command", required=True)

    render = sub.add_parser("render", help="PDF → pages/")
    render.add_argument("--pdf", type=Path, required=True)
    render.add_argument("--out", type=Path, required=True)
    render.add_argument("--dpi", type=int, default=160)

    ocr = sub.add_parser("ocr", help="pages.jsonl → elements.jsonl")
    ocr.add_argument("--pages", type=Path, required=True)
    ocr.add_argument("--out", type=Path, required=True)
    ocr.add_argument("--engine", default="oxr")
    ocr.add_argument("--run-id", required=True)
    ocr.add_argument("--page-limit", type=int)

    segment = sub.add_parser("segment", help="elements.jsonl → questions.jsonl")
    segment.add_argument("--elements", type=Path, required=True)
    segment.add_argument("--out", type=Path, required=True)

    gate = sub.add_parser("gate", help="golden 容差判定")
    gate.add_argument("--cases", type=Path, required=True)
    gate.add_argument("--questions", type=Path, required=True)
    gate.add_argument("--elements", type=Path, required=True)
    gate.add_argument("--report", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "render":
        print(render_pdf(args.pdf, args.out, dpi=args.dpi))
    elif args.command == "ocr":
        engine = get_engine(args.engine)
        print(run_ocr(args.pages, args.out, engine, run_id=args.run_id, page_limit=args.page_limit))
    elif args.command == "segment":
        print(run_segment(args.elements, args.out))
    else:
        report = run_gate(args.cases, args.questions, args.elements)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({k: report[k] for k in ("case_count", "passed", "blocking_failure", "false_accepted", "gate_pass")}, ensure_ascii=False))
        return 0 if report["gate_pass"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
