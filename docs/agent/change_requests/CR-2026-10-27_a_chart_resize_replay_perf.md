# CR-2026-10-27 A 路图表修复：ResizeObserver + 重播视口裁剪

## 背景

TradingView 化 Spike 结论：第一阶段只做 A 路修复，不引入 Lightweight Charts，不动 C 自研内核。用户 2026-10-27 选择“只做 A 路修复切片”。Spike 详见 `CR-2026-10-27_tv_chart_core_spike.md`。

本 CR 只修两个已实测的真实痛点：

1. `src/quant_research_engine/gui/saas/templates/symbol.html` 的 K 线图只有 `window.addEventListener('resize')`，没有 `ResizeObserver`；侧栏折叠、布局变化、375 窄屏等场景不能可靠重排。
2. `src/quant_research_engine/gui/static/replay.js` 每帧把 `[0, cursor]` 全量切片后 `setOption(..., {replaceMerge:['xAxis','series']})`；4000 点全期重放实测约 40–41ms/帧，会掉帧。

## 目标

- K 线静态图容器尺寸变化时可靠 `resize()`，不依赖窗口 resize；不支持 `ResizeObserver` 时保留窗口 resize 兜底。
- 重播渲染从“全量切片”改为“可见窗口 ± buffer”，后退/seek/首帧时重建；未来数据仍不可见。
- 不改变数据合同、因子 display 合同、Night Mode、重播 core 口径、末帧指标一致性。

## 边界

- 只改 `src/quant_research_engine/gui/saas/templates/symbol.html` 与 `src/quant_research_engine/gui/static/replay.js` 及必要测试；不改 `job.html`、`lab_symbol.html`、游戏、worker、引擎、schema、因子注册表。
- 不新增依赖、不引 CDN、不抓取 TradingView 资产、不引入 Lightweight Charts。
- 不跑回测；按 R-DEPLOY-001 测试通过后部署 ECS；用户验收前不 commit/push。

## 实施要求

### 1. ResizeObserver

- 在 `renderKline()` 中用单个全局 `ResizeObserver` 观察 K 线容器；回调通过 `echarts.getInstanceByDom(el)` 取当前实例并 `resize()`，避免持有已 dispose 的旧实例。
- 重播接管同一容器时，观察者应作用于重播实例，不能调用已销毁静态实例。
- 无 `ResizeObserver` 时保留现有 `window.resize` 兜底。
- 不得重复绑定 observer 或重复 resize 调用。

### 2. 重播视口裁剪

- 在 `QREReplay.core` 增加纯函数 `visibleWindow(cursor, n, size)`，返回 `{start, end}`；`end = cursor + 1`，`start = max(0, end - size)`，默认 size 建议 240，可被 opts 覆盖。
- `renderFrame()` 使用 `visibleWindow()` 渲染可见窗口；首帧、后退、seek、窗口起点变化时重建；同方向仅前进且窗口不变时仍不得泄露未来数据。
- `frameMetrics` 必须继续基于全量 `dates/equity/roundTrips` 计算，不因视口裁剪改变末帧一致性。
- 事件标记只渲染可见窗口内的事件；seek 后重建，不出现重复/未来事件。

## 测试与验收

- TDD：先补失败测试，再实现。
- 新增/更新：
  - `replay.js` 的 `visibleWindow` 纯函数测试：首帧、中间、末尾、size 大于 n、cursor 越界。
  - `symbol.html` 静态/Node 测试：存在 `ResizeObserver`、无重复绑定、无 `ResizeObserver` 时有兜底。
  - 既有重播边界测试不得回归。
- 命令：
```bash
uv run pytest tests/test_saas_replay_boundaries.py tests/test_gui_saas_pages.py tests/test_saas_night_mode.py -q
uv run pytest tests/ -q
```
- 性能证据：在 `.tmp/a-replay-perf/` 用生产 `replay.js` + vendored ECharts 对 4000 点合成数据做浏览器基准，报告修复前后 rAF 每帧耗时；不得伪造。若达不到 <16.7ms，如实记录实测值和剩余瓶颈。

## 发布

