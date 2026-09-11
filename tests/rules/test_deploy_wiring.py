"""部署接线哨兵(2026-09-11 部署演练:部署链路原本只覆盖探活服务,对外服务不受管)。

四条断言对应四个实测过的坑,任一被改回即红:

1. `deploy.sh` 缺 `-E`(errtrace)→ **函数内失败不触发 ERR trap**,`finish failed`
   不执行,台账零记录(实测:非交互 shell 缺 `uv`,step_sync 失败,台账无痕);
2. 被部署的服务必须是**对话服务**(自带 /healthz),healthz 专用独立进程已删——
   回到两个服务就是"同一环境两个端口",违反 04 §2.1;
3. plist 模板的两个占位符必须都被 deploy.sh 替换(漏替换 → launchd 读到字面量);
4. 启动器必须自己读 `.env.<EDU_ENV>`:launchd 不继承 shell 环境,实测 plist 里
   没有 IDENTITY_* 时登录直接 503(凭据的真相源只能是那个 600 文件)。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEPLOY_SH = REPO / "scripts" / "deploy.sh"
LAUNCHD = REPO / "deploy" / "launchd"
LAUNCHER = REPO / "scripts" / "serve_partner_api.py"
APP_LABEL = "com.edu-agent.partner-api"
APP_PORT = 8300


def test_deploy_script_enables_errtrace():
    source = DEPLOY_SH.read_text(encoding="utf-8")
    assert re.search(r"^set -eEuo pipefail", source, re.M), (
        "缺 -E(errtrace):函数内失败不写台账,04 §2.1 的「成功与失败都记」不成立"
    )


def test_deployed_service_is_the_dialogue_service_only():
    source = DEPLOY_SH.read_text(encoding="utf-8")
    assert APP_LABEL in source, "deploy.sh 必须部署对话服务"
    assert (LAUNCHD / f"{APP_LABEL}.plist").is_file()
    assert not (LAUNCHD / "com.edu-agent.app.plist").exists(), (
        "healthz 专用独立服务已删:同一环境只留一个服务、一个端口(04 §2.1)"
    )


def test_single_port_across_wiring():
    template = (LAUNCHD / f"{APP_LABEL}.plist").read_text(encoding="utf-8")
    source = DEPLOY_SH.read_text(encoding="utf-8")
    assert f"APP_PORT={APP_PORT}" in source
    assert re.search(
        rf"<key>EDU_PARTNER_API_PORT</key>\s*<string>{APP_PORT}</string>", template
    ), "plist 必须把服务钉在同一个端口上"


def test_deploy_script_reexecs_after_updating_itself():
    """脚本 reset 的是自己所在的 checkout:不换一份跑,bash 会按偏移读到新旧混用。"""
    source = DEPLOY_SH.read_text(encoding="utf-8")
    assert "DEPLOY_REEXEC" in source and re.search(r"exec env DEPLOY_REEXEC=1", source)


def test_plist_placeholders_are_substituted_by_deploy_script():
    template = (LAUNCHD / f"{APP_LABEL}.plist").read_text(encoding="utf-8")
    source = DEPLOY_SH.read_text(encoding="utf-8")
    for placeholder in ("__DEPLOY_ROOT__", "__ENV_NAME__"):
        assert placeholder in template, f"模板缺占位符 {placeholder}"
        assert placeholder in source, f"{placeholder} 未被 deploy.sh 替换"


def test_launcher_reads_env_file():
    source = LAUNCHER.read_text(encoding="utf-8")
    assert ".env." in source and "EDU_ENV" in source, (
        "启动器必须按 EDU_ENV 读 .env.<ENV>(launchd 不继承 shell 环境)"
    )
