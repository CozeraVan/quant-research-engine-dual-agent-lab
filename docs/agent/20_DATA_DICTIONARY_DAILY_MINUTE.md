# 20_DATA_DICTIONARY_DAILY_MINUTE.md — 行情数据字典（日线 / 分钟线）

> 单一权威文档：任何 agent 处理行情数据（读取、入库、因子计算、回测）前必须先读本文。
> 最后更新：2026-10-11（分时数据验证与入库方案立项）

---

## 1. 数据库总览

- 实例：本机 WSL PostgreSQL + TimescaleDB 2.28.2
- 连接：`postgresql://van:***@127.0.0.1:5432/tushare_data`（密码见本地配置，勿入文档）
- 行情主表全部启用了 TimescaleDB hypertable，按时间列分 chunk。

## 2. 日线行情：`public.stock_daily`

| 列 | 类型 | 单位/口径 | 说明 |
|---|---|---|---|
| ts_code | text | 带后缀 `000001.SZ/.SH/.BJ` | 主键之一 |
| trade_date | date | `2026-10-09` | 主键之一；hypertable 时间列 |
| open/high/low/close | double | 元，**不复权原始价** | |
| pre_close | double | 元 | 前收盘（复权处理后口径，tushare 原生） |
| change / pct_chg | double | 元 / % | 涨跌额、涨跌幅 |
| vol | double | **手（=100 股）** | tushare 原生单位 |
| amount | double | **千元** | tushare 原生单位 |
| adj_factor | double | 复权因子 | 后复权价 = 原始价 × adj_factor |
| vwap | double | 元 | 成交均价 |

- 主键 `(ts_code, trade_date)`；索引 `trade_date DESC`。
- hypertable：`trade_date`，**chunk = 7 天**，未开压缩。
- 数据量：1483 万行，**2009-01-05 → 最新交易日**（2026-10-11 方案A重建时向前扩展了 2009 年），全 A 约 5573 只。
- 数据源：tushare `daily`（**原始价**，2026-10-11 起；此前为 qfq）+ `adj_factor`，每日定时任务增量同步（quant_ts）。

### ⚠️ 2.1 历史问题（已解决，2026-10-12）：stock_daily 曾为前复权口径

- 旧口径：`ts.pro_bar(adj='qfq')` 前复权价且自愈机制失效（混合锚点），详见 `change_requests/CR-2026-10-11_stock_daily_qfq.md`。
- **现行口径（方案A，已生效）**：表内 OHLC 为**原始价**，`adj_factor` 列随行；复权在读取层做（indicators `IND_PRICE_BASIS=raw` / QRE `QRE_PRICE_BASIS=raw`，价格列×adj_factor=后复权；K线展示锚定最新价=前复权@today，与东财一致）。因子 10 表 + alpha191 已于 2026-10-12 按新口径全历史重算完成并抽查通过。
- 旧表保留为 `public.stock_daily_qfq_legacy`（回滚用，方案A验收后删除）。
- **坑：表重建 RENAME 后 PostgreSQL 表级 GRANT 不随迁**——2026-10-11 换名后 `qre_worker_ro` 失去 SELECT 致 job 56 冒烟失败。今后任何表重建/换名必须随迁 `GRANT SELECT ON ... TO qre_worker_ro`（及其他只读角色）。

## 3. 分钟线行情：`public.stock_minute_1m`（2026-10-11 全量入库完成）

### 3.1 数据源

- 本地 CSV：`/home/van/mindata/`（**2009-01-05 → 2026-10-09，4313 个交易日，324GB，预估约 30+ 亿行**）
- 文件组织：按年目录、按日一个 CSV（`2009_…/1min/YYYYMMDD_….csv` … `2026/YYYYMMDD_….csv`），含全市场股票；中文表头带 BOM，全年份格式一致（已抽查 2009/2013/2017/2021）
- CSV 列：`证券代码, 证券名称, 交易日期, 分钟时间, 开盘价（元）, 最高价（元）, 最低价（元）, 收盘价（元）, 成交量, 成交额, 复权因子`
- **价格为不复权原始价**（经 tushare `daily` API 逐年裁决验证：2010/2013/2015/2020/2023/2026 末 bar 收盘与 API 原始价逐年吻合，2026-10-09 全市场 5559 只 100% 一致；量额换算后与日线 1:1 精确吻合）
- 沪深每股 241 根 bar（09:30–15:00，09:30 bar 含集合竞价）；北交所 271 根（交易至 15:30）；约 4% 零量 bar 为无成交分钟；停牌日部分源文件给全日零量占位行

### 3.2 入库表结构（与日线对齐）

| 列 | 类型 | 单位/口径 | 来源/转换 |
|---|---|---|---|
| ts_code | text | 带后缀 | CSV `证券代码` 原样 |
| trade_time | timestamp | `2026-10-09 09:30:00` | CSV `分钟时间` |
| trade_date | date | 冗余列，便于按日查询/分区对齐 | `trade_time::date` |
| open/high/low/close | double | 元，**不复权** | CSV 原样 |
| vol | double | **手** | CSV `成交量` ÷ 100 |
| amount | double | **千元** | CSV `成交额` ÷ 1000 |
| adj_factor | double | 复权因子 | CSV `复权因子`（日内不变，与日线当日值一致） |

