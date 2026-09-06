"""02 §2.2 四条包依赖合同的红灯测试:违规导入必须让 lint-imports 非零退出并点名合同。"""

import os
import shutil
import subprocess

import pytest

from rulekit import REPO_ROOT

CONTRACT_VIOLATIONS = {
    "gateway-no-agents-evals-api-store": ("gateway", "import edu_agent.evals"),
    "agents-no-api-store": ("agents", "import edu_agent.store"),
    "evals-no-api": ("evals", "import edu_agent.api"),
    "contracts-imports-nothing-internal": ("contracts", "import edu_agent.gateway"),
}


@pytest.fixture(name="lint_imports")
def lint_imports_bin():
    binary = shutil.which("lint-imports")
    if binary is None:
        pytest.fail("找不到 lint-imports(请在 uv 环境中运行,如 uv run pytest)")
    return binary


def run_linter(lint_imports, root):
    env = {
        **os.environ,
        "PYTHONPATH": f"{root}{os.pathsep}{os.environ.get('PYTHONPATH', '')}",
    }
    return subprocess.run(
        [lint_imports, "--config", str(REPO_ROOT / ".importlinter")],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
        env=env,
    )


@pytest.mark.parametrize("contract", sorted(CONTRACT_VIOLATIONS))
def test_contract_turns_red(lint_imports, pkg_tree, contract):
    package, violation = CONTRACT_VIOLATIONS[contract]
    (pkg_tree / "edu_agent" / package / "__init__.py").write_text(
        violation + "\n", encoding="utf-8"
    )
    result = run_linter(lint_imports, pkg_tree)
    output = result.stdout + result.stderr
    assert result.returncode != 0, f"{contract} 未被拦截:\n{output}"
    assert contract in output


def test_clean_tree_passes(lint_imports, pkg_tree):
    """干净的六包骨架必须通过(合同不误伤)。"""
    result = run_linter(lint_imports, pkg_tree)
    assert result.returncode == 0, result.stdout + result.stderr
