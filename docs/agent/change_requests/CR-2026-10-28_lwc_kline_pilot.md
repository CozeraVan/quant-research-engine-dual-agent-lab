# CR-2026-10-28 TradingView 化 B 路：Lightweight Charts 受控试点

`CR-2026-10-27_tv_chart_core_spike.md` 的续篇。Spike 阶段 0（attribution 决策）
已于 2026-10-28 由产品负责人决断，B 路解除阻塞。

## 阶段 0 决断记录（原硬阻塞项）

| 项 | 决断 | 依据 |
| --- | --- | --- |
| attribution 形式 | **保留 LWC 默认文本链接**（`attributionLogo: false`），自绘一行 `[品牌水印] TradingView` | 产品负责人提供品牌资产；Apache-2.0 要求保留许可与 attribution，文本链接即合规形式，且不引入 TradingView 官方图形标识与第四色相 |
| 品牌资产来源 | `/home/van/logo/A股回测台-brand-assets/`，图表水印用 `logo-icon-white-1024.png`（深底反白）/ `logo-icon-on-light-1024.png`（浅底彩色） | 品牌规范：浅底用彩色或单黑，深底/紫底用单白；禁止拉伸改色 |
| 引入形态 | vendored 单文件进 `static/chart-core/vendor/`，**不允许 CDN** | `12_UI_STYLE_GUIDE.md` |
| NOTICE 文本来源 | 包内无 NOTICE 文件（已核实 `pkg/package/` 只有 LICENSE/README/dist/package.json），Apache-2.0 只需保留 LICENSE | Spike §2.4 记录 |
| 其余 UI 设计 | 由 DeepSeek 子代理决断，规格见下节 | 产品负责人指示 |

**版本锁定**：`lightweight-charts.standalone.production.js` = v5.2.1，
`sha256 = e21cc5caa0226ef30bd8549c50b9ef926615f2a4ee6b4e486353477a55f598cf`。
升级必须重跑 Spike 基准与截图，不得静默跟版本。

## 设计规格（DeepSeek 子代理产出，2026-10-28）

已用 bundled `typings.d.ts` 逐项校对：`createSeriesMarkers` /
`ISeriesMarkersPluginApi.setMarkers/detach` / `SeriesMarkerBase.size` /
`SeriesMarkerPosition`(`aboveBar|belowBar|inBar|atPriceTop|atPriceBottom|atPriceMiddle`) /
`SeriesMarkerShape`(`circle|square|arrowUp|arrowDown`) / `PriceScaleOptions.minimumWidth` /
`IPaneApi.setHeight` / `LayoutOptions.attributionLogo` / `IChartApi.addPane` /
`ISeriesApi.createPriceLine` / `PriceScaleOptions.scaleMargins` /
`unsubscribeCrosshairMove` 均存在，签名与规格一致。

### 1. 主题映射（`LWC_THEME.light` / `.dark`，整体 `chart.applyOptions`）

| 项 | 浅色 | 暗色 |
| --- | --- | --- |
| `layout.background.color` | `#FFFFFF` | `#2E236C` |
| `layout.textColor` | `#6F6879` | `#C8ACD6` |
| `layout.fontSize` | `11` | `11` |
| `layout.attributionLogo` | `false` | `false` |
| `grid.horzColor` | `rgba(103,80,164,0.10)` | `rgba(200,172,214,0.12)` |
| `grid.vertColor` | `rgba(0,0,0,0)` | `rgba(0,0,0,0)` |
| `crosshair.mode` | `Normal` | `Normal` |
| `crosshair` 竖/横线色 | `#8B7FBE` | `#A99BD8` |
| 十字线样式 | `lineStyle:2`(dashed)、`lineWidth:1`、`labelVisible:true` | 同 |
| `crosshair` 标签底/字 | `#6750A4` / `#FFFFFF` | `#7E60BF` / `#FFFFFF` |
| `rightPriceScale.borderColor` | `#E4DFEE` | `#433D8B` |
| `rightPriceScale.textColor` | `#6F6879` | `#C8ACD6` |
| `rightPriceScale.minimumWidth` | `56` | `56` |
| `timeScale.borderColor/textColor` | `#E4DFEE` / `#6F6879` | `#433D8B` / `#C8ACD6` |
| `timeScale.timeVisible` | `true` | `true` |
| `timeScale.fixLeftEdge` / `rightOffset` | `true` / `4` | 同 |
| `paneSeparator.color` | `#E4DFEE` | `#433D8B` |

