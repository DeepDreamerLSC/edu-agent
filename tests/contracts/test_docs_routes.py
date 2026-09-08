"""公开文档路由合同(老系统 URL 结构兼容):/api/docs 索引 + guides raw.md。

公开免鉴权(与 /chat、/static 同段);白名单制 = 路径穿越天然免疫。
"""

from __future__ import annotations

import httpx
import pytest
from test_api_service import _assert_local_base

from edu_agent.api import build_server, build_service


@pytest.fixture
def base():
    class StubKernel:
        def start(self, question, learner): ...
    server = build_server(build_service(StubKernel()))
    import threading

    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    yield url
    server.shutdown()
    server.server_close()


def get(base: str, path: str) -> httpx.Response:
    _assert_local_base(base)
    return httpx.get(f"{base}{path}", timeout=5.0, trust_env=False)


def test_docs_index_lists_all_guides_without_auth(base):
    """索引页公开可访问,列出全部 guide 链接(无 Authorization 头)。"""
    response = get(base, "/api/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["Content-Type"]
    for name in ("small-lecturer-v1", "files", "partner-sso", "response-conventions"):
        assert f"/api/docs/guides/{name}/raw.md" in response.text


def test_guide_raw_markdown_served(base):
    """guide 原文:markdown Content-Type,内容来自 docs/partner(非空且有标题)。"""
    response = get(base, "/api/docs/guides/small-lecturer-v1/raw.md")
    assert response.status_code == 200
    assert "text/markdown" in response.headers["Content-Type"]
    assert "小讲师" in response.text


@pytest.mark.parametrize("path", [
    "/api/docs/guides/../../pyproject/raw.md",   # 穿越尝试
    "/api/docs/guides/unknown-guide/raw.md",     # 白名单外
    "/api/docs/guides/small-lecturer-v1",        # 缺 raw.md 后缀
])
def test_non_whitelisted_docs_paths_are_not_served(base, path):
    """白名单外/穿越路径不落文档路由(401 鉴权闸或 404,绝不 200)。"""
    response = get(base, path)
    assert response.status_code != 200
