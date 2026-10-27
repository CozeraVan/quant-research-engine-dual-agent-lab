# 23_KLINE_IMPLEMENTATION.md — 当前 K 线实现与特性交接

> 目的：供 DeepSeek 后续评估或重写 K 线实现时使用。本文只记录**当前真实实现、数据合同、交互与已知边界**，不是 TradingView 重写任务书，也不要求立即修改代码。
> 范围：QRE 本地 lab、aguhuice.com SaaS、《我不是股神》WSL Demo。三者不是同一套页面，但共享 ECharts、部分因子合同与 UI 规范。
> 当前状态日期：2026-10-27。游戏后续优化暂停到明日，Night Mode 与因子呈现协议已部署待用户验收，均未 commit/push。

## 1. 总体架构与文件地图

### 1.1 共用前端基础

- 图表库：`src/quant_research_engine/gui/static/echarts.min.js`（本地 vendored，不用 CDN）。
- 因子分组：`src/quant_research_engine/gui/static/factor-layout.js`。
- 重播组件：`src/quant_research_engine/gui/static/replay.js`。
- 夜间主题：`src/quant_research_engine/gui/static/night-mode.css`、`night-mode.js`。
- 主题与提示：`lab-theme.css`、`lab-ui.js`（含 `LabUI.helpTips`、日历等）。
- SaaS 页面：`gui/saas/templates/job.html`、`symbol.html`、`base.html`。
- 本地 lab：`gui/lab_result.py` 与 `gui/templates/lab_symbol.html`。该模板是独立静态个股页，不是 SaaS 模板副本；没有因子 chips、重播、Night Mode 或显式 `dispose()`。
- 游戏：`src/quant_research_engine/game/templates/game.html`，后端为 `game/{session,data,factors,engine,web}.py`。

### 1.2 后端到页面的主要链路

**QRE 本地/worker**

1. 回测产物生成 orders、trades、round_trips、equity_curve、risk_report 等 CSV/JSON。
2. `gui/lab_result.py::build_lab_symbol_detail()` 组合单股详情。
3. `_fetch_stock_daily()` 读 K 线，`_fetch_factor_panels()` 读策略因子并按交易日对齐。
4. `gui/saas/app.py::api_result_symbol_detail()` 优先返回 worker 的 gzip 详情；本地没有对应产物时可走 fallback 组装。
5. 页面收到统一 detail 结构后渲染静态图；只有 SaaS 页面会进一步进入重播，本地 lab 模板不加载 `replay.js`。

**数据口径**

- 当前日线底表是原始不复权 OHLC + `adj_factor`，不是历史混合前复权快照。读取/展示层负责复权与锚点处理，不能把旧 qfq 当现行事实。
- `stock_daily_qfq_legacy` 已不存在，禁止把它写成可用的回滚路径。
- K 线、成交量与技术指标均为日线；分钟表 `stock_minute_1m` 当前没有用于这三类页面。

### 1.3 单股 detail 的核心字段

```text
{
  ok, run_id,
  summary: {ts_code, name, total_pnl, total_ret_pct?, trades, avg_ret, win_rate, percentile, bench_ret},
  kline: {dates: [...], ohlc: [[open, close, low, high], ...], vols: [...]},
  factors: [{name, col, table, values, thresholds?, display?}, ...],
  trades: [...],
  orders: [...],
  failed_orders: [...],
  equity: {dates: [...], values: [...]},
  risk: {...},
  benchmarks?: {...},
  kline_note?: string,
  trades_source?: string,
  data_until: "YYYY-MM-DD"
}
```

注意：

- `ohlc` 顺序是 **open, close, low, high**，不是 open, high, low, close。
- 因子 `values` 与 `kline.dates` 按日一一对齐，缺失值用 `null`，不能用未来值补齐。
- orders 与 trades 不同：orders 是实际下单/成交记录，round trips 是出入场回合；重播优先 orders，缺省时回退 round trips。
- `display` 是因子呈现合同，不是数据库字段；它来自注册表，详见第 4 节。

## 2. QRE / aguhuice.com 静态 K 线实现

### 2.1 主实现：`gui/saas/templates/symbol.html::renderKline(d)`

渲染顺序：

