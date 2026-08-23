# CR：衍生品行情数据源接入（期权/可转债/利率曲线）

- 日期：2026-08-23 ｜ 状态：⏳ 待批准（路线已定稿：用户 tushare 实测 **2120 积分**）
- **路线定稿（2026-08-23，按积分实况）**：转债 = tushare cb_basic/cb_daily（2000 分 ✓）；
  利率曲线 = **akshare `bond_china_yield`（免费官方源，yc_cb 单独权限不开通）**；
  期权 = tushare `opt_daily`（2000 分 ✓）+ **akshare 交易所接口替代 opt_basic**
  （5000 分不满足，放弃升档，理由见 §3/§8）。全路线零新增花费。
- 前置：`docs/frm/CR_2026-08-23_risk_derivatives_extension.md`（R5–R7 衍生品计算内核已完成，
  纯函数零 DB，其 §5 明确「行情接入留待未来数据源 CR，内核函数签名即为消费接口」——本文档即该 CR）
- 涉及项目：quant_ts（数据入库归属方）、quant-research-engine-dual-agent-lab（消费方 QRE）

## 1. 背景与目标

FRM 风险模块 R5（rates/bonds）、R6（options）、R7（portfolio/derivatives_var）计算内核已完成并通过
教材数值验收，但当前 `tushare_data` 库只有股票日线/因子/reference 数据，**期权、可转债、利率曲线
行情全部缺失**，内核无真实数据可算。本 CR 目标：

1. 可转债全量档案与日线行情入库（`cb_basic` / `cb_daily`），对接 R5 转债债底计算。
2. 中债国债收益率曲线（即期）日更入库，对接 R5 零息曲线插值。
3. 50ETF/300ETF 期权合约档案与日线行情入库（`opt_basic` / `opt_daily`），对接 R6 BSM/隐波。

定位与内核 CR 一致：数据接入 + 最小适配示例管道，不做策略、不做 GUI。

## 2. 范围

### In Scope

- 新建 DB schema `derivatives`（归属 quant_ts 写入，QRE 只读），含表：
  `cb_basic`、`cb_daily`、`yc_curve`、`opt_basic`、`opt_daily`。
- quant_ts 侧新增入库 handler 与日更接线（遵循其冻结清单纪律：备份→dry-run→评审→上线）。
- 历史回填（范围见各阶段）。
- QRE 侧最小只读适配模块（每阶段一个示例管道函数 + 单测/冒烟），证明内核有数据可算。

### Out of Scope（明确不做）

- 期权波动率曲面拟合/插值、Greeks 全市场批量预计算入库（隐波/Greeks 由 QRE 按需计算，不落库）。
- 转债条款引擎（赎回/回售/下修）、转债期权腿定价。
- 分钟级行情（`opt_minute`）、商品期权、股指期权（50ETF/300ETF 之外）、国债期货。
- FR007 利率互换曲线、信用债收益率曲线（仅国债无风险曲线）。
- GUI 展示、risk_report 扩展、晋升闸对接。
- 存量表 hypertable 修复（quant_ts README「常见故障 #1」是独立运维事项）。

## 3. 接口可用性与字段确认（调研结论）

- `cb_basic`（doc_id=185，≥2000 积分）：ts_code、bond_short_name、stk_code（正股）、maturity、par、
  coupon_rate、pay_per_year、value_date、maturity_date、list_date、delist_date、conv_price 等。
  注：转债多为累进票息，`coupon_rate` 为参考值，精确现金流需 `cb_coupon`（票面利率接口）——
  D1 先用累进票息近似并在结果披露，精确化列为后续可选项。
- `cb_daily`（doc_id=187，≥2000 积分，单次 2000 行，支持 trade_date 快照）：OHLC、vol、amount，
  **自带 bond_value（纯债价值）/cb_value（转股价值）**，可用于 R5 债底交叉验证。
- `opt_basic`（doc_id=158，≥5000 积分）：**用户 2120 分不满足，放弃升档**。
  替代：akshare `option_current_day_sse/szse`（交易所源，当日存续合约全量：
  行权价、到期日、合约单位、call/put、前结算价），免费。口径差异披露：
  仅覆盖当日存续合约，历史已摘牌合约档案不全——历史回填时用 opt_daily
  实际出现过的 ts_code 反推档案（exercise_price/maturity_date 从当日
  合约列表抓不到的老合约，从合约代码规则解析行权价/到期月，精度足够
  BSM/隐波使用）；日常日更只需当前合约，无影响。
