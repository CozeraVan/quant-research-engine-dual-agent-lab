# CR-2026-10-27 K 线重播 TV 化首片

## 背景

TradingView 化第一阶段已完成静态 K 线 TV 化、MACD 别名/复权口径修复。用户选择下一步做“重播界面 TV 化”。本 CR 只对齐个股 K 线重播的视觉与交互，不新造第二套 K 线模块，不改防未来数据规则。

## 目标

1. 重播图表与静态 TV 化布局一致：右侧价格/数值标尺、底部时间轴、x 轴全联动、grid 留白一致。
2. 重播期间顶部信息区显示当前帧 OHLC、成交量、涨跌与可见因子值；无未来数据；移出/暂停不得停留在未来。
3. 重播控制继续复用 `QREReplay` core；`frameMetrics` 仍按全量数据，末帧一致性不变。
4. 退出重播后恢复静态 K 线 TV 化视图，工具栏/信息区复原。
5. Night Mode、红涨绿跌、因子 display 合同、chip 状态不变。

## 边界

- 只改 `src/quant_research_engine/gui/saas/templates/symbol.html` 与必要 `src/quant_research_engine/gui/static/replay.js`；不改 `job.html`、`lab_symbol.html`、游戏、worker、引擎、schema。
- 不新增依赖、不引 CDN、不引入 Lightweight Charts、不抓取 TradingView 资产。
- 不跑回测；不部署 ECS 由主 Agent 执行；未 commit/push。
- 当前工作区有未提交/已提交的 TV 化基础，必须在其上继续，不得 revert/format。

## 实施要求

### 1. 布局一致

- `mountKlineReplay()` 复用静态布局规格（或等价实现）：主图/量/因子副图右侧标尺、底部时间轴、动态 grid。
- `replay.js` 如确需支持右侧标尺，只能做最小增量：例如 `yAxes[].position` 透传；默认行为不影响 `job.html` 收益曲线重播。

### 2. 信息区

- 重播帧更新 `#kline-ohlc` 或同等顶部信息区：日期、开高低收、涨跌、成交量、overlay/pane 因子值。
- 缺失显示 `—`；不得显示未来数据；退出时清空或交还静态渲染。

### 3. 控制与交接

- 播放/暂停/单步/倍速/进度条/空仓快进语义不变。
- 接管/退出继续走 `chartEl` + `destroy(keepDom)`；不得出现第二个同内容 K 线模块。
- `ResizeObserver` 在重播期间应作用于重播实例。

## 测试与验收

- TDD：先补失败测试，再实现。
- 新增/更新测试至少覆盖：重播 grid/yAxis 右侧标尺、信息区更新、无未来数据、退出恢复静态、现有重播边界不回归。
- 命令：
```bash
uv run pytest tests/test_saas_replay_boundaries.py tests/test_saas_static_kline_tv.py tests/test_saas_chart_a_fix.py tests/test_gui_saas_pages.py -q
uv run pytest tests/ -q
```
- 浏览器证据放 `.tmp/replay-tv/`：最小合成 detail + 生产 replay.js/symbol 片段 + vendored ECharts，验证 1280/375、零 JS error、右侧标尺、信息区随帧更新、退出恢复；不得伪造。

## 发布

- 测试通过后由主 Agent 部署 ECS，仅同步实际改动文件并重启 qre-saas；用户验收前不 commit/push。

## 实现记录（2026-10-27）

### 改动位置

- `src/quant_research_engine/gui/saas/templates/symbol.html:1057` `mountKlineReplay()`：布局改用静态 TV 规格 —— `klineGridSpec(true, panes.length, true)`（1098，`left:16/right:56`）、`klineAxisLabelIndex(panes.length, true, true)`（1099，时间轴只挂末格索引 `1+n`）、yAxes 主图与量轴均 `pct:false, position:'right'`，量轴 `formatter` 为 `(v/10000).toFixed(0)+'万'`（1100–1103），每个因子 pane 轴 `pct:false, position:'right', scale:true`（1108）；attach 追加 `axisPointer:{link:[{xAxisIndex:'all'}]}`（1149）与 `axisLabelIndex: labelIdx`（1150）。
- `symbol.html:1154` `onFrame` 同时驱动侧边卡片与顶部信息区：`infoFrame(cursor)` + `klineSetInfo(klineInfoHTML(d, plan, cursor))`。`klineInfoHTML`（704–728）按当前帧生成 日期/开高低收/涨跌（相对前一交易日收盘，首根 `—`）/量/overlay/pane 因子值，越界或缺失一律 `—`，不读取 cursor 之后的数组元素。`klineSetInfo`（729）写入 `#kline-ohlc`（`aria-live="polite"`，原静态节点，未新增 DOM）。
- `src/quant_research_engine/gui/static/replay.js:307-311`：`yAxes[].pct===false` 时不加默认 `%` 后缀（有 `formatter` 用之，否则不设），`y.position` 存在才透传 `position`；`:317` 仅当 `opts.axisPointer` 传入时才写 `option.axisPointer`；`:295` `axisLabelIndex` 缺省仍为末格。三处均为可选参数，`job.html` 收益曲线重播不传时输出与改动前一致。
- 静态路径未改语义：`renderKline`（921–1025）、`initKlineReplay`（1028–1056）沿用原实现；工具栏接管 `setKlineToolsEnabled(false)`、退出 `destroy(true)` + `renderKline(klineData)` 的控制语义与接管合同不变，未新增第二个 K 线模块。

