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
- 数据量：1363 万行，2010-01-04 → 最新交易日，全 A 约 5573 只。
- 数据源：tushare `daily` + `adj_factor`，每日定时任务增量同步（quant_ts）。

## 3. 分钟线行情：`public.stock_minute_1m`（方案已锁定，待全量入库）

### 3.1 数据源

- 本地 CSV：`/home/van/mindata/`（2025-01-02 → 2026-10-09，426 个交易日，52GB，约 5.7 亿行）
- 文件组织：**按日一个 CSV**，文件名含 `YYYYMMDD`，含全市场股票；中文表头带 BOM。
- CSV 列：`证券代码, 证券名称, 交易日期, 分钟时间, 开盘价（元）, 最高价（元）, 最低价（元）, 收盘价（元）, 成交量, 成交额, 复权因子`
- 已验证（2026-10-09 全日 + 2025-01-02 复查，验证记录见 11_AGENT_STATE / CR 文档）：
  - 与日线逐股对账：收盘价 100% 一致；分时量合计 ÷ 日线 vol = 恒 100；成交额与日线 1:1 吻合
  - OHLC 逻辑零违规；无重复 (code+minute)；交易日零缺失
  - 沪深每股 241 根 bar（09:30–15:00，09:30 bar 含集合竞价）；北交所 271 根（交易至 15:30）
  - 约 4% 零量 bar 为无成交分钟（真实市场结构）；停牌日部分源文件给全日零量占位行

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
4. 耗时估算：串行 6-8 小时；6 worker 并行约 1-1.5 小时。
5. 存储估算：表体约 30-35GB + 索引 10-15GB（磁盘余量 717G，无压力）。
6. 验收 SQL：每日行数 vs CSV 行数、每股 bar 数分布（241/271）、与日线收盘价抽样对账。

### 3.4 已知注意事项

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
