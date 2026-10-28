# 24_PERF_METRICS_CONTRACT.md — 风险调整收益与持股周期口径合同

> **这份文档是「持股周期」与「α / β / IR / Sharpe」四个指标的唯一权威口径**。
> 改任何公式、常量、基准选择或数据来源，必须先改这份文档，再改代码，并让
> `tests/test_perf_metrics.py` 通过。**不允许**在模板或页面里另写一套公式。

---

## 1. 两个共享实现（必须逐值一致）

| 实现 | 位置 | 用途 |
|---|---|---|
| Python 权威实现 | `src/quant_research_engine/risk/performance.py` | 后端 `risk_report.json` 的 performance 节、lab 8081 |
| JS 共享层 | `src/quant_research_engine/gui/static/perf-metrics.js`（`window.QREPerfMetrics`） | SaaS `job.html` / `symbol.html` 前端现算 |

常量单一来源 `src/quant_research_engine/risk/constants.py`：

- `ANNUALIZATION_FACTOR = 252`
- `DEFAULT_RISK_FREE_RATE = 0.03`（年化，simple 口径）

`tests/test_perf_metrics.py` 用 Python `performance_summary` 在三组固定序列上现算期望值，
让 Node vm 跑真实 `perf-metrics.js` 比对，**容差 1e-9**；并有源码合同断言 JS 里的
`var ANN = 252;` / `var RF = 0.03;` 与 Python 常量一致。**任何一侧漂移立即红。**

---

## 2. 公式（与 `risk/performance.py` 逐条对应）

| 指标 | 公式 | Python 出处 |
|---|---|---|
| 日收益 | `v[i]/v[i-1] − 1`，跳过 null / 非有限 / ≤0 | `perf-metrics.js::dailyReturns` |
| Sharpe | `mean(r − rf/252) / std(r, ddof=1) × √252` | `performance.sharpe_ratio` |
| β | `cov(r, m, ddof=1) / var(m, ddof=1)` | `performance.beta`（书1 Ch5 式 5.1） |
| IR | `mean(r − m) / std(r − m, ddof=1) × √252` | `performance.information_ratio` |
| Jensen's α | `(r − rf/252) = α + β(m − rf/252) + ε` 的截距；`alpha_annual = alpha_daily × 252` | `performance.jensens_alpha`（式 5.5） |
| 持股周期 | `exit_date − entry_date`（**自然日**） | `round_trips.csv::holding_days` |

### 2.1 与 Python 的已知行为差异（刻意保留，不是 bug）

基准恒定（方差 0）时：

- Python `beta()` / `jensens_alpha()` **抛 `ValueError`**；
- JS **降级返回 `null`**（前端不能抛错，整页会变成「加载失败」）。

IR 在基准恒定下**仍然有效**（active = 策略 − 恒定基准，TE = 策略自身波动），两端都算。

### 2.2 输入序列差异（数值可有差，方向应一致）

| 路径 | 收益序列 | 基准 |
|---|---|---|
| 前端（JS） | **净值曲线差分**（`chart_data.equity` / symbol 的 `equity.values`） | 见 §3 |
| 后端 `risk_report.json` | **引擎日收益序列**（`extract_strategy_returns`） | 基准指数 |

两者输入序列不同 → 数值可有差。前端口径的优势是**与页面曲线同源、用户可自行复算**。
tooltip 与 UI 上已披露「按净值曲线差分的日收益计算，与上方曲线同源」。

---

## 3. 基准选择规则（硬规则）

| 页面 | 基准 | 数据来源 | 存量产物是否立即可用 |
|---|---|---|---|
| `job.html`（策略级） | `chart_data.benchmarks` 里**第一个 `closes` 非空**的指数 | 快照内已有（已实测 job 58：上证指数 4069 点） | ✅ 是 |
| `symbol.html`（个股级） | **区间内买入并持有该股** | `d.kline.dates` + `d.kline.ohlc[i][1]`（收盘），按 `d.equity.dates` 对齐 | ✅ 是（kline 在所有快照里都有） |

