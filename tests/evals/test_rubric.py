"""#254 P2:rubric 资产回归 pin——判据文本任何无意识改动在此炸(指纹随之变,须显式重注册)。"""
import hashlib
from pathlib import Path

import yaml

import edu_agent.evals
from edu_agent.evals import DIMENSION_GUIDE, user_prompt

judge_path = edu_agent.evals.judge.__file__
ASSET = Path(judge_path).parent / "rubrics" / "small_lecturer_v3_2.yaml"
# 通过资产重组还原 SYSTEM_PROMPT(不直接导入非公开名)
_rubric = yaml.safe_load(ASSET.read_text(encoding="utf-8"))
SYSTEM_PROMPT = _rubric["preamble"] + "\n\n" + DIMENSION_GUIDE

PINNED_SYSTEM_PROMPT_SHA256 = "ec7378665960f53f6c3cefb0b6eb6267ffa645e93abc9cd44d78220198a5bf78"


def test_rubric_version_and_composition():
    rubric = yaml.safe_load(ASSET.read_text(encoding="utf-8"))
    assert rubric["version"] == "small_lecturer_v3_2"
    guide = "\n\n".join(rubric[k] for k in ("dimension_guide", "math_integrity_guide", "verdict_policy"))
    assert guide == DIMENSION_GUIDE  # 组装口径:三节 "\n\n" 连接
    assert SYSTEM_PROMPT == rubric["preamble"] + "\n\n" + DIMENSION_GUIDE
    assert len(rubric["user_instructions"].split("\n")) == 4
    # user_prompt 渲染 smoke:骨架行来自 rubric 资产
    rendered = user_prompt("q", "g", "r", [{"role": "user", "content": "x"}])
    assert "逐维度按 0/1/2 打分" in rendered
    assert "只输出一个符合 Schema 的 JSON 对象" in rendered


def test_system_prompt_rendering_pinned():
    """渲染 pin:改动判据文本须显式更新此值并重注册判据指纹(#253 落档)。"""
    assert hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest() == PINNED_SYSTEM_PROMPT_SHA256
