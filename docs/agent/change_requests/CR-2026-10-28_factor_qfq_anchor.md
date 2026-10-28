# CR-2026-10-28 因子前复权锚点按 K 线末日（600330 EMA 偏离根因）

状态：已实施 + 存量产物已补救，未 commit/push（等用户验收）
关联：`docs/agent/20_DATA_DICTIONARY_DAILY_MINUTE.md`、`23_KLINE_IMPLEMENTATION.md`

## 1. 现象

个股回测详情里技术指标与 K 线严重偏离，且反复出现、每次治标不治本：

- #78 任务 600330.SH：`ema_5 = 113.26` vs qfq 收盘 `21.97`，差 **5.0637 倍**
- 920195：MACD 直到 2020-09 才有数据（上市 2022-12，属另一问题，见 6）
- 92xxxx.BJ 类：收益曲线早于上市日（新三板旧数据，已结论无需处理）

## 2. 根因（三层叠加，非猜测，已实证）

### 2.1 尺度不一致是设计固有属性，不是 bug

| 数据源 | 口径 |
| --- | --- |
| 因子表 `factors.*` | **hfq**（`raw × adj_factor`） |
| 个股详情 K 线 | **qfq @ K 线最后交易日** |
| worker 回测引擎 | hfq（口径不变） |

价格型因子必须除以「K 线最后交易日」的 `adj_factor` 才能与 K 线同尺度。
该换算**只存在于实时生成路径** `lab_result._fetch_factor_panels`。

### 2.2 SaaS API 优先下发 worker 回传的 gzip 快照，快照永不失效

→ 1013/1013 个存量产物全部是旧口径（hfq 尺度）。线上复扫确认：
`factor_basis` 缺失率 100%。

### 2.3 次要根因：`_latest_adj_factor` 取全局最新日

原实现无条件 `ORDER BY trade_date DESC LIMIT 1`。若回测区间结束后该股又除权，
锚点就与 K 线所用锚点不一致 → 因子被除了一个**错误倍数**。
这是"修了又坏"的真正原因：实时路径本身锚点就是错的。

## 3. 实证方法（不是猜的）

用产物自身携带的 qfq K 线收盘价重算比值：

- 600330 的 `ema_hfq / adj(latest)` 与 qfq 收盘价比值 **0.9883–1.1020**
  ——正是 EMA5 相对收盘该有的滞后形态，证明因子数据本身没错，只是尺度错了
- rescale 后与重算值比值 **1.0000**

40 个随机产物大规模校验（各自 qfq K 线重算）：

| 指标 | 修复前比值中位数 | 修复后 |
| --- | --- | --- |
| EMA | 2.677 | 1.0001 |
| MACD | 1.434 | 0.9999 |

## 4. 修复

### 4.1 代码根因（`gui/lab_result.py`）

`_latest_adj_factor(conn, ts_code, as_of)` 增加 `as_of`，SQL 加
`AND trade_date <= :d`；调用点传 `dates[-1]`（K 线最后交易日）。
缺省 `None` 才退回全局最新，仅用于无 K 线日期的兜底路径。

回归测试 `tests/test_gui_lab_result.py::TestQfqAnchorDate`（2 例）。

### 4.2 存量产物补救（1013 个）

ECS 打包陈旧产物 → 本地 `/tmp/qfq_fix/rescale.py` 按正确锚点 rescale
（分类用 `reg.display(table,col)`；旧产物无 table/col 时用 `reg.resolve(name)` 兜底）
→ 回传 ECS `install`（`installed=1013`）。
线上复扫：`total=1013 新口径=1013`；600330 线上
`factor_basis: qfq_anchor_v1, anchor: 5.0639 @ 2026-10-20`，
`ema5/收盘 = 0.9883 / 1.0029 / 1.0180`。

### 4.3 预防机制（`gui/saas/app.py`）

缺 `factor_basis` 的产物一律 `data = None` → 走 404 `can_generate`，
前端出「生成详情」按钮。**宁可让用户点一下，也不 silent 展示错尺度数据。**

### 4.4 测试夹具同步

`tests/test_gui_saas.py`（`_ready_artifact` 加 `legacy` 参数 + NaN 夹具补
`factor_basis` + 新增 `test_legacy_artifact_without_basis_is_not_served`）、
`tests/test_saas_symbol_ux.py`、`tests/test_saas_result_help.py`。

## 5. 环境约束（决定了补救方式）

- 行情库在家用机本地（`tushare_data`），**ECS 无行情库** → 无法在 ECS 重算因子，
  只能改快照
- 本地 run 产物已全部清空（`outputs/gui-console/runs` 为空，全盘无 `status.json`）
  → worker 的 `_execute_symbol_detail` 无法工作，「刷新详情」按钮对这些 job 实际无效，
  这正是必须直接改快照的原因

## 6. 不在本 CR 范围（已另行结论）

- 920195 MACD 从 2020-09 起：该股 2022-12-30 才上市，属数据起始问题
- 92xxxx.BJ 收益曲线早于上市日：新三板/旧三板历史数据，用户明确「无需理会」

## 7. 验收

- 全量 `uv run pytest tests/ -q` → `3009 passed, 24 skipped`
- ECS 线上复扫 1013 产物口径 100% 新
- 浏览器实测（待用户验收）：`/saas/jobs/78/symbols/600330.SH` EMA 与 K 线同尺度
