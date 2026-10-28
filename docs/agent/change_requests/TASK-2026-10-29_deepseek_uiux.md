# DeepSeek 任务书：QRE UI/UX 三项改造（2026-10-29）

> 派发人：Kimi（主 Agent，负责主线推进 + bug 检查）
> 执行人：DeepSeek 子 agent
> 批准人：用户（2026-10-29）
>
> **边界**：只改**尺寸、布局、图表结构**。字体家族、色板（除本书记名的基准曲线色）、
> 圆角风格、玻璃/夜间机制、动效一律不动。不得改任何后端 Python 与数据库。
> 不得引入外部依赖（禁 CDN）。不得新增灰色小字备注（R-UI-001）。
> 每完成一项必须自测并通过 `uv run pytest tests/ -q` 全绿，再进入下一项。

---

## A. 波动率状态展示改造（FRM 模块）

### A1. 背景（Kimi 已查清，不是数据错误）

`risk/constants.py::REGIME_QUANTILES = (1/3, 2/3)`，规则是**按自身样本三分位**切分，
所以三桶观测数**恒等于各 1/3**。Kimi 实测生产 4 个 job：

| job | n | low | mid | high |
|---|---|---|---|---|
| 58 | 4068 | 1356 | 1356 | 1356 |
| 66 | 4069 | 1356 | 1356 | 1357 |
| 74 | 4073 | 1358 | 1357 | 1358 |
| 78 | 4075 | 1358 | 1358 | 1359 |

全部 33.3%/33.3%/33.3%。**数据正确，但原展示（只显示三个计数）不携带任何信息**，
用户误判成数据错误。

### A2. Kimi 已完成后端改动

`risk/report.py` 的 `volatility.regime` 节新增 `thresholds_annual`：

```json
"thresholds_annual": {"low_below": 0.18344, "high_at_or_above": 0.202309}
```

（切点对应的**年化波动率**，日波动 ×√252。）

### A3. 你要做的（两处模板同改）

文件：
- `src/quant_research_engine/gui/saas/templates/job.html` → `renderRiskVol(d)`
- `src/quant_research_engine/gui/templates/lab_result.html` → `renderRiskVol(d)`

现状（job.html 约 777-800 行）把三桶计数平铺成文字，例如
`EWMA 年化波动 22.1%；GARCH 年化波动 22.8%；当前波动状态 mid`。

**改为**（保留 EWMA/GARCH 两项，替换 regime 那一段）：

1. **当前状态**用中文标签：`低波动` / `中波动` / `高波动`（现在直接显示 `mid` 等英文）
2. **给出阈值含义**，例如：
   `当前：中波动（年化 18.3%–20.2% 为中档；≥20.2% 为高，<18.3% 为低）`
   —— 阈值从 `d.volatility.regime.thresholds_annual` 取，缺字段时退回只显示中文标签
3. **三桶计数可以保留但降级**：移到 hover tip 里（`data-tip`），
   主文案不再平铺三个相等的数字
4. 若 `thresholds_annual` 不存在（旧产物），**不得显示 `undefined`/`NaN`**，只显示中文标签

### A4. 验收

- 用生产 job 58 的真实 `risk_report.json`（Kimi 已放到
  `.tmp/perf-browser/risk_report_58.json`）在浏览器渲染，断言：
  - 中文标签出现（`低波动`/`中波动`/`高波动` 之一）
  - 阈值百分比出现（如 `18.3%`、`20.2%`）
  - 无 `undefined` / `NaN` / `null`
- 旧产物（无 `thresholds_annual`）不得出现 `undefined`

---

## B. 统一「策略收益」与「个股收益」对比图

### B1. 现状差异（Kimi 已核实）

| | job.html `#chart-main` | symbol.html `#chart-equity` |
|---|---|---|
| 策略曲线 | 累计收益率%（蓝 #2563eb） | **净值(元)** + 累计收益% **双 y 轴** |
| 基准切换 | `#bench-bar` **按钮单选**（一次一个） | **图例开关多选**（默认只显示上证） |
| 基准色彩 | 单一 | 全部 `#B7A6E8`（同一色，分不出） |
| 买入持有该股 | 无 | 有（`#9A93A6` 虚线） |
| 回撤 | ✅ 独立副图（红 #d43030 area） | ❌ 无 |
| grid | 主图 52% + 回撤 16% | 单 grid |

