"""缓存命中 token 的三种命名兜底(#142 step2):OpenAI / llama.cpp / DeepSeek。

llama.cpp 本地服务(8302/8303)在 `usage.prompt_tokens_details.cached_tokens` 报缓存命中;
该字段此前不进兜底链 → `edu.usage.cache_read.input_tokens` 对本地模型恒为 null,
"缓存归一化 TTFT"(#142 step3)无数据可用。本测试锁住三种命名都能落到 facts。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fake_openai import FakeOpenAI, completion

from edu_agent.gateway import ModelRequest

from gwkit import gateway_for


def facts_line(facts_dir: Path) -> dict:
    files = list(Path(facts_dir).glob("model_calls-*.jsonl"))
    assert len(files) == 1, "单次调用应只有一个事实文件"
    lines = files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


@pytest.mark.parametrize(
    ("usage", "expected"),
    [
        # OpenAI 官方命名
        ({"prompt_tokens": 11, "completion_tokens": 7,
          "prompt_tokens_details": {"cache_read_input_tokens": 1024}}, 1024),
        # llama.cpp 命名(#142 step2 新增)
        ({"prompt_tokens": 11, "completion_tokens": 7,
          "prompt_tokens_details": {"cached_tokens": 768}}, 768),
        # DeepSeek 命名(issue #3)
        ({"prompt_tokens": 11, "completion_tokens": 7,
          "prompt_cache_hit_tokens": 512}, 512),
        # 三者都没有 → 保持 None(不得凭空造值)
        ({"prompt_tokens": 11, "completion_tokens": 7}, None),
    ],
)
def test_cache_read_naming_fallback(tmp_path, usage, expected):
    server = FakeOpenAI([completion("答案", usage=usage)]).start()
    try:
        gateway = gateway_for(server.url, tmp_path)
        gateway.invoke(ModelRequest(role="tutor", messages=[{"role": "user", "content": "题"}],
                                    max_tokens=8))
        gateway.close()
    finally:
        server.stop()
    assert facts_line(tmp_path)["gen_ai.usage.cache_read.input_tokens"] == expected
