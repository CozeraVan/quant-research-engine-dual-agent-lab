# CR-2026-10-29 · MACD 旧系产物归档（TV R6 收尾 · 用户选「归档」）

## 背景

`familyOf` 旧系 MACD 列名（`macd_dif`/`macd_dea`/`macd_hist`）的退场有两条机械判定条件
（`deploy/saas/scan-macd-legacy-names.sh`，数据字典 §4.1.1）：

- ① 连续 4 次周扫「新产物含旧系名」计数为 0；
- ② 所有含旧系的 job 均已过期（`> LEGACY_RETENTION_DAYS`，用户 2026-10-30 确认为 **15 天**）或已归档。

15 天过期只满足②——产物文件还在 ECS 上，周扫照样读到旧列名，① 永远不会归零。
用户 2026-10-29 在「保留分支 / 归档退场 / 重跑旧 job」中选**归档**。

## 改动

### 1. ECS 产物归档（一次性，可回退）

```
/srv/aguhuice/uploads/job_58/_symbol_details   (263 个 gzip)
/srv/aguhuice/uploads/job_66/_symbol_details   (233 个 gzip)
  → mv →
/srv/aguhuice/archive/job_58/_symbol_details
/srv/aguhuice/archive/job_66/_symbol_details
```

同文件系统 `mv`（秒级、零拷贝、45MB），回退即反向 `mv`。
`job_<id>/` 下的其它产物（`risk_report.json`、逐股 CSV 目录）**未动**。

### 2. `QRE-SAAS-ARTIFACT-ARCHIVE`：详情页归档回落（app.py）

58/66 是公开展示的经典策略，归档 ≠ 下线。新增两个嵌套函数
（`create_saas_app()` 内，`api_result_symbol_detail` 之前）：

- `_symbol_detail_dirs(job_id)` → `[live, archive]`，归档根缺省取
  `upload_root` 的兄弟目录 `archive/`，`SAAS_ARCHIVE_DIR` 可显式覆盖；
- `_find_symbol_detail(job_id, code)` → live 精确 → live 6 位前缀兜底 →
  归档精确 → 归档前缀兜底，都没有返回 `None`。

`api_result_symbol_detail` 与 `_symbol_detail_ready` 都改走它
（后者影响「按需生成」的幂等判定：归档 job 的详情仍算就位，不会被反复重建）。
live 与归档同时存在时 **live 优先**，新产物不被旧快照盖住。

## 验证

| 项 | 结果 |
|---|---|
| 归档后周扫 | `scanned_files 1013 → 517`、`legacy_total 0`、条件② 满足 |
| 详情页回落 | job 58 / 66 各抽样 12 只，全部 `200` 且 `ok:true`（归档目录读取） |
| 公开展示页 | `/saas/showcase` 200、`/saas/jobs/58` 200、`/saas/jobs/58/symbols` 200 |
| live 优先 | 单测 `test_live_dir_still_wins_over_archive` |
| 都没有时 | 保持既有 `404 + can_generate`（不静默给空数据） |
| 单测 | `tests/test_saas_symbol_ux.py` 新增 `TestSymbolDetailArchiveFallback` 4 例 |
| 部署 | `deploy-ecs.sh src/quant_research_engine/gui/saas/app.py`，回滚副本在 ECS `/tmp/qre-deploy-*.bak` |

## 遗留（删 `familyOf` 旧名分支前必须处理）

归档产物里的因子名仍是旧系，靠 `familyOf` 第 52-58 行的旧名分支才能与
`macd_12_26_9` 等同组合流成同一个 MACD 副图。**直接删该分支会让 58/66 详情页退回
「三个指标各自独立副图」**。三选一待产品负责人定：① 展示层保留窄化旧名映射；
② 一次性改写归档 gzip 的因子名为新系 canonical；③ 重跑 58/66。

## 时间表

条件① 只计 `--record` 落盘的周扫（临时手动跑不计入，防污染连续计数）。
4 个零预计落在 **2026-11-02 / 11-09 / 11-16 / 11-23**，**11-23 之后**方可删旧名分支。