行情序列色（色相恒定，红 H=0° / 绿 H≈152°，与 `night-mode.js` 现有映射一致）：

| 序列 | 浅色 | 暗色 |
| --- | --- | --- |
| 阳线 body/wick/border | `#C93A3A` | `#FF7A7A` |
| 阴线 body/wick/border | `#1E8E5A` | `#4FD69A` |
| 成交量柱 | `#B7A6E8` | `#C8ACD6` |
| 均线/因子线 | `QREFactorLayout.COLORS` 原值 | 紫系提亮 `#6750A4→#9B84D8`、`#8B7FBE→#A78BE0`；`#E8A33D`/`#2A9D8F` 不变 |
| MACD DIF / DEA | `#6750A4` / `#E8A33D` | `#9B84D8` / `#E8A33D` |
| MACD 柱（逐点 color） | 正 `#C93A3A` 负 `#1E8E5A` | 正 `#FF7A7A` 负 `#4FD69A` |
| 阈值线 | `#8B7FBE` | `#A78BE0` |

蜡烛 `borderVisible:true` 且 border 与 body 同色（避免暗色黑边）。成交量 `histogram`
+ `priceScaleId:'volume'`，单色不随涨跌分支。同 pane 纵配比用 `scaleMargins` 复刻
原 42%/10%：蜡烛 `{top:0.08,bottom:0.22}`，量柱 `{top:0.82,bottom:0.02}` 且量轴 `visible:false`。

### 2. 买卖点 marker
`createSeriesMarkers(candleSeries, markers)`，一次建实例、后续只 `setMarkers()`。
买入 `arrowUp`/`belowBar`、卖出 `arrowDown`/`aboveBar`，`size:2`，色取主题表阳/阴色，
红买绿卖语义固定，主题切换整体重刷。位置用 `belowBar/aboveBar`（不复刻 `low*0.99`）。
hover 明细走 `subscribeCrosshairMove` 的 `param.time` 反查 `Map<time, order>`。

### 3. 阈值线
`series.createPriceLine(opts)`，挂该 pane **第一条 line series**（无均线挂蜡烛）。
`color` 见主题表、`lineStyle:2`、`lineWidth:1`、`axisLabelVisible:true`、
`title` 为 `toFixed(2)`。每阈值只挂一次；pane 重建前必须 `removePriceLine`。

### 4. 图例替代
`#kline-ohlc` 下方新增 `#kline-legend`（`role="group"`），两组 pill：主图组
（K线 说明用不可点 / 成交量 / 买卖点 / 各均线）与副图组（每 pane 一项）。
pill 高 22px、`border-radius:11px`、`border:1px solid var(--lav)`、带 `tabindex`/
`aria-pressed`/`data-tip`；隐藏态 `st-hidden` = 删除线 + `opacity:.45`。
点击 = 翻转 `chipStates()` 对应键后重建，**重建前后保持 `getVisibleLogicalRange()`**。
三态循环只留在「指标设置」模态；图例只做二值（hidden ↔ 原态）。

### 5. tooltip 与信息区
保留 `#kline-ohlc` 为唯一数值区，**取消浮动 hover tooltip**（防遮挡、保 375 不溢出）。
数据源 `subscribeCrosshairMove`，`param.time` 空则回落末根。价格 2 位、量沿用原口径、
因子 4 位；缺失 `—`，禁 `NaN`/`undefined`。375 下换行、不加 ellipsis。

