# QRE Cloud Migration Prep

本目录是“数据库上云 + 云端 worker/DB 数据传输”的部署准备资产。**默认不执行任何迁移**，所有脚本默认 `--dry-run`。

## 文档

- 主 Runbook：`docs/agent/28_CLOUD_MIGRATION_RUNBOOK_2026-11-02.md`
- 长期路线：`docs/agent/14_LAUNCH_ROADMAP.md` §11.7

## 脚本

| 脚本 | 作用 |
|---|---|
| `backup-market-db.sh` | 本地大库一致备份（custom dump + sha256 + manifest） |
| `migrate-market-db.sh` | 逻辑迁移 `pg_restore` 到云端目标库 |
| `verify-migration.sh` | 源/目标对账：DB 大小、TimescaleDB 版本、核心表行数与 min/max |
| `sync-artifacts.sh` | 结果产物同步到对象存储并生成 sha256 manifest |
| `qre-cloud-worker.service` | 云端 worker systemd 模板 |
| `qre-cloud-worker.env.example` | 云端 worker 环境变量模板 |

## 使用顺序（真迁移时）

```bash
# 1) 预检
bash deploy/cloud/backup-market-db.sh --dry-run
bash deploy/cloud/migrate-market-db.sh --dry-run
bash deploy/cloud/verify-migration.sh --dry-run
bash deploy/cloud/sync-artifacts.sh --dry-run --src /home/van/qre-outputs --dst s3://<bucket>/qre-artifacts

# 2) 备份
bash deploy/cloud/backup-market-db.sh --out /path/to/backup

# 3) 恢复 + 对账
bash deploy/cloud/migrate-market-db.sh --full --source /path/to/backup.dump --target "$CLOUD_DB_URL"
bash deploy/cloud/verify-migration.sh --source "$HOME_DB_URL" --target "$CLOUD_DB_URL"

# 4) 产物同步
bash deploy/cloud/sync-artifacts.sh --src /home/van/qre-outputs --dst s3://<bucket>/qre-artifacts
```

## 红线

- 不自动购买云资源、不自动切流。
- 目标库非空时迁移脚本会拒绝，除非显式 `--allow-nonempty`。
- 大表 `count(*)` 很慢；验收必须跑，不接受“导入成功”作为通过。
- 迁移后 home 保留只读回滚窗口。


---

## 买云后「一键部署」入口（2026-11-03 新增）

目标：**买云后不再写代码、不再临时搭架构**，只跑一条命令完成全链路部署。

### 你只需要做 3 步

1. **按 `docs/agent/32_CLOUD_FULLSTACK_PREP_2026-11-03.md` 买好资源**
   （云 DB + 云 worker + 对象存储，全部同 VPC/同 region）。
2. **填配置**：
   ```bash
   cp deploy/cloud/cloud.env.example deploy/cloud/cloud.env
   # 编辑 cloud.env：云 DB 私网地址、worker 主机、worker token、对象存储目标
   ```
3. **先 dry-run 核对，再一键执行**：
   ```bash
   bash deploy/cloud/bootstrap-cloud.sh --dry-run   # 只打印将执行的步骤
   bash deploy/cloud/bootstrap-cloud.sh             # 备份→迁移→对账→worker→产物→验收
   ```

### 也可以分步执行
```bash
bash deploy/cloud/bootstrap-cloud.sh --step backup
bash deploy/cloud/bootstrap-cloud.sh --step migrate
bash deploy/cloud/bootstrap-cloud.sh --step verify
bash deploy/cloud/bootstrap-cloud.sh --step worker
bash deploy/cloud/bootstrap-cloud.sh --step artifacts
bash deploy/cloud/bootstrap-cloud.sh --step check
```

### 说明
- 脚本**不购买资源、不切流、不修改源库 `stock_daily`**；真迁移仍需用户批准。
- `cloud.env` 已加入 `.gitignore`，真实密码不会进仓库。
- 预检缺任何必需项会直接报错退出，不会带病执行。
