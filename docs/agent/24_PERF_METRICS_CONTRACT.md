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
| 前端（JS） | **统一账户净值曲线差分**（`chart_data.equity` / symbol 的 `equity.values`） | 见 §3 |
| 后端 `risk_report.json` | **同一账户日收益序列**（`extract_strategy_returns`） | 基准指数 |

两者均以统一账户曲线为来源；若历史风险报告尚未迁移，可能保留旧值，迁移后应一致。
tooltip 与 UI 上已披露「按净值曲线差分的日收益计算，与上方曲线同源」。

---

## 3. 基准选择规则（硬规则）

### 2.3 页面收益率唯一口径（2026-11-25 起）

- batch 每只股票视为回测起点已预留 `initial_cash` 的独立账户；上市前持有现金，在市期间使用真实权益，最后净值日后结转最终权益，无净值行股票也保留预留现金账户。
- 组合累计收益曲线：`cumret_t = Σ账户权益_t / Σinitial_cash − 1`；日收益为组合总权益环比。终点必须等于 `Σfinal_equity/Σinitial_cash−1`。
- 总指标、收益曲线、区间卡、重播及超额全部使用该序列；区间收益=`(1+cumret_end)/(1+cumret_start)−1`，超额=`策略区间收益−同期上证指数区间收益`。
- shared_cash 使用同一账户总权益首末归一；个股使用`期末权益/期初权益−1`。禁止再把交集累乘或原始注资净值作为另一套页面收益。

## 3. 基准选择规则（硬规则）

| 页面 | 基准 | 数据来源 | 存量产物是否立即可用 |
|---|---|---|---|
| `job.html`（策略级） | **固定上证指数 `000001.SH`** | `chart_data.benchmarks` 内同名指数，按策略净值日期对齐 | ✅ 是 |
| `symbol.html`（个股级） | **固定上证指数 `000001.SH`** | `d.benchmarks` 内同名指数，按个股策略净值日期对齐 | ✅ 是；缺指数时指标为 null |

自 2026-11-17 起，用户决定取消股票/股票池的持有至到期统计。所有“超额收益”均为
`策略区间收益 − 同期上证指数区间收益`，不得回退到买入持有；风险调整 α/β/IR 的
市场基准也统一为上证指数。多指数曲线仍可对照，但不改变超额口径。

**为什么整体前端算而不是后端算**：快照已带指数序列；前端与页面曲线同源，存量结果
可在无行情库的 ECS 上复算。缺基准必须显式为空，不编数。

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
