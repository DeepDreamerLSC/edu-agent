#!/usr/bin/env python3
"""路线 a(#256)elicit 数据集富化——合成图生成器(零依赖、零模型调用)。

为 12 个新案例各生成一张示意图 PNG(stdlib 手写 PNG 编码,无 Pillow),写入
`edu_agent/api/static/bank/`(文件名前缀 synthetic_v2_ 与真实题图池明确区分)。
完全确定性:无随机、无时间戳——重跑字节一致,数据集内 sha256 对账恒成立。

用法(仓根): .venv/bin/python edu_agent/evals/artifacts/gepa-spike/dataset-enrichment/generate_images.py
输出: 12 张 PNG + stdout 的 {文件名: sha256} JSON 映射(数据集构建输入)。
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
BANK = REPO / "edu_agent" / "api" / "static" / "bank"
W, H = 96, 72
INK = (45, 45, 45)
MARK = (200, 60, 60)
PAPER = (250, 250, 250)


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))


def encode_png(pixels: list[list[tuple[int, int, int]]]) -> bytes:
    raw = b"".join(b"\x00" + bytes(ch for px in row for ch in px) for row in pixels)
    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b""))


def canvas() -> list[list[tuple[int, int, int]]]:
    return [[PAPER for _ in range(W)] for _ in range(H)]


def px(pic: list, x: int, y: int, color=INK) -> None:
    if 0 <= x < W and 0 <= y < H:
        pic[H - 1 - y][x] = color


def rect(pic: list, x0: int, y0: int, x1: int, y1: int, fill=None) -> None:
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            edge = x in (x0, x1) or y in (y0, y1)
            if fill and not edge:
                px(pic, x, y, fill)
            elif edge:
                px(pic, x, y)


def line(pic: list, x0: int, y0: int, x1: int, y1: int, color=INK) -> None:
    dx, dy = x1 - x0, y1 - y0
    steps = max(abs(dx), abs(dy), 1)
    for i in range(steps + 1):
        px(pic, round(x0 + dx * i / steps), round(y0 + dy * i / steps), color)


def arrow(pic: list, x0: int, y0: int, x1: int, y1: int) -> None:
    line(pic, x0, y0, x1, y1)
    angle = math.atan2(y1 - y0, x1 - x0)
    for side in (-1, 1):
        a = angle + math.pi + side * 0.45
        line(pic, x1, y1, round(x1 + 6 * math.cos(a)), round(y1 + 6 * math.sin(a)))


def circle(pic: list, cx: int, cy: int, r: int) -> None:
    for i in range(3600):
        a = i / 3600 * 2 * math.pi
        px(pic, round(cx + r * math.cos(a)), round(cy + r * math.sin(a)))


def axis(pic: list) -> None:
    line(pic, 8, H - 10, W - 8, H - 10)
    line(pic, 10, 6, 10, H - 12)


def grid_u1(pic: list) -> None:  # 数对:5 列 4 行,第 3 列第 2 行标记
    for c in range(6):
        line(pic, 18 + c * 12, 10, 18 + c * 12, 58)
    for r in range(5):
        line(pic, 18, 10 + r * 12, 90, 10 + r * 12)
    for x in range(18 + 2 * 12 + 1, 18 + 3 * 12):
        for y in range(H - 1 - (10 + 2 * 12 + 1), H - 1 - (10 + 3 * 12)):
            px(pic, x, y, MARK)


def bars_u2(pic: list) -> None:  # 条形图:7/9/8/12
    axis(pic)
    for i, h in enumerate((7, 9, 8, 12)):
        x0 = 18 + i * 18
        for x in range(x0, x0 + 10):
            for y in range(10, 10 + h * 3):
                px(pic, x, H - 11 - y, INK if i % 2 else MARK)


def strips_u3(pic: list) -> None:  # 8 份涂 3 份
    rect(pic, 14, 16, 82, 48)
    for i in range(8):
        line(pic, 14 + (i + 1) * 8.5, 16, 14 + (i + 1) * 8.5, 48)
    for x in range(15, 14 + 3 * 8):
        for y in range(17, 48):
            px(pic, x, y, MARK)


def circle_u4(pic: list) -> None:  # 圆 + 直径
    circle(pic, 48, 34, 24)
    line(pic, 24, 34, 72, 34)
    px(pic, 48, 34, MARK)


def poly_s1(pic: list) -> None:  # 折线:前平缓后陡
    axis(pic)
    for x0, y0, x1, y1 in ((14, 40, 36, 36), (36, 36, 56, 30), (56, 30, 64, 16), (64, 16, 88, 8)):
        line(pic, x0, y0, x1, y1, MARK if x0 >= 56 else INK)


def strips_s2(pic: list) -> None:  # 4 份涂 1 份
    rect(pic, 20, 20, 76, 46)
    for i in range(1, 4):
        line(pic, 20 + i * 14, 20, 20 + i * 14, 46)
    for x in range(21, 34):
        for y in range(21, 46):
            px(pic, x, y, MARK)


def cards_s3(pic: list) -> None:  # 四张卡片两两一对
    for i, x0 in enumerate((12, 30, 54, 72)):
        rect(pic, x0, 22, x0 + 12, 44, fill=MARK if i in (0, 3) else None)


def compass_s4(pic: list) -> None:  # 北偏东 60°
    px0, py0 = 48, 58
    arrow(pic, px0, py0, px0, 10)
    arrow(pic, px0, py0, round(px0 + 34 * math.sin(math.radians(60))),
          round(py0 - 34 * math.cos(math.radians(60))))
    line(pic, px0 - 20, py0, px0 + 20, py0)


def rope_c1(pic: list) -> None:  # 绳 4 段剪 1 段 + 5 米段
    rect(pic, 10, 24, 62, 34)
    for i in range(1, 4):
        line(pic, 10 + i * 13, 24, 10 + i * 13, 34)
    for x in range(11, 23):
        for y in range(25, 34):
            px(pic, x, y, MARK)
    rect(pic, 70, 26, 86, 32)


def circle_c2(pic: list) -> None:  # 圆 + 周长箭头
    circle(pic, 48, 36, 24)
    for i in range(0, 900):
        a = i / 900 * 2 * math.pi
        px(pic, round(48 + 28 * math.cos(a)), round(36 + 28 * math.sin(a)), MARK)


def ribbon_c3(pic: list) -> None:  # 绳 3 段剪 1 段
    rect(pic, 14, 26, 80, 38)
    for i in range(1, 3):
        line(pic, 14 + i * 22, 26, 14 + i * 22, 38)
    for x in range(15, 36):
        for y in range(27, 38):
            px(pic, x, y, MARK)


def shop_c4(pic: list) -> None:  # 两件商品 + 套装
    rect(pic, 14, 14, 40, 40)
    rect(pic, 52, 26, 70, 40)
    rect(pic, 30, 52, 66, 64, fill=MARK)


DIAGRAMS = {
    "u1_textpos": grid_u1, "u2_bars": bars_u2, "u3_strips": strips_u3,
    "u4_circle": circle_u4, "s1_polyline": poly_s1, "s2_strips": strips_s2,
    "s3_cards": cards_s3, "s4_compass": compass_s4, "c1_rope": rope_c1,
    "c2_circle": circle_c2, "c3_ribbon": ribbon_c3, "c4_shop": shop_c4,
}


def main() -> int:
    BANK.mkdir(parents=True, exist_ok=True)
    mapping = {}
    for name, draw in DIAGRAMS.items():
        filename = f"synthetic_v2_{name}.png"
        pic = canvas()
        draw(pic)  # 原地绘制(无返回值)
        data = encode_png(pic)
        (BANK / filename).write_bytes(data)
        mapping[filename] = hashlib.sha256(data).hexdigest()
    print(json.dumps(mapping, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
