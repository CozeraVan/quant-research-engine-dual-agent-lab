# CR-2026-10-27 TradingView 化第一阶段：共享图表内核 Spike

## 背景与输入

- 用户目标：未来将系统内所有 K 线图与图表功能向 TradingView 体验还原。
- 参考文档：`/home/van/dshguide/README-AGENT.md`。该目录当前只有 README，没有其引用的 `linux/` 脚本与 `../demo/index.html`；因此本任务不执行 S1–S8 资产抓取，只把该文档当作“TradingView 四功能取证判据/交互清单”。
- 当前实现权威文档：`docs/agent/23_KLINE_IMPLEMENTATION.md`、`docs/agent/12_UI_STYLE_GUIDE.md`、`docs/agent/21_FACTOR_LIBRARY_PLAN.md` §0.3。

## 目标

在不改变生产页面、不跑回测、不部署 ECS、不 commit/push 的前提下，完成共享图表内核选型 Spike：

1. 评估三条路线：
   - A：增强现有 ECharts 实现，向 TradingView 交互靠拢。
   - B：引入 TradingView Lightweight Charts 作为 K 线内核，外围保留因子/重播/主题层。
   - C：自研轻量 Canvas/WebGL 图表内核。
2. 用同一组需求对三条路线打分，并给出推荐路线、迁移路径、风险与回滚策略。
3. 产出可复核证据：代码走查、依赖/许可证检查、必要的小型隔离原型、Node/浏览器验证记录（如可行）。

## 评估需求（必须逐项覆盖）

- K 线/成交量/十字光标/OHLC 图例、滚轮缩放、拖拽平移、DPR 适配、375px 不破版。
- 因子呈现合同：EMA/BOLL overlay、MACD/PPO/PVO 同副图、KDJ/STOCH 家族同副图、RSI/风险/流动性/Alpha 独立副图；`panel_id` 含价格口径。
- 重播集成：不能出现第二个同内容 K 线模块；重播帧只暴露 `[0, cursor]`；退出后能重建静态图。
- Night Mode：主题切换只改色，不改 panel/role/series/data。
- 数据合同：`kline.dates`、`ohlc` 顺序为 open/close/low/high、因子 `values` 与日期对齐、缺值 `null`、不造未来数据。
- 作图工具：至少评估趋势线、水平线、射线、矩形、Fibonacci 的可行性与工作量；完整 94 工具不在本阶段。
- 性能：全期约 4000+ 点、多副图、重播逐帧 setOption 的可行性；给出降采样/虚拟化建议。
- 可维护性：共享组件边界、测试策略、与现有 `factor-layout.js` / `replay.js` / `night-mode.js` 的集成方式。

## 边界

- 不修改任何生产代码、模板、静态资源、测试、schema、worker、引擎、游戏。
- 不新增生产依赖，不修改 `pyproject.toml`/`package.json`，不把 CDN 引入产品；如需评估第三方库，只在 `.tmp/tv-chart-spike/` 内做隔离验证并记录版本与许可证。
- 不抓取 TradingView 生产资产，不 hook pine-facade，不接入 pushstream 实时流。
- 不跑回测、不部署 ECS、不 commit/push。
- 只创建 Spike 产物与本 CR；共享进度文档由主 Agent 统一回写。

## 交付物

- `docs/agent/change_requests/CR-2026-10-27_tv_chart_core_spike.md` 追加“评估记录/推荐路线/迁移路径/风险”。
- `.tmp/tv-chart-spike/` 下的隔离原型、脚本输出、截图或证据（如产生）。
- 明确推荐路线与第一阶段实施切片建议；不得伪造浏览器或性能结果。

## 验收

- 三条路线均有基于当前代码/文档的证据，不是空泛比较。
- 推荐路线必须说明如何保留因子显示合同、重播防未来数据、Night Mode 和移动 375 约束。
- 如某项不可行（如 WSL 网络不可达、第三方库无法下载），如实记录阻塞，不编造。
---

# 评估记录（2026-10-27 实测，Spike 执行结果）

本节为本次 Spike 的取证与结论。所有数字均为本机实测；标注「未实测」的项不臆测。

## 0. 取证环境

