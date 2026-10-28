# CR-2026-10-28 平均持股周期 + 风险调整收益（α/β/IR）

状态：已实施，未 commit/push（等用户验收）
关联：`docs/agent/24_PERF_METRICS_CONTRACT.md`（口径合同，本轮新建）

## 1. 需求

1. 策略回测信息加入平均持股周期分析
2. 个股回测详情加入平均持股周期分析，交易明细表加入**每次交易**的持股周期
3. 回测详情加入 α、β、information ratio 数据统计

## 2. 关键调研结论（已核实）

- `round_trips.csv` **已有 `holding_days` 列**，实证为**自然日**（04-21→05-22 = 31，交易日约 22）
- `strategy_performance.json` **已有** `average_bars_in_trade` / `_winning_trades` / `_losing_trades`，但未下发前端
- `risk/performance.py::performance_summary` **已实现** Sharpe/β/IR/Jensen's α
- ECS 生产库实测：job 58 的 `chart_data` **有 `benchmarks`（4069 点）+ `equity`**；
  600330 的 symbol 快照**无 `benchmarks`** 但**有 `kline`**
- 本地 run 产物已清空、ECS 无行情库 → **后端补算对存量产物不可行**

## 3. 核心决策：前端算，不后端算

| 方案 | 存量产物 | 结论 |
|---|---|---|
| 后端算 + 重跑 | 需重跑全部回测才生效 | **不可行**（run 产物已清空） |
| **前端算（选此）** | **1013 个存量产物零重跑立即显示** | job 用 benchmarks、symbol 用 kline，都在快照里 |

代价是 JS/Python 双实现 → 用**交叉验证测试**锁死（见 §5）。

## 4. 实施

### 4.1 新增 `static/perf-metrics.js`（`window.QREPerfMetrics`）

纯函数层：`dailyReturns` / `alignReturns` / `sharpe` / `beta` / `informationRatio` /
`jensensAlpha` / `riskAdjusted`（主入口）/ `holdingDaysOf` / `avgHoldingDays`。
IIFE + `typeof window` 守卫，Node vm 可测。每个函数注释标注 Python 出处。

### 4.2 `job.html`

- 引入 `perf-metrics.js`
- `#metric-strip` 加第 7 张卡「平均持股周期」：
  优先 `m.avg_holding_days`（后端）→ 回退 `chart_data.trades.points` 现算（仅 `!sampled`）→ 「—」
- 新增 `#ra-strip` + `renderRiskAdjusted(d)`：α（年化）/ β / 信息比率
- 基准 = `benchmarks` 里第一个 `closes` 非空的指数；三项全 null → 整块隐藏

### 4.3 `symbol.html`

- 引入 `perf-metrics.js`
- `renderSummary(s, trades)` 签名加 `trades`，`#sum-strip` 加「平均持股周期」卡
- 交易明细表两条 `tradeCols` 路径都加「持股周期」列（前端从 entry/exit 现算，两条路径统一）
- 新增 `#ra-strip` + `renderRiskAdjusted(d)`；**基准 = 区间买入持有该股**
  （从 `d.kline.ohlc[i][1]` 收盘按 `d.equity.dates` 对齐）

### 4.4 后端（最小改动）

- `gui/engine.py::SUMMARY_METRIC_FIELDS` 加三项持股周期 → worker summary → DB → job.html
- `gui/lab_result.py` chart_data `metrics` 同步加 `avg_holding_days` / `_win` / `_lose`
- **未改** symbol detail 后端

### 4.5 Sharpen 不重复（决策）

两处均已有引擎口径「夏普比率」且已验收，**保持不动**。理由：① 既有展示不动最安全；
② 同页两个口径的夏普会造成困惑；③ α/β/IR 是本次真正的增量；④ 后续要补一行即可
（`ra.sharpe` 已算好）。已向用户明示此决策。

## 5. 测试

新增 `tests/test_perf_metrics.py` 10 例：

1. **交叉验证**：Python `performance_summary` 在三组序列（β=0.116/0.85/1.4）上现算期望值，
   Node vm 跑真实 `perf-metrics.js` 比对，容差 1e-9；覆盖主入口、单函数入口、
   dated-benchmark 对齐路径、含 null/0/负值的脏序列
2. **边界**：样本不足、基准恒定（β/α 降级 null 而 IR 仍有效）、脏净值、长度不齐、
   `holdingDaysOf` / `avgHoldingDays` 的非法日期与未平仓
3. **源码合同**：JS 常量与 `risk/constants.py` 一致、公式标注 Python 出处、
   两模板必须引入共享层且不得内联公式
