# 32_CLOUD_FULLSTACK_PREP_2026-11-03.md — 全链上云预准备：吞吐/传输优化与整体架构

> 目标（用户 2026-11-03 明确要求）：**不马上上云**，但把「数据库、计算端、服务端」全链上云
> 所需的准备全部做完，包括数据备份、DB 吞吐优化、DB↔计算端传输优化与整体架构，
> 使租用云服务器后能在**短时间内快速部署**。
> 前置文档：`28_CLOUD_MIGRATION_RUNBOOK_2026-11-02.md`（备份/迁移/对账/worker 模板已就绪）。
> 本文是其补充，重点在**性能与传输**，不重复迁移流程。
> 资源画像依据：`31_RESOURCE_MODEL_2026-11-03.md`。

---

## 1. 目标全链架构（准备态）

```
用户/外部 Agent
     │ HTTPS
     ▼
ECS SaaS（公网 Web/API/队列/小库 aguhuice）
     │ 私网（同 VPC）
     ├──────────────► 云 DB：PostgreSQL + TimescaleDB（主库）
     │                    ├─ 只读副本（可选，供 worker 大查询）
     │                    └─ 每日全量备份 + WAL/PITR
     │
     ▼
云 worker（计算实例，可多开）
     │ 私网只读连接云 DB（或只读副本）
     │ 执行回测 → 产物直传对象存储（分片+压缩）
     ▼
对象存储 OSS/S3（产物）  ←─  SaaS 只存 manifest/元数据，用 presigned URL 分发
```

关键原则：
- **计算与数据同 region/同 VPC**，worker 不出公网；
- **SaaS 小库只存元数据**，大产物一律走对象存储，不堆在 ECS 本地盘；
- **先读后写分离**：worker 的大查询可打到只读副本，主库只承担写入与日更。

---

## 2. 已就绪与缺口清单

### 2.1 已就绪（无需重做）
- `deploy/cloud/backup-market-db.sh`：本地一致备份 + manifest（dry-run 已过）。
- `deploy/cloud/migrate-market-db.sh`：`pg_dump -Fc` + `pg_restore -j` 逻辑迁移（dry-run 已过）。
- `deploy/cloud/verify-migration.sh`：行数/日期/校验和对账（dry-run 已过）。
- `deploy/cloud/sync-artifacts.sh`：产物同步 OSS/S3（dry-run 已过）。
- `deploy/cloud/qre-cloud-worker.service` 与 `.env.example`：云端 worker 模板。
- `28_CLOUD_MIGRATION_RUNBOOK`：预检、全量、增量追数、双读/影子、切流校验清单。
- 实测基线：大库 519GB、核心表行数与日期范围（28 号文档 §2）。

### 2.2 本补充要解决的缺口
1. **DB 吞吐优化**：大查询的 IO 与临时空间是实测瓶颈，需要参数与架构预案。
2. **DB↔worker 传输优化**：产物与数据的网络传输量、分片与压缩策略。
3. **快速部署编排**：从「买机器」到「全链路可用」的分步 Runbook 与验证脚本。
4. **回传链完整性**：当前 20MiB 截断 + multipart 单点失败，直接决定上云后数据可用性。

---

## 3. 数据库吞吐优化预案

实测：单任务 `temp_bytes` +2.1–2.3GB、磁盘读 40–50GB、`tup_returned` ~17 亿行、PSI io 峰值 >86。

| 优化项 | 预案 | 目的 |
|---|---|---|
| 存储 | NVMe SSD + 按 IOPS  provisioning（而非仅按容量） | 解决 IO 峰值瓶颈 |
| 临时空间 | `temp_tablespaces` 放到独立高速盘；监控 `temp_bytes` | 避免临时文件挤占数据盘 |
| 内存参数 | `shared_buffers`≈内存 25%、`effective_cache_size`≈50–75%、`work_mem` 按并发×大查询上调、`maintenance_work_mem` 提高 | 提升缓存命中与排序/聚合性能 |
| 连接 | worker 使用只读账号 + 连接数上限；`max_connections` 按 worker 数×槽位预留 | 防止连接打满 |
| 只读副本 | 大查询（全市场回测）打到只读副本；主库只承担日更/写入 | 读写分离，避免回测拖垮主库 |
| 分区/压缩 | 分钟线保持 Timescale 压缩策略；迁移后复核 chunk 与压缩状态 | 控制存储与扫描成本 |
| 日常维护 | 定期 `ANALYZE`、大表索引复核、慢查询日志 | 防止统计信息过期导致计划退化 |