| 项 | 值 |
| --- | --- |
| 仓库 | `quant-research-engine-dual-agent-lab` |
| 运行时 | `node v18.19.1`、`npm 9.2.0`、`.tmp/browser-venv/bin/python`（playwright）+ `.tmp/ms-playwright/chromium-1248` |
| 生产 ECharts | `src/quant_research_engine/gui/static/echarts.min.js`，1,034,102 B，运行时 `echarts.version === "5.6.0"`（文件内另有 `5.6.1` 字样，以运行时值为准） |
| 隔离目录 | `.tmp/tv-chart-spike/`（`.tmp/` 已在 `.gitignore`，不进版本库） |
| 生产改动 | 零。本轮未改任何代码/模板/静态资源/测试/schema/worker/引擎/游戏 |

两条路线的基准页都只读引用生产 vendored 文件，不复制、不进产品：
- A 路：`.tmp/tv-chart-spike/bench_echarts.html` 以相对路径 `<script src="../../src/quant_research_engine/gui/static/echarts.min.js">` 加载。
- B 路：`.tmp/tv-chart-spike/vendor/lightweight-charts.standalone.production.js`（从 npm tarball 解出）。

## 1. 现有图表栈画像（A 路的起点）

| 事实 | 证据 |
| --- | --- |
| K 线详情页唯一实现：`renderKline` 组装 3 grid（主图 42% / 量 10% / 副图区 66%–93%） | `gui/saas/templates/symbol.html:648-754` |
| 容器高度 `420 + panes.length * 160`，无副图时 460 | `symbol.html:663`、`:823` |
| 静态图 `echarts.init` → `themeChart` → series 顺序 K线/量/overlay/买卖 scatter/副图 | `symbol.html:666-690` |
| `dataZoom` inside + slider，`axisPointer.link` 全 xAxis 联动 | `symbol.html:745-748` |
| resize 只有 `window.addEventListener('resize', ... chart.resize())`，**无 ResizeObserver** | `symbol.html:749-751` |
| 因子分组走 `QREFactorLayout.plan(factors, states)`，display 合同优先、旧数据启发式回退 | `gui/static/factor-layout.js:94-109` |
| overlay 调色板仅 3 色 | `factor-layout.js:26`（`#E8A33D` / `#2A9D8F` / `#6750A4`） |
| 重播渲染：每帧 `setOption({xAxis, series}, {replaceMerge:['xAxis','series']})`，rAF 节流 | `gui/static/replay.js:246-278` |
| 重播 `core`（`indexDates/binEvents/positionCounts/nextEventfulCursor/frameMetrics`）是纯逻辑，与渲染无关 | `replay.js` 同文件，但无 DOM/echarts 依赖 |
| 主题：`themeChart` **monkey-patch 了 `chart.setOption`**，`repaint()` 用 `notMerge: true` 整棵 option 重放 + 12 对色映射 | `gui/static/night-mode.js:149-153`、`:201-202`、`:208-221` |
| 重播为**共享模块**：K 线详情 `symbol.html:869` 与策略结果页收益曲线 `job.html:1271` 都用 `QREReplay.attach({chartEl})` 接管容器 | 两处 grep 命中 |
| 策略结果页另有 5 处独立 `echarts.init`（收益曲线 / treemap / 风险三图），**不是 K 线** | `job.html:260,453,744,769,796` |
| 全站 `echarts.init` 分布 | `templates/lab_result.html` 5、`templates/lab_symbol.html` 2、`saas/templates/job.html` 5、`saas/templates/symbol.html` 2 |
| 因子注册表规模 | `display` 块 895；`chart_type` pane 774 / overlay 121；`series_type` line 884 / bar 11；`panel_id` 唯一值 743；`precision` 2→673、4→222；distinct color 仅 3 个 |

数据合同（三条硬约束，B 路必须逐条对上）：
- `kline.ohlc` 顺序是 **`[open, close, low, high]`**，不是 OHLC 习惯序 —— `gui/lab_result.py:753` 组装 `[r[1], r[4], r[3], r[2]]`，SQL 为 `trade_date, open, high, low, close, vol`（`:739`）。
- 因子 `values[i]` 与 `dates[i]` 逐位对齐，缺值是 `None`，**不前向填充** —— `lab_result.py:907`、`:923`。
- 面板元数据来自注册表 `display`（8 字段），无注册返回 `None` 由前端启发式兜底 —— `lab_result.py:825`。

