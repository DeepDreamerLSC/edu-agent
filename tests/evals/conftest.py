"""tests/evals 夹具:scripts/ 下评测工具模块可被合同测试导入(与 tests/rules 的 rulekit 同款口径)。"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = str(Path(__file__).resolve().parents[2] / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