**验收口径**：迁移后同一全量任务在云 DB 上的执行时长与磁盘读取量必须实测，
与 31 号文档基线对比；不达标先调存储与参数，不先加机器。

---

## 4. DB↔计算端传输优化预案

### 4.1 数据传输（worker 读 DB）
- 同 VPC 私网连接，使用只读 endpoint；禁止跨公网 5432。
- 大查询分批（chunk）读取，沿用现有 250 只/批策略，避免一次性拉全市场。
- 评估对只读副本的查询路由，避免主库长事务/大查询阻塞。
- 网络与 DB 同 region，避免跨区流量与延迟。

### 4.2 产物传输（worker → 对象存储）
当前痛点：20MiB 静默截断 + multipart part 数限制（P0-9 已修 MAX_FORM_PARTS，但未解决完整性）。

准备方案：
1. **分片上传**：大产物按 chunk/文件组分片，支持失败重传与断点续传；
   避免一次性 multipart 全部文件（当前 413 的根因模式）。
2. **直传对象存储**：worker 直接把产物传到 OSS/S3，SaaS 只接收 manifest
   （文件名、大小、sha256、presigned URL）。SaaS 不再做「大文件中转站」。
3. **压缩与格式**：JSON 明细保留 gzip；大 CSV/报告可再评估 zstd（若工具链允许）。
4. **元数据补齐**：manifest 增加 `produced_bytes`、`truncated`、分片清单与校验和，
   让「产物是否完整」可观测（对应 B3 预算失效问题）。
5. **回退策略**：对象存储不可用时，才回退 ECS 本地盘，且显式标记降级。

### 4.3 传输量估算（用于选规格）
- 全量回测产物：0.85–1.52 GB/任务。
- 日 100 全量任务：约 **85–152 GB/日** 产物传输；日 1000 任务约 **0.85–1.52 TB/日**。
- 必须同 VPC 私网传输，公网直传既贵又易超时。

---

## 5. 快速部署 Runbook（买机器后按序执行）

> **2026-11-03 一键入口已落地**：`deploy/cloud/bootstrap-cloud.sh`。
> 买云后只需：①按本文买资源；②`cp deploy/cloud/cloud.env.example deploy/cloud/cloud.env` 填值；
> ③`bash deploy/cloud/bootstrap-cloud.sh --dry-run` 核对 → `bash deploy/cloud/bootstrap-cloud.sh` 执行。
> 该入口已串联下面 1–9 步，**不需要再临时写部署代码**；dry-run 已验证全流程命令可展开。

> 前置：用户已批准迁移，资源规格已确认。

1. **建 VPC/子网与安全组**：DB/worker 同私网；DB 仅放行 worker 网段 5432，禁公网。
2. **建云 DB**：同 PG 主版本 + TimescaleDB，按 §3 预设参数与高速临时盘。
3. **恢复数据**：`backup-market-db.sh` → 传备份 → `migrate-market-db.sh` → `verify-migration.sh`。
4. **建对象存储**：`artifacts/` 前缀 + 15 天生命周期 + 私网访问。
5. **部署云 worker**：套用 `qre-cloud-worker.service` 与 env，指向私网 DB 与云端 SaaS。
6. **部署 SaaS 配置**：SaaS 小库仍 authoritative；产物读改为 presigned URL（本地盘回退）。
7. **小样本验证**：先 smoke，再 100 只×2 年，再全量影子；对比收益/交易数/产物 sha256。
8. **灰度切流**：按 job 类型/比例切云端；home 保留只读回滚窗口。
9. **全量校验**：按 28 号文档 §5 清单逐项打勾后才正式切换。

**每一步都必须有验证输出**，不满足不得进入下一步。

---

## 6. 上云前必须完成的工程前置（否则迁移后仍不可靠）

1. **分片上传 + 产物完整性**（P0-9 B 方案）：当前 99% 产物无法上云，迁移只会放大问题。
2. **produced_bytes/truncated 元数据**：让产物体积与截断可观测（B3）。
3. **容量模型按交易笔数重建**（P0-10）：高换手任务按 14GB 预算，不按 6GB。
4. **NL 语义正确性**（CR-2026-11-03）：语义错了，换到云上算得再快也是错的。
5. **备份与回滚演练**：本地无 `tushare_data` 逻辑备份是已登记缺口，必须先在本地跑一次完整备份演练。

---

## 7. 明确不做（本轮）

- 不购买云资源、不实际迁移、不切流、不改生产 DB 参数。
- 不做分钟线专项优化（用户此前明确不做分钟线任务）。
- 不为了上云而先加硬件：先做分片上传、抽样粗筛与语义正确性。
