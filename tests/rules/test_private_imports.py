"""02 §6 测试私有导入检查红灯测试:测试只能导入公开入口。"""

from rulekit import run_py


def write_test_file(base_repo, source):
    tests = base_repo / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "check_something.py").write_text(source, encoding="utf-8")


def test_private_module_import_fails(base_repo):
    write_test_file(base_repo, "from edu_agent.gateway.retry import invoke\n")
    result = run_py("check_test_imports.py", "--root", str(base_repo))
    assert result.returncode != 0
    assert "PRIVATE-IMPORT" in result.stdout
    assert "edu_agent.gateway.retry" in result.stdout


def test_public_entry_imports_pass(base_repo):
    source = (
        "from edu_agent.gateway import invoke\n"
        "from edu_agent.contracts import schemas\n"
        "from edu_agent.agents.small_lecturer import start\n"
        "from edu_agent.api import app\n"
        "import edu_agent\n"
    )
    write_test_file(base_repo, source)
    result = run_py("check_test_imports.py", "--root", str(base_repo))
    assert result.returncode == 0, result.stdout


def test_non_edu_agent_imports_pass(base_repo):
    write_test_file(base_repo, "import json\nimport subprocess\nfrom pathlib import Path\n")
    result = run_py("check_test_imports.py", "--root", str(base_repo))
    assert result.returncode == 0, result.stdout
