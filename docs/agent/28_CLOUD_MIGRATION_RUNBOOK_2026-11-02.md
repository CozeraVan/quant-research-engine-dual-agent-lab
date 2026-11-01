# 28_CLOUD_MIGRATION_RUNBOOK_2026-11-02.md — 数据库上云与云端 worker/DB 传输完全准备

> 目标：**不马上迁移**，但把“决定全端上云后能快速部署”的所有准备做完。
> 本文档 + `deploy/cloud/` 脚本构成上云作业 Runbook。真迁移前必须经用户批准。

---

## 1. 当前架构与目标架构

### 1.1 当前
- 家里 WSL：数据中心 + 主测 worker。
  - 大库：PostgreSQL/TimescaleDB `tushare_data`（行情/因子/参考）。
  - Worker：`qre-saas-worker.service`（轮询 ECS SaaS 队列）。
- ECS：公网 Web/API + 小库 `aguhuice` + Nginx + 对象上传目录 `/srv/aguhuice/uploads`。
- 结果回传：worker → ECS SaaS API → ECS 本地磁盘。

### 1.2 目标（准备态）
- 云端与 ECS 同 region/同 VPC：
  - 云数据库：PostgreSQL + TimescaleDB（如 RDS 不支持 TimescaleDB，则云主机自建 PG）。
  - 云 worker：ECS 同 VPC 计算实例，只连私网 DB，不出公网。
  - 对象存储：OSS/S3 存大产物；SaaS 小库只存元数据。
- 家里 WSL：迁移后先保留只读回滚窗口，验收后再停写。

---

## 2. 迁移范围与基线（2026-11-02 实测）

### 2.1 大库 `tushare_data`
- 总大小：**519 GB**（`pg_database_size`）。
- 核心表：
  | 表 | 行数 | 时间范围 | 体量 |
  |---|---:|---|---:|
  | `public.stock_daily` | 14,888,045 | 2009-01-05 ~ 2026-10-30 | 4.7 GB |
  | `public.stock_minute_1m` | 3,648,592,718 | 2009-01-05 ~ 2026-10-21 | 241 GB（708/922 chunk 已压缩） |
  | `factors.stock_daily_overlap_close` | 14,888,286 | 2009-01-05 ~ 2026-10-30 | 16 GB |
  | `factors.stock_daily_momentum_close` | 16,264,829 | 2009-01-05 ~ 2026-10-30 | 24 GB |
  | `factors.stock_daily_alpha191` | 16,162,861 | 2009-01-05 ~ 2026-10-30 | 43 GB |
  | `reference.stock_basic` | 5,531 | — | <1 MB |
- 其他大表：
  - `cluster.daily_tags` 7.6 GB（聚类/标签分析用；可选迁移）。
  - `public.stock_daily_repair_20261028` 3.0 GB（历史修复影子表；建议**不迁移**，仅归档）。
- 重要口径：
  - 日线/因子为原始价 + `adj_factor` 口径，迁移后必须保持 `factor_basis = qfq_anchor_v1` 契约。
  - 分钟线为 TimescaleDB hypertable，压缩状态必须迁移后复核。

### 2.2 SaaS 小库 `aguhuice`
- 现已在 ECS，无需从 WSL 迁移；但上云前要确认：
  - `cloud_schema.sql` 已 apply；
  - 每日 `pg_dump` 与本地拉取备份可用；
  - 结果元数据、showcase、share_links、nl 缓存等表在云端 authoritative。

### 2.3 产物
- 本地 `/home/van/qre-outputs` 当前约 536M（历史清理后）。
- ECS `/srv/aguhuice/uploads` 为线上结果；上云后大文件应迁到对象存储。

---

## 3. 上云架构准备（部署即就绪）

### 3.1 数据库
- 目标准备：
  - region 与 ECS 相同；私网地址，禁止公网 5432。
  - PostgreSQL 主版本与本地一致（当前本地以 `psql` 实际版本为准，迁移前必须核对）。
  - TimescaleDB 扩展可用；`timescaledb_information` 可查。
  - 参数：shared_buffers、work_mem、maintenance_work_mem、max_connections、effective_cache_size 按目标规格预设。
  - 备份：每日全量 + WAL/PITR；保留 7 天以上。
