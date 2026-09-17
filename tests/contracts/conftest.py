"""合同测试共享 server fixture(#97 ①):启停脚手架单点化。

体在 partner_api.serve_fixture(02 §6:fixtures 不计测试比分子),此处仅绑定。
"""

from __future__ import annotations

import pytest

from partner_api import serve_fixture

serve = pytest.fixture(serve_fixture)