### B2. 目标（用户原话："两者各取部分特点"）

1. **可以显示策略 or 个股对比多个基准** —— 两页都支持**同时**显示多条基准
2. **区别各基准曲线的色彩** —— 每条基准一个独立色
3. **在个股收益中加入回撤数据** —— symbol 页也要回撤副图

### B3. 实现方式：抽共享模块（**不要**在两模板各写一份）

历史教训：双引擎/双实现只回归一边已经坑过多次（LWC 图例开关、K 线双引擎叠加）。
所以本次必须把**图表 option 的构造**抽成共享纯函数。

**新建 `src/quant_research_engine/gui/static/equity-chart.js`**，导出
`window.QREEquityChart`（IIFE + `typeof window` 守卫，Node vm 可测）：

```js
QREEquityChart.BENCH_COLORS   // {code: color} 或按序循环的取色函数
QREEquityChart.STRATEGY_COLOR // '#2563eb'（不变）
QREEquityChart.DD_COLOR       // '#d43030'（不变）
QREEquityChart.toPct(values)  // 净值/收盘 → 起点 0% 的累计收益率（纯函数）
QREEquityChart.drawdownPct(equity)  // → 回撤%序列（≤0），纯函数
QREEquityChart.benchPct(closes)     // 基准收盘 → 起点 0%，纯函数
QREEquityChart.option({dates, strategyPct, benches, benchmarks, holdPct, drawdownPct})
// ↑ 返回完整 ECharts option 对象（纯函数，不碰 DOM）
```

**基准配色**（用户要求"区别各基准曲线的色彩"；不得与策略蓝 #2563eb、
回撤红 #d43030 冲突；沿用项目既有色，不引新色相）：

| 基准 | 色值 |
|---|---|
| 上证指数 | `#B7A6E8` |
| 沪深300 | `#2A9D8F` |
| 深证成指 | `#E8A33D` |
| 中证500 | `#4A3A78` |
| 创业板指 | `#9A93A6` |
| 中证1000 | `#6750A4` |
| 买入持有该股（仅 symbol） | `#6750A4`，**虚线** `type:'dashed'` |
| 策略 | `#2563eb`（宽 2px） |
| 回撤 | `#d43030`（area，opacity .35） |

未列出的基准code按上面顺序循环取色。

**统一后的图表结构（两页一致）**：

- 上 grid：策略累计收益率% + 各基准累计收益率% + （symbol 额外）买入持有该股%
- 下 grid：回撤%（两页都有）
- 单 y 轴（累计收益率%）——**去掉 symbol 的"净值(元)"双轴**，统一口径
- `axisPointer: {link: [{xAxisIndex:'all'}]}` 全联动
- `dataZoom`：inside + slider，x 轴跨两 grid 联动
- `legend`：策略 / 各基准名 / 回撤

**页面 glue 留在各自模板**（不抽）：
- job.html：`#bench-bar` 按钮改为**多选开关**（点击切换该基准显示/隐藏，
  `aria-pressed` 反映状态），保留「无基准」语义（全部关掉时只看策略）
  —— 这是"取 job 的特点"
- symbol.html：保留图例开关能力（ECharts legend 原生），同时**加上 bench-bar 按钮**
  与 job 一致 —— 这是"取 symbol 的特点"
- 两页的「区间信息卡」（`#range-strip`）随 dataZoom 重算的逻辑**保持不变**

### B4. 不得破坏的既有行为

- 区间信息卡（区间策略收益 / 买入持有收益 / 基准收益 / 超越买入持有 / 交易日数 /
  持仓暴露度 / 持仓期年化）随滑块实时重算 —— **逻辑一行不改**
- 重播（`#btn-kreplay` / replay.js）接管 `#chart-main` / `#chart-equity` 的行为不变
- 窄屏（375px）无横向溢出
- 夜间模式（`QRETheme.themeChart`）仍生效

