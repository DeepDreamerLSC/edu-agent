"""02 §5 基础设施关键词扫描红灯测试:命中 lease/heartbeat/worker_pool/scheduler/preload 即失败。"""

import pytest

from rulekit import run_py

KEYWORDS = ("lease", "heartbeat", "worker_pool", "scheduler", "preload")

SAMPLES = {
    "lease": "class LessonLease:\n    pass\n",
    "heartbeat": "heartbeat_interval = 30\n",
    "worker_pool": "WORKER_POOL = None\n",
    "scheduler": "def start_job_scheduler():\n    pass\n",
    "preload": "preload_cache = {}\n",
}


@pytest.mark.parametrize("keyword", KEYWORDS)
def test_keyword_identifier_turns_red(base_repo, keyword):
    (base_repo / "edu_agent" / "infra.py").write_text(SAMPLES[keyword], encoding="utf-8")
    result = run_py("check_infra_keywords.py", "--root", str(base_repo))
    assert result.returncode != 0
    assert "INFRA-KEYWORD" in result.stdout
    assert keyword in result.stdout.lower()


def test_clean_repo_passes(base_repo):
    result = run_py("check_infra_keywords.py", "--root", str(base_repo))
    assert result.returncode == 0, result.stdout


def test_strings_and_comments_do_not_trigger(base_repo):
    """只扫标识符,不扫字符串/注释:合作方错误码字面量(00 §5.2)不受影响。"""
    source = (
        'PARTNER_NOT_READY = "TEACHING_CONTEXT_PRELOAD_NOT_READY"'
        "  # 合作方既有错误处理兼容,字符串字面量不是标识符\n"
    )
    (base_repo / "edu_agent" / "api_errors.py").write_text(source, encoding="utf-8")
    result = run_py("check_infra_keywords.py", "--root", str(base_repo))
    assert result.returncode == 0, result.stdout
