"""关键文件哨兵(#34 P0 流程修正:已合并内容静默回退的防再发闸)。

#70 事件:堆叠 PR 把已合并内容带回旧版,CI 全绿零报警。本测试断言关键交付物
存在性——vision plist、models.yaml 角色/主选、kernel schema 字段、统一 Open
三件套——任一缺失即红。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_YAML = REPO_ROOT / "configs" / "models.yaml"
VISION_PLIST = REPO_ROOT / "deploy" / "launchd" / "com.edu-agent.m0.vision-8303.plist"
KERNEL = REPO_ROOT / "edu_agent" / "agents" / "small_lecturer" / "kernel.py"
SERVER = REPO_ROOT / "edu_agent" / "api" / "server.py"
SERVICE = REPO_ROOT / "edu_agent" / "api" / "service.py"
UNIFIED_OPEN_TEST = REPO_ROOT / "tests" / "contracts" / "test_unified_open.py"


def test_vision_plist_exists():
    assert VISION_PLIST.is_file(), f"丢失 {VISION_PLIST.relative_to(REPO_ROOT)}(#70 回退哨兵)"


def test_models_yaml_has_vision_role_and_vl_tutor_primary():
    config = yaml.safe_load(MODELS_YAML.read_text(encoding="utf-8"))
    roles = config["roles"]
    assert "vision" in roles, "models.yaml 缺 vision 角色(#70 回退哨兵)"
    assert roles["tutor"]["primary"] == "qwen3_vl_8b", (
        f"tutor primary 应为 qwen3_vl_8b(VL 切换人批 2026-09-07),得到 "
        f"{roles['tutor']['primary']!r}"
    )
    assert len(roles) >= 4, f"models.yaml 角色数 {len(roles)} < 4(#34 流程修正)"


def test_kernel_vision_schema_has_transcription():
    source = KERNEL.read_text(encoding="utf-8")
    schema_block = re.search(r"OPEN_SCHEMA = \{(.*?)\n\}", source, re.DOTALL)
    assert schema_block, "kernel 缺 OPEN_SCHEMA(#70 回退哨兵)"
    assert '"transcription"' in schema_block.group(1), (
        "OPEN_SCHEMA 缺 transcription 字段(#70 回退哨兵)"
    )


def test_unified_open_router_exists():
    source = SERVER.read_text(encoding="utf-8")
    assert "_OPEN_UNIFIED" in source, "server.py 缺统一 Open 路由(#87 丢失哨兵)"


def test_unified_open_service_method_exists():
    source = SERVICE.read_text(encoding="utf-8")
    assert "def open_unified" in source, "service.py 缺 open_unified 方法(#87 丢失哨兵)"


def test_unified_open_test_file_exists():
    assert UNIFIED_OPEN_TEST.is_file(), (
        f"丢失 {UNIFIED_OPEN_TEST.relative_to(REPO_ROOT)}(#87 丢失哨兵)"
    )


def test_answer_correct_mapping_exists():
    source = SERVICE.read_text(encoding="utf-8")
    assert '"answer_status": "correct"' in source, (
        "service.py 缺 answer_correct→answer_status 映射(#90 恢复不完整哨兵,"
        "PR-4/R6 首问策略的生产端接线,丢失即裸奔绿)"
    )
    assert '"answer_correct_provenance": "partner_open"' in source, (
        "service.py 缺 partner_open provenance 标记(#90 恢复不完整哨兵)"
    )