## 2. B 路隔离验证（TradingView Lightweight Charts 5.2.1）

### 2.1 依赖获取与许可

```
npm pack lightweight-charts --registry=https://registry.npmmirror.com
```

| 项 | 值 |
| --- | --- |
| version | **5.2.1** |
| author / license | TradingView, Inc. / **Apache-2.0** |
| tarball / unpacked | 616.6 kB / 3.1 MB / 10 files |
| shasum | `5a27ead719573607d4d3483ad2728c055ccea8fd` |
| integrity | `sha512-IVwoK1RLFiLPu[...]EWd1CLB2a1nsQ==` |
| 声明依赖 | `fancy-canvas@2.1.0` |
| 采用文件 | `dist/lightweight-charts.standalone.production.js`，197,922 B，UMD，导出 `window.LightweightCharts` |
| 来源 | `https://registry.npmmirror.com/lightweight-charts`，上游 `github.com/tradingview/lightweight-charts` |
| 许可证全文 | 已存 `.tmp/tv-chart-spike/vendor/LICENSE.lightweight-charts.txt`（11,347 B，Apache-2.0 全文） |
| 文件头版权 | `TradingView Lightweight Charts™ v5.2.1 / Copyright (c) 2026 TradingView, Inc. / Licensed under Apache License 2.0` |

**npm 包内没有 `NOTICE` 文件**（只有 `LICENSE`、`README.md`、`package.json`、`dist/`）。standalone 产物是自包含 UMD，`fancy-canvas` 已内联，页面只需一条 `<script>`。

### 2.2 API 与数据合同对照（依据 `dist/typings.d.ts`，非记忆）

| 合同点 | LWC v5.2.1 事实 | 映射结论 |
| --- | --- | --- |
| `ohlc` 顺序 | `CandlestickData extends OhlcData`，字段名 `open/high/low/close` | 需适配层按 `[0],[3],[2],[1]` 重排（已在 `demo.js:36-43` 验证） |
| 日期 | `export type Time = UTCTimestamp \| BusinessDay \| string` | 生产 `'YYYY-MM-DD'` 字符串**可直接用**，无需转时间戳 |
| 缺值 `null` | 接受 `WhitespaceData`（仅 `{time}`） | `null` → `{time}`，语义与「不前向填充」等价（`demo.js:47-57`） |
| 多副图 | `addPane()` / `panes(): IPaneApi[]` / `IPaneApi.setHeight()` | 可做；但高度百分比要自己换算（生产 42%/10%/66–93%） |
| 多序列共 pane | `addSeries(def, options, paneIndex)` | 一个 pane 挂 DIF/DEA/HIST 三条，OK |
| 逐点着色 | candlestick 支持逐点 `color/borderColor/wickColor`；任意 series data point 带 `color` | MACD 柱正红负绿、量柱涨跌色可逐点给 |
| 买卖标记 | `createSeriesMarkers(series, markers, options)`（UMD 已导出）；形状 `circle/square/arrowUp/arrowDown`，位置 `aboveBar/belowBar/inBar/atPriceTop/...` | 生产 `scatter` + `symbolRotate` 的三角买卖点可替代 |
| 阈值线 | `ISeriesApi.createPriceLine()` | 生产 `markLine` 阈值线可替代，但每条线单独创建，895 个 `display` 中只有带 `thresholds` 的因子需要 |
| 主题 | `applyOptions(DeepPartial<ChartOptions>)`，`LayoutOptions` 覆盖 `background/textColor/fontSize/fontFamily/panes`，`grid/crosshair/rightPriceScale/timeScale` 均可改 | 主题切换无需重建 option 树 |
| 自适应 | `autoSize: true`（内建 ResizeObserver） | 直接解决 A 路缺 ResizeObserver 的问题 |

### 2.3 浏览器实测（`.tmp/tv-chart-spike/verify.py`，EXIT=0）

