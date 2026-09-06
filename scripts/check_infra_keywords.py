#!/usr/bin/env python3
"""基础设施关键词扫描(02 §5)。

扫描 edu_agent/ 下 *.py 的标识符(tokenize 的 NAME 词元;字符串与注释不算,
因此合作方错误码 "TEACHING_CONTEXT_PRELOAD_NOT_READY" 这类字面量不受影响):
出现 lease、heartbeat、worker_pool、scheduler、preload 命中即失败。
误报通过改名解决,不加白名单(02 §5)。只依赖标准库。
"""

import argparse
import sys
import tokenize
from pathlib import Path

KEYWORDS = ("lease", "heartbeat", "worker_pool", "scheduler", "preload")
SKIP_DIRS = frozenset({
    ".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
    "node_modules", "build", "dist",
})


def identifier_hits(path: Path) -> list[tuple[int, str]]:
    """文件中命中关键词的标识符:(行号, 标识符)。"""
    hits = []
    with path.open(encoding="utf-8") as handle:
        try:
            for token in tokenize.generate_tokens(handle.readline):
                if token.type != tokenize.NAME:
                    continue
                lowered = token.string.lower()
                if any(keyword in lowered for keyword in KEYWORDS):
                    hits.append((token.start[0], token.string))
        except tokenize.TokenError:
            # 语法损坏的文件由 ruff 关卡负责;这里只报告已解析到的部分。
            pass
    return hits


def scan(root: Path) -> list[str]:
    """扫描 root/edu_agent 下的 Python 标识符,返回违规描述列表。"""
    base = root / "edu_agent"
    if not base.is_dir():
        return []
    problems = []
    for path in sorted(base.rglob("*.py")):
        if SKIP_DIRS.intersection(path.parts):
            continue
        for lineno, identifier in identifier_hits(path):
            rel = path.relative_to(root)
            problems.append(
                f"INFRA-KEYWORD {rel}:{lineno}: 标识符'{identifier}'命中禁用关键词(02 §5 不自建基础设施)"
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="仓库根目录(默认当前目录)")
    args = parser.parse_args()
    problems = scan(Path(args.root).resolve())
    if problems:
        print("\n".join(problems))
        print(f"基础设施关键词扫描未通过:{len(problems)} 处命中(02 §5)")
        return 1
    print("INFRA-KEYWORDS-OK: 0 命中(02 §5)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