1. 无 `d.kline.dates` 时整块隐藏，保留空壳错误信息的规则不适用于此处。
2. `QREFactorLayout.plan(factors, chipStates())` 生成 overlays、panes、chips。
3. 动态高度：有副图时 `420 + 160 * paneCount`，无副图时 `460px`。
4. 销毁旧 ECharts 实例，避免 chip 切换时残留配置。
5. 创建主 K 线与成交量，再追加 overlay、订单点和副图。
6. `echarts.init` 之后、第一次 `setOption` 之前调用 `QRETheme.themeChart(chart)` 应用当前主题。

### 2.2 主图组成

- `K线`：`type='candlestick'`，gridIndex=0。
  - 阳线 `#C93A3A`（红涨），阴线 `#1E8E5A`（绿跌）。
- `成交量`：`type='bar'`，gridIndex=1，浅紫 `#B7A6E8`。
- 均线 overlay：`type='line'`，与 K 线共用价格轴，不创建独立 DIV。
- 成交量轴以“万”为单位缩写，价格轴可缩放。

### 2.3 订单买卖点

只有 `d.orders.length > 0` 时添加两个 scatter 系列：

- 买入：红色正三角，放在当日最低价 × 0.99。
- 卖出：绿色倒三角，放在当日最高价 × 1.01。
- tooltip 包含方向、数量、成交价、金额、佣金、印花税、过户费。
- 没有 orders 的回合不会从 round trips 伪造静态订单点；重播才使用 round trips 兜底。

### 2.4 副图布局

- 有副图时，主图与成交量分别占约 42% 和 10% 高度，剩余区域按副图数均分。
- 无副图时，主图与成交量占约 58% 和 14%。
- 副图阈值线只挂在该面板第一条线上，避免重复。
- MACD 柱正红负绿，与 K 线涨跌语义一致。
- `dataZoom` 同时提供 inside 缩放和底部 slider，所有 grid 的 xAxisIndex 联动。
- 十字光标使用 `axisPointer.link: [{xAxisIndex:'all'}]`，多副图同步。

### 2.5 因子 chips

- overlay 因子：`overlay → pane → hidden`。
- 普通副图：`pane → hidden`。
- 状态存 localStorage，键由因子/面板决定。
- 切换时静态图销毁重建；若正在重播，则销毁重播并按新布局重挂，不能再创建第二个同内容 K 线模块。

## 3. 重播实现

> 本章只适用于 SaaS 的策略页 `job.html` 与个股页 `symbol.html`。本地 `lab_symbol.html` 只有静态图，游戏采用第 5 节的逐日状态机，二者都没有重播组件。

### 3.1 共用组件：`gui/static/replay.js`

核心接口：

```js
QREReplay.attach(mountEl, {
  dates,
  series: [{id, name, type, data, grid, color, raw?, extra?}],
  grids,
  yAxes,
  events: [{date, kind: 'entry'|'exit', symbol, sym, qty, price, pnl}],
  roundTrips: [{symbol, entry_date, exit_date, net_return, net_pnl}],
  chartEl,
  metricsEl,
  eventsEl,
  initialCursor,
  onFrame(cursor, metrics)
})
```

纯逻辑 exposed at `QREReplay.core`：

- `indexDates()`：日期到主轴索引。
- `binEvents()`：按交易日归箱。
- `positionCounts()`：从 round trips 展开每日持仓数。
- `nextEventfulCursor()`：跳到下一有事件或持仓变化日。
- `frameMetrics()`：截至当前帧计算累计收益、最大回撤、夏普、胜率、盈亏比、持仓和暴露度。

### 3.2 渲染与防未来数据

- 全量序列保留在内存，但每帧只把 `[0, cursor]` 截断后传给 ECharts。
- `replaceMerge: ['xAxis', 'series']`，`requestAnimationFrame` 节流。
- 主轴以净值/行情交易日为准，事件按日归箱。
- 信号日 T 用淡紫小点，成交日 T+1 用“入/出”pin，不能把信号与成交画在同一天。
- 有真实事件价格时用事件价格定位，否则使用该帧序列值。

### 3.3 接管而非复制图表

- `opts.chartEl` 存在时接管原容器，先 dispose 静态实例。
- 退出重播时 `destroy(keepDom=true)`，页面再用内存中的原数据重建静态图。
- 不允许出现第二个同内容 K 线模块。

### 3.4 控制与事件流

