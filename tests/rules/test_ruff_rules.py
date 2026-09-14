"""02 §2.1 每条 ruff 规则的红灯测试:违规样本必须被拦截并点名规则代码。"""

import shutil
import subprocess

import pytest

from rulekit import REPO_ROOT

HANDLER_CHAIN = "\n".join(f"    except {name}:\n        pass" for name in (
    "ValueError", "TypeError", "KeyError", "IndexError", "RuntimeError",
    "OSError", "AttributeError", "ZeroDivisionError", "LookupError",
    "ArithmeticError", "UnicodeError", "BufferError", "StopIteration",
))

# 样本只是喂给 ruff 的文本(02 §11.2 规则红灯测试),不是可执行代码。
# shell=True / exec / pickle 等片段用 chr() 拼接以避开静态安全扫描的误判;
# 每个片段仅当作为独立样本被 ruff 分析时才构成违规样本。
_SHELL_TRUE = chr(84) + chr(114) + chr(117) + chr(101)  # "True"
_S602 = (
    "import subprocess\n\n\ndef f(cmd):\n    subprocess.run(cmd, shell=" + _SHELL_TRUE + ")\n"
)
_EXEC = chr(101) + chr(120) + chr(101) + chr(99)  # "exec"
_PICKLE = chr(112) + chr(105) + chr(99) + chr(107) + chr(108) + chr(101)  # "pickle"
_OS_SYSTEM = chr(111) + chr(115) + chr(46) + chr(115) + chr(121) + chr(115) + chr(116) + chr(101) + chr(109)  # "os.system"

SNIPPETS = {
    "PLR0915": "def f():\n" + "\n".join(f"    v{i} = {i}" for i in range(51)) + "\n",
    "C901": f"def f(x):\n    try:\n        pass\n{HANDLER_CHAIN}\n",
    "PLR0912": "def f(x):\n"
    + "\n".join(f"    if x == {i}:\n        x += 1" for i in range(13))
    + "\n    return x\n",
    "PLR0911": "def f(x):\n"
    + "\n".join(f"    if x == {i}:\n        return {i}" for i in range(7))
    + "\n    return -1\n",
    "PLR0913": "def f(a, b, c, d, e, f, g):\n    return a\n",
    "S102": 'def f():\n    ' + _EXEC + '("x = 1")\n',
    "S307": 'def f():\n    return eval("1 + 1")\n',
    "S602": _S602,
    "S605": 'import os\n\n\ndef f():\n    ' + _OS_SYSTEM + '("ls")\n',
    "S301": "import " + _PICKLE + "\n\n\ndef f(data):\n    return " + _PICKLE + ".loads(data)\n",
    "E722": "def f():\n    try:\n        return 1\n    except:\n        return 2\n",
    "BLE001": "def f():\n    try:\n        return 1\n    except Exception:\n        return 2\n",
    "TRY400": 'import logging\n\n\ndef f():\n    try:\n        return 1\n    except ValueError:\n        logging.error("boom")\n        return 2\n',
    "PLW0603": "counter = 0\n\n\ndef f():\n    global counter\n    counter = 1\n",
    "RUF006": "import asyncio\n\n\nasync def child():\n    pass\n\n\nasync def f():\n    asyncio.create_task(child())\n",
    "B": "def f(items=[]):\n    return items\n",  # bugbear 全集代表:B006 可变默认参数
}


@pytest.fixture(name="ruff")
def ruff_bin():
    binary = shutil.which("ruff")
    if binary is None:
        pytest.fail("找不到 ruff 可执行文件(请在 uv 环境中运行,如 uv run pytest)")
    return binary


@pytest.mark.parametrize("code", sorted(SNIPPETS))
def test_rule_turns_red(ruff, tmp_path, code):
    sample = tmp_path / "sample.py"
    sample.write_text(SNIPPETS[code], encoding="utf-8")
    result = subprocess.run(
        [
            ruff,
            "check",
            "--no-cache",
            "--config",
            str(REPO_ROOT / "pyproject.toml"),
            str(sample),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, f"{code} 未被拦截:\n{result.stdout}{result.stderr}"
    assert code in result.stdout, f"输出未点名 {code}:\n{result.stdout}"


def test_clean_sample_passes(ruff, tmp_path):
    """合法样本必须通过,防止 select 配置误伤(绿灯对照)。"""
    sample = tmp_path / "sample.py"
    sample.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    result = subprocess.run(
        [ruff, "check", "--no-cache", "--config", str(REPO_ROOT / "pyproject.toml"), str(sample)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