### B5. 测试（必写）

新建 `tests/test_equity_chart.py`：

1. **纯函数单测**（Node vm 跑真实 `equity-chart.js`）：
   `toPct` / `drawdownPct` / `benchPct` 的边界（空数组、含 null、含 0/负值、单点）
2. **交叉验证**：`drawdownPct` 与 Python 侧等价实现对同一序列结果一致（容差 1e-9）；
   Python 侧用 `pandas` 现算期望值写在测试里
3. **源码合同**：
   - `equity-chart.js` 存在且导出上述 7 个成员
   - job.html 与 symbol.html **都**引入 `/static/equity-chart.js`
   - 两模板都调用 `QREEquityChart.option(`
   - 两模板都**不再**出现内联的 `grid: hasDD ? [...]` 这类自建 option 片段
   - symbol.html 必须出现回撤副图（`QREEquityChart.drawdownPct` 或 option 里的 dd series）
4. **RED 验证**：把 symbol 的回撤去掉 → 合同测试红

---

## C. 全局尺寸调整（用户 28 寸 + MacBook 主观：字小、密度大、主题窄）

### C1. 现状值（Kimi 已量，`static/lab-theme.css`）

| 目标 | 现值 |
|---|---|
| `.wrap` max-width | `1280px`，`padding:32px 32px 80px` |
| `.topbar-inner` max-width | `1280px`，`padding:0 32px` |
| `body` font-size | `15px` |
| `.chart-box` | `padding:16px 18px`，`margin-bottom:20px`，圆角 24px |
| `.card` | `padding:20px 22px`，`margin-bottom:20px` |
| `.metric-strip` | `gap:10px`，`margin-bottom:16px` |
| `.metric-card` | `padding:12px 14px`（在 `card-class.css`） |

### C2. 目标值（用户三项要求逐条对应）

**① 扩大各页面主体 width，所有页面一致，主题 width 与两侧间距尽量小**

| 目标 | 现值 → 新值 |
|---|---|
| `.wrap` max-width | `1280px` → **`1600px`** |
| `.wrap` 左右 padding | `32px` → **`20px`** |
| `.topbar-inner` max-width | `1280px` → **`1600px`** |
| `.topbar-inner` 左右 padding | `32px` → **`20px`** |

> **`.wrap` 与 `.topbar-inner` 的 max-width 和 padding 必须严格一致**，否则顶栏与
> 内容左右对不齐。改完请用浏览器量两者 `clientWidth` 与 `getBoundingClientRect().left`
> 断言相等。
> 注意：`lab-theme.css` 是 8081 lab 与 SaaS **共用**的，改它会同时影响两边——
> 这正是用户要的"所有页面 width 保持一致"。但改前请先确认 8081 页面没有依赖
> 1280px 的硬编码布局（grep `1280`）。

**② 加大整体文本字号**

| 目标 | 现值 → 新值 |
|---|---|
| `body` font-size | `15px` → **`16px`** |
| `.page-head p` | `14.5px` → `15.5px` |
| `.m-label`（card-class.css） | `12px` → `13px` |
| `.metric-card .m-value` | `18px` → `20px`；`#sum-strip/#ra-strip` 的 `15px` → `16.5px` |
| `.chart-title` | `13px` → `14px` |
| `.tbl` / `.detail-table` | 同比 +1px（不要逐个数，用相对值） |
| `.opt` / 提示类 | **不放大**（保持弱化层级），但不得小于 12px |

> 只放**大**，不放小；只改 px 数值，不改 `font-family`、`font-weight`、`line-height` 比例。

**③ 扩大相邻 div 大小、div 间距、div 内主题与边框间距**

| 目标 | 现值 → 新值 |
|---|---|
| `.chart-box` padding | `16px 18px` → **`22px 24px`** |
| `.chart-box` margin-bottom | `20px` → **`28px`** |
| `.card` padding | `20px 22px` → **`26px 28px`** |
| `.card` margin-bottom | `20px` → **`28px`** |
| `.metric-strip` gap | `10px` → **`14px`** |
| `.metric-strip` margin-bottom | `16px` → **`22px`** |
| `.metric-card` padding | `12px 14px` → **`16px 18px`** |
| `.metric-strip`/`.metric-card` 圆角 | 不变（24px，已是玻璃规格） |
| `.wear-cards` / `.risk-cards` gap | `10px` → `14px` |

