# CR-2026-10-29 · 专业价格格式化框架（TV_ROUND2 T2）

- **任务书**：`docs/agent/TV_ROUND2_TASKS_2026-10-29.md` §7 T2（P0，1–2 人日）
- **验收口径**：§4 样式规格表「价格轴」行 + T2 两条验收（4 种 mode 右轴截图对比；
  价格跨 3 个数量级时轴宽不跳动）
- **实施日期**：2026-10-29

## 1. 背景

逆向侧 §1 评分把「K 线呈现」的差距定位为「功能 85 / 视觉 55，差距全落在价格格式化与
样式规格」。§2.4 已定量出三个具体症状：

1. 右轴标签精度由 ECharts 自动决定 → 同一根轴上 `3 / 2 / 1 / 0.00 / -1 / -2 / -3` 混排
   （用户据此判断"MACD 各自坐标系"的次要放大因素之一）；
2. 无末价标签、无 1-2-5 刻度密度控制、竖网格线干扰；
3. 价格跨数量级时右轴观感宽度跳动（标签位数变化 + 右留白固定）。

## 2. 实施内容

### 2.1 新增共享静态层 `static/price-scale.js`（`window.QREPriceScale`）

纯函数层（Node vm 可测）+ ECharts 规格构造函数（symbol.html 静态图与重播共用）：

| 出口 | 职责 |
|---|---|
| `MODES` / `modeOf` / `modeMeta` / `nextMode` | 4 种 priceScaleMode：0 普通 / 1 对数 / 2 百分比 / 3 指数化 |
| `precisionFromMinMove` / `decimalsOf` / `inferPrecision` / `autoPrecision` | 自动精度 = minMove（0.01→2 位；minMove 缺省才按数据推断） |
| `niceStep` / `niceTicks` | 1-2-5 阶梯刻度密度 |
| `formatValue` | 4 模式 + 千分位 + 固定小数位；base 可为函数（可见区间首根，随缩放变化） |
| `axisWidthPx` / `candidateLabels` / `labelsWidthPx` | 轴宽按**全量数据极值**预算，不随可见窗口跳动 |
| `axisLabelSpec` | ECharts axisLabel：固定 width + `align:'left'` + `margin:6` + formatter |
| `priceAxisSpec` | 主图价格轴（右置 / 1-2-5 splitNumber / 只画水平 splitLine / log 回落） |
| `lastPriceMarkLine` | 末价标签（markLine，带背景块，silent） |
| `crosshairSpec` | 十字光标 1px 虚线 + 价格/时间标签背景块 |
| `legendSpec` | 图例圆点 + 名称 + 当前值 |
| `categoryAxisSpec` | 类别轴不画竖网格线 |
| `readMode` / `setMode` | `localStorage['qre.kline.priceScaleMode']` 持久化 |

### 2.2 `factor-layout.js`（共享映射层增量，不破坏 T1 合同）

- `paneYAxes` 新增 `spec.paneAxisLabel(pane, i)`：副图轴也可走固定精度 + 恒定轴宽；
- `panesToOption` 的 xAxis 默认 `splitLine:{show:false}`（§4：只画水平线）；
- `plan()` 的 pane 对象新增 `precision`（display 合同给的首个非空精度），供副图轴用。

### 2.3 `symbol.html`

- 引入 `/static/price-scale.js`；工具栏新增 `kt-pscale`（循环 4 模式，标签显示当前模式短名）；
- 新增 `klineCloses / klineAxisRightPx / klineGrids / klineVisibleStart / klinePriceBase /
  klinePriceFmt / klinePriceAxis / klineVolAxis / klineHeadYAxes / klinePaneValues /
  klinePaneAxisLabel / klinePaneAxisLabelFn / klineLegendText / klineLegendSpec /
  klineLastPriceColor / klineLastPriceMarkLine / klineCrosshairSpec / klineSetPriceMode`；
- `renderKline`：主图/量轴走 `klineHeadYAxes`，pane 轴走 `paneAxisLabel`，蜡烛
  `barWidth:'70%'` + 末价标签 markLine，legend/axisPointer 走共享规格，
  grid 右留白走 `klineGrids()`（≥56，按标签宽度预算）；
- `klineApplyLayout`（量/因子开关）改走同一套出口，消掉原先手写的
  `panes[i-2]` 轴拼装；
- `mountKlineReplay`：重播主图轴的 `axisLabel` 为**函数(s0)**（基准 = 当前帧可见窗口
  首根收盘），pane 轴同样走 `paneAxisLabel`，末价标签经 `markLineFor(s, idx, s0)`
  **按当前帧**生成（不得泄露未来数据）。

