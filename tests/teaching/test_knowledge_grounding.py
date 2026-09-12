"""年级知识点树 → 开题年级依据(grade_grounding + 统一 open 注入)。

数据随配置走(02 §6 只导入公开入口):grade_grounding 已从包公开导出;
开题注入经 start() 全链路验证,零真实模型(假上游)。本文件是配置新增的打底:
树读不到/年级未存 → 空串,不扰动现有教学弧线。
"""

from __future__ import annotations

from fake_openai import completion

from edu_agent.agents.small_lecturer import grade_grounding, start

from teachkit import kernel_env, open_json

GRADE6_KQ = {
    "text": "鸡和兔一共有8只,共有26只脚。鸡和兔各有多少只?说明思路。",
    "knowledge_points": ["鸡兔同笼", "假设法"],
}
GRADE6_LEARNER = {"grade": "六年级"}
GRADE5_LEARNER = {"grade": "五年级"}


# ---------- grade_grounding 核心 ----------

def test_grade_grounding_matches_grade6_topic():
    # 主题名精确命中 → 该主题四级清单
    assert grade_grounding("六年级", ["鸡兔同笼"]) == "鸡兔同笼:鸡兔同笼问题"
    # 命中四级子知识点 → 归到父主题(解方程ax=b 属 简易方程)
    assert "简易方程" in grade_grounding("六年级", ["解方程ax=b"])


def test_grade_grounding_empty_when_unmatched():
    assert grade_grounding("六年级", []) == ""            # 无题目知识点
    assert grade_grounding("", ["鸡兔同笼"]) == ""         # 无年级
    assert grade_grounding("五年级", ["鸡兔同笼"]) == ""    # 五年级未存树
    assert grade_grounding("六年级", ["米勒猜想"]) == ""    # 树里没有的知识点


# 年级键精确匹配(负责人指定干净年级标签,如「六年级」);非精确即无树,不猜测。

# ---------- 开题注入:命中才注入,不命中不动弧线 ----------

def test_open_injects_grade_grounding_when_topic_matches(tmp_path):
    with kernel_env(tmp_path, [completion(open_json("这道题我们先明确一下要求什么?"))]) as (fake, gateway):
        start(GRADE6_KQ, GRADE6_LEARNER, gateway=gateway)
        user_message = fake.requests[0]["messages"][1]
        assert user_message["role"] == "user"
        assert "年级知识点依据" in user_message["content"]
        assert "鸡兔同笼" in user_message["content"]
        assert "鸡兔同笼问题" in user_message["content"]


def test_open_skips_grounding_when_grade_unmatched(tmp_path):
    with kernel_env(tmp_path, [completion(open_json("这道题我们先明确一下要求什么?"))]) as (fake, gateway):
        start(GRADE6_KQ, GRADE5_LEARNER, gateway=gateway)
        user_message = fake.requests[0]["messages"][1]
        assert "年级知识点依据" not in user_message["content"]
