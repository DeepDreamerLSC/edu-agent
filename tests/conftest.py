"""tests 公共夹具路径:tests/fixtures 下的假上游服务器等基础设施可供各合同测试目录复用(02 §6)。"""

from __future__ import annotations

import sys
from pathlib import Path

_FIXTURES = str(Path(__file__).resolve().parent / "fixtures")
if _FIXTURES not in sys.path:
    sys.path.insert(0, _FIXTURES)
