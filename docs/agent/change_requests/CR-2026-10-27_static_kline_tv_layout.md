# CR-2026-10-27 静态 K 线 ECharts 深度 TV 化首片

## 背景

TradingView 化 Spike 结论：A 增强 ECharts 为主线。A 路第一轮已修复 `ResizeObserver`、重播视口裁剪、左端基线和 dispose resize 守卫，但**静态 K 线视觉/交互仍未 TV 化**。用户 2026-10-27 明确选择“ECharts 深度 TV 化”。

本 CR 只做**静态 K 线首片**，范围限定 `src/quant_research_engine/gui/saas/templates/symbol.html` 的 `renderKline()` 及其必要测试；重播 TV 化、画线工具、多股对比、实时流不在本片。

## 目标

在不改变数据合同、因子 display 合同、Night Mode、防未来数据规则的前提下，把静态 K 线从“工程图表感”提升到“TradingView 式工作区”：

1. **价格标尺右侧化**：K 线主图、成交量、因子副图的价格/数值轴统一到右侧，底部保留时间轴；不再使用左侧大边距价格轴。
2. **十字光标 OHLC/图例**：鼠标/触摸移动时，顶部信息区显示当前交易日 K 线 OHLC、成交量、涨跌幅（如可算）及当前可见因子值；十字光标轴标签可见。
3. **TV 式缩放/平移/重置**：滚轮缩放、拖拽平移、一键重置/适应窗口；缩放不得泄露未来数据，不得改变静态报告数值。
4. **左侧紧凑工具栏**：至少提供放大、缩小、重置/适应、切换成交量或因子面板可见性的按钮；图标用内联 SVG + 可见文字/aria，不用 emoji。
5. **因子呈现保持合同**：EMA/BOLL 等 overlay 仍叠加 K 线主图；MACD/PPO/PVO 同副图；KDJ/STOCH 家族同副图；RSI/风险/流动性/Alpha 独立副图；chip 状态继续生效。
6. **Night Mode 保持**：只改布局/交互，不改主题机制；红涨绿跌不变。

## 边界

- 只改 `symbol.html` 及必要测试；不改 `job.html`、`lab_symbol.html`、`replay.js` 的既有防未来数据核心、游戏、worker、引擎、schema、因子注册表、Night Mode 机制。
- 不新增依赖、不引 CDN、不引入 Lightweight Charts、不抓取 TradingView 资产。
- 不跑回测；不部署 ECS 由主 Agent 复核后执行；未 commit/push。
- 当前工作区已有未提交的 A 路遗留修补，DeepSeek 必须在其基础上继续，不得 revert/format/混入无关改动。

## 实施要求

### 1. 布局与标尺

- `renderKline()` 的 grid/yAxis 调整为右侧价格标尺；时间轴在底部；主图、成交量、因子副图共用 x 轴联动。
- 高度策略保留现有动态高度逻辑或等价实现，375px 不横向溢出。
- 坐标轴标签、网格线、分割线风格保持现有 UI token，不引入第四色相。

### 2. 十字光标与信息区

- 使用 ECharts `updateAxisPointer` / `globalout` 或等价事件，更新静态 K 线顶部/现有信息区的当前帧 OHLC、成交量、因子值。
- 无指针悬停时显示最后一根已完成 K 线或空态，不得显示未来数据。
- 数值缺失显示 `—`，不造值。

### 3. 工具栏与缩放

- 工具栏按钮需 44px 可点击区域、`:focus-visible` 紫环、375px 不破版。
- 滚轮缩放/拖拽平移可使用 ECharts `dataZoom` inside/slider 或等价实现，但需提供重置。
- 缩放只影响可见窗口，不得改变 `frameMetrics`/静态报告口径。

### 4. 因子与重播共存

- 因子 chips 与 overlay/pane 状态继续复用 `QREFactorLayout.plan()` 和 `chipStates()`。
- 本片可暂不把重播界面也 TV 化，但必须保证现有 K 线重播仍能接管/退出，不出现第二个同内容 K 线模块。

