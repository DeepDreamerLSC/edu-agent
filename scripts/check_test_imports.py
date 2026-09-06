#!/usr/bin/env python3
"""测试私有导入检查(02 §6)。

tests/ 下的测试只能导入公开入口:edu_agent.gateway、edu_agent.agents.small_lecturer、
edu_agent.api、edu_agent.contracts(以及包名 edu_agent 本身),导入私有模块即失败。
只依赖标准库。
"""

import argparse
import ast
import sys
from pathlib import Path

PUBLIC_MODULES = frozenset({
    "edu_agent",
    "edu_agent.gateway",
    "edu_agent.agents.small_lecturer",
    "edu_agent.api",
    "edu_agent.contracts",
})
SKIP_DIRS = frozenset({
    ".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
    "node_modules", "build", "dist",
})


def imported_modules(path: Path) -> list[str]:
    """文件顶层与函数内全部 import 语句引用的模块名(相对导入记为 <relative>)。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        return [f"<syntax-error:{exc.lineno}>"]
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None and node.level == 0:
                modules.append(node.module)
            else:
                modules.append("<relative>")
    return modules


def is_private(module: str) -> bool:
    """edu_agent 模块且不在公开入口名单内,即为私有导入。"""
    if module == "edu_agent" or module.startswith("edu_agent."):
        return module not in PUBLIC_MODULES
    return False


def scan(root: Path) -> list[str]:
    """扫描 root/tests 下全部测试文件,返回违规描述列表。"""
    base = root / "tests"
    if not base.is_dir():
        return []
    problems = []
    for path in sorted(base.rglob("*.py")):
        if SKIP_DIRS.intersection(path.parts):
            continue
        for module in imported_modules(path):
            if module.startswith("<syntax-error"):
                problems.append(f"PRIVATE-IMPORT {path.relative_to(root)}: 语法错误无法分析({module})")
            elif is_private(module):
                problems.append(
                    f"PRIVATE-IMPORT {path.relative_to(root)}: 导入 '{module}' 不是公开入口(02 §6)"
                )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="仓库根目录(默认当前目录)")
    args = parser.parse_args()
    problems = scan(Path(args.root).resolve())
    if problems:
        print("\n".join(problems))
        print(f"测试私有导入检查未通过:{len(problems)} 处(02 §6)")
        return 1
    print("TEST-IMPORTS-OK: 测试只导入公开入口(02 §6)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
