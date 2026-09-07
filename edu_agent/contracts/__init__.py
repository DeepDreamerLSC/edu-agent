"""合作方接口合同快照(00 §5.2「合同快照来源」;contracts 包首次激活)。

数据即规格:本包只放合同数据与轻量加载校验(零第三方依赖),M3 的 api 包装层
按这些文件实现,合同测试(tests/contracts/)按它们断言。
- public_openapi_required_paths.json:题库/题图工作台面 16 条必需路径(老合同脚本原样);
- partner_endpoints.json:小讲师对话面端点/错误码/不变式(00 §5.2 复用清单落位);
- postman/:合作方 Postman 集合与环境变量(逐字节原样,含占位符无真实凭据);
- skill_interaction_definition_v1.json / skill_interaction_v1.schema.json:
  Skill 交互输入定义与响应信封(字段与枚举自老 pydantic 模型转换)。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_CONTRACTS_DIR = Path(__file__).resolve().parent


def _load_json(name: str) -> dict:
    return json.loads((_CONTRACTS_DIR / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def public_openapi_paths() -> dict:
    """题库/题图工作台面 16 条必需路径清单(路径+方法+语义注记)。"""
    return _load_json("public_openapi_required_paths.json")


@lru_cache(maxsize=1)
def partner_endpoints() -> dict:
    """小讲师对话面端点、错误码表与必须保留的约定(00 §5.2)。"""
    return _load_json("partner_endpoints.json")


@lru_cache(maxsize=1)
def skill_interaction_schema() -> dict:
    """skill_interaction/v1 响应信封 JSON Schema。"""
    return _load_json("skill_interaction_v1.schema.json")


@lru_cache(maxsize=1)
def skill_interaction_definition() -> dict:
    """skill_interaction_definition/v1 输入定义(老 skills/small-lecturer-coaching/interaction.json 原样)。"""
    return _load_json("skill_interaction_definition_v1.json")


def postman_dir() -> Path:
    return _CONTRACTS_DIR / "postman"
