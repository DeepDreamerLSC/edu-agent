"""公开文档路由合同(老系统 URL 结构兼容):/api/docs 索引 + guides raw.md。

公开免鉴权(与 /chat、/static 同段);白名单制 = 路径穿越天然免疫。
"""

from __future__ import annotations

import pytest
from partner_api import ScriptedKernel, get, serving


@pytest.fixture
def base():
    with serving(ScriptedKernel([])) as url:
        yield url


def test_docs_index_lists_all_guides_without_auth(base):
    """索引页公开可访问,列出全部 guide 链接(无 Authorization 头)。"""
    response = get(base, "/api/docs", token=None)
    assert response.status_code == 200
    assert "text/html" in response.headers["Content-Type"]
    for name in ("small-lecturer-v1", "files", "partner-sso", "response-conventions"):
        assert f"/api/docs/guides/{name}/raw.md" in response.text


def test_guide_raw_markdown_served(base):
    """guide 原文:markdown Content-Type,内容来自 docs/partner(非空且有标题)。"""
    response = get(base, "/api/docs/guides/small-lecturer-v1/raw.md", token=None)
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
    response = get(base, path, token=None)
    assert response.status_code != 200
