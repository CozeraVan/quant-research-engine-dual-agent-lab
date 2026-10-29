# 20_DATA_DICTIONARY_DAILY_MINUTE.md — 行情数据字典（日线 / 分钟线）

> 单一权威文档：任何 agent 处理行情数据（读取、入库、因子计算、回测）前必须先读本文。
> 最后更新：2026-10-27（QRE-DATA-CLEANUP-AUDIT 只读盘点：qfq_legacy 已不存在、分钟线压缩缺口 140GB、mindata 已空、分钟线落后日线 10 天；新增 §7 遗留数据盘点）

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
  **⚠️ 2026-10-27 更新（QRE-DATA-CLEANUP-AUDIT）：该表已不存在**——全库所有 schema 搜 `%legacy%`/`%qfq%` 返回 0 条，
  本地也没有 `tushare_data` 的 dump（`~/quant-workspace/backups/ecs-aguhuice/` 只有 ECS 上 aguhuice SaaS 库的 dump）。
  **即「回滚到 qfq 口径」这个选项已永久失去且不可恢复。** 新口径自 2026-10-12 起生产生效、因子 10 表 + alpha191
  已按新口径全历史重算并抽查通过，生产回测一直跑在新口径上；但今后不得再声称存在 qfq 回滚路径。
  若用户要求重建应急档，只能从 tushare 重新拉一批 qfq 历史另存新表（不要再用 `qfq_legacy` 这个名字）。
- **坑：表重建 RENAME 后 PostgreSQL 表级 GRANT 不随迁**——2026-10-11 换名后 `qre_worker_ro` 失去 SELECT 致 job 56 冒烟失败。今后任何表重建/换名必须随迁 `GRANT SELECT ON ... TO qre_worker_ro`（及其他只读角色）。

## 3. 分钟线行情：`public.stock_minute_1m`（2026-10-11 全量入库完成）

### 3.1 数据源

- 本地 CSV：`/home/van/mindata/`（**2009-01-05 → 2026-10-09，4313 个交易日，324GB，预估约 30+ 亿行**）
  **⚠️ 2026-10-27 更新（QRE-DATA-CLEANUP-AUDIT）：该目录已空**——0 个文件、24 KB（只剩 `mindata/` 与
  `mindata/2026/` 两个空目录 inode）。历史 CSV 已全部不在，**源数据不可恢复**；今后若发现数据缺口，
  唯一补救是回原始数据商重新下载，不要再假设「CSV 还在、可以重跑」。删除轨迹：日志
  `quant_ts/logs/minute_import.log` 只记录了 5 个文件（20261012–1016）走「先校验 `rows_csv==rows_db`
  再删除」（2026-10-18 17:06）；`import_minute_csv.py` 无任何删除代码，4308 个历史 CSV 属脚本外删除
  （`mindata/` mtime 2026-10-11 23:19 晚于审计最后写入 20:10，顺序正确但无审计轨迹）。
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
- **⚠️ 2026-10-27 压缩缺口（QRE-DATA-CLEANUP-AUDIT 实测）**：当前 922 个 chunk 中 **708 个已压缩 = 396 MB**，
  **214 个未压缩 = 140 GB**（压缩比约 350:1）。其中 **213 个 `range_end` 早于 T-7 却仍未压缩，合计 140 GB**，
  覆盖 2022-09-01 → 2026-10-08（2022:18 个/11G、2023:52/33G、2024:52/34G、2025:51/35G、2026:40/27G）
  ——**违反上一行的 T-7 规则**。`minute_compress.log` 结尾写「2026-10-11 17:55:09 压缩完毕 707 chunks」，
  但未压缩 chunk 的内部 ID（如 2022-09-01 = `_hyper_67_56121_chunk`）明显高于已压缩集合（`_hyper_67_45526` 等），
  说明它们是那次压缩**之后**才创建、之后再没跑过压缩。**定期跑 `compress_minute_chunks.sh` 必须纳入例行**，
  预计重跑可回收约 139 GB。核查 SQL：
  ```sql
  select count(*), pg_size_pretty(sum(pg_relation_size(format('%I.%I',chunk_schema,chunk_name))::bigint))
  from timescaledb_information.chunks
  where hypertable_name='stock_minute_1m' and not is_compressed and range_end < (now()-interval '7 days');
  ```

### 3.5 已知注意事项