```json
{"spike":{"version":"5.2.1","bars":4000,"panes":3,"narrowWidth":375,"markerCount":41,"attributionLogo":false},
 "bench":{"frames":200,"growMs":1177,"perFrameMs":5.9,"fullMs":2.1},
 "bench_raf":{"frames":20,"totalMs":357,"perFrameMs":17.8},
 "dark_bg":{"type":"solid","color":"#17153B"},
 "mobile":{"innerWidth":375,"scrollWidth":375,"overflowX":false,"narrowWidth":343,"narrowHeight":460,"canvasCount":15},
 "console":[]}
```

即：4000 根 K + 量 + MACD 三 pane + 41 个买卖 marker，**零 console 报错、零 pageerror**；375 视口 `scrollWidth == innerWidth == 375`（无横向溢出），窄屏图 343×460、15 个 canvas；主题切到 `#17153B` 后 `chart.options().layout.background` 正确读回。截图：`shot-desktop-light.png` / `shot-desktop-dark.png` / `shot-mobile-375.png`。

### 2.4 合规事项（必须由产品决策，不能在实现里悄悄绕过）

`typings.d.ts` 对 `attributionLogo`（**默认 `true`**）的注释原文：

> The licence for library specifies that you add the "attribution notice" from the NOTICE file to your code and a link to https://www.tradingview.com/ to the page of your website or mobile application that is available to your users. Using this attribution logo is sufficient for meeting this linking requirement. However, if you already fulfill this requirement then you can disable this attribution logo.

两条互斥的满足方式：
1. 保留 TradingView logo（默认行为）—— 但 `docs/agent/12_UI_STYLE_GUIDE.md` 明确「全页不得引入第四种色相、不得引入外部品牌」，logo 会破坏视觉纪律。
2. 关闭 logo，由我们在页面放一个指向 `https://www.tradingview.com/` 的文本链接 —— 需要产品/法务拍板这个链接放哪（页脚 / 关于页 / 图表角落 `tip-trigger`），且包内**没有 NOTICE 文件**可取原文，attribution notice 文本需另行确定来源。

本 Spike 的 `demo.js` 为看视觉效果设为 `attributionLogo: false`，**这不代表推荐该配置**；生产接入前必须先确认第 2 条方案落地，否则不得上线 B 路。

## 3. A/B 同环境重播基准

测法一致：同一份 4000 点合成数据（同 seed `20261027`，`demo.js:59-102` / `bench_echarts.html` 内同实现）、同一结构（K 线 + 量 + overlay + DIF/DEA/HIST 共 6 条 series，3 个 pane/grid）、同一 chromium headless、同一 200 帧切片推进（`end = round(n*f/200)`）。

| 指标 | A：ECharts 5.6.0 | B：LWC 5.2.1 | 比值 |
| --- | --- | --- | --- |
| 200 帧同步循环总耗时 | 6744 / 6793 / 6929 ms | 1177 / 1209 / 1261 ms | 5.5× |
| 每帧（同步，仅数据+布局） | 33.7–34.6 ms | 5.9–6.3 ms | 5.5× |
| 每帧（rAF 节奏，含实际绘制，20 帧） | 40.0–41.1 ms | 17.5–17.9 ms | 2.3× |
| 单次全量 4000 点替换 | 59.6–67.9 ms | 1.5–2.1 ms | ~35× |
| 等效帧率（rAF） | ≈ 24 fps | ≈ 56 fps（vsync 底 ≈16.7ms，实际贴顶） | — |

方法学说明（不掩饰口径差异）：
- 两条路线都跑了「同步循环」与「rAF 节奏」两个口径，四个数可横向比。同步口径只测「数据灌入 + 布局」，rAF 口径把实际绘制算进去 —— 所以两条路线的 rAF 值都高于同步值，A 从 34 → 41，B 从 6 → 18，说明 B 把绘制推迟到下一帧更彻底。
- rAF 口径下 B 的 17.7ms 已经贴着 vsync 16.7ms 的下限，即「不丢帧」；A 的 40.7ms 意味着 4000 点全期重播时必然掉帧（约 24fps）。
- 两侧都**未计入**买卖标记更新：B 侧 marker 在循环外一次性创建，A 侧 scatter series 未纳入本轮 6 条 series。若计入，A 会因多 2 条 series 更慢、B 需每帧 `setMarkers()` 会更慢，量级不改变结论。
- headless chromium 无 GPU 合成；真实设备/低端安卓的绝对值会不同，但 A/B 的相对差是稳定的（三次重复标准差 < 3%）。
- 生产 `replay.js` 的 rAF 节流本身会限制到 ~60fps 上限，所以在 A 路当前实现里表现为「每帧预算 16.9ms 被 41ms 撑爆 → 每 2~3 帧才更新一次」。