- 主键 `(ts_code, trade_time)`。
- **TimescaleDB hypertable：`trade_time`，chunk = 7 天**（与 stock_daily 一致；单日 chunk 约 133 万行，7 天约 930 万行/chunk，共约 61 chunk）。
- 另建索引 `(trade_date)` 用于全市场单日截面。
- **不存** 证券名称（维度信息归 `reference` 层股票列表表）。
- 不预存 vwap：分钟 vwap = amount/vol（换算后 = amount×1000/(vol×100)，口径自洽）。

### 3.3 入库流程（确定方案）

1. 刷新 `reference.trade_calendar`（当前缺 20260715/16 等新日期）。
2. 建表 + hypertable + 索引。
3. 入库脚本（放 `quant_ts/`，复用现有 DB 连接与审计习惯）：
   - 逐文件：pandas 读 CSV（处理 BOM/中文表头映射）→ 单位换算 → 写 staging 表（UNLOGGED）→ `INSERT ... ON CONFLICT (ts_code, trade_time) DO NOTHING` → 记录每文件审计行数（文件行数 vs 入庫行数）。
   - 幂等：中断可安全重跑。
   - 并行 worker ≤ 6（单文件 pandas 峰值约 2-3GB RAM，32G 内存留余量）。
4. 耗时估算：实测约 4-9s/文件（随年份规模），6 worker 并行全量约 **1.5-2.5 小时**。
5. 存储估算：约 30+ 亿行，表体+索引预估 **150-250GB**（磁盘余量 717G，可承受）。
6. 入库脚本：`quant_ts/import_minute_csv.py`（2026-10-11 上线，6 worker + 审计表 `stock_minute_1m_audit` 幂等断点续跑）。
7. 验收 SQL：每日行数 vs CSV 行数（审计表 rows_csv vs rows_db）、每股 bar 数分布（241/271）、与日线收盘价抽样对账。

### 3.4 存储与压缩（2026-10-11 磁盘事故后确立）

- **stock_minute_1m 必须开 TimescaleDB 原生压缩**（`compress_segmentby='ts_code', compress_orderby='trade_time'`）。未压缩约 187B/行（708 chunk/439GB @ 23.5亿行），全量 32 亿行装不下 1TB 盘。
- 压缩脚本：`quant_ts/compress_minute_chunks.sh`（未压缩 chunk 大到小逐个 compress_chunk，日志 logs/minute_compress.log）。
- 规则：**T-7 之前的 chunk 必须处于压缩态**；新入库先落未压缩 chunk（压缩 chunk 不支持 ON CONFLICT 写入），定期压缩旧 chunk。
- 事故记录：2026-10-11 17:15 磁盘 100% 导致 PG PANIC 两次（WAL 写不进去）。教训：大批量入库前必须先看 `df -h /` 余量，本机 PG 与数据同盘（sdd 1TB）。

### 3.5 已知注意事项

- 停牌占位行（全日零量）：保留入库，回测引擎需将零量 bar 视为不可成交。
- 北交所 271 bar：任何按会话网格生成时间的逻辑必须区分市场。
- 后续增量数据用户会追加拷贝到 `/home/van/mindata/`，重跑脚本即可幂等入库。

## 4. 因子表速览（`factors` schema，11 表约 490 列）

- 全部按 `(ts_code, trade_date)` 主键、hypertable（chunk 7 天）。
- `stock_daily_alpha191`（191 列 Alpha191 全套）；`stock_daily_momentum_close`（RSI/MACD/KDJ/CCI 等 88 列）；`stock_daily_overlap_close`（各类均线 88 列）；`stock_daily_volatility_close`（布林带/ATR/DC 等 52 列）；`stock_daily_volume_close`（OBV/MFI/CMF 等 23 列）；`stock_daily_trend_close`（ADX/PSAR 等 43 列）；`stock_daily_performance_close`（pctret_5/10/20/60/250、mom_12_1 等 16 列）；`stock_daily_statistics_close`（stdev/sharpe/skew 等 22 列）；`stock_daily_candle_close`（K线形态 12 列）；另有 average_price / typical_price 两个变体表。
- 当前全部为**纯量价因子**；无基本面/估值/换手率因子（规划见因子立项方案）。

## 5. 基本面与参考数据（相关表）

- `fundamentals.fina_indicator / income / balancesheet / cashflow`：主键含 `ann_date`（PIT 防未来函数），income 自 1990 年起。
- `reference.daily_basic`：换手率、PE/PB、总市值/流通市值。
- `fundamentals.dividend`：分红送转（回填中）。
- `market.*`：moneyflow、stk_limit、margin、龙虎榜、大宗交易等核心层（回填中）。

## 6. 给其他 agent 的硬规则

1. 价格一律**原始不复权价 + adj_factor 列**，复权在因子计算/回测时做，禁止入库前锁死口径。
2. 量=手、额=千元（tushare 口径），跨表计算前先核对单位。
3. 财务数据 join 必须用 `ann_date <= 交易日` 做 PIT 对齐，禁止用报告期直接对齐。
4. 新行情表一律 TimescaleDB hypertable + 7 天 chunk + `(ts_code, 时间列)` 主键。