## 测试与验收

- TDD：先补失败测试，再实现。
- 新增测试至少覆盖：
  - `symbol.html` 含右侧价格标尺、轴指针标签、工具栏与重置控件；
  - 无灰色小字备注、无 admin 链接、无 CDN；
  - 因子 overlay/pane 合同未被破坏；
  - 现有重播边界测试不回归。
- 命令：
```bash
uv run pytest tests/test_saas_chart_a_fix.py tests/test_saas_replay_boundaries.py tests/test_gui_saas_pages.py tests/test_saas_night_mode.py -q
uv run pytest tests/ -q
```
- 浏览器证据放 `.tmp/static-kline-tv/`：用生产 `symbol.html` 需要的最小合成 detail + vendored ECharts 验证 1280/375、零 JS error、十字光标信息更新、缩放/重置、EMA overlay、MACD 同副图；不得伪造。

## 发布

- 测试通过后由主 Agent 部署 ECS，仅同步实际改动文件并重启 qre-saas；用户验收前不 commit/push。

---

## 实施记录（2026-10-27）

改动面：`src/quant_research_engine/gui/saas/templates/symbol.html`（唯一生产文件，1153 行）新增 366 行 + 新回归 `tests/test_saas_static_kline_tv.py`（10 例）。未改 `job.html` / `lab_symbol.html` / `replay.js` / 引擎 / schema / 因子注册表 / Night Mode；未加依赖、未引 CDN（ECharts 仍为仓库内置 5.6.1）。

### 1. 结构落点（symbol.html）

| 位置 | 内容 |
| --- | --- |
| 6–25 | 内联 `<style>`：`.kline-tools .kline-tool` 44×44、`:focus-visible` 紫环、`[aria-pressed="false"]` 0.55、`:disabled` 0.4、`.kline-ohlc` + `.up/.down/.k-dim`、`@media(max-width:640px)` 隐藏按钮 `<span>` 且 `.wrap` 收 12px |
| 58–80 | `.kline-tv` 两栏：左 `#kline-tools[role=toolbar]` + 5 个 `button.kline-tool`（`#kt-zoom-in/zoom-out/reset/vol/fct`，均 `aria-label` + `data-tip` + 内联 `svg` + `<span>` 文字，vol/fct 带 `aria-pressed="true"`）；右 `.kline-main` 内 `#kline-ohlc[aria-live=polite]` 与 `#chart-kline`（全文件唯一，height 460px） |
| 693–920 | 新 helper：`KLINE_TOOL_KINDS`/`KLINE_TOOL_VIS`/`klineToolState`、`klineNum/klineText/klineInfoHTML/klineSetInfo`、`klineZoomSpan/klineClampSpan/klineZoom/klineResetZoom`、`klineGridSpec/klineAxisLabelIndex/klineLegendSelected`、`klineToolBtn/klineSetPressed/setKlineToolsEnabled/klineSyncPressed/klineApplyLayout/bindKlineTools`、`klineResize/bindKlineResize` |
| 921–1025 | `renderKline()`：yAxis 三处 `position:'right'`（982/983/989）、`grid: klineGridSpec(...)`、`axisLabel.show` 只挂 `klineAxisLabelIndex(...)` 指定格（时间轴落最后一个可见格）、`legend.selected: klineLegendSelected(plan)`、`dataZoom` inside + slider（`bottom:4,height:18`）；`setOption` 后 `setKlineToolsEnabled(true)` → `bindKlineInfo` → `bindKlineTools` |
| 1041 | `initKlineReplay` 进入重播前 `setKlineToolsEnabled(false)`（并清空信息区），重播帧不会让静态信息条停在未来数据上；退出重播仍走 `renderKline(klineData)` 恢复 |

红涨绿跌字面量 `#C93A3A/#1E8E5A/#d43030/#1a9e4b` 原样保留（回归测试反向断言其仍在 `renderKline` 内），未引入第四色相；网格/轴样式沿用现有 UI token。

### 2. 信息区口径

