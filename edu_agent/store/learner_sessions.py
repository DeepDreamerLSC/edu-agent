"""LearnerSession 文件持久化(M3 PR6,00 §5.2 上下文保留;02:文件就是 v1 的 store)。

一会话一文件:data/sessions/{session_id}.json;不用数据库不用 SQLite。
additive-only:LearnerSession 新增字段靠 dataclass 默认值从旧文件补齐,
不删字段、不写迁移。启动扫描 = load_all();api 层在每次内核回合后 save()。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from edu_agent.agents.small_lecturer.session import LearnerSession, Summary


class FileSessionStore:
    """LearnerSession 的 JSON 文件存取(save/load/load_all 三操作即全接口)。"""

    def __init__(self, root: Path | str = "data/sessions") -> None:
        self.root = Path(root)

    def save(self, session: LearnerSession) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{session.session_id}.json"
        path.write_text(json.dumps(asdict(session), ensure_ascii=False), encoding="utf-8")

    def load(self, session_id: str) -> LearnerSession | None:
        path = self.root / f"{session_id}.json"
        if not path.exists():
            return None
        return self._restore(json.loads(path.read_text(encoding="utf-8")))

    def load_all(self) -> list[LearnerSession]:
        """启动扫描:目录内全部会话恢复为可用 session(文件名序,稳定)。"""
        if not self.root.exists():
            return []
        return [self._restore(json.loads(path.read_text(encoding="utf-8")))
                for path in sorted(self.root.glob("*.json"))]

    @staticmethod
    def _restore(data: dict) -> LearnerSession:
        if data.get("summary") is not None:
            data["summary"] = Summary(**data["summary"])
        return LearnerSession(**data)