## 4. 评分矩阵（10 维度 × 3 路线，0–5 分）

| # | 维度 | A 增强 ECharts | B Lightweight Charts | C 自研 Canvas/WebGL |
| --- | --- | --- | --- | --- |
| 1 | 数据合同契合度 | **5** — `ohlc` 直吃 `[open,close,low,high]`（`symbol.html:674`），`values` 与 category 轴天然逐位对齐，`null` 天然空洞 | **4** — 日期字符串直用、`null`→`{time}`；但 6 处字段重排/换名需适配层（`demo.js:36-57`） | **3** — 合同自由，但时间轴映射、`null` 断点、精度全自建 |
| 2 | 因子渲染能力（895 display / 774 pane / 121 overlay / 11 bar） | **5** — 已落地：`factor-layout.js:94` 的 `plan()` 直接产出 chips/overlays/panes；bar 型 hist 逐点着色、`markLine` 阈值现成 | **3** — overlay/pane/逐点着色都可做，但 pane 高度、轴名位置、阈值 priceLine、11 个 bar 的逐点色要重写；743 个 `panel_id` 的 cap/高度策略需另实现 | **1** — 全部从零 |
| 3 | 重播防未来数据 | **4** — 语义正确（只喂 `[0,cursor]`，`replay.js:246-278`），但 4000 点每帧 34–41ms 会掉帧 | **5** — 同语义下 5.9–6.3ms 同步 / 17.8ms rAF，贴 vsync | **2** — 裁剪逻辑自建 |
| 4 | Night Mode 主题成本 | **5** — `night-mode.js` 12 对色映射 + `themeChart` 已就绪 | **2** — 背景/文字/网格/十字光标/蜡烛/线色可用 `applyOptions` 改；但 `MAP_DARK/MAP_LIGHT`、`repaint()`、`notMerge:true` 重放机制、legend/tooltip 的 DOM 样式全部要重写一套 | **2** — 全自绘，主题即参数，但等于零起点 |
| 5 | 375 响应式 | **3** — 只有 `window.resize`（`symbol.html:749`），无 ResizeObserver；60px 左边距 + slider 在 375 下已偏挤 | **5** — `autoSize:true` 内建 ResizeObserver；实测 `scrollWidth==innerWidth==375` 无溢出，图 343×460 | **3** — 自理 |
| 6 | 性能（4000 点重播） | **2** — 33.7–34.6ms/帧同步、40–41ms rAF、全量 60–68ms | **5** — 5.9–6.3ms / 17.5–17.9ms / 全量 1.5–2.1ms | **4** — 理论最优，但无实测，且要自己保证 |
| 7 | 测试覆盖可迁移性 | **5** — `test_factor_display_contract` / `test_factor_registry` / `test_saas_replay_boundaries` / `test_saas_night_mode` 全部继续有效 | **3** — `replay.js` 的纯逻辑测试（`frameMetrics`/`binEvents`/`positionCounts`）继续有效；渲染与主题断言需重写 | **1** — 全部重写 |
| 8 | 交互扩展（画线/水平线/矩形/Fibonacci/测量/多股对比/实时流） | **3** — `graphic` + 自定义 series 可做，但画线/测量/Fibonacci 全要自己写；实时流靠定时 `setOption` | **4** — `ISeriesPrimitive` + 坐标转换可承载画线/测量；`series.update()` 天生适合实时流；多股对比可多 pane 或多实例 | **2** — 最灵活但成本最高 |
| 9 | 依赖与合规 | **5** — 已 vendored，Apache-2.0，无新增 | **3** — Apache-2.0 可 vendored；但 attribution 要求未决（logo 与 UI 风格指南冲突 / 文本链接需产品定），新增 198KB + `fancy-canvas` 声明依赖 | **5** — 无第三方 |
| 10 | 迁移风险与回滚成本 | **5** — 零迁移 | **3** — 需双内核并存 + 灰度开关；`chartEl` 接管/交还已有先例（`replay.js` `destroy(keepDom)`） | **1** — 重写整套 |
| — | **合计** | **42 / 50** | **37 / 50** | **24 / 50** |