- 播放/暂停、单步、1/2/5/10 倍速、起始日、可拖进度、空仓快进。
- 进度条在图表下方，主控制组保持同排。
- 同日同类事件超过 5 个时聚合；当前实现按 `sym` 去重计“只”，同时披露实际“笔”数，展开可看全部明细。
- seek 会清空并重建事件流，避免重复行或未来事件。

### 3.5 策略级重播（job.html）

- 主体是策略净值、基准和回撤，不是单股蜡烛图。
- 事件来自 round trips；job 的 `lab_result._trade_points` 在 CSV 有字段时补 quantity/entry_price/exit_price，旧产物缺字段则保持纯标的，不编价量。
- 指标卡包括累计收益、最大回撤、夏普、胜率、盈亏比、当前持仓和暴露度。

### 3.6 个股 K 线重播（symbol.html）

- 默认从近 2 年起播，仍可用起始日或进度查看更早数据。
- orders 优先，round trips 兜底；同样遵守无字段不造值。
- 与静态图共用 `QREFactorLayout.plan`。
- `onFrame` 另显示当前 OHLC、成交量、全部因子值、持仓状态、毛浮动盈亏和已实现净盈亏。

### 3.7 当前格式注意点

- `yAxes` 可传 `pct:false` 关闭价格/成交量轴的百分号。
- 但重播 tooltip 仍有统一的 `valueFormatter` 百分号逻辑；未来若改提示格式，必须区分价格、百分比、数量和文本，不能一刀切。

## 4. 因子呈现与别名协议

### 4.1 单一来源

- `configs/factor_registry.json` 是 canonical、中文名、价格口径、别名、参数及呈现合同的权威来源。
- `scripts/gen_factor_registry.py` 负责生成；`gui/factor_registry.py` 负责加载、索引、解析和校验。
- canonical 形式：`factors.<table>.<column>`。
- 当前注册表 895 列均有中文名；SaaS metadata 还包含行情字段，合计 902 项。
- 中文名必须来自真实公式/官方定义/明确字段语义，不能靠猜译。Alpha191、Alpha101、quality/growth、PIT 等已覆盖。

### 4.2 `display` 数据成员

每个 canonical 的 display 包含：

```text
chart_type: overlay | pane
panel_id: 面板标识（含价格口径）
role: main / signal / hist / k / d / j / up / down / line / band
series_type: line | bar
axis: price | value
precision: 数字精度
color: #RRGGBB
price_basis: close | typical_price | average_price | na
render_order: 非负整数
```

约束：

- EMA、其他均线、BOLL 和 overlap 表：必须 overlay 主图。
- MACD/PPO/PVO：同参数 DIF + DEA + HIST 同副图。
- KDJ/STOCH 等家族：同副图。
- RSI、风险、流动性、Alpha：默认独立副图。
- 同列不同价格口径必须使用不同 panel_id，不能共用缓存键或面板。
- 只有旧数据缺 display 时才允许启发式回退，显式 display 不得被启发式覆盖。

### 4.3 消费方

- SaaS 因子目录与三级弹窗。
- `gui/lab_result.py::_panel_display()`。
- `gui/static/factor-layout.js`。
- SaaS symbol 静态图与重播，以及本地 lab 静态个股页。
- 游戏不是 `display` 合同的直接消费方：`game/factors.py::factor_catalog()` 不返回该字段，`game.html` 不加载 `factor-layout.js`，而是独立分组并硬编码 MACD 三元组。后续统一呈现协议时需显式迁移，不能假设已经共享。

## 5. 《我不是股神》独立交互模型

### 5.1 页面与数据

- 桌面：左侧大 K 线，右侧统一操作栏（匿名股票信息、回合、交易、账户、成交详情、因子）。
- 不是 QRE 回测详情页的简单复刻，核心是用户主动逐日交易。
- 真实代码、真实日期、完整未来行情只在服务端；前端只见匿名股票 B、代码 X00001B 和相对 T 日。
- 原始价 + adj_factor 的缩放锚点取全历史最后一根，开局后固定不变；它只是统一缩放常量，不表示从当局首根复权，也不向前端泄露未来行情。
- `_state` 向前端暴露 `cursor`、`game_bars`、`should_end` 等进度/终止信号；这些不是未来 OHLCV。真实日期、代码与 `start_index` 仍只留在服务端。

### 5.2 回合状态机

后端 `game/session.py` 保持 `phase=open|closed`：

