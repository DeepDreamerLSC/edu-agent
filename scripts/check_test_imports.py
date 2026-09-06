#!/usr/bin/env python3
"""测试私有导入检查(02 §6)。

tests/ 下的测试只能导入公开入口:edu_agent.gateway、edu_agent.agents.small_lecturer、
edu_agent.api、edu_agent.contracts(以及包名 edu_agent 本身),导入私有模块即失败。
"私有模块"包括 from 公开入口 import 私有子模块的形式(评审发现的绕过路径):
from edu_agent.gateway import middleware —— alias 按文件系统解析为
edu_agent/gateway/middleware.py,存在且不在公开名单内即报 PRIVATE-IMPORT;
公开入口子模块(from edu_agent.agents import small_lecturer)与普通符号不受影响。
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


def module_exists(root: Path, module: str) -> bool:
    """module 是否是仓库内真实存在的 edu_agent 子模块(文件或包)。"""
    if not (module == "edu_agent" or module.startswith("edu_agent.")):
        return False
    base = root.joinpath(*module.split("."))
    return base.with_suffix(".py").is_file() or (base / "__init__.py").is_file()


def is_private(module: str) -> bool:
    """edu_agent 模块且不在公开入口名单内,即为私有导入。"""
    if module == "edu_agent" or module.startswith("edu_agent."):
        return module not in PUBLIC_MODULES
    return False


def is_public_prefix(module: str) -> bool:
    """module 是否是某个公开入口的路径前缀(如 edu_agent.agents之于 small_lecturer)。

    前缀本身不是公开入口,但 from 前缀 import 公开入口子模块是合法形式,
    这类节点交给 alias 级解析判断。
    """
    return any(entry.startswith(module + ".") for entry in PUBLIC_MODULES)


def module_problem(rel: Path, module: str) -> str:
    return f"PRIVATE-IMPORT {rel}: 导入 '{module}' 不是公开入口(02 §6)"


def alias_problems(root: Path, rel: Path, node: ast.ImportFrom) -> list[str]:
    """from 公开入口 import 的名字若解析为私有子模块,同样是私有导入。"""
    problems = []
    for alias in node.names:
        candidate = f"{node.module}.{alias.name}"
        if candidate in PUBLIC_MODULES or not module_exists(root, candidate):
            continue
        problems.append(
            f"PRIVATE-IMPORT {rel}: from '{node.module}' import '{alias.name}'"
            f" 引入私有模块 {candidate}(02 §6)"
        )
    return problems


def node_problems(root: Path, rel: Path, node: ast.AST) -> list[str]:
    """单个 import 节点的违规描述。"""
    if isinstance(node, ast.Import):
        return [module_problem(rel, a.name) for a in node.names if is_private(a.name)]
    if not isinstance(node, ast.ImportFrom):
        return []
    if node.module is None or node.level > 0:
        return [f"PRIVATE-IMPORT {rel}: 相对导入不是公开入口(02 §6)"]
    if is_private(node.module) and not is_public_prefix(node.module):
        return [module_problem(rel, node.module)]
    return alias_problems(root, rel, node)


def scan(root: Path) -> list[str]:
    """扫描 root/tests 下全部测试文件,返回违规描述列表。"""
    base = root / "tests"
    if not base.is_dir():
        return []
    problems = []
    for path in sorted(base.rglob("*.py")):
        if SKIP_DIRS.intersection(path.parts):
            continue
        rel = path.relative_to(root)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            problems.append(f"PRIVATE-IMPORT {rel}: 语法错误无法分析(第 {exc.lineno} 行)")
            continue
        for node in ast.walk(tree):
            problems.extend(node_problems(root, rel, node))
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