- 停牌占位行（全日零量）：保留入库，回测引擎需将零量 bar 视为不可成交。
- 北交所 271 bar：任何按会话网格生成时间的逻辑必须区分市场。
- 后续增量数据用户会追加拷贝到 `/home/van/mindata/`，重跑脚本即可幂等入库（日常增量已由 3.6 的定时工作流接管，无需手动跑全量脚本）。

### 3.6 分钟线 CSV 定时入库工作流（2026-10-18 上线）

- **脚本**：`quant_ts/minute_csv_daily_ingest.py`（复用 `import_minute_csv.import_one` 的解析/换算/ON CONFLICT 口径，不另造轮子）。
- **定时器**：systemd `minute-csv-ingest.timer` / `minute-csv-ingest.service`，**Mon..Fri 17:20**（避开 16:30 日线同步、16:40 因子日更），`Persistent=true`，User=van，`uv run` 于 `quant_ts/`。
- **流程**：扫描 `/home/van/mindata/**/*.csv` → 审计表已完成的日期跳过解析直接进校验（幂等断点续跑）→ 新日期逐文件串行入库（单文件单事务，避免长事务）→ **校验：CSV 数据行数 == stock_minute_1m 该 trade_date 实时行数** → 通过才更新 `stock_minute_1m_audit` 并**删除对应 CSV**；失败保留 CSV、日志标 ERROR、进程 exit 1。
- **日志**：`quant_ts/logs/minute_import.log`（另 journalctl -u minute-csv-ingest.service）。
  ⚠️ 本文档此前写作 `minute_daily_ingest.log`，**该文件不存在**，实际日志就是 `minute_import.log`（与全量入库共用一个文件，靠时间戳区分）。
- **手动入口**：`uv run python minute_csv_daily_ingest.py`；`--force` 强制重入库（验证幂等用，ON CONFLICT DO NOTHING 保证行数不增）；`--keep-csv` 校验后保留 CSV。
- **失败处理**：校验不一致（rows_csv ≠ rows_db）或单文件异常 → 该文件不入审计、不删除，下个周期自动重试；排查看日志中 ❌ 行。
- 首跑验证（2026-10-18）：`mindata/2026/` 5 个文件（20261012–20261016）共 6,769,394 行，强制重跑行数不变（幂等通过），校验全过后 5 个 CSV 已删除。
- **⚠️ 2026-10-27 数据新鲜度缺口（QRE-DATA-CLEANUP-AUDIT 实测）**：`stock_minute_1m` 最新交易日 **2026-10-16**，
  而 `stock_daily` 最新 **2026-10-26**——分钟线**落后日线 10 天**。`minute-csv-ingest.timer` 自 10-18 起
  每天「扫描到 CSV 0 个」，即用户未再往 `mindata` 拷新 CSV。需用户确认是「有意暂停分钟线」还是「漏拷数据」。
- **⚠️ 审计表现状（2026-10-27 核查）**：`stock_minute_1m_audit` 4318 行（2009-01-05 → 2026-10-16），
  `done_at` 分布 = 2026-10-11 的 4313 条 + 2026-10-18 的 5 条；**全部 `rows_csv == rows_db`（0 条不一致）**；
  审计日期与 `stock_minute_1m` 实际日期**双向差集均为 0**；抽查 8 个日期（含 10-11 磁盘打满失败的
  2022-08-22/25/29）审计 `rows_db` 与实时行数 **8/8 MATCH**。**「已入库」不等于「源 CSV 可删」**——
  本轮删掉的源文件已不可恢复，上述一致性只能证明 DB 内完整，不能作为删除源数据的依据。

## 4. 因子表速览（`factors` schema，11 表约 490 列）

- 全部按 `(ts_code, trade_date)` 主键、hypertable（chunk 7 天）。
- `stock_daily_alpha191`（191 列 Alpha191 全套）；`stock_daily_momentum_close`（RSI/MACD/KDJ/CCI 等 88 列）；`stock_daily_overlap_close`（各类均线 88 列）；`stock_daily_volatility_close`（布林带/ATR/DC 等 52 列）；`stock_daily_volume_close`（OBV/MFI/CMF 等 23 列）；`stock_daily_trend_close`（ADX/PSAR 等 43 列）；`stock_daily_performance_close`（pctret_5/10/20/60/250、mom_12_1 等 16 列）；`stock_daily_statistics_close`（stdev/sharpe/skew 等 22 列）；`stock_daily_candle_close`（K线形态 12 列）；另有 average_price / typical_price 两个变体表。
- 当前全部为**纯量价因子**；无基本面/估值/换手率因子（规划见因子立项方案）。

