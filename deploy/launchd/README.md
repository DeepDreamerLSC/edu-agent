# launchd 部署件(plist)

Mac(模型服务机)用户级 LaunchAgents 模板,随 PR 入库(配置改动 = 结构类,合并键在人)。

## com.edu-agent.backup(每日备份,治理④)

- **链路** = `scripts/backup-db.sh`(单源,勿另写):VACUUM INTO 快照 + integrity_check + 行数对账 + sha256 侧车 + 原子发布 + OSS 上传(HTTPS,凭据单源 `~/.config/edu-agent/oss.env`,0600)+ 本地滚动。
- **14 天滚动(治理④:试点数据治理裁定)**:
  - 本地 `~/edu-agent-backups/`:脚本内 `find -mtime +14` 清理(默认 `OSS_BACKUP_RETENTION_DAYS=14`)。
  - OSS 备份前缀:**选型 = bucket 生命周期规则(服务端清理,零代码)**——#205 轮换后的备份钥匙为**只写**权限,实测 `ls` / `stat` / `rm` / `lifecycle` 均 403(对象列举/读/删与桶管理全不可用),客户端清理不可行,服务端规则是唯一可行路径。**一次性人配置**:桶管理员(用户)在 OSS 控制台为备份 bucket(`~/.config/edu-agent/oss.env` 的 `OSS_BUCKET`)前缀 `edu-agent-backup/` 设「14 天后删除」规则。
- **装载(合并后一次性)**:

  ```bash
  cp deploy/launchd/com.edu-agent.backup.plist ~/Library/LaunchAgents/
  launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.edu-agent.backup.plist
  launchctl kickstart -k gui/$UID/com.edu-agent.backup   # 手动触发一次验活
  tail -1 ~/Library/Logs/edu-agent/backup.log
  ```

- **验证**:`scripts/verify-db-backup.sh [备份文件]`(sha256 + integrity + 行数;不带参数取最新)。
