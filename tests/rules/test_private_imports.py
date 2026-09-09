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
        "from edu_agent.evals import Runner\n"
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


def test_from_import_private_submodule_fails(base_repo):
    """from 公开入口 import 私有子模块也算私有导入(评审发现的绕过路径,已修)。"""
    gateway = base_repo / "edu_agent" / "gateway"
    gateway.mkdir()
    (gateway / "middleware.py").write_text("def wrap():\n    pass\n", encoding="utf-8")
    write_test_file(base_repo, "from edu_agent.gateway import middleware\n")
    result = run_py("check_test_imports.py", "--root", str(base_repo))
    assert result.returncode != 0
    assert "PRIVATE-IMPORT" in result.stdout
    assert "edu_agent.gateway.middleware" in result.stdout


def test_from_import_public_entry_submodule_passes(base_repo):
    """from edu_agent.agents import small_lecturer 是公开入口,必须放行。"""
    agents = base_repo / "edu_agent" / "agents"
    agents.mkdir()
    (agents / "small_lecturer.py").write_text("def start():\n    pass\n", encoding="utf-8")
    write_test_file(base_repo, "from edu_agent.agents import small_lecturer\n")
    result = run_py("check_test_imports.py", "--root", str(base_repo))
    assert result.returncode == 0, result.stdout


def test_from_public_prefix_import_private_submodule_fails(base_repo):
    """公开入口的父路径(edu_agent.agents)下 import 私有子模块,同样拦下。"""
    agents = base_repo / "edu_agent" / "agents"
    agents.mkdir()
    (agents / "kernel.py").write_text("def reply():\n    pass\n", encoding="utf-8")
    write_test_file(base_repo, "from edu_agent.agents import kernel\n")
    result = run_py("check_test_imports.py", "--root", str(base_repo))
    assert result.returncode != 0
    assert "PRIVATE-IMPORT" in result.stdout
    assert "edu_agent.agents.kernel" in result.stdout


def test_from_package_import_public_package_passes(base_repo):
    """from edu_agent import gateway 引入的是公开入口包本身,放行。"""
    write_test_file(base_repo, "from edu_agent import gateway\nfrom edu_agent import contracts\n")
    result = run_py("check_test_imports.py", "--root", str(base_repo))
    assert result.returncode == 0, result.stdout


def test_unknown_test_directory_fails(base_repo):
    """tests/ 下出现六类(+fixtures)之外目录 → 非零退出(防止目录漂移无 CI 拦截)。"""
    unknown = base_repo / "tests" / "whatever"
    unknown.mkdir(parents=True)
    (unknown / "check.py").write_text("import json\n", encoding="utf-8")
    result = run_py("check_test_imports.py", "--root", str(base_repo))
    assert result.returncode != 0
    assert "whatever" in result.stdout


def test_six_classes_and_fixtures_dirs_pass(base_repo):
    """六类目录 + fixtures 都放行,不误报。"""
    for name in ("teaching", "gateway", "contracts", "e2e", "rules", "evals", "fixtures"):
        (base_repo / "tests" / name).mkdir(parents=True)
    result = run_py("check_test_imports.py", "--root", str(base_repo))
    assert result.returncode == 0, result.stdout