矩阵的读法：A 总分领先是因为「存量资产」占优（合同、测试、主题、零迁移）；但在**用户能直接感知的三项**上 B 完胜 —— 重播帧率（6 分 vs 2 分）、375 自适应（5 vs 3）、主题切换机制更现代。C 在任何维度都没有压倒性优势，且重播性能那 4 分是「理论值、未实测」，不能当作可信收益。

工作量估算（人日，含自测）：
- A 增强到「TradingView 观感」：重播性能改造（降采样 + 视口裁剪 + 差分 append）3–5；ResizeObserver 与 375 收口 0.5–1；主题一致性收口 1–2；画线/测量/Fibonacci 8–12（本阶段不做）。**第一阶段切片 5–8 人日**。
- B 受控试点（仅 `symbol.html` K 线区）：display 合同 → panes/series 适配层 4–6；主题适配层 2–3；重播渲染段重写 2；阈值线/买卖 marker 1；pane 高度与 375 收口 1；灰度开关与回滚路径 1。**合计 11–14 人日**，attribution 决策另计。
- C 自研：20–40 人日起步，且后续每个交互工具都要自己维护。

## 5. 推荐路线

**A 为第一阶段主力，B 做受控试点；C 明确不在第一阶段。**

理由（按证据强度排序）：

1. **B 的收益集中在 K 线区，不在全站。** 策略结果页的 5 张图（`job.html:260,453,744,769,796`）是收益曲线 / treemap / 风险分布，全部不是 K 线，换 LWC 收益为零；而 `QREReplay` 是共享模块（`symbol.html:869` + `job.html:1271`），B 只能替换它的渲染段，`core` 与控制条 DOM 必须保留给两页共用。全量替换的收益面远小于改动面。
2. **重播是真实痛点，B 在这里有实测 2.3×（rAF）/ 5.5×（数据灌入）优势。** 4000 点全期 A 路 40.7ms/帧 ≈ 24fps 掉帧，B 17.7ms 贴 vsync。这是唯一一项「用户肉眼可见」的差距，也是唯一值得为 B 付迁移成本的理由。
3. **主题是 B 的真实成本，不是零成本。** `night-mode.js:208-221` 的 `themeChart` 靠 monkey-patch `chart.setOption` + `notMerge:true` 整棵 option 重放 + 12 对色映射实现；这套机制在 LWC 下完全无意义，必须新写一层 `applyOptions` 适配，且要保证「红涨绿跌」在两种主题下仍是同两个色相（`12_UI_STYLE_GUIDE.md` 的硬规则）。保守估计 2–3 人日，且是回归风险最高的一块。
4. **attribution 未决。** 见 §2.4。在产品/法务给出结论前，B 不能进生产；这是硬阻塞，不是技术问题。
5. **A 路仍有明确的、低风险的改进空间**：`symbol.html:749` 缺 ResizeObserver、重播每帧全量 `setOption` + `replaceMerge` 是全量重建而非增量 append。这两项在 A 内就能修，且不触碰任何合同。

结论一句话：**先把 A 的「掉帧 + 375 自适应」两个真实痛点修掉（5–8 人日，零迁移风险）；同时用 11–14 人日在 `symbol.html` K 线区做 B 的受控试点，验证主题层与 attribution 两项硬成本；试点达标再谈扩大，不达标一键回滚到 A，沉没成本仅限试点工时。**

## 6. 迁移路径（若 B 试点获批）

阶段 0 —— 决策前置（0 人日，阻塞项）
- 产品/法务确认 attribution 方案（logo vs 页面文本链接），并确定 NOTICE 文本来源（包内无 `NOTICE` 文件）。
- 确认 B 的引入形态：vendored 单文件进 `gui/static/`（与 `echarts.min.js` 同级），**不允许 CDN**（`12_UI_STYLE_GUIDE.md`）。