`klineInfoHTML(d, plan, i)`：`日期 · 开 · 高 · 低 · 收 · 涨跌 · 量(万) · <每个 overlay 名 值> · <每个 pane 系列名 值>`。

- 涨跌 = 相对**前一根**收盘；首根无前收盘 → `<span class="k-dim">涨跌 —</span>`。
- 任何缺失/非有限值一律 `—`（`klineNum` 与 `klineText` 双保险，不造 0、不继承）。
- 悬停：`chart.on('updateAxisPointer')` 读 `ev.axesInfo[0].value`，经 `klineInfoIndex` 映射；`globalout` 与初始态都回末根（末根 = 已完成数据，不含未来）。
- 实测（Playwright）：`axesInfo[0].value` 为 **number**（值 5），未走 category 字符串分支；初始/移出均为末根 `2026-05-08 · 开 23.86 · … · macdh_12_26_9 0.29`，移入变为 `2026-02-18 · …`。

### 3. 工具栏与缩放

- 5 按钮全部 44×44（浏览器实测逐枚 44/44），`aria-label` + 内联 SVG，无 emoji；375px 下 `.kline-tool span{display:none}` 只留图标，实测 display 为 none；工具栏在图表左侧（1280: 51 vs 103；375: 31 vs 83），无横向溢出（scrollWidth == clientWidth：1280/375 两档）。
- 放大/缩小：`klineZoom(chart, 0.7 / 1.4)` 只 `dispatchAction({type:'dataZoom',start,end})`，跨度上下限 2%/100%，触边时平移回窗口内；**不改数据、不重建实例、不影响 frameMetrics/静态报告**。实测 `#kt-zoom-in` → `[15,85]`。
- 重置：`#kt-reset` 恢复 `[0,100]` 且把量与因子面板同时打开（回到全量视图）。
- 滚轮：走 ECharts `dataZoom inside`，实测生效 `[5.69,96.60]`。**注意**：ECharts 只在指针位于某个网格坐标系内响应滚轮，格与格之间的空隙不响应——浏览器验证脚本把指针放在主图格内（`y + 0.18*height`）才复现，这是 ECharts 既有行为，不是本片缺陷。
- 量/因子开关：`klineApplyLayout` 重建**完整** `grid`/`xAxis`/`yAxis` 三组数组（隐藏格收为 `height:1`，索引不变，轴与系列索引沿旧顺序），随后按 `klineLegendSelected` 逐名 `dispatchAction legendSelect/legendUnSelect`；只改布局与图例可见性，不重建实例、不动数据。实测关闭量面板后 zrender 渲染元素 416 → 315（真实移除 101 个），再点回 416；`yAxis[1].show` false/true、`aria-pressed` 同步、因子面板同理（`yAxis[2]` 与 3 条 MACD + 均线 legend 一起 false）。
- 禁用态：重播接管期间 `setKlineToolsEnabled(false)` 置 `disabled` + `aria-disabled="true"` 并清空信息区；`klineSyncPressed` 在无图表或无因子时也会禁用 vol/fct。

### 4. 因子合同未变

`QREFactorLayout.plan()`、`chipStates()`、chip 三态、overlay 主图 / MACD 合并 pane / 其余独立 pane 的分组逻辑均未改；`klineGridSpec`/`klineAxisLabelIndex` 只是把同一批 pane 映射到右侧标尺与单一可见时间轴。

### 5. 测试

```bash
uv run pytest tests/test_saas_static_kline_tv.py -q
# 10 passed in 0.22s   （TDD 基线：7 failed / 3 passed）

uv run pytest tests/test_saas_chart_a_fix.py tests/test_saas_replay_boundaries.py \
  tests/test_gui_saas_pages.py tests/test_saas_night_mode.py \
  tests/test_factor_display_contract.py tests/test_saas_symbol_ux.py \
  tests/test_saas_help_copy.py -q
# 195 passed in 47.10s

uv run pytest tests/ -q      # 首跑
# 1 failed, 2926 passed, 24 skipped, 4 warnings in 239.89s
#   唯一失败：tests/test_gui_risk_report.py::TestRiskReportEndpoints::test_post_starts_job_and_poll

uv run pytest tests/ -q      # 同代码立即复跑
# 2927 passed, 24 skipped, 4 warnings in 171.68s   (exit 0)
```