### C3. 必须同步调整的连带项（漏一个就破版）

1. **图表高度**：`#chart-main` 420px、`#chart-equity` 260px、`#chart-risk-dist` 240px、
   `#chart-risk-vol` 240px、`#chart-risk-stress` 220px、`#chart-kline` 460px
   → 统一 **+60px**（宽屏更宽，图更高才不扁）
2. **`klineHeightForPanes` / `QRELwcAdapter.klineHeight`**（replay.js 与 kline-lwc.js）
   → 同步 +60px，否则静态图与重播高度会不一致
3. **`@media(max-width:960px)` 与 `@media(max-width:640px)`** 断点：
   width 放到 1600 后，断点阈值**不变**（仍按视口宽度），但要把 960 档的
   `flex:1 1 45%` 改成 `1 1 100%`（更宽的容器在两列时卡片会过宽）
4. **ECharts grid 的 `left/right/top/bottom` 数值**：字号变大后轴标签更宽，
   `#chart-main` 的 `left:55`、`#chart-equity` 的 `left:70,right:60` 需相应 +10~15，
   否则轴标签会被裁。**改完必须截图看轴标签完整。**
5. **`card-class.css` 的密集条 min 130px**：容器宽了以后 7 卡仍能一行，
   但为保险起见把 `#sum-strip/#ra-strip` 的 250px 提到 **280px**（8 卡 → 4+4 更舒展）

### C4. 验收（必做，用户用 28 寸 + MacBook 看）

在 **1440 / 1920 / 2560 / 375** 四个视口，用真实 Chromium 断言并截图：

1. `.wrap` 与 `.topbar-inner` 的 `clientWidth` 相等、`left` 相等（顶栏与内容对齐）
2. 四个视口 `document.documentElement.scrollWidth <= innerWidth`（无横向溢出）
3. 首页 / 新建策略 / 回测结果 / 个股详情 / 使用说明 / 经典策略 / 个人信息 七页
   各截一张全页图，人工看：无重叠、无裁切、无挤成一团
4. 轴标签完整可见（不被 grid 裁掉）
5. 静态 K 线与重播高度一致
6. 夜间模式下同样四项通过

---

## D. 通用纪律（每次交互都要遵守）

1. **不新增灰色小字备注**（R-UI-001）：要解释就用 `tip-trigger` + `data-tip` + `LabUI.helpTips`
2. **不引外部依赖**（禁 CDN），所有 JS/CSS 走 `/static/`
3. **每完成一项就跑** `uv run pytest tests/ -q`，全绿才进入下一项
4. **新增/改动的共享模块必须配 Node vm 测试**（参照 `tests/test_perf_metrics.py` 的写法），
   并且做 **RED 验证**（把改动改坏，确认测试红）
5. **改完必须真实浏览器验证**（Chromium + `.tmp/browser-venv/bin/python`），
   VM 单测全绿但生产炸的教训已经有过多次
6. **涉及 `node -e` 的测试**：脚本超 100KB 时改写临时文件跑
   （Linux 单参数上限 128KB，`symbol.html` 已经 107KB）
7. 每完成一项，把该项的 CR 写进 `docs/agent/change_requests/CR-2026-10-29_*.md`，
   并追加 `05_PROGRESS.md` / `09_CODING_HANDOFF.md` / `11_AGENT_STATE.md`
8. **不要 commit / push**——完成后报告 Kimi，由 Kimi 复核并提交

---

## E. 建议顺序

```
A（波动率展示，最小） → C（尺寸，影响面最大但机械） → B（图表统一，最复杂）
```

理由：C 会改变所有图表尺寸，B 要重写图表 option，先定尺寸再定图表结构，
避免 B 做完又被 C 的尺寸改动打破。