阶段 1 —— 适配层（4–6 人日）
- 新建 `gui/static/chart-core/` 下的纯函数模块，输入是现有 detail JSON 合同（`kline.dates` / `kline.ohlc` / `kline.vols` / `factors[].values` / `display`），输出是 LWC 的 `SeriesDefinition` + pane 分配 + 高度比例。
- 关键约束：适配层**只消费** `QREFactorLayout.plan()` 的输出（`chips/overlays/panes/paneCount`），不复制 display 合同解析逻辑，避免两套合同解析漂移。
- `panel_id` 继续作为 pane 唯一键（743 个唯一值，4 段格式 `instance:table:params:price_basis` 已含价格口径）。

阶段 2 —— 渲染与主题（3–4 人日）
- `renderKline` 增加内核分支：`if (kernel === 'lwc') renderKlineLwc(d) else renderKline(d)`，两分支共用 `plan()` 与高度公式（`420 + panes.length * 160`，`symbol.html:663`）。
- 主题层新写 `chart-core/theme-lwc.js`，映射 `--paper/--panel/--line/--ink/--grey/--faint/--up/--down` 与暗色 token（`#17153B` / `#2E236C` / `#433D8B` / `#F1EDF8` / `#C8ACD6` / `#7E60BF`），保留 `night-mode.js` 的 `localStorage['qre-theme']` 与 `matchMedia` 单一口径，**不新增第二套主题状态**。

阶段 3 —— 重播复用（2 人日）
- `replay.js` 拆成「core（纯逻辑，不动）+ adapter（渲染）」，新增 LWC adapter：每帧 `series.setData(slice)`，控制条 DOM 与 `frameMetrics` 继续复用。
- `job.html:1271` 的收益曲线重播**保持 ECharts adapter**，验证双 adapter 并存不串味。

阶段 4 —— 灰度与交接（1 人日）
- 开关：URL 参数 / cookie 双通道（沿用既有 `QRETheme`/`chipStates` 的 localStorage 习惯），默认 `echarts`。
- 容器交接沿用 `replay.js` 已验证的 `destroy(keepDom)` → 重建语义，避免同内容图表双实例（CR 原文硬约束「不能出现第二个同内容 K 线模块」）。
- 退出条件（任一满足即回滚）：主题切换后出现色相漂移、375 下 `scrollWidth > innerWidth`、重播 rAF 帧耗时 > 33ms、attribution 未落地。

## 7. 风险与回滚

| 风险 | 触发信号 | 处置 |
| --- | --- | --- |
| attribution 合规 | 页面无 TradingView 链接 / logo 破坏视觉纪律 | 阶段 0 前置决策；未决不上线。回滚 = 继续用 A |
| 主题一致性 | 暗色下 `--up/--down` 色相漂移，或 legend/tooltip 未换肤 | 双主题截图对比纳入验收；回滚开关置 `echarts` |
| pane 布局退化 | `420+160*n` 高度下副图被压扁、轴名遮挡 | 保留 A 分支做 A/B 同数据截图比对 |
| 375 破版 | `scrollWidth > innerWidth` | 已有可复现断言（本 Spike 的 `verify.py` 即测法），可直接转成验收脚本 |
| 依赖升级 | v5 → v6 API 变动（`addSeries` 的 series 定义式已与 v4 不同） | 锁死 5.2.1 + 记录 shasum/integrity；升级必须重跑本案基准与截图 |
| `fancy-canvas` | 声明依赖但 standalone 已内联 | 采用 standalone 单文件，不引构建链；若改用 `.mjs` 则需补 `fancy-canvas` |
| 体积 | 新增 197,922 B 静态资源 | 与 `echarts.min.js` 1,034,102 B 并存期总体积上升；试点期可接受，全量替换后可减 |
| 热路径性能回归 | rAF 帧耗时 > 33ms | 保留 `frameMetrics` 作为运行时探针 |

回滚成本：B 试点全程被单开关隔离，回滚 = 开关置 `echarts` + 删除 `chart-core/` 目录，无数据/接口/schema 影响（B 只消费 detail JSON，不产生新合同）。