1. 初始 closed：只显示预热历史。
2. `advance()` 进入 open：只额外公开下一日 open，不能看 high/low/close。
3. open 决策：可提交/撤销限价单，或无委托表示空仓。
4. `close_day()` 收束一根 K 线并结算，转 closed，公开完整 OHLCV 和当日结果。
5. closed 禁止交易，只能查看结算，点击“进入下一回合”才推进。

`close` API 在 closed 状态重复调用是幂等返回，不重复成交；advance、下单、撤销都需防竞速。

### 5.3 决策区间可视化

open 时：

- 右侧显示前收、次日 open、委托上下限、当前状态。
- K 线主图用 `markArea` 显示前收 ±10% 区域。
- `markLine` 显示前收、次日 open、当前委托价。
- 成交判定仍是服务端：当日 low ≤ 委托价 ≤ high，成交价即委托价，滑点为 0；一字涨停禁买、一字跌停禁卖。
- 未触及或未成交都显示在结算信息里。

### 5.4 游戏图表组成

- K 线只画已经完整的 OHLC，open 阶段仅显示 open 参考线，不把未完成蜡烛当完整 K 线。
- 成交量、overlay 和副图共用同一 ECharts 实例与动态高度：`560 + 185 * paneCount`。
- EMA/BOLL overlay 主图；MACD DIF/DEA/HIST 同副图；其他因子按选择生成独立副图。
- 没有自动跨日连播；“播放并结算”只收束一根。
- 创建会话时已预载 `DEFAULT_CANONICALS` 的 11 个默认因子；其余因子在用户勾选后才按 canonical 白名单增量加载。因子目录与序列分离，同列不同口径分别缓存，不使用共享芯片 remap。

### 5.5 交易规则

- 只做多、A 股 T+1、100 股整数手、最小价格 0.01、初始资金 1,000,000。
- 佣金、最低佣金、印花税、过户费复用 `AShareMarketProfile`，不另造费率。
- 费用、现金、持仓、可卖数量与总权益由服务端引擎决定。
- 游戏结束：时间耗尽或总权益低于初始资金 10%。

## 6. Night Mode 与主题机制

- 浅色原设计保留，Night Mode 是新增主题，不是全站色板重装修。
- 当前 Night Mode 覆盖 SaaS 页面；本地 `lab_symbol.html` 与游戏 `game.html` 都未加载 `night-mode.css/js`，不能假设它们已支持主题切换。
- `night-mode.css` 仅作用于 `html[data-theme="dark"]`，夜间 token：背景 `#17153B`、卡片 `#2E236C`、线 `#433D8B`、正文 `#F1EDF8`、辅助 `#C8ACD6`、主紫 `#7E60BF`、深紫强调 `#C8ACD6`、柔和底 `#2E236C`。
- `night-mode.js` 处理 localStorage、系统偏好、首帧防 FOUC、meta theme-color 和按钮 aria。
- `QRETheme.themeChart(chart)` 递归改 ECharts 背景、坐标轴、文字、tooltip、图例与品牌紫，保留红绿及数据，不重算 grid 或 series.data。
- 主题切换与因子 display 合同是正交的：不得因夜间模式改变 overlay/panel/role。

## 7. 性能与数据规模边界

- 静态图和重播都把当前 detail 全量留在浏览器内存；重播只是逐帧截断，不是服务端分页。
- 大 detail 会放大首次下载和 JSON 解析成本；目前没有 LTTB 降采样或按视口抽稀。
- 重播事件流没有虚拟滚动，长任务可能产生大量 DOM。
- 游戏渲染时会 `chart.clear()` 后重绘，简单直接但不是增量更新优化方案。
- 375px 只做响应式不破版，不是独立移动端交互设计。
- 某些公开经典任务并不提供所有个股的现成详情；没有详情时不能伪造 K 线。

## 8. 当前不具备或不应假设存在的 TradingView 特性

以下不是当前已实现能力，后续不能当成已有合同：

- 自由画线、Fibonacci、形状、测量工具和注释编辑。
- 多股票同图对比、跨品种联动、行情告警编辑器。
- 秒级/分钟级实时流、逐笔成交、盘口、热图或订单簿。
- 完整快捷键体系、指标脚本语言、策略编辑器内嵌图。
- 成交量分布（Volume Profile）、市场深度、时段模板、图表截图/导出一键分享。
- 任意周期切换（周线/月线/自定义周期）与交易日历/时区专业设置。
- 统一的专业金融格式化框架（百分比/对数/绝对价格/指数化）已全部覆盖。