### 6. 多 pane 与 x 轴
**单 chart 实例 + `addPane()`**（x 轴天然共享，禁止每 pane 一实例）。时间轴只在底部
出现一次。高度沿用 `QREReplay.klineHeightForPanes(n)`，副图 `pane.setHeight(160)`，
主 pane 吸收剩余。`kt-reset` 改为 `timeScale().fitContent()`。重建后必须恢复
`getVisibleLogicalRange()`；`fitContent` 仅 reset 用。

### 7. 品牌水印
容器内绝对定位，与 attribution 同行（右下角），**不入 canvas**。24×24px、
`border-radius:6px`、浅色 `opacity:.55` / 暗色 `.40`、`pointer-events:none`、
`aria-hidden="true"`、`alt=""`。不用横版。不得压住最后一根 K 线影线（375 同验）。

### 8. TradingView attribution
`#kline-attrib`：`position:absolute; right:8px; bottom:6px; display:flex;
align-items:center; gap:8px; height:24px; z-index:2`。行内
`[品牌水印 24px] → 8px → <a>TradingView</a>`，`href="https://www.tradingview.com/"`、
`target="_blank"`、`rel="noopener noreferrer"`、`font-size:11px`、
浅色 `#6F6879` / 暗色 `#C8ACD6`、hover 下划线、`aria-label`。
`vendor/LICENSE.lightweight-charts.txt` 随包分发不得删除。

### 9. 实现注意事项（DeepSeek 标注的坑）
- ECharts 路径 `renderKline` **原样保留**作回滚实现，既有 Node harness 断言全绿。
- 新增 `static/chart-core/kline-lwc.js`（小写文件名，避开 `test_no_forbidden_deps`
  对 `"LightweightCharts"` 字面量的检查）；`symbol.html` 只加两行 `<script src>` +
  一个派发函数 + `#kline-legend`/`#kline-attrib` 两处 DOM。
- **数据适配**：OHLC 合同序 `open/close/low/high` → LWC `{open,high,low,close}`
  按 `[0],[3],[2],[1]` 重排；`null` 转 `{time}` 空点；时间直接用 `YYYY-MM-DD` 字符串；
  同时间戳必须升序去重，否则 `setData` 抛 "data must be asc ordered"。
- **主题切换**：`night-mode.js` 的 `themeChart` monkey-patch 对 LWC 无效，必须显式
  调 `QRELwc.applyTheme()`；主题判定只读 `QRETheme.current()`，不自监听 `matchMedia`。
- 重建前必须 `chart.remove()` + `unsubscribeCrosshairMove`，避免双实例/双 canvas。
- 引擎开关：`localStorage['qre.kline.engine']`，默认 `echarts`；开关入口放「指标设置」
  模态底部，不新增工具栏按钮（保持 9 按钮栅格）。

## 边界

- 只改 `symbol.html`、新增 `static/chart-core/kline-lwc.js` 与 vendor 资产。
- ECharts 路径逐字节保留作回滚；`job.html`、`lab_symbol.html`、游戏不动。
- 不跑回测、不改因子注册表/schema。
- 重播 LWC adapter（阶段 3）与灰度开关的完整交接（阶段 4）本期不做，留后续。

## 测试与验收

- TDD：先 RED 后 GREEN。
- 适配层纯函数合同（OHLC 重排 / 时间去重排序 / null 空点 / pane 分配 / 高度 / 阈值线
  归属 / marker 构造 / 主题表双套）。
- 源码合同：ECharts 路径断言不回归、双 `<script src>`、`#kline-legend`/`#kline-attrib` DOM。
- 命令：
```bash
uv run pytest tests/test_saas_static_kline_tv.py tests/test_lwc_kline_adapter.py -q
uv run pytest tests/ -q
```

## 实现记录（2026-10-28，TDD：先 RED 后 GREEN）

### 新增文件