### 口径

- 顶部信息区与侧边卡片共用「当前帧」：重播首帧 `cursor=0`，`xAxis[0].data` 与 candlestick series 长度均等于 `cursor+1`，未来行不进 ECharts。
- 播放/暂停/单步/倍速/进度条/空仓快进、`frameMetrics` 全量口径、夜间模式、红涨绿跌、因子 display 与 chip 三态均未改。

### 测试（真实输出）

- 新增 `tests/test_saas_replay_tv.py`（6 例）覆盖：重播 yAxis 右置与 grid 56px 留白、单时间轴索引、x 轴 link、`onFrame` 信号、信息区当前帧/缺失 `—`、退出恢复静态。
- `tests/test_saas_replay_boundaries.py`、`tests/test_factor_display_contract.py` 仅改 `mountKlineReplay` 抽取正则，断言未动：`mountKlineReplay` 现在复用页面级 `klineGridSpec`/`klineAxisLabelIndex`/`klineInfoHTML`/`klineSetInfo`，只截该函数体会在 node vm 里 `ReferenceError: klineGridSpec is not defined`（首轮全量回归实测 1 例失败），抽取起点改为 `let klineResizeBound = false;`（这些 helper 紧随其后、在 `mountKlineReplay` 之前）。
- `uv run pytest tests/test_saas_replay_boundaries.py tests/test_saas_static_kline_tv.py tests/test_saas_chart_a_fix.py tests/test_gui_saas_pages.py tests/test_saas_replay_tv.py tests/test_factor_display_contract.py -q` → `141 passed in 17.68s`。
- `uv run pytest tests/ -q` → `2936 passed, 24 skipped, 4 warnings in 171.69s (0:02:51)`，`EXIT=0`（正则修正后的全量；修正前首轮全量 `1 failed, 2935 passed`，失败项即上述抽取正则）。
- `bash scripts/check-progress-docs.sh` → `Progress docs check passed.`

### 浏览器证据（`.tmp/replay-tv/`，真实 Chromium 1248）

- `build.py` 从 `symbol.html` 抽取 `style`（5–26 行）、chip/kline/`initKlineReplay`/`mountKlineReplay` JS 块（650–1156 行）与 `#box-kline` 标记（51–82 行），配生产 `static/replay.js`/`factor-layout.js`/`echarts.min.js`；90 根合成日 K，经真实路径点击 `#btn-kreplay` 接管。
- `check.py` 两视口：**33/33 通过**，零 console/page error。关键数值：
  - 1280×900 重播：yAxis `['right','right','right']`（panes=1 → 3 格），grid right `[56,56,56]`，可见时间轴索引 `[2]`，`axisPointer.link[0].xAxisIndex='all'`；首帧 `.rp-cur='1 / 90'`、x 轴与 candlestick 长度均 `1`，信息区含 `2026-01-05` 且不含末日期 `2026-05-08`；单步后 `2 / 90`，信息区日期 `2026-01-06`；进度条拉满后 `90 / 90`，x 轴 90 根，信息区末日期。
  - 接管时 5 个 `.kline-tool` 均 `disabled=true`/`aria-disabled=true`；退出后恢复 `disabled=false`、`kt-vol aria-pressed=true`、`#kreplay-note` 消失、`#kreplay-bar-slot` 子节点 0、`#chart-kline` 仍唯一、静态 yAxis 全 `right`、单时间轴索引 `[2]`、静态 candlestick 90 根、信息区回到末日期。
  - 375×812：yAxis 全 `right`、单时间轴 `[2]`、`scrollWidth 375 = clientWidth 375`、图表宽 261px、信息区首帧日期在列；无横向溢出。
  - `result.json` 记录全部 33 项 ok/detail，`1280.png`（1280×900）、`375.png`（375×1497）为整页截图。

### 遗留 / 未改

- 重播 tooltip 的 `valueFormatter` 仍统一追加 `%`（`replay.js:301`），价格/量轴 tooltip 会显示 `19.70%`；本次只对齐标尺与信息区，tooltip 口径未动，待单独 CR。
- `mountKlineReplay` 的容器高度仍是 `420 + panes*160`（`symbol.html:1096`），未与静态 `460px` 归一；panes=0 时 460px，panes≥1 时比静态高。属视觉遗留，不在本片验收面。
- 375 视口信息区为 nowrap + ellipsis（`.kline-ohlc` 原样式），只保证首段日期可见，不保证整行可读。
- 明确未触碰：`job.html`、`lab_symbol.html`、游戏、worker、引擎、schema、因子注册表、`docs/agent/04/05/09/10/11/14/16/23`、`08_IMPLEMENTATION_BRIEF.md`；未部署、未 commit、未 push。