### 4.1 ⚠️ MACD 双列名并存（2026-10-29 R3-5 记录，写判据/脚本前必读）

产物里的 MACD 有**两套并列列名**，不要假设只有一套：

| 系 | 列名 | 产物里的形态 | 用途 |
|---|---|---|---|
| **新系（现行）** | `macd_12_26_9` / `macds_12_26_9` / `macdh_12_26_9` | `col` + `display` 合同齐全 | 2026-10-28 之后的新产物一律用这套 |
| **旧系（存量）** | `macd_dif` / `macd_dea` / `macd_hist` | **只有 `name`，`col=None`、`display=None`** | job 58/66/74/78 等 2026-10-28 前完成的回测 |

**取舍（明确记录，避免未来反复讨论）**：
- **不回刷旧产物**（job 58/66 保持原样）——价值低，且会改变已验证的历史结果。
- **前端呈现层不分裂**：`factor-layout.js::familyOf` 对两套都归组到一个 MACD 面板
  （TV_ROUND2 判据已用生产 job 58 真实产物证实：三 series 同 `yAxisIndex/gridIndex`、
  同像素映射）。旧产物因此获得与新系同等的面板呈现。
- **NL / 因子选择入口已收敛**：`configs/factor_registry.json` 的 `extra_aliases`
  把旧名映射到新系 canonical（`macd_dif→macd_12_26_9`、`macd_dea→macds_12_26_9`、
  `macd_hist→macdh_12_26_9`），用户用旧名描述也能命中。生成器
  `scripts/gen_factor_registry.py::EXTRA_ALIASES` 同步维护，两者由
  `tests/test_factor_registry.py::TestMacdDualNamingAliases` 防漂移。
- **新产物一律新系命名**；旧名仅作兼容，不新增旧系因子。

**给写判据/验证脚本的 agent**：拉产物后先打印因子的 `col`/`name` 确认是哪一套
（旧系 `col` 为 `None`），再决定判据脚本匹配哪套列名——用错会得出"归组失败"的
错误结论。本项目 `.tmp/perf-browser/` 下的判据脚本已按此在文件头声明。

#### 4.1.1 旧系分支退场：事件触发制（R4-4，2026-10-29 定，替代日历式）

**不定日历，定触发条件。** 两条**同时满足**才动手删 `familyOf` 的旧名分支：

1. **连续 4 次周扫**「新产物因子名含旧系（`macd_dif`/`macd_dea`/`macd_hist`）」
   计数为 **0**；
2. 所有 `legacy_count>0` 的 job **均已过期（创建时间早于保留期）或已归档**。

**两条条件均可由脚本机械判定**，一条命令出结论。

**周扫脚本**：`deploy/saas/scan-macd-legacy-names.sh`
（扫 ECS `saas_uploads` 下所有 job 的 per-symbol 产物因子名 + job 年龄；
`--record` 追加到 `.tmp/macd-legacy-scan.log`）。

**systemd timer（已落地）**：`deploy/systemd/qre-macd-legacy-scan.{service,timer}`
→ 已安装到 `/etc/systemd/system/` 并 enable，每周一 03:17 跑一次
（`Persistent=true`，错过开机补跑），输出 append 到 `.tmp/macd-legacy-scan.timer.log`。

**保留期**：`LEGACY_RETENTION_DAYS`，默认 **90 天**（service 单元里 `Environment=`
固定为 90；手动跑可用环境变量覆盖）。**参数值待用户确认。**
年龄取 `risk_report.json` 的 mtime 作稳定证据（不用 `_symbol_details` 目录 mtime——
部署/拷贝会刷新它，实测会把 5 天前的 job 算成 0.8 天）。

**退场动作**（一个 PR）：删 `factor-layout.js::familyOf` 的旧名分支 + 判据脚本的
双列名警示同步退场。
**明确不删**：`configs/factor_registry.json` 的 `extra_aliases` 旧名别名——
入口层成本≈0，防 NL 断链（用户用旧名描述仍能命中新系 canonical）。