- `opt_daily`（doc_id=159，≥2000 积分，单次 15000 行，支持 trade_date 快照）：
  OHLC、settle、pre_settle、vol、oi（settle 为隐波反解输入，比 close 更稳）。
- `yc_cb`（doc_id=201）：**已决定不开通**（单独权限接口，需另行付费）。
  采用 akshare `bond_china_yield`（中国债券信息网 chinabond 官方源，
  标准期限 0~30 年全曲线，免费；单次调用区间 <1 年，回填分段循环）。
  chinabond 官网 Excel 整年打包下载作为兜底校验。
- 权限验证方式：复用 quant_ts `reference_data_permission_smoke.py` 模式，只读不调库，
  作为各阶段第一步验收。

## 4. 管线归属与惯例（依据 quant_ts README/代码）

quant_ts 的标准做法有两套：

- **参考数据套件**（`handlers/reference_data_handler.py` + REFERENCE_DATASETS 注册表 +
  `sync_reference_data.py` + `full_reference_sync.py`）：显式列类型声明、建表+PK+hypertable、
  staging upsert、`reference.sync_audit` 审计、dry-run plan。适合静态/小数据量参考表。
- **行情 handler**（`handlers/daily_handler.py`，BaseHandler 子类）：`fetch_snapshot(trade_date)`
  全市场日快照 + 逐代码历史抓取 + `core/base_engine.py` DDL/upsert，挂在
  `sync_manager.py --mode daily` 流程中。

**决策：`derivatives.cb_basic` / `opt_basic`（静态档案）走参考数据套件模式（注册进
REFERENCE_DATASETS 或等价新注册表）；`cb_daily` / `opt_daily` / `yc_curve`（日行情）
新建 `handlers/derivatives_handler.py`，按 trade_date 快照复用 base_engine，挂入
sync_manager 日更链。** 理由：转债/期权日线与 stock_daily 同类（行情快照），且没有复权自愈需求，
不需要 reference 套件的周/月分块审计逻辑；但所有新列一律显式 TEXT/DATE/NUMERIC 声明
（quant_ts README 故障 #3 的教训），不依赖 pandas 类型推断。

冻结纪律：改动 `sync_manager.py`（冻结清单内）前必须备份 → 只读 dry-run 验证 → 人工评审，
通过后方可赶在次日 16:30 前上线。新 handler 的首次上线先以「只同步、不接下游」灰度一天。

## 5. 表结构设计（新 schema `derivatives`）

| 表 | PK | 时间列（hypertable） | 关键列 | 写入方 |
|---|---|---|---|---|
| `derivatives.cb_basic` | (ts_code) | 无（静态表，普通表） | 全部 cb_basic 输出列，显式类型；coupon_rate/par/maturity NUMERIC，日期列 DATE | quant_ts |
| `derivatives.cb_daily` | (ts_code, trade_date) | trade_date | pre_close/open/high/low/close/change/pct_chg/vol/amount + bond_value/bond_over_rate/cb_value/cb_over_rate（NUMERIC） | quant_ts |
| `derivatives.yc_curve` | (trade_date, ts_code, curve_type, curve_term) | trade_date | curve_name TEXT、curve_term NUMERIC（年）、yield NUMERIC（%，原始口径，换算留给消费方） | quant_ts |
| `derivatives.opt_basic` | (ts_code) | 无（静态表） | 字段对齐 tushare opt_basic 结构（exercise_price NUMERIC，maturity_date/list_date/delist_date DATE）+ `source` 列（akshare_sse/akshare_szse/backfill_inferred）；**来源为 akshare 交易所接口**，历史摘牌合约由 opt_daily 反推补齐 | quant_ts |
| `derivatives.opt_daily` | (ts_code, trade_date) | trade_date | pre_settle/pre_close/open/high/low/close/settle/vol/amount/oi（NUMERIC） | quant_ts |

hypertable：沿用 `ensure_reference_table`/`base_engine.init_db_structure` 的
`create_hypertable(..., if_not_exists=TRUE)` 模式（失败仅告警不阻塞——当前实例 hypertable
注册故障已知，新表按普通 PG 表也能工作）。

## 6. 分阶段实施

### D1 可转债（cb_basic + cb_daily → R5 债底）

- 入库：如上表；`cb_basic` 全量（历史+存续，约 1300 行）；`cb_daily` 按 trade_date 日快照。
- 回填：cb_daily 全历史 2010-01-01 至今（约 4000 交易日 × ~0.15–0.3s 限速 ≈ 20–40 分钟，
  约 100–150 万行；周末低峰执行，避开 16:20–17:30 日更窗口）。