### 2.4 `replay.js`

- yAxis 支持调用方下发 `axisLabel`（对象或函数(可见窗口起点)→对象），未下发时保持
  原有 `%` / `formatter` 口径（job 默认路径逐字节不变）；
- 新增 `opts.markLineFor(series, idx, startIdx)`；
- xAxis 默认 `splitLine:{show:false}`。

## 3. 与任务书 §4 规格表的逐条对照

| 规格项 | 状态 | 证据 |
|---|---|---|
| 价格轴右置 | ✅ | 真实浏览器 `opt.yAxis[0].position === 'right'` |
| 轴宽恒定（不随位数跳动） | ✅ | 3 个数量级三档窗口，右轴标签左边缘像素恒为 1244（`align:'left'`+`margin:6`+右留白预算） |
| 刻度 1-2-5 密度 | ✅ | `niceTicks` 纯函数 + 与 Python 等价实现逐值交叉验证；对数轴实测 `1.00/10.00/100.00/1,000.00` |
| 千分位 | ✅ | `formatValue(1234.5) === '1,234.50'` |
| 精度 = minMove | ✅ | `autoPrecision(0.01, …) === 2`；qfq 4 位小数不复权价不抬高精度 |
| 末价标签带背景块 | ✅ | markLine `label.backgroundColor` + `data[0].yAxis === 末根收盘`，颜色随涨跌（红涨绿跌） |
| 网格只画水平线 | ✅ | 真实浏览器 `opt.xAxis[*].splitLine.show === false`，`yAxis[0].splitLine.show === true` |
| 蜡烛实体宽 = 0.7×间距 | ✅ | 实测 `mean(bodyWidth)/band = 0.725 / 0.728`（放大档） |
| 十字光标 1px 虚线 + 标签背景块 | ✅ | `axisPointer.lineStyle/crossStyle.type === 'dashed'`、`width:1`、`label.backgroundColor` |
| 图例左上单行，圆点+名称+当前值 | ✅ | 截图可见 `EMA12 101.00 · EMA26 85.32 · 成交量 50.00 万` |
| 右轴前 6px | ✅ | `axisLabel.margin === 6` |
| 顶 8px / 底 26px 时间轴 | ⚠️ 近似 | 顶部留给图例行（`grid.top:30`，原值未动）；底部时间轴位置沿用原有 dataZoom slider 布局，未改 |
| 底色 `#131722` / 面板 `#1e222d` | ⚠️ 有意偏离 | 见 §5 |
| 蜡烛涨 `#26a69a` / 跌 `#ef5350` | ⚠️ 有意偏离 | 见 §5 |

## 4. 测试与验证

### 4.1 Node vm 单测（`tests/test_price_scale.py`，15 例）

- minMove→精度（含 2.5→1、0.05→2 等非 10 幂用例）；
- 二进制尾差不放大精度（`0.1+0.2` 不得变 17 位）；
- 1-2-5 阶梯性质 + 与 Python 等价实现逐值交叉验证；
- 4 模式格式化 + 千分位 + 缺失/异常一律 `—`；
- 轴宽恒定：跨 3 个数量级、4 种窗口长度 × 3 种模式，任何窗口的最宽标签都不得超出预算轴宽；
- ECharts 规格（log 回落 value、末价标签、十字光标、图例、类别轴）；
- mode 持久化 + 循环 + 隐私模式（localStorage 抛错）不炸；
- 源码合同：symbol.html 必须引入并调用 `priceAxisSpec/lastPriceMarkLine/crosshairSpec/legendSpec`，
  replay.js 必须支持 `y.axisLabel`，且不得残留手写 pane 索引。

**RED 验证**（逐条变异真实源码，确认测试真的能抓到）：

| 变异 | 结果 |
|---|---|
| `precisionFromMinMove` 恒返回 2 | 3 failed |
| 1-2-5 阶梯退化为 10 阶梯 | 4 failed |
| 轴标签 `margin 6 → 0` | 3 failed |
| 百分比公式错成 `n/base*100` | 5 failed |
| 末价标签去掉背景块 | 3 failed |
| 类别轴画竖网格线 | 3 failed |

### 4.2 真实浏览器验证（`.tmp/perf-browser/t2_verify.py`）

Chromium（`.tmp/ms-playwright/chromium-1248`）+ 生产同款 echarts 5.6.1 + 真实
`symbol.html` 模板 + 真实 `price-scale.js`，数据为**价格跨 3 个数量级**（0.5 → ~5000，
400 根）+ 2 overlay + MACD 三列 + RSI 的合成产物。

