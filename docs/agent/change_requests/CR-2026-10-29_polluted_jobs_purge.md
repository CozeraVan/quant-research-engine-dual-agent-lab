# CR-2026-10-29 · 删除被北交所三板残留数据污染的全期任务（58/66/74/78）

## 触发

P0-2 全库极值扫描发现 `920%.BJ` 的 2021-11-15 之前历史是**三板残留脏数据**
（226 个代码 / 78,423 行 / 74.7% 垃圾行，`close` 恒 1、成交 30 股、最早 2009-01-09），
量化影响：job 58/66/74/78 各 25–32 只北交所个股，占毛盈亏 12.9% / 22.6% / 15.3% / 21.3%
（口径：个股 `summary.total_pnl` 加总占比，非收益贡献）。
用户 2026-10-29 裁定：**「将这些回测全部清除，从本地到公网的数据全部删除」**。

## 删除范围（4 个全期任务）

| job | kind | 窗口 | 原状态 |
|---|---|---|---|
| 58 | full | 2010-01-04 → 2026-10-11 | completed，**showcase 经典策略** |
| 66 | full | 2010-01-04 → 2026-10-13 | completed，**showcase 经典策略** |
| 74 | full | 2010-01-04 → 2026-10-19 | completed，**showcase 经典策略** |
| 78 | full | 2010-01-04 → 2026-10-21 | completed，2 条分享链接 |

**保留**：73 / 75 / 76 / 77 / 79 / 80 / 81（76 扫描干净；73/77 是 smoke 且未见 2021 前北交所交易）。

## 删除内容

**ECS 数据库 `aguhuice`**（单事务，按 FK 依赖顺序）：

| 表 | 删除行数 |
|---|---|
| `share_links` | 2 |
| `showcase_daily` | 27 |
| `showcase` | 3 |
| `results` | 4 |
| `jobs` | 4 |

**ECS 产物目录**：
- `/srv/aguhuice/uploads/job_{58,66,74,78}/`（5.7M / 5.6M / 23M / 23M）
- `/srv/aguhuice/archive/job_{58,66}/`（17M / 17M，2026-10-29 归档的 496 个旧系产物）

**本地 WSL**：这四个 job 在本地**没有任何回测数据**（本地 `outputs/saas_uploads` 最大到
`job_38`，`runs/` 为空；worker 生成后即上传 ECS，本地 run 产物已清）。
唯一残留是 `.tmp/perf-browser/` 下的两份 job 58 派生夹具：`risk_report_58.json`
（无任何消费者，**已删**）与 `real_symbol_58_000014.json`（**保留**——
10 个 TV 判据探针依赖它做真实数据渲染验证，删了 `tv_check_all.sh` 跑不了；
它是 gitignore 的 scratch，不是用户可见的回测结果。若要彻底清除，需先把探针迁到合成夹具）。

## 删除前备份（可恢复）

`~/quant-workspace/backups/polluted-jobs-20261029/`：

| 文件 | 内容 |
|---|---|
| `uploads-job_{58,66,74,78}.tar.gz` | 4 个 live 产物目录 |
| `archive-job_{58,66}.tar.gz` | 2 个归档产物目录 |
| `db-rows.sql` | `jobs`/`results`/`showcase`/`share_links` **全量** data-only dump（11 jobs） |
| `db-showcase_daily.sql` | `showcase_daily` 全量 dump（27 行） |

恢复方式：`psql -d aguhuice -f db-rows.sql`（注意会覆盖现有行，需先清空目标表）+
`tar xzf` 回 `/srv/aguhuice/{uploads,archive}/` + `chown -R www-data:www-data`。

## 验证（删除后实测）

| 项 | 结果 |
|---|---|
| `/saas/showcase` | 200，`{"items":[],"ok":true}`（空列表，无坏条目） |
| `/saas/jobs/{58,66,74,78}` 详情接口 | 匿名 401（与私人 job 一致，**不暴露存在性**） |
| `/api/results/58/symbols/000014` | 401 |
| job 76（保留）页面 | 200 正常 |
| MACD 旧系周扫 | `scanned_files 1013 → 96`、`legacy_total 0`、条件② 满足 |
| 复权契约审计 | `scanned_files 96`、全部带 `qfq_anchor_v1`、`bad_total 0` |
| ECS 磁盘 | 34G 可用（未显著变化，删除量 ~90MB） |

## 后果与后续

1. **`stock_daily` 一行未改**（源数据只读纪律）。脏数据仍在表里，
   **「宇宙排除 920xxx 三板残留」这条规则仍必须落地**，否则下次全期回测再次被污染。
2. **经典策略页（showcase）现在是空的**。要用干净结果重新填充，前提是先把股票池规则定下来
   （排除 `920%.BJ` 且 `trade_date < 2021-11-15`）再重跑。
3. **`familyOf` 旧名分支退场简化**：归档产物已随删除消失，不再有依赖旧名渲染的在线产物，
   原「删前后置风险」（58/66 详情页会退回三指标独立副图）**随之消失**；
   只剩条件①连续 4 次 `--record` 周扫为 0（预计 2026-11-02/09/16/23），11-23 后可直接删。
4. `deploy/saas/macd-legacy-scan.log` 历史保留作审计轨迹（其中引用 job 58/66 的行为历史记录）。