- 日更 timer：插入 `sync_manager.py --mode daily` 第 5 步（reference 增量）之后，
  即 16:30 quant-ts 作业内，不新建 timer。预估增量 <1 分钟，不影响 16:40 indicators 起跑。
- QRE 适配（新模块，如 `risk/data_adapters.py` 或 `risk/cb_data.py`，QRE 只读）：
  `load_cb_terms(ts_code)`（读 cb_basic）→ 现金流 (times, amounts)；
  `load_zero_curve(trade_date)`（读 yc_curve 即期，yield% ÷100 → 连续复利近似，
  披露近似口径）→ `bonds.convertible_bond_floor(times, amounts, curve, credit_spread)`。
  示例管道输出：纯债价值 vs cb_daily.bond_value 的差异披露（验证用，不求一致——
  tushare bond_value 口径未必是教材口径）。
- 验收标准：
  - [ ] 权限冒烟通过（cb_basic/cb_daily 可调）
  - [ ] 表建成且列类型为显式声明；`(SELECT COUNT(*) FROM derivatives.cb_daily)` 与
        tushare 抽样对账（抽 3 个交易日逐行核对 close/vol）
  - [ ] 回填完成，存续转债最近交易日覆盖率 ≥ 98%
  - [ ] 连续 2 个自然日（至少 1 个交易日）日更自动入库成功（journalctl 核对）
  - [ ] 示例管道：任选 5 只存续转债输出 convertible_bond_floor 结果 dict，
        数值为正、spread_duration 合理（0–10），quant_ts 与 QRE 各自 pytest 绿

### D2 利率曲线（yc_curve → rates.py）

- 注意：D2 在排期上先于或并行于 D1 的 QRE 适配部分（D1 适配依赖曲线），入库本身可与 D1 并行。
- 入库：`derivatives.yc_curve`，curve_type=1（即期）为必收，curve_type=0（到期）顺带收（同接口）。
- 回填：2010-01-01 至今（每日 500–1000 行，约 4000 日 ≈ 200–400 万行，
  按 trade_date 循环，预计 30–60 分钟）。
- 权限预案：**yc_cb 已决定不用**（见 §3）。曲线数据源固定为 akshare
  `bond_china_yield`（写入 yc_curve 表结构，curve_term 年、yield %，
  ts_code 记 '1001.CB'、curve_type='1'），落库目标库仍为 tushare_data
  （不用 akshare_data，保持 QRE 单库只读）。chinabond Excel 下载作兜底校验。
- 日更 timer：同 D1，挂 sync_manager 第 5 步后。
- QRE 适配：`load_zero_curve(trade_date)` → `{期限年: 连续复利利率}` dict，直接满足
  `rates.interp_zero_rate`、`bonds.price_from_zero_curve/dv01/key_rate_shifts` 的入参契约。
  示例管道：最新交易日曲线插值 + 一个 5 年期附息债 price_from_zero_curve/effective_duration。
- 验收标准：
  - [ ] yc_curve 数据源（akshare bond_china_yield）决策记录进 06_DECISION_LOG.md
  - [ ] 表建成；抽查 3 个交易日曲线节点数 ≥ 20、yield 在 0–10% 合理区间
  - [ ] 日更自动入库成功
  - [ ] 示例管道：interp_zero_rate 对曲线上/曲线外期限插值结果单调合理；pytest 绿

### D3 期权（opt_basic + opt_daily → R6 BSM/隐波）

- 入库：`opt_basic` 表（**akshare 交易所接口**当日合约档案 + opt_daily 反推历史合约，
  source 列标注来源）；`opt_daily` 按 trade_date 快照（每日 ~300–500 行，tushare 2000 分 ✓）。
- 回填：50ETF 期权自 2015-02-09、300ETF 期权自 2019-12-23 至今
  （约 100–200 万行，按 trade_date 循环约 3000 次调用，30–60 分钟）。
- 日更 timer：同 D1/D2，挂 sync_manager 第 5 步后（三个 handler 合计增量 <2 分钟）。
- QRE 适配：`load_option_chain(trade_date, underlying)`（join opt_basic/opt_daily，
  取 settle 为市价、exercise_price=K、maturity_date 算 T（actual/365，披露口径）、
  underlying 标的价格读 `reference.index_daily` 或 stock_daily 对应 ETF——50ETF 为
  510050.SH，日线在 stock_daily）→ `options.bsm_price` / `options.implied_vol`。
  示例管道：某一交易日 50ETF 平值附近 4 个合约的隐波反解 + BSM 价格 vs settle 披露。