**首扫结果（2026-10-29，timer 首跑同值）**：扫 1013 个产物文件，**496 个含旧系名**
（job 58: 263 / job 66: 233，年龄 4.9 天，`active`）→ 条件①②**均不满足**。
这两个 job 正是 2026-10-24 生成的 MACD 金叉/死叉经典策略，退场要等它们过期
（按 90 天保留期约在 2027-01-22 之后）或归档。

## 5. 基本面与参考数据（相关表）

- `fundamentals.fina_indicator / income / balancesheet / cashflow`：主键含 `ann_date`（PIT 防未来函数），income 自 1990 年起。
- `reference.daily_basic`：换手率、PE/PB、总市值/流通市值。
- `fundamentals.dividend`：分红送转（回填中）。
- `market.*`：moneyflow、stk_limit、margin、龙虎榜、大宗交易等核心层（回填中）。

## 6. 给其他 agent 的硬规则

1. 价格一律**原始不复权价 + adj_factor 列**，复权在因子计算/回测时做，禁止入库前锁死口径。
2. **呈现口径分离**：因子表与引擎 raw 模式是 hfq（原始价 × adj_factor）；GUI K 线详情是前复权（原始价 × adj_factor / **K 线最后交易日的** adj_factor）。GUI 呈现层必须用 `gui.factor_registry.is_price_scaled()` 把价格型因子/阈值除以该锚点；无量纲因子不换算。买入持有收益恒用 hfq。
   - **锚点日期必须是 K 线最后一个交易日，不是全局最新交易日**（QRE-FACTOR-QFQ-ANCHOR）。若取全局最新日，回测区间结束后该股又除权时，因子会被除错倍数，EMA 与 K 线重新偏离——此类 bug 已复发三次，根因全在锚点。落地见 `gui/lab_result.py::_latest_adj_factor(conn, ts_code, as_of)`。
   - **产物必须带 `factor_basis` 标记**（`qfq_anchor_v1`）。SaaS API 对缺该字段的存量快照一律拒发（走 404 + 前端按需生成），绝不 silent 展示错尺度数据。任何新增的产物写入路径都必须带上该字段。
   - 校验方法（排查同类问题时直接用）：用产物自身携带的 qfq K 线收盘价与因子比值，EMA5 应呈现 0.99–1.10 的滞后形态；比值恒定且远离 1 即纯尺度错误。详见 `change_requests/CR-2026-10-28_factor_qfq_anchor.md`。
2. 量=手、额=千元（tushare 口径），跨表计算前先核对单位。
3. 财务数据 join 必须用 `ann_date <= 交易日` 做 PIT 对齐，禁止用报告期直接对齐。
4. 新行情表一律 TimescaleDB hypertable + 7 天 chunk + `(ts_code, 时间列)` 主键。
5. **禁止声称存在 qfq 回滚路径**——`stock_daily_qfq_legacy` 已不存在（见 2.1）。
6. **大批量写入/压缩前先 `df -h /`**；T-7 之前的 chunk 必须处于压缩态，压缩要纳入例行（见 3.4）。
7. **禁止以「已入库」为由删除源数据**——`/home/van/mindata` 的源 CSV 已空且不可恢复（见 3.1）。

## 7. 遗留数据盘点与清理（2026-10-27）

> 当前执行状态：用户批准后，QRE-DATA-CLEANUP-EXECUTION 已完成。以下为历史盘点快照，不能再把其中的“待确认/可删候选”理解为数据仍存在。

**本轮结果**：删除 `akshare_data`、`aguhuice_test`、`quant_hub`、`aguhuice_local` 及指定旧回测/实验产物；`qre-outputs` 27G→536M，磁盘可用 386G→418G。留档 `/home/van/quant-workspace/backups/local-cleanup-20261027/`：aguhuice_local 全量 dump、akshare 结构+行数（本体不可恢复）、旧文件 manifest。保留 refresh 活配置、saas_uploads、market_risk、video_packages 和两个待验收 staging 库。8080/8092 HTTP 200；8081 staging 重用前需重建/替换 aguhuice_local。新增 20261019/20/21 三份分钟 CSV 只读检查通过，三日 pending，等待 2026-10-27 17:20 CST timer 自动入库、校验并删除 CSV；未手动入库、未清洗、未压缩。M10.4 依赖已批准且 `.venv-ml` 已具备 scikit-learn / pandas / numpy。