- 仅部署 `src/quant_research_engine/gui/saas/templates/symbol.html` 与 `src/quant_research_engine/gui/static/replay.js`。
- 部署后验证 `/saas/new`、公开经典策略 job58 页面与应用层 200；未验收前不 commit/push。
## 实施记录（2026-10-27）

### 改动文件（仅两个生产文件 + 一个新测试）

1. `src/quant_research_engine/gui/static/replay.js`
2. `src/quant_research_engine/gui/saas/templates/symbol.html`
3. `tests/test_saas_chart_a_fix.py`（新增，5 个测试）

未改 `job.html` / `lab_symbol.html` / `lab_result.html` / 游戏 / worker / 引擎 / schema / 因子注册表 / Night Mode；未加依赖，未引 CDN，未跑回测，未部署，未 commit。

### 痛点 1：K 线容器 ResizeObserver

`symbol.html:648-669`

- `klineResizeObserver` / `klineObserved` 两个模块级变量，与既有 `klineResizeBound`、`symbolKlineChart` 并列。
- `klineResize(el)`：通过 `echarts.getInstanceByDom(el)` 取**当前**实例，取不到或 `isDisposed()` 为真则直接返回，否则 `inst.resize()`。这样在重播接管（dispose 旧实例 + init 新实例）之后，observer 回调自动指向新实例，不需要重新绑定。
- `bindKlineResize(el)`：
  - 有 `ResizeObserver` 时**单例**创建 observer，且用 `klineObserved` 保证只 `observe(el)` 一次（容器 DOM 复用时不会重复 observe）；
  - 无 `ResizeObserver` 时退回 `window.resize`，用既有 `klineResizeBound` 去重，回调里 `$('#chart-kline')` 重新取容器再交给 `klineResize`。
- `symbol.html:689` 在 `echarts.init(el)` 之后立即 `bindKlineResize(el)`。
- 删除原 `renderKline` 尾部的旧绑定 `window.addEventListener('resize', () => symbolKlineChart && symbolKlineChart.resize())`（它在 chip 切换 dispose 后会对已销毁实例 resize，且不响应面板高度变化）。

### 痛点 2：重播可见窗口裁剪

`replay.js:124-131` 新增纯函数 `visibleWindow(cursor, n, size)`，`:134-137` 挂在 `QREReplay.core` 上导出。

契约：`(cursor, n, size) -> {start, end}`

- `n <= 0` → `{start: 0, end: 0}`；
- `cursor` 先 clamp 到 `[0, n-1]`，`end = cursor + 1`（右端含光标当日）；
- `size` 缺省为 `DEFAULT_WINDOW = 240`；`size <= 0` 或非数值 → 视为全量（`start = 0`）；
- 否则 `start = max(0, end - size)`（窗口未满时自然从 0 开始）。

`replay.js:255`：`winSize = Math.max(1, Number(opts.windowSize) || DEFAULT_WINDOW)`，`opts.windowSize` 可覆盖（基准测试里用 `1000000` 复现修复前的全量行为）。

`replay.js:263-268`：rAF 帧内 `win = visibleWindow(cursor, n, winSize)`，`xData = dates.slice(s0, c0)`、每个 series `data: s.data.slice(s0, c0)`，`viewStart` 记录给事件标记用；`replaceMerge: ["xAxis","series"]` 语义不变。`frameMetrics` 仍按全量序列计算，末帧指标口径未变。

`replay.js:312, 323`：`markPoints` 过滤 `i < viewStart` 的信号日与成交日，避免渲染窗口外（含未来）的事件；信号日 T 分支额外要求 `i-1 >= viewStart`。

`replay.js:474-475, 491`：窗口 resize 改为只在自建容器（`ownChartEl`）时绑定，destroy 时解绑；接管模式下容器尺寸归宿主页面负责，避免与宿主双重绑定。

### 验证

- TDD 先 RED（`4 failed, 1 passed`，缺 `visibleWindow` / 默认 240 / destroy 解绑 / observer 单例），实现后 `uv run pytest tests/test_saas_chart_a_fix.py -q` → `5 passed in 0.34s`。
- 既有回归：`uv run pytest tests/test_saas_replay_boundaries.py tests/test_gui_saas_pages.py tests/test_saas_night_mode.py -q` → `122 passed in 17.13s`。
- 全量套件：`uv run pytest tests/ -q` → 见下方「全量回归」一节。

