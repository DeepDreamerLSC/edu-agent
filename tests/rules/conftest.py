"""tests/rules 夹具:构造全部指标通过的临时仓库与含六个顶层包的骨架(02 §11.2)。"""

import shutil
import sys
from pathlib import Path

import pytest

from rulekit import REPO_ROOT, VALID_PYPROJECT

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def base_repo(tmp_path: Path) -> Path:
    """一个全部预算指标通过的临时仓库(真实 02 文档 + 合法 pyproject + 空 edu_agent)。"""
    root = tmp_path / "repo"
    (root / "docs" / "plan").mkdir(parents=True)
    shutil.copy(
        REPO_ROOT / "docs" / "plan" / "02-complexity-budget.md",
        root / "docs" / "plan" / "02-complexity-budget.md",
    )
    (root / "edu_agent").mkdir()
    (root / "edu_agent" / "__init__.py").touch()
    (root / "scripts").mkdir()
    (root / "pyproject.toml").write_text(VALID_PYPROJECT, encoding="utf-8")
    return root


@pytest.fixture
def pkg_tree(tmp_path: Path) -> Path:
    """含 02 §2 预定六个顶层包的临时仓库,import-linter 合同可评估。"""
    root = tmp_path / "pkgrepo"
    (root / "edu_agent").mkdir(parents=True)
    (root / "edu_agent" / "__init__.py").touch()
    for name in ("gateway", "agents", "evals", "contracts", "api", "store"):
        package = root / "edu_agent" / name
        package.mkdir()
        (package / "__init__.py").touch()
    return root
