"""matched-surface renderer/runner 机械测试:格式行/锚框架/暴露检测/泄漏门/执行附录。

不触网零模型;用合成 mini-pack(一 plain 案 + 一 dict 题面含 answer 案)走
parse → render → build → assert 全链,并锚 P0-1 系统级执行附录的前缀完整性。
"""

from __future__ import annotations

import hashlib
import json

import d6d7_gold_consume as gc  # scripts/(conftest 挂载)
import d6d7_matched_surface as ms

MINI_PACK = """# 包头
---
## P1-01
**题面**:47本书每6本装一盒，至少需要多少个盒子？

逐轮原文:
- [轮0·学生] (无学生输入)
- [轮0·Tutor] 你好同学,这道题你的答案是什么呀?
- [轮1·学生] 47除以6等于7余5。
- [轮1·Tutor] ▶ **判定锚** 那剩下的5本书还需要再加一个盒子吗?

**P1-01 标注**:S2a=____ S2b=____
---
## P1-02
**题面**:{'text': '一个圆的直径是 10 厘米,半径是多少?', 'answer': '5厘米'}
**年级**:六年级

逐轮原文:
- [轮0·学生] (无学生输入)
- [轮0·Tutor] 你好同学,这道题你的答案是什么呀?
- [轮1·学生] 半径是 5 厘米。
- [轮1·Tutor] ▶ **判定锚** 说得对。

**P1-02 标注**:S2a=____ S2b=____
"""

GOLD = {"cases": [
    {"blind_id": "P1-01", "s2a": "NO", "s2b": "NO"},
    {"blind_id": "P1-02", "s2a": "NO", "s2b": "YES"},
]}


def test_render_format_and_anchor():
    cases = ms.parse_pack(MINI_PACK)
    prompt = ms.render_user_prompt(cases["P1-01"])
    lines = prompt.splitlines()
    assert lines[0] == "【题面】47本书每6本装一盒，至少需要多少个盒子？"
    assert "【年级】" not in prompt  # 无年级行不渲染
    assert "学生(轮1):47除以6等于7余5。" in lines
    assert "小讲师(轮1):那剩下的5本书还需要再加一个盒子吗?" in lines
    assert any(line.startswith("【判定锚】判定对象 = 小讲师(轮1)") for line in lines)
    assert prompt.count("【判定锚】") == 1
    # 引擎尾部输出要求逐字共享(renderer 模块引用的 _USER_INSTRUCTIONS)
    assert lines[-2:] == ms._USER_INSTRUCTIONS


def test_grade_line_and_exposure():
    cases = ms.parse_pack(MINI_PACK)
    prompt = ms.render_user_prompt(cases["P1-02"])
    assert "【年级】六年级" in prompt.splitlines()
    assert ms.answer_exposed(cases["P1-02"]["question"]) is True
    assert ms.answer_exposed(cases["P1-01"]["question"]) is False


def test_build_rows_and_leak_gate():
    rows = ms.build_rows(ms.parse_pack(MINI_PACK), GOLD)
    assert [row["case_id"] for row in rows] == ["P1-01", "P1-02"]
    assert rows[0]["answer_exposed"] is False
    assert rows[1]["answer_exposed"] is True
    assert rows[1]["gold"] == {"s2a": "NO", "s2b": "YES"}
    ms.assert_surface(rows)  # 泄漏门零命中
    # gold 标签不进 user_prompt(P1-2 防火墙镜像;合成案内容不含 YES 字样)
    assert "YES" not in rows[1]["user_prompt"]


def test_missing_anchor_refused():
    cases = ms.parse_pack(MINI_PACK)
    cases["P1-01"]["turns"] = [t for t in cases["P1-01"]["turns"] if not t[3]]
    try:
        ms.render_user_prompt(cases["P1-01"])
    except AssertionError:
        return
    raise SystemExit("缺锚案应拒绝渲染")


def test_gold_json_shape_matches_builder():
    # gold 真件字段形态(builder 消费面):cases[].blind_id/s2a/s2b
    for case in GOLD["cases"]:
        assert {"blind_id", "s2a", "s2b"} <= set(case)
    json.dumps(GOLD)  # 可序列化


def test_system_addendum_p0_1():
    """P0-1(#485 冻结审):附录存在、只桥接输入形态、sha 可复算、前缀完整。"""
    assert gc._SYSTEM_ADDENDUM.startswith("【matched-surface 执行附录")
    # 只桥接输入形态,不做任何判据语义改写
    for banned in ("改为", "不适用", "忽略上述", "override", "以本附录为准"):
        assert banned not in gc._SYSTEM_ADDENDUM
    assert gc._addendum_sha() == hashlib.sha256(
        gc._SYSTEM_ADDENDUM.encode()).hexdigest()
    # 系统消息 = 冻结件逐字前缀 + 附录(经 runner 自身的公开属性引用,不私有导入)
    content = gc._system_content()
    assert content.startswith(gc.SYSTEM_PROMPT)
    assert content.endswith(gc._SYSTEM_ADDENDUM)