- 迁移方式二选一，Runbook 均支持：
  1. **逻辑迁移**：`pg_dump -Fc` + `pg_restore -j`。适合跨版本/跨类型。
  2. **物理/复制**：基础备份 + WAL 或逻辑复制。适合大库低 RPO。

### 3.2 worker
- `deploy/cloud/qre-cloud-worker.service`：云端 systemd 模板。
- `deploy/cloud/qre-cloud-worker.env.example`：机密与连接模板。
- 关键点：
  - worker 与 DB 同 VPC，使用私网 DNS/Endpoint。
  - `QRE_SAAS_BASE_URL` 指向云端 SaaS；`QRE_WORKER_TOKEN` 与 SaaS 一致。
  - `QRE_MARKET_DB_URL` 使用云端只读账号（至少 SELECT）。
  - 产物上传优先直传对象存储；SaaS 只收 manifest。
  - 槽位/内存闸门沿用现有环境变量。

### 3.3 结果与对象存储
- `deploy/cloud/sync-artifacts.sh`：把本地/ECS 产物同步到 OSS/S3。
- 命名：`artifacts/<job_id>/<relative_path>`；manifest 记录 sha256 与 size。
- SaaS 读取：优先对象存储 presigned URL；缺失回退 ECS 本地盘（过渡期）。

---

## 4. 数据迁移流程（准备态，不执行）

### 4.1 预检
```bash
bash deploy/cloud/backup-market-db.sh --dry-run
bash deploy/cloud/migrate-market-db.sh --dry-run
bash deploy/cloud/verify-migration.sh --dry-run
```

### 4.2 全量
```bash
# 1) 本地一致备份 + manifest
bash deploy/cloud/backup-market-db.sh --out /path/to/backup

# 2) 传到云端（内网/OSS）
# 3) 云端恢复
bash deploy/cloud/migrate-market-db.sh --full --source /path/to/backup.dump --target "$CLOUD_DB_URL"

# 4) 对账
bash deploy/cloud/verify-migration.sh --source "$HOME_DB_URL" --target "$CLOUD_DB_URL"
```

### 4.3 增量追数
- 日线/因子按 `trade_date` watermark 增量。
- 分钟线按 `trade_time` 或 hypertable chunk 区间增量。
- 每批记录：起止时间、行数、checksum、应用版本。

### 4.4 双读/影子
- 云 worker 先跑小样本 → 全量影子。
- 与 home 结果逐任务对账：收益、交易数、产物 sha256。
- 灰度切流：按 job 类型/百分比切云端；home 保留只读回滚。

---

## 5. 校验清单（必须全绿才能切流）

- [ ] 表清单一致（含 schema/extension）。
- [ ] 行数一致：核心表逐一比对。
- [ ] 最大交易日一致：日线/因子/分钟线。
- [ ] 抽样 checksum 一致：按主键抽样。
- [ ] `factor_basis` 契约一致：`qfq_anchor_v1`。
- [ ] Timescale chunk/压缩状态一致。
- [ ] GRANT/权限最小化：worker 只读，SaaS 写小库。
- [ ] 备份恢复演练通过。
- [ ] 云 worker 小样本/全量性能达标。
- [ ] 回滚窗口内 home 可重新切回。

---

## 6. 风险与红线

- **不修改源数据**：迁移前 `stock_daily` 只读；任何修复走影子表。
- **不只看“导入成功”**：必须行数/日期/校验和对账。
- **不做不可逆切换**：home 保留只读回滚窗口。
- **worker 与 DB 同 region**：减少跨公网传输与延迟。
- **大文件走对象存储**：避免 SaaS 磁盘打爆。
- 成本/规格需用户确认：本 Runbook 不自动购买资源。

---

## 7. 相关文件

- `deploy/cloud/backup-market-db.sh`
- `deploy/cloud/migrate-market-db.sh`
- `deploy/cloud/verify-migration.sh`
- `deploy/cloud/sync-artifacts.sh`
- `deploy/cloud/qre-cloud-worker.service`
- `deploy/cloud/qre-cloud-worker.env.example`
- `deploy/cloud/README.md`