- 验收标准：
  - [ ] akshare 期权档案接口冒烟通过（option_current_day_sse/szse 返回当日合约全量，
        字段含行权价/到期日/合约单位；接口失效时自动重试+告警，降级不影响其他管线）
  - [ ] 表建成；抽样对账 2 个交易日 settle/oi
  - [ ] 日更自动入库成功
  - [ ] 示例管道：50ETF 平值 call/put 隐波均在 (1%, 150%) 区间、put-call parity
        偏差 < 阈值披露；pytest 绿

## 7. 对接契约总表（内核函数 ← 数据源）

| 消费方函数 | 需要输入 | 来源表 |
|---|---|---|
| `rates.interp_zero_rate` / `bootstrap` 下游全部 | {期限(年): 连续复利零息利率} | `derivatives.yc_curve`（即期，yield%÷100，近似披露） |
| `bonds.price_from_zero_curve` / `dv01` / `key_rate_shifts` / `effective_duration_convexity` | 现金流 (times, amounts) + 曲线 | `cb_basic` + `reference.trade_calendar` + `yc_curve` |
| `bonds.convertible_bond_floor` | 同上 + credit_spread（调用方给定或按评级映射，本 CR 不做评级映射） | 同上 |
| `options.bsm_price` / `implied_vol` / `bsm_greeks` | S0, K, T, r, σ/price, call_put | `opt_daily.settle`、`opt_basic`、`stock_daily`(510050/510300)、`yc_curve` 短端 |
| `derivatives_var` / `portfolio` | 上述 Greeks/DV01 序列 | 间接消费 |

内核签名不变；适配层是唯一直接读 DB 的新代码，放 QRE 侧（quant_ts 只负责写入）。
tushare 日期字符串与 DB DATE 列的转换、curve_term=0 点（隔夜）的处理、缺失节点丢弃，
全部在适配层处理并单测。

## 8. 风险

1. ~~opt_basic 需 5000 积分~~ **已解决（2026-08-23）**：用户 2120 分，opt_basic 不可得；
   用 akshare 交易所接口替代（口径差异：仅当日存续合约，历史档案由 opt_daily 反推，
   已在 §3/§5 披露）。剩余风险：akshare 免费接口改版失效——管道需重试+缓存+失败告警。
2. ~~yc_cb 单独权限~~ **已解决（2026-08-23）**：不开通，固定用 akshare bond_china_yield
   （chinabond 官方源，口径与 yc_cb 即期曲线一致）。需引入 akshare 依赖到 quant_ts
   （新依赖已获用户知情，本机 uv 缓存已有 1.18.x，零网络成本）。
3. **转债累进票息**：cb_basic.coupon_rate 非逐年票息，D1 债底现金流为近似——结果 dict 中披露，
   精确化（cb_coupon 接口）列为后续可选项，不阻塞验收。
4. **冻结文件改动**：sync_manager.py 接线按 quant_ts 冻结纪律执行；新 handler 先灰度一天。
5. **hypertable 注册故障**：新表 hypertable 激活可能静默失败（已有容错），按普通表运行，
   性能无影响（量级小）；修复属独立运维事项。
6. **日更窗口时间预算**：三个新 handler 增量 <2 分钟，16:30 作业留有余量；回填一律周末执行。

## 9. Suggested Tasks

| Task ID | Task | Priority | Status |
|---|---|---|---|
| D1.1 | 权限/接口冒烟：tushare cb_basic/cb_daily/opt_daily + akshare option_current_day_sse/szse + akshare bond_china_yield（只读脚本） | High | TODO |
| D1.2 | quant_ts：derivatives schema + cb_basic/cb_daily handler + 单测 | High | TODO |
| D1.3 | cb_daily 历史回填（周末） + 对账 | High | TODO |
| D1.4 | sync_manager 接线（备份→dry-run→评审→上线→灰度） | High | TODO |
| D2.1 | yc_curve 入库（akshare bond_china_yield，分段回填）+ 决策记录 | High | TODO |
| D2.2 | QRE load_zero_curve 适配 + 示例管道 + 单测 | High | TODO |
| D1.5 | QRE 转债债底示例管道 + 单测 | Medium | TODO |
| D3.1 | opt_basic/opt_daily 入库 + 回填 | Medium | TODO |
| D3.2 | QRE 期权链适配 + 隐波示例管道 + 单测 | Medium | TODO |
| ALL | docs/agent 全套记忆文件 + quant_ts README 表归属更新 | High | TODO |

## 10. Proposed Agent State Transition

- Next Phase: `PLANNING`（批准后进入 D1 实施 brief）
- Next Owner: `KIMI_CODE`
