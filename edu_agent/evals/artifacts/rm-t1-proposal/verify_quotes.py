#!/usr/bin/env python3
"""rm-t1-proposal 引文逐字核验(#253):对源文件逐字节比对,机械证明逐字可定位。

口径同 #272 审查(引文逐字可定位)。只依赖标准库;零模型调用。
用法:python3 edu_agent/evals/artifacts/rm-t1-proposal/verify_quotes.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES = {
    "judge-v3.2-rescore-93/judge-cases.jsonl": HERE / "../judge-v3.2-rescore-93/judge-cases.jsonl",
    "teacher-gate-slice/slice-cases.jsonl": HERE / "../teacher-gate-slice/slice-cases.jsonl",
}
# 每源读一次,按 case_id 建索引
POOLS = {name: {c["id"]: c for c in map(json.loads, open(path, encoding="utf-8"))}
         for name, path in SOURCES.items()}


def check(pair: dict) -> tuple[int, int]:
    """返回 (核验轮数, 不符轮数);引文与源 role/content 逐字节比对。"""
    total = mismatches = 0
    for side in ("a", "b"):
        pool = POOLS[pair[side]["source"]]
        messages = pool[pair[side]["case_id"]]["messages"]
        for turn in pair[side]["turns"]:
            source = messages[turn["index"]]
            total += 1
            if source["role"] != turn["role"] or source["content"] != turn["content"]:
                mismatches += 1
                print(f"MISMATCH {pair['pair_id']} {side}[{turn['index']}]")
    return total, mismatches


def main() -> int:
    pairs = [json.loads(line) for line in
             open(HERE / "pairs.jsonl", encoding="utf-8") if line.strip()]
    total = mismatches = 0
    for pair in pairs:
        t, m = check(pair)
        total, mismatches = total + t, mismatches + m
    print(f"逐字核验 {total}/{total} 轮 {'ALL MATCH' if mismatches == 0 else 'FAIL'}"
          f"({len(pairs)} 组)")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