### 性能基准（真实实测，非估算）

临时目录 `.tmp/a-replay-perf/`（已 gitignore），使用生产 `replay.js` 与 vendored `gui/static/echarts.min.js` (5.6.0)，4000 根合成 K 线，接管模式，candlestick + 成交量 + MA20 + DIF + DEA + MACD 柱，3 grid，事件标记开启；Playwright Chromium headless 跑同步 200 帧 + 60 帧 rAF 节奏，各 3 轮。

| 模式 | perFrameMs（3 轮） | lastFrameMs | rAF 帧间隔 | renderedBars |
| --- | --- | --- | --- | --- |
| 修复后（windowSize=240） | 9.5 / 9.2 / 9.5 | 8.8 / 7.0 / 6.9 | 16.8 / 16.8 / 16.8 ms | 240 |
| 修复前等价（windowSize=1000000） | 38.8 / 39.8 / 39.1 | 66.6 / 79.5 / 74.6 | 44.8 / 45.9 / 45.8 ms | 4000 |

结论：单帧绘制耗时降到约 1/4，rAF 节奏从 44–46 ms 提升到 16.8 ms（顶到 60fps 显示上限，即浏览器不再是被绘制阻塞的一方）。浏览器 console 无 error / pageerror。

产物：`bench.html`、`bench.py`、`probe.py`（调试探测脚本）、`run.log`、`run2.log`、`run3.log`、`result.json`、`shot-window.png`、`shot-full.png`、`pytest-full.log`。

### 口径变化说明（需在验收时确认可接受）

可见窗口裁剪 + yAxis `scale: true` 自适应，导致重播过程中：

- 「累计收益 / 回撤」曲线左端不再固定在 0（窗口内首根即左端）；
- 纵轴随窗口数据自动缩放，跨时段视觉基准会变。

末帧 `frameMetrics`（总收益、最大回撤、胜率等）仍是全量口径，数值不变。若产品要求曲线左端恒为 0，可后续把累计类 series 的起点值改为常量 `0`，与本次性能修复解耦。

### 遗留风险（本轮未改）

- `src/quant_research_engine/gui/saas/templates/job.html:392` 仍对已 dispose 的 `mainChart` 调用 `resize()`，只在 console 产生警告，不影响功能。属于既有权重问题，本轮按范围约定不动。
- 本轮按父任务约束未更新 `04/05/09/10/11/14/16/23` 等共享进度文档；合入时需由主流程补齐。

### 全量回归

`uv run pytest tests/ -q` → `2914 passed, 24 skipped, 4 warnings in 170.23s`（exit 0）。上一轮同仓基线为 `2909 passed, 24 skipped, 4 warnings`，差值 5 即本轮新增的 `tests/test_saas_chart_a_fix.py`。执行日志：`.tmp/a-replay-perf/pytest-full.log`。

## 遗留修补记录（2026-10-27）

- `job.html`：`mainChart` 的 window resize 回调增加 `isDisposed()` 守卫，避免对已 dispose 实例 resize 产生 console 警告。
- `replay.js`：新增纯函数 `windowDisplayData(data,start,end,zeroBase)`；`zeroBase=true` 时以窗口内首个非空值为基线，让策略/基准累计收益曲线在可视左端回到 0。指标仍基于全量 `raw`，数值不变。
- `job.html` 重播的“策略”和“基准”系列设置 `zeroBase: true`；回撤系列不设，避免把回撤曲线平移成“变化量”而误导风险。
- 测试：`tests/test_saas_chart_a_fix.py` 新增 3 例；该文件 8 passed；相关 130 passed；全量 `2917 passed, 24 skipped, 4 warnings`。
- 生产：ECS 同步 `job.html` + `replay.js`，qre-saas active；`/saas/jobs/58` 200，生产 replay.js 含 `windowDisplayData`，job58 页面含 `mainChart.isDisposed` 守卫。未 commit/push。