## 8. 第一阶段切片建议（可独立交付的最小单元）

**A 路切片（先做，5–8 人日）**
1. `symbol.html:749` 补 ResizeObserver（现只有 `window.resize`），375 窄屏与侧栏折叠场景自动重排。
2. 重播性能：`replay.js:246` 的每帧 `replaceMerge:['xAxis','series']` 改为**增量 append**（仅追加新点）+ 视口裁剪（只保留可见窗口 ± buffer），把 4000 点全量重绘降为增量更新。
3. 验收：4000 点 rAF 帧耗时从 40.7ms 降到 < 16.7ms；375 下 `scrollWidth == innerWidth`。

**B 路切片（并行，11–14 人日，仅 `symbol.html` K 线区）**
- 范围：K 线 + 成交量 + **1 个**副图（MACD）+ 十字光标 OHLC 图例 + `420+160*1=580px` 高度适配 + 375 窄屏。
- 不做：多副图（>1）、重播、买卖 marker、阈值线、画线/测量/多股对比/实时流 —— 全部留第二片。
- 验收：与 A 分支同数据同视口截图逐项比对；`verify.py` 的 375 断言转成 CI 断言；零 console 报错。

**第二片（视试点结果）**：重播 adapter、买卖 marker、多副图与 `panel_id` 高度策略、阈值 priceLine。
**明确排除**：`job.html` 收益/treemap/风险图（非 K 线，换内核无收益）；C 自研内核。

## 9. 未实测 / 不可行项（如实记录，不臆测）

- **未用真实 DB 数据实测**：本 Spike 用 4000 点合成数据（同 seed 可复现），未接生产 `lab_result.py:711` 的 SQL 与实际 `QRE_PRICE_BASIS` 口径数据。
- **未测极端点数**：10k+ 点、单 pane 12 条 series 的退化曲线未知。
- **未测 Safari / iOS / 低端安卓**：LWC 依赖 canvas + ResizeObserver，iOS 老版本行为未知；375 断言只在 chromium headless 验证过。
- **未验证 attribution logo 的视觉可接受性**：`demo.js` 设为 `false` 是为看干净效果，不代表推荐。
- **未验证 B 的全部交互扩展**：`ISeriesPrimitive` 承载画线/Fibonacci/测量的实际人日只是估算，未做原型。
- **未跑回测**、**未部署 ECS**、**未 commit/push**（与任务书边界一致）。
- 与 `AGENTS.md` 第 12 条「改代码即部署」的冲突：本轮按任务书明确不部署；且本轮未改生产代码，无部署对象。

## 10. 验证命令与真实输出

```
$ node --check .tmp/tv-chart-spike/demo.js
node check OK

$ .tmp/browser-venv/bin/python .tmp/tv-chart-spike/verify.py     # B 路
EXIT=0  # 输出见 §2.3 JSON，console 为空

$ .tmp/browser-venv/bin/python .tmp/tv-chart-spike/bench_a.py    # A 路
EXIT=0
{"base":{"version":"5.6.0","bars":4000,"gridCount":3,"seriesCount":6},
 "bench":{"frames":200,"growMs":6793,"perFrameMs":34,"fullMs":62.3,
          "raf":{"frames":20,"totalMs":818,"perFrameMs":40.9}},
 "console":[]}

$ npm pack lightweight-charts --registry=https://registry.npmmirror.com   # 见 §2.1
```

`.tmp/tv-chart-spike/` 产物清单：
- `demo.html` / `demo.js` —— B 路原型（合同适配 + 三 pane + 主题 + 重播基准）
- `bench_echarts.html` / `bench_a.py` —— A 路同结构同数据基准
- `verify.py` —— playwright 验证（截图 + 尺寸 + console + 基准）
- `vendor/lightweight-charts.standalone.production.js` —— 197,922 B
- `vendor/LICENSE.lightweight-charts.txt` —— Apache-2.0 全文
- `pkg/lightweight-charts-5.2.1.tgz` / `pkg/package/` —— npm pack 原始产物（版本/许可取证）
- `shot-desktop-light.png` / `shot-desktop-dark.png` / `shot-mobile-375.png` / `shot-bench-echarts.png`