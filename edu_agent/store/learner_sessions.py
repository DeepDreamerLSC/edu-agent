"""LearnerSession 持久化——文件实现(生产装配已切 SqliteStore,PR #196)。

FileSessionStore 降级为**迁移源 + 复盘存档 + 合同对照**(serve_partner_api
不再注入它):migrate_json_to_sqlite.py 从 data/sessions/{session_id}.json
读入,原件保留到人工确认清理。语义:新增字段靠 dataclass 默认值从旧文件补齐;
删字段自 #198 第一步起支持——已删字段的旧键由 `restore_session` 按
dataclasses.fields() 过滤(单条 load 无隔离网,不过滤则部署前存盘会话在
重启后首回合 TypeError→503,故兼容与删字段同批闭环)。
启动扫描 = load_all()(坏文件隔离跳过,不炸全部);api 层在每次内核回合后
save()(tmp+os.replace 原子落盘,#31 runner 同款——进程被杀不留半截 JSON)。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, fields
from pathlib import Path

from edu_agent.agents.small_lecturer.session import LearnerSession, Summary


class FileSessionStore:
    """LearnerSession 的 JSON 文件存取(save/load/load_all 三操作即全接口)。"""

    def __init__(self, root: Path | str = "data/sessions") -> None:
        self.root = Path(root)

    def save(self, session: LearnerSession) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{session.session_id}.json"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(asdict(session), ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)  # 原子替换:重启恢复场景不留半截 JSON(#31 同款)

    def load(self, session_id: str) -> LearnerSession | None:
        path = self.root / f"{session_id}.json"
        if not path.exists():
            return None
        return restore_session(json.loads(path.read_text(encoding="utf-8")))

    def load_all(self) -> list[LearnerSession]:
        """启动扫描:目录内全部会话恢复为可用 session(文件名序,稳定)。

        单文件损坏(半截 JSON)只跳过该文件,不炸整个扫描——重启恢复不被
        一个坏文件全歼(审查 P2)。"""
        if not self.root.exists():
            return []
        sessions = []
        for path in sorted(self.root.glob("*.json")):
            try:
                sessions.append(restore_session(json.loads(path.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, OSError, TypeError):
                print(f"[store] 跳过损坏的会话文件:{path}")
        return sessions


def restore_session(data: dict) -> LearnerSession:
    """JSON dict → LearnerSession(文件/SQLite 两实现共用;Summary 子结构重建)。

    纯函数:拷贝入参再改——迁移对账会对同一份源 dict 调两次,原地改会 TypeError。
    未知键(已删字段的旧存盘,如 #198 第一步删的 scaffold_faded;回滚/改名遗留)
    按 dataclasses.fields() 过滤后丢弃——单条 `load()` 是 `_rehydrate` 的活路径
    (每个内核回合取本体,重启后即走),没有 load_all 的隔离网,不过滤即 503。"""
    data = dict(data)
    if data.get("summary") is not None:
        data["summary"] = Summary(**data["summary"])
    known = {field.name for field in fields(LearnerSession)}
    return LearnerSession(**{key: value for key, value in data.items() if key in known})
