# CR-2026-10-11: stock_daily 前复权混合锚点问题与修复方案

## 问题（已确证，证据见 20 号文档 §2.1）

`public.stock_daily` 由 `quant_ts/handlers/daily_handler.py` 用 `pro_bar(adj='qfq')` 拉取，OHLC 为**前复权价**。qfq 锚点 = 拉取时刻的最新复权因子，导致：

1. **每股锚点不统一**：取决于该股最后一次全历史重建的时间（例：000001.SZ 2010 年段锚定在 2020-05 的因子 109.169，而当前最新因子 142.07）。
2. **同股序列混合尺度**：历史段是旧锚 qfq，近期增量段是当前锚（≈原始价尺度）。除权自愈机制（README 声称因子变化即全历史重建）实测未生效——000001.SZ 因子 2026-09-24 变了，但 2010 年段仍是旧锚。
3. **后果**：以 close 序列直接计算收益率/价格型因子（MA、动量等）在除权日和锚点交界处有假性跳变；回测引擎若以 close 序列算收益，长区间结果失真。`pct_chg` 列正确（tushare 按调整后 pre_close 算）。

对比：`stock_minute_1m`（分钟线）为原始价 + adj_factor，口径规范（raw + factor，复权在计算层做）。

## 方案选项

### A. stock_daily 重建为原始价（推荐）
- 用 tushare `pro.daily`（原始价）全量重建 stock_daily（约 1363 万行，逐股/逐日拉取，估 4-8 小时，需测限速）。
- 因子与回测层统一在计算时按需复权（用 adj_factor 做前复权到指定基准日，或收益率口径用 pct_chg）。
- 优点：与分钟线口径一致，一次到位，永久消除锚点漂移；符合 20 号文档 §6 硬规则。
- 代价：因子 11 表需按新口径重算（约等于一次全量因子回填，数小时）；QRE 引擎收益率计算路径需确认使用口径（建议收益统一用前复权收益率 = 今日 adj_close/昨日 adj_close - 1）。
- 风险：重建期间引擎读到的表处于中间态——需重建到影子表 `stock_daily_raw` 再原子换名。

### B. 修复 qfq 自愈，统一锚点
- 保留 qfq 设计，修自愈 bug，并加"全表锚点一致性巡检"（每股最新 adj_factor vs 表内隐含锚点）。
- 优点：改动小。缺点：qfq 每天因新除权而全历史漂移，巡检/重建是长期运维负担；与分钟线口径仍不一致。

### C. 暂不动日线，仅分钟线入库 + 引擎侧适配
- 仅记录风险，回测收益率改用 pct_chg 链式计算（该列正确）。
- 优点：零迁移。缺点：价格型因子仍受影响；问题遗留给未来。

## 建议

选 A，且放在因子库 P0 之前执行（因子库回填依赖价格口径最终态，避免二次重算）。与分钟线入库（进行中）不冲突。

## 状态

2026-10-11 用户批准方案 A。实施步骤：

1. `quant_ts/rebuild_daily_raw.py`：用 `pro.daily`（按 trade_date 逐日拉全市场）+ `adj_factor` 建影子表 `public.stock_daily_raw`（同结构、hypertable 7天chunk），含逐日行数审计；验收后原子换名。
2. `quant_ts/handlers/daily_handler.py`：增量同步改用 `pro.daily` 原始价（qfq 自愈逻辑废弃）。
3. `indicators_tushare/core/db_manager.py`：`load_stock_history*` 加载后把 open/high/low/close/pre_close × adj_factor（后复权尺度，收益率正确、序列同锚），因子全量重算。
4. QRE `data/postgres.py::load_daily_bars`：价格列 × adj_factor；GUI 展示层（lab_result）锚定最新价（×fac/fac_latest）。
5. 顺序：1 与分钟入库并行（API-bound）→ 验收 → 换名 → 2/3/4 生效 → 因子全量重算 → QRE 冒烟回测对账。
