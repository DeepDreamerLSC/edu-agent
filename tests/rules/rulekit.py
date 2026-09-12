"""tests/rules 的公共工具:临时仓库构造与仓库脚本调用(02 §11.2)。"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 与仓库真实 pyproject.toml 的 [tool.ruff] 段保持一致的有效夹具;
# test_budget_consistency.py 里有测试强制两者不漂移。
VALID_PYPROJECT = """\
[project]
name = "fixture-repo"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = []

[tool.ruff]
target-version = "py312"

[tool.ruff.lint]
select = [
    "PLR0915",
    "C901",
    "PLR0912",
    "PLR0911",
    "PLR0913",
    "S102",
    "S307",
    "S602",
    "S605",
    "S301",
    "E722",
    "BLE001",
    "TRY400",
    "PLW0603",
    "RUF006",
    "B",
    "F401",
]

[tool.ruff.lint.mccabe]
max-complexity = 12

[tool.ruff.lint.pylint]
max-statements = 50
max-branches = 12
max-returns = 6
max-args = 6
"""


def run_py(script: str, *args: str, env_extra: dict[str, str] | None = None):
    """以当前解释器运行仓库 scripts/ 下的脚本,捕获输出,不抛异常。"""
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / script), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
