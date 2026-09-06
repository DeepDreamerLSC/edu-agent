"""学生内容脱敏(01 §7):在记录之前把消息体替换为长度与 sha256 前 16 位,内容绝不进记录。"""

from __future__ import annotations

import hashlib


def redact_text(text: str) -> dict:
    """单条文本的脱敏形态:只有长度与哈希。"""
    return {"len": len(text), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]}


def redact_messages(messages: list[dict]) -> list[dict]:
    """事实记录 edu.redacted 字段的载荷:每条消息只留 role 与长度+哈希。"""
    return [
        {"role": message.get("role"), **redact_text(str(message.get("content", "")))}
        for message in messages
    ]
