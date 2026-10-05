"""M7-1 B 件钉(集成面):KernelSubject result 行携带 git_sha 来源指纹(#545)。

与 git rev-parse HEAD 一致;git 缺席 None 不伪造;既有字段(session_id)照旧 additive。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from fake_openai import completion
from teachkit import kernel_env, open_json


def test_run_case_result_carries_git_sha(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    try:
        expected = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                                  capture_output=True, text=True, check=True,
                                  timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        expected = None
    with kernel_env(tmp_path, [completion(open_json("我们来看看这道题。"))]) as (_fake, gateway):
        from edu_agent.evals import KernelSubject

        result = KernelSubject(gateway).run_case(
            {"id": "spine-c", "question": "解方程 2x+5=17。", "grade": "五年级",
             "student_turns": []})
    assert result["git_sha"] == expected
    assert isinstance(result["session_id"], str)