- `static/chart-core/vendor/lightweight-charts.standalone.production.js`（v5.2.1，197,922 B）
- `static/chart-core/vendor/LICENSE.lightweight-charts.txt`（Apache-2.0，必须随包分发）
- `static/chart-core/vendor/brand-mark-white.png` / `brand-mark-color.png`（品牌水印）
- `static/chart-core/kline-lwc.js`：`QRELwcAdapter` 纯函数适配层（不碰 DOM、不依赖
  LWC 全局，可在 Node 断言）
- `tests/test_lwc_kline_adapter.py`

### 改动文件

- `saas/templates/symbol.html`
  - 新增两个 `<script src>`（vendored LWC + 适配层）
  - 新增 `#kline-legend`（DOM 图例）与 `#kline-attrib`（品牌水印 + TradingView 链接）
  - 新增 `.kline-legend` / `.kline-attrib` 样式，全部复用主题 token
  - `klineEngine()/setKlineEngine()/renderKlineDispatch()`：引擎开关，默认 `echarts`
  - `lwcDispose/lwcApplyTheme/lwcSyncAttrib/lwcRenderLegend/renderKlineLwc`
  - `renderKline`（ECharts 路径）**逐字节保留**作回滚实现，仅在入口处隐藏 LWC 专属 DOM
  - 三个渲染调用点改走 `renderKlineDispatch`
  - 「指标设置」模态底部新增引擎切换按钮
  - 重播进入前 `lwcDispose()`（否则同容器双 canvas）
  - 末尾注册 `document.addEventListener('qre:themechange')` → LWC 换肤

### 关键 API 校正（实测，勿再凭记忆）

standalone 构建**没有** `addCandlestickSeries/addLineSeries/addHistogramSeries`，
必须 `chart.addSeries(LWC.CandlestickSeries, opts)`；`createChart` 用 `autoSize:true`
+ 容器显式高度（固定 width 会导致 375 溢出）。`createSeriesMarkers(series, markers)`
的第一个参数必须是 series（传 chart 会抛 `attachPrimitive is not a function`）。
`CustomEvent` 默认 `bubbles:false`，`qre:themechange` 必须监听 `document`。

### 测试

- `tests/test_lwc_kline_adapter.py`：OHLC 重排/日期去重升序/null 空点、成交量、
  overlay、histogram 逐点色、marker 红买绿卖、阈值线、主题双套、高度公式；
  源码合同（ECharts 路径不回归、双 script、DOM、vendor 资产、适配层导出）。
- 四个 Node harness 补 `localStorage` / `document.addEventListener` /
  `setChipState`（新增依赖都在各自抽取区之外）。
- 三处测试的源码抽取正则放宽为 `klineResizeBound → load() 前`。
- `test_no_forbidden_deps` 改为「禁 CDN/绝对 URL 资源」+「LightweightCharts 必须走
  vendored 路径」，允许 attribution 外链。
- 结果：相关 6 文件 132 passed；**全量 2972 passed, 24 skipped**。

### 生产验证（真实浏览器，ECS）

- 部署 MainPID 518848，回滚副本 `/tmp/qre-deploy-20261028T015314Z.bak`。
- LWC 引擎：蜡烛红绿、成交量、MACD 副图（DIF/DEA + 正红负绿柱）、0 轴阈值线、
  买卖三角 marker、右侧价格标尺、图例 4 pill、顶部信息区全部因子值、
  TradingView 链接 + 品牌水印（深色自动换白版）均在。
- 图例点击可隐藏/恢复；主题切换 LWC 换肤且水印换图；切回 `echarts` 后
  attribution/图例正确隐藏、ECharts 图正常。
- 重播进入前销毁 LWC 实例 → 无双 canvas；退出重播回到 LWC 静态图。
- 375 窄屏 `scrollWidth === innerWidth`；全程零 pageerror / console error。
- 截图 `.tmp/replay-bench/shot-lwc-final-dark.png`。
