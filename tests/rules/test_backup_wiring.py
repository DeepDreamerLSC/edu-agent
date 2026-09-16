"""备份接线哨兵(治理④:launchd 定时备份 + 14 天滚动;派单 backup-plist r2,2026-09-16)。

断言守住已实测的接线事实,任一被改回即红:

1. 备份 plist 存在、每日定时触发(StartCalendarInterval)、调用 scripts/backup-db.sh;
2. 首进程 = TCC 已授权的 uv python3.12,bash 作子进程(launchd 直跑 bash 被 TCC 拒,
   EPERM 实测 2026-09-16);
3. plist 不含任何凭据(真相源只能是 0600 的 ~/.config/edu-agent/oss.env);
4. 脚本本地滚动默认 14 天(治理④;M3 旧默认 7 不得改回),连 .sha256 侧车一起删;
5. 远端滚动选型登记在 deploy/launchd/README.md:OSS 生命周期规则(桶管理员一次性
   配置)——备份钥匙只写(ls/stat/rm/lifecycle 实测 403),客户端清理不可行。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLIST = REPO / "deploy" / "launchd" / "com.edu-agent.backup.plist"
SCRIPT = REPO / "scripts" / "backup-db.sh"
README = REPO / "deploy" / "launchd" / "README.md"
LABEL = "com.edu-agent.backup"


def test_backup_plist_daily_and_wired_to_script():
    template = PLIST.read_text(encoding="utf-8")
    assert f"<string>{LABEL}</string>" in template
    assert "scripts/backup-db.sh" in template, "plist 必须调用 backup-db.sh(链路单源,勿另写)"
    assert "<key>StartCalendarInterval</key>" in template, "每日定时触发(治理④)"
    assert "<key>Hour</key>" in template and "<key>Minute</key>" in template


def test_backup_plist_launcher_survives_tcc():
    """首进程必须是 TCC 已授权的 uv python(DesktopFolder),bash 作子进程继承授权;
    launchd 直跑 /bin/bash 实测被 macOS TCC 拒(EPERM,2026-09-16)。"""
    template = PLIST.read_text(encoding="utf-8")
    assert "uv/python" in template and "python3.12" in template, (
        "启动器必须是有 TCC DesktopFolder 授权的 uv python3.12(与 partner-api 同源)"
    )
    assert 'subprocess.call(["/bin/bash"' in template, "bash 只能作 python 的子进程"


def test_backup_plist_has_no_credentials():
    template = PLIST.read_text(encoding="utf-8")
    for leak in ("OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_SECRET", "accessKeySecret"):
        assert leak not in template, f"凭据不得进 plist(真相源 = 0600 oss.env):{leak}"


def test_local_rolling_default_is_14_days():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "OSS_BACKUP_RETENTION_DAYS:-14" in source, (
        "本地滚动默认必须 14 天(治理④);M3 旧默认 7 不得改回"
    )


def test_local_rolling_covers_sha256_sidecar():
    source = SCRIPT.read_text(encoding="utf-8")
    m = re.search(r'find "\$DIR".*?-delete', source, re.S)  # find 命令折行,跨行匹配
    assert m, "本地滚动 find 必须存在"
    assert '-mtime "+$RETENTION"' in m.group(0)
    assert "edu-agent-*.db.sha256" in m.group(0), "侧车 .sha256 必须随备份一起滚动删除"


def test_remote_rolling_choice_registered_in_readme():
    readme = README.read_text(encoding="utf-8")
    assert "生命周期" in readme and "14" in readme
    assert "403" in readme, "选型理由必须留实证:备份钥匙只写,客户端清理不可行"