### 7.1 历史本机数据库清单（清理前只读快照）

| 库 | 大小 | 内容 | 判定 |
|---|---|---|---|
| `tushare_data` | 513 GB | 行情主库（`public.stock_daily` 1488 万行 / `stock_minute_1m` 约 36.4 亿行 / `fund_daily` 306 万行 / `stock_holder_number` 42.9 万行 / `stock_daily_raw_audit` 4149 行） | **主库，勿动** |
| `akshare_data` | **5.8 GB** | `stock_ticks` 36,147,932 行，2026-04-07 → 04-24，10 个分区 | **高风险待确认**：`AK_DB_URL` 仅在 `quant_ts/config.py` 定义、全仓无消费者，4 月 tick 实验遗留 |
| `aguhuice_local` | 8.9 MB | 3 users / 15 jobs（2026-09-27 → 10-05） | 可删候选（陈旧本地测试数据） |
| `qre_factor_display` | 8.7 MB | 1 user / 1 completed job | 上一任务 staging，待 QRE-FACTOR-DISPLAY-CONTRACT 验收后再删 |
| `qre_readonly_share_browser` | 8.7 MB | 1 user / 3 completed jobs | 上一任务 staging，验收后再删 |
| `aguhuice_test` | 7.5 MB | **0 张表** | 可删候选（空壳） |
| `quant_hub` | 10 MB | **0 张 public 表** | 可删候选（空壳） |

任务书曾提到的 `qre_saas` / `dbg` **两个库都不存在**（早已不在）。

### 7.2 文件系统遗留（`/home/van/qre-outputs` 27G，仓库 `outputs` 符号链接指向它）

| 路径 | 大小 | 最后写入 | 判定 |
|---|---|---|---|
| `refresh/incremental` | **17 G** | 2026-08-02 | 陈旧产物，可删候选；**但同目录 `registry.json`/`state.json`/`delta/` 是 KB 级活配置，被 `gui/refresh_registry.py` 引用，绝不能整目录删** |
| `gui-console/runs` | **5.4 G** | 2026-08-20 | 陈旧 run 产物（`worker/runner.py` 以此为 runs 根） |
| `backtests` | 4.3 G | 2026-08-18 | 陈旧 |
| `gui-run` | 442 M | 2026-09-13 | 陈旧 |
| 约 20 个 `*_check`/`*_smoke` 目录 | 合计小 | 2026-05 ~ 07 | 旧实验产物 |
| `saas_uploads` | — | **今天** | **活跃，勿动**（job_38 今日仍在写） |
| `market_risk` | 262 M | 2026-10-26 | **活跃，勿动** |
| `video_packages` | 233 M | 2026-10-24 | 近期活跃，勿动 |

QRE 仓库 `.tmp` 874M：`ms-playwright` 681M + `browser-venv` 142M 是浏览器审计工具链（要留），其余约 60M 是各任务证据。

### 7.3 决策状态

1. `stock_daily_qfq_legacy` 已消失：仍待用户决定接受无 qfq 回滚，或从 tushare 重拉应急档（另起新名）。
2. 分钟 chunk 压缩：用户本轮要求暂停分钟数据清洗/整理，未重跑 `compress_minute_chunks.sh`。
3. 分钟 CSV：用户已补入 20261019/20/21 三日；只读检查通过，等待 timer 自动入库，未手动触发。
4. ~~删除 `akshare_data`~~：已批准并执行；仅留结构与行数，本体不可恢复。
5. ~~删除 `aguhuice_test` / `quant_hub` / `aguhuice_local`~~：已批准并执行；aguhuice_local 有全量 dump。
6. ~~清理指定旧回测/实验产物~~：已批准并执行；refresh 活配置和活跃目录均保留。
7. 两个上一任务 staging 库继续保留，待各自任务验收后再删。

### 7.4 备份缺口（重要）

- 本地**没有 `tushare_data` 的 pg_dump**（`~/quant-workspace/backups/ecs-aguhuice/` 只有 ECS 上 aguhuice SaaS 库的 dump）。
- 因此 513 GB 主库目前**只有 TimescaleDB 自身 + 磁盘这一层保护**，没有逻辑备份。建议用户决定是否建立定期 dump 策略（可参考 `deploy/saas/pull-ecs-backup.sh` 的模式做本地版）。