4. **渲染行为** `TestRiskAdjustedRendering`：全 null → 整块隐藏并清空；
   有值 → 3 张卡且数值与 Python 夹具一致；跳过 `closes` 为空的基准；
   symbol 版用 kline 买入持有基准；缺 kline → 隐藏

**RED 验证两次**：① 把 β 分母改成 `var*m` → 交叉验证 2 例立即红；
② 让 `renderRiskAdjusted` 不再跳过空 `closes` 基准 → 渲染测试立即红。

## 6. 过程踩坑（已写进 24 号文档纪律）

1. **夹具序列错位**：期望值按构造策略的原始收益序列算（400 点），JS 从净值曲线差分得 399 点，
   Sharpe 差 2.6%。夹具必须按 **JS 实际看到的序列** 算。
2. **vm harness 的 `window` 不是全局**：`window.QREPerfMetrics` 只落在普通对象上，
   vm 内 `typeof QREPerfMetrics` 恒 `'undefined'` → `renderRiskAdjusted` 永远走隐藏分支。
   修法：`sandbox.window = sandbox`（浏览器同构）。
3. **harness 抽取区窄于依赖**：`renderRiskAdjusted` 定义在各 harness 抽取区之外，
   `poll()` / `load()` 调它 → ReferenceError 被 catch 吞掉、页面静默「加载失败」，
   4 个测试同时红。已在 3 个 harness 补桩（与 `renderMetrics` 同规格）。
4. **主指标卡 6 → 7**：`test_job_keeps_six_main_metric_cards` 死守 6 张，
   已按其本意（盈亏比不得混进主指标卡）改写为 7 张 + 排除项 + 必须含平均持股周期。
5. 测试里 `const el = els['ra-strip']` 在读的时候元素还没被创建（元素由函数内部
   `getElementById` 创建）→ 必须先调用再读。

## 7. 验证

- `uv run pytest tests/test_perf_metrics.py -q` → 10 passed
- 相关 5 文件 → 154 passed
- 全量 `uv run pytest tests/ -q` → `3018 passed, 24 skipped`
- 两模板 `<script>` 块 `node --check` 通过（Jinja 占位符先渲染）

### 7.1 真实浏览器端到端（Chromium，`.tmp/perf-browser/`）

进程内起 Flask SaaS（临时库 + `SAAS_DEV_AUTH`）灌真实 chart_data 与 symbol 详情产物 →
test client 渲染两个页面 → 本地 HTTP server（页面 + `/static` + `/sw.js`）→ Playwright
路由拦截 `/api/**` 回 fixture → 真实 Chromium 断言。**跑的是真实模板 + 真实
perf-metrics.js + 真实 DOM/CSS，不是桩。**

| 断言 | 结果 |
|---|---|
| job `#metric-strip` 卡数 | **7**（含「平均持股周期」） |
| job 平均持股周期 | `45.3 天`（来自后端 `avg_holding_days`） |
| job `#ra-strip` 三卡 | α=**12.00%** / β=**0.89** / IR=**0.78** |
| **与 Python 对账** | `performance_summary` 同序列：α=0.1200、β=0.8904、IR=0.7812 → **完全一致** |
| 全 null → 隐藏 | `display:none` 且 `innerHTML` 长度 0（不留空壳） |
| 不重复夏普 | `#ra-strip` 不含「夏普」 |
| 口径披露 | tooltip 含「与上方曲线同源」/「基准 = 区间内买入持有该股」 |
| symbol 平均持股周期 | `48.7 天`（= (31+35+80)/3，前端从 trades 现算） |
| symbol 交易表持股周期列 | `31.00 / 35.00 / 80.00 / —`（未平仓显示 —） |
| 375px 横溢 | `scrollWidth == innerWidth`，无横溢 |
| pageerror / console error | **0** |

（symbol 页 α/β/IR 与 job 页相同是 fixture 故意同序列所致，生产两者基准不同、数值会不同。）

## 8. 已知限制（已告知用户）

1. **存量 job 的平均持股周期**：交易数 >500（`sampled=true`）且 DB summary 无新键 → 「—」。
   新回测全部有值。
2. **存量 symbol 的平均持股周期与 α/β/IR**：立即可用（前端从快照内 `d.trades` / `d.kline` 算）。
3. **前端 α/β/IR 与后端 `risk_report.json` 的 performance 节口径不同**（净值曲线差分 vs
   引擎日收益序列），数值可有差、方向应一致。已在 tooltip 与 24 号文档声明，不视为 bug。