关键实测值：

```text
mode0 普通: position=right type=value splitNumber=5
           axisLabel{width:46, margin:6, align:left, overflow:truncate}
           labelLeftXs=[1244]  maxLabelRight=1277.64  chartW=1298  gridRight=60
           lastPrice{yAxis:105.2705, bg:#C93A3A, text:"105.27"}
           crosshair{lineType:dashed, lineWidth:1, crossType:dashed, labelBg:#6750A4}
3 个数量级（span 0-60 / 150-210 / 330-400）:
           labels 0.60…1.20 | 4.00…9.00 | 40.00…110.00
           labelLeftXs 全部 = [1244]（左边缘像素恒定）
           candle ratio = 0.725 / 0.725 / 0.728
4 种 mode（点 kt-pscale 循环）:
           对数  axisType=log  labels 1.00/10.00/100.00/1,000.00
           百分  axisType=value labels 3,807.78%…23,346.66%  lastPrice "20,468.68%"
           指数  axisType=value labels 3,907.78…23,446.66  lastPrice "20,568.68"
           价格  axisType=value labels 20.00…120.00        lastPrice "105.27"
mode 持久化: localStorage['qre.kline.priceScaleMode']="0"，readMode()=0
副图轴精度: MACD → 4 位（-2.0000/0.0000/…，display 合同 precision=4）
           RSI14 → 2 位（50.00…100.00，display 合同 precision=2）
           同一根轴不再出现"3 与 0.00 混排"
```

截图：`.tmp/perf-browser/t2-mode-{0,1,2,3}.png`（4 种 mode 右轴对比）、
`.tmp/perf-browser/t2-magnitude-3orders.png`（跨 3 个数量级）；
机器可读结果：`.tmp/perf-browser/t2_result.json`。

## 5. 有意偏离任务书 §4 的两处（需用户/逆向侧确认）

1. **蜡烛涨跌色未改用 TV 的 `#26a69a` / `#ef5350`**，保持 A 股红涨绿跌
   （`#C93A3A` / `#1E8E5A`）。理由：全站买卖点三角、MACD 柱正负色、小数据卡盈亏色
   都是红涨绿跌；单独把蜡烛改成绿涨红跌会让同一页面出现两套涨跌语义，用户理解成本
   更高。末价标签颜色因此也随涨跌（红/绿），与蜡烛一致。
2. **画布/面板底色未硬编码 `#131722` / `#1e222d`**。理由：项目有浅色（默认）+ 夜间
   模式两套主题，图表背景由 `night-mode.js` 的 `applyNeutral` 统一管理（深色下它优先
   于本文件取值）；硬编码 TV 深色会在浅色主题下变成一块黑布。网格线色同理交给主题层。

另有两项只能算"近似"：顶部留白（`grid.top:30` 让给图例行，未按 8px 收）、底部时间轴
位置（沿用既有 dataZoom slider 布局）。二者不影响价格轴验收，未改动以避免牵连重播
与游戏页布局。

## 6. 影响面与风险

- **三处 K 线副本**：`symbol.html` 静态图与重播都改了；`game.html` 只受
  `panesToOption` 的 xAxis `splitLine:{show:false}` 影响（类别轴本就不画竖线，行为等价），
  未引入 price-scale.js（游戏无价格轴模式入口）。
- **job.html 重播默认路径**：replay.js 的 `axisLabelOf` 在调用方未下发 `axisLabel` 时
  逐字节保持原口径（`%` 或 `formatter`），由 `test_saas_replay_tv.py` /
  `test_saas_replay_boundaries.py` 覆盖。
- **复权口径**：未触碰。精度取 minMove（0.01→2 位）而不是数据小数位，正是为了
  qfq 复权价带 4~6 位小数时轴宽不跳。
- **防未来数据**：重播末价标签经 `markLineFor(s, idx, s0)` 只挂当前帧最后一根，
  基准取当前帧可见窗口首根，不接触未来数据。

## 7. 复现方式

```bash
cd /home/van/quant-workspace/quant-research-engine-dual-agent-lab
.venv/bin/python .tmp/perf-browser/verify.py                    # 渲染真实模板页
.tmp/browser-venv/bin/python .tmp/perf-browser/t2_verify.py     # 真实浏览器断言 + 截图
.venv/bin/python -m pytest tests/test_price_scale.py -q         # Node vm 单测
```