## 9. 验证资产

### 9.1 代码测试

- `tests/test_saas_replay_boundaries.py`：同日聚合、seek、重入、orders 优先、事件价量、布局。
- `tests/test_factor_display_contract.py`：display 全字段、overlay/pane、MACD/KDJ 分组、panel_id、metadata。
- `tests/test_factor_registry.py`：别名、canonical、价格口径、失效引用。
- `tests/test_saas_night_mode.py`：主题 token、FOUC、模板、主题图表不改数据。
- `tests/test_trading_game_*.py`：游戏规则、匿名数据、回合、撤单、因子与 API。
- 完整回归通过数会随用例增加而变化，本文不把它冻结为接口合同；每次实际变更后都应重新运行并记录。本次 DeepSeek 只读核对没有重跑测试。

### 9.2 浏览器与审计

- `.tmp/replay-boundaries/`：重播聚合和末帧一致性。
- `.tmp/factor-display-contract/`：生产 display 驱动的 EMA overlay、MACD 同副图和夜间切换。
- `.tmp/factor-zh-coverage/`：因子目录中文名和搜索。
- `.tmp/night-mode/`：SaaS 多页面浅/夜审计，不覆盖本地 lab 或游戏页。
- `.tmp/trading-game-v11-kimi/`：真实回合制游戏流程与移动视口。

## 10. TradingView 化 Spike 结论（2026-10-27）

- 选型结论：**A 增强 ECharts 为主，B Lightweight Charts 5.2.1 仅在 `symbol.html` K 线区受控试点，C 自研不做**。
- A 路当前两个真实痛点：`symbol.html` 只有 `window.resize`、缺 `ResizeObserver`；`replay.js` 每帧全量 `replaceMerge:['xAxis','series']`。第一阶段应优先做增量更新与视口裁剪。
- B 路硬阻塞：attribution 合规未决，且可能与 UI 外部品牌/配色纪律冲突；未解决不得上生产。
- 详细评分、迁移路径、风险、回滚与验收见 `change_requests/CR-2026-10-27_tv_chart_core_spike.md`。
- A 路首片已实施：`symbol.html` 单例 ResizeObserver；`replay.js` `visibleWindow()` 默认 240 点视口裁剪；4000 点 rAF 45.8→16.8ms。遗留 `job.html` dispose resize 警告与重播左端不固定 0 的口径变化。
- A 路遗留已修补：`job.html` dispose resize 守卫；`replay.js` `windowDisplayData(zeroBase)` 让策略/基准左端回 0，指标仍全量口径。
- 静态 K 线 TV 化首片已实施：`symbol.html` 左侧工具栏、顶部 OHLC/因子信息区、右侧价格标尺、底部时间轴；因子合同与 Night Mode 不变。重播界面尚未 TV 化。
- MACD 旧别名修复：`factor-layout.js` 启发式回退现在识别 `macd_dif/macd_dea/macd_hist/macd_signal/macd_histogram`，旧无 display 产物也会合并成一个 MACD 副图。

## 11. 后续阅读顺序（给 DeepSeek）
1. `gui/saas/templates/symbol.html`：SaaS 静态图与个股重播。
2. `gui/templates/lab_symbol.html`：本地 lab 独立静态个股页及其功能边界。
3. `gui/static/replay.js`：通用重播核心。
4. `gui/static/factor-layout.js` + `configs/factor_registry.json`：因子分组、display 权威字段与消费。
5. `gui/lab_result.py`：detail 组装与 `_panel_display()`。
6. `gui/factor_registry.py` + `scripts/gen_factor_registry.py`：别名、参数与呈现合同。
7. `game/{web,session,data,factors,engine}.py` + `game/templates/game.html`：游戏 API、回合制、因子加载与防未来数据。
8. `night-mode.js`：主题变换和 ECharts 改色。
9. `12_UI_STYLE_GUIDE.md`、`21_FACTOR_LIBRARY_PLAN.md`、`22_TRADING_GAME.md`：长期约束。

后续若要重写，必须先明确哪些现有合同需要保持，不得把本文理解为允许删除现有测试、匿名防未来数据规则、因子注册表或交易状态机。