新增用例覆盖：工具栏 DOM/结构、`#chart-kline` 唯一、44px 与 `:focus-visible`/`aria-pressed`/`data-tip`、右侧标尺与网格留白、无 CDN/无新依赖、因子合同（`plan()`/`chipStates()` 仍被调用）、重播进入时禁用工具栏、信息条与工具行为（node 侧断言）。

关于那一例失败：`test_post_starts_job_and_poll` 是 **既有 timing flake**，`05_PROGRESS.md`（2026-09-20、2026-10-26 两条）与 `04_TASK_HANDOFF.md`（1314、1615 行）已三次记录同一用例在全量并发下瞬时失败、单测复跑即绿。本次同样：单测 `1 passed in 0.41s`、整个 `tests/test_gui_risk_report.py` `24 passed in 1.69s`，且**同代码紧接着的全量复跑 2927 passed 全绿**（用例本身轮询后台线程最多 10s，全量并发高负载下会超时）。它与本片改动（只改 symbol 页 Jinja 模板）无调用关系。

### 6. 浏览器证据（`.tmp/static-kline-tv/`，gitignore）

`build.py` 从生产 `symbol.html` 抽取真实 `<style>` 与 693–1025 行 JS，配 vendored `lib/echarts.min.js` + `factor-layout.js` + `lab-theme.css`，合成 90 根日 K + `ema_5` overlay + MACD 三序列（合并为一个 pane）+ 2 笔订单；`check.py`（Playwright，Chromium 1248）在 1280×900 与 375×812 两档共 46 项断言 **全绿**，产物 `1280.png`(103KB) / `375.png`(52KB) / `result.json`：

- yAxis 三个 `position` 全 `right`；可见 `axisLabel` 只有 1 个（MACD 格）；grid 数 3。
- 信息条初值/移出 = 末根，移入改写；`axesInfo.value` 类型 `number`（两档一致）。
- 缩放 `[15,85]`、重置 `[0,100]`、滚轮两档均生效（375 为 `[6.78,97.69]`）。
- 量开关渲染元素 416→315→416（375 档 376→275→376），`yAxis`/legend/`aria-pressed` 三处状态同步；因子开关隐藏 `yAxis[2]` 与 4 条因子 legend。
- `#chart-kline` 唯一；无横向溢出；**两档零 console error / pageerror**。
- `chartW`：桌面 1126（grid left 16 / right 56），移动 261。

辅助脚本 `debug.py`（display list 时序、滚轮探测）、`min_wheel.py`（最小 ECharts 滚轮对照）留作证据，不必复跑。

### 7. 遗留与风险

- 重播界面本身未 TV 化（CR 允许本片暂不做）：工具栏在接管期间禁用；且 `initKlineReplay` 里既有的 `<p class="opt" id="kreplay-note">` 灰字备注属于 2026-10-04 切片遗留，本片未增删，但下一片若要彻底执行"无灰字"纪律需一并迁移到 `tip-trigger` + `data-tip`。
- 移动端 375 下绘图区约 189px（261 − 左右留白 16/56），布局不破但信息密度高；属可接受，未再压缩右侧标尺。
- 隐藏格收为 `height:1` 的路径（面板全关时时间轴上移）在同页合成数据里未触发，仅由单测静态断言覆盖，属未在浏览器实测的分支。
- 截图未经人眼核对（本 agent 无法读图），布局质量目前只有数值证据（grid 数 / 宽度 / 无溢出 / 44px / 元素增删计数）；建议由主 Agent 目视 `1280.png`、`375.png` 确认有因子时时间轴标签与 slider 不拥挤。
- 未 commit、未部署（部署由主 Agent 执行）；`09/04/05/11` 等长期记忆文件的同步留待主 Agent 在切片收口时统一更新。
