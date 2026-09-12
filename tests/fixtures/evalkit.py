"""tests/evals 共享工具(02 §6 tests/fixtures:不计测试比分子)。

评测线单测的公共件:FakeLegacy+LegacyAdapter 生命周期上下文(legacy_env)、
jsonl 读写助手(write_jsonl/read_jsonl)、runner 结果目录读取(results_of)。
原散落在 test_legacy_adapter.py / test_runner.py / test_tuning_round.py,
收拢后各测试文件只保留自己的剧本与断言(与 partner_api.py 同款决策)。

谁在用:tests/evals 的 test_legacy_adapter / test_runner(test_tuning_round 部分助手)。
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from edu_agent.evals import LegacyAdapter
from fake_legacy import FakeLegacy


@contextmanager
def legacy_env(replies: list[str], **fake_kwargs) -> Iterator[tuple[FakeLegacy, LegacyAdapter]]:
    """FakeLegacy(按 replies 剧本)+ LegacyAdapter 的生命周期:进入即启动,退出即停。"""
    fake = FakeLegacy(replies, **fake_kwargs).start()
    try:
        yield fake, LegacyAdapter(base_url=fake.url)
    finally:
        fake.stop()


def write_jsonl(path: Path, rows: list) -> Path:
    """逐行 JSON 写盘(评测数据集/工件的标准形态)。"""
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
                    encoding="utf-8")
    return path


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def results_of(run_dir: Path) -> dict[str, dict]:
    """runner 结果目录 → {case_id: 结果 dict}。"""
    return {path.stem: json.loads(path.read_text(encoding="utf-8"))
            for path in (run_dir / "results").glob("*.json")}