**为什么个股级用「买入持有该股」而不是指数**：symbol 快照**不带** `benchmarks` 键
（per-symbol 产物为控体量不下发指数序列），而个股层面唯一有经济意义的对比就是
「交易节奏 vs 单纯拿着不动」——这也与 `summary.bench_ret`（区间自然涨幅）口径一致。

**为什么整体前端算而不是后端算**：本地 run 产物已清空、ECS 无行情库，后端补算对
存量产物不可行；前端算让 1013 个存量产物**零重跑立即显示**。

---

## 4. 展示契约

| 页面 | 位置 | 卡片 |
|---|---|---|
| `job.html` | `#metric-strip` 第 7 张 | 平均持股周期 |
| `job.html` | `#ra-strip`（新，紧跟 `#metric-strip`） | α（年化）/ β / 信息比率 |
| `symbol.html` | `#sum-strip` | 平均持股周期 |
| `symbol.html` | 交易明细表 `#tbl-trades` | 「持股周期」列（逐笔自然日） |
| `symbol.html` | `#ra-strip`（新，紧跟 `#sum-strip`） | α（年化）/ β / 信息比率 |

**硬规则**：

1. **Sharpe 不在这两处重复**。`#metric-strip` 与 symbol FRM 条均已有引擎口径「夏普比率」
   且已验收；同页出现两个口径的夏普会造成困惑。若将来要「曲线口径 Sharpe」，
   在 `renderRiskAdjusted` 里加一张卡即可（`ra.sharpe` 已算好）。
2. 三项（α/β/IR）**全为 null → 整块隐藏并清空 innerHTML**，不留空壳。
3. 缺数据一律「—」，**不编 0**（`avgHoldingDays` 全行无效时返回 null）。
4. tooltip 必须披露基准名与「与上方曲线同源」。

---

## 5. 数据来源与已知限制

### 5.1 平均持股周期

| 层级 | 首选来源 | 回退 | 说明 |
|---|---|---|---|
| 策略级 | `strategy_performance.json::average_bars_in_trade` → `SUMMARY_METRIC_FIELDS` → `results.summary` → `chart_data.metrics.avg_holding_days` | `chart_data.trades.points` 现算（**仅当 `sampled === false`**，即 ≤500 笔） | 全量口径；>500 笔时 points 被采样，不能用来算均值 |
| 个股级 | 前端从 `d.trades` 现算 | — | trades 全量在快照里 |

**存量 job 的限制**：该 job 交易数 >500 且 DB `results.summary` 无新键 → 显示「—」。
新回测全部有值。

### 5.2 `holding_days` 口径实证

`round_trips.csv::holding_days` 是**自然日**，不是交易日：

- `2025-04-21 → 2025-05-22` = 31（交易日约 22）
- `2025-10-16 → 2025-11-13` = 28

所以前端从 `entry_date`/`exit_date` 现算自然日，与后端口径逐值一致，
`trades.csv` 路径（本无该列）与 `round_trips.csv` 路径因此统一。

---

## 6. 防漂移纪律（每次交互必须执行）

1. 改公式/常量 → **同时**改 `risk/performance.py`（或 `constants.py`）与 `perf-metrics.js`，
   并让 `tests/test_perf_metrics.py` 全绿。
2. 新增页面要用这些指标 → **只准调 `QREPerfMetrics`**，禁止在模板里内联公式
   （`test_templates_use_shared_helpers_not_inline_formulas` 会抓）。
3. 新增 render 函数被 `poll()` / `load()` 调用时，**必须同步给所有 Node vm harness 补桩**
   （`test_gui_saas_pages.py` 的 job/symbol 两个 harness、`test_saas_classic_actions_ui.py`），
   否则会 ReferenceError 被 catch 吞掉、页面静默「加载失败」。
   本次踩过：`renderRiskAdjusted` 定义在 harness 抽取区之外，4 个测试同时红。
4. 测试夹具算期望值时，**必须按 JS 实际看到的序列算**（从净值曲线差分），
   不能拿构造策略时的原始收益序列——两者差一个元素，Sharpe 能差 2.6%。
