# CR-2026-10-27 K 线画线工具子集首片

## 背景

TradingView 化 todolist 中，“画线工具子集”是下一项。为控制风险，本 CR 只做最小可用首片：趋势线、水平线、删除/清除；不做 Fibonacci、射线、矩形、测量、多股对比或持久化同步。

## 目标

1. 在个股 K 线左侧工具栏新增画线入口：趋势线、水平线、删除画线；入口用既有 `.kline-tool` 样式与 `data-tip`，不新增灰色小字备注。
2. 画线只作用于静态 K 线图，不进入重播；重播接管期间禁用画线，退出重播后恢复静态图与画线状态。
3. 交互最小可用：
   - 趋势线：两次点击确定起点/终点，支持 Esc 或再次点击工具取消；
   - 水平线：一次点击确定价格；
   - 删除：删除最近一条或全部画线（实现时明确其一，本片建议“清除全部”）。
4. 画线数据使用真实 K 线坐标（日期 + 价格），不得凭空造点；缩放到只可见窗口时不得泄露未来数据。
5. Night Mode、红涨绿跌、因子 display 合同、现有工具栏/重播行为不回归。

## 边界

- 只改 `src/quant_research_engine/gui/saas/templates/symbol.html` 及必要测试。
- 不改 `replay.js`、`job.html`、游戏、worker、引擎、schema、因子注册表。
- 不新增依赖、不引 CDN、不引入 Lightweight Charts。
- 不跑回测、不部署 ECS（主 Agent 复核后部署）、未 commit/push。

## 测试与验收

- TDD：先 RED 后 GREEN。
- 至少覆盖：
  - 工具栏存在趋势线/水平线/清除入口，样式与 aria/data-tip 合规；
  - 画线函数把像素坐标转换为真实日期/价格，缺失值降级不造点；
  - 重播进入时禁用画线，退出后恢复；
  - 现有 K 线 TV 化、重播、因子合同测试不回归。
- 命令：
```bash
uv run pytest tests/test_saas_static_kline_tv.py tests/test_saas_replay_tv.py tests/test_saas_replay_boundaries.py tests/test_gui_saas_pages.py -q
uv run pytest tests/ -q
```

## 发布

- 测试通过后由主 Agent 部署 ECS，仅同步实际改动文件并重启 qre-saas；用户验收前不 commit/push。

## 实现记录（2026-10-27，TDD：先 RED 7 例后 GREEN）

### 改动文件

- `src/quant_research_engine/gui/saas/templates/symbol.html`（唯一产品文件）：
  - 工具栏新增 3 个 `.kline-tool` 按钮：`kt-trend`（趋势线）、`kt-horizontal`（水平线）、
    `kt-clear`（清除画线），内联 SVG + `aria-label` + `data-tip`（走 LabUI.helpTips），
    无新增灰字备注；`KLINE_TOOL_KINDS` 纳入 3 个 kind（重播禁用/启用自动覆盖）。
  - 画线状态 `klineDrawState`（mode/pending/lines）与 `klineToolState.baseSeries`
    （基础序列，供 replaceMerge 重建）。
  - 纯函数（可测）：
    - `klinePixelToPoint(chart, pixel, dates)`：`convertFromPixel({gridIndex:0})`
      → 类别轴取整到最近一根真实日期 + 价格；越界/缺失/抛错一律 null（不造点）。
    - `klineDrawingSeries(lines, dates)`：水平线跨真实首末日期、趋势线两个真实点，
      缺字段跳过；颜色复用既有因子 token `#6750A4`/`#8B7FBE`（无第四色相）。
  - 交互：`klineDrawToggleMode`（再点一次取消）、`klineDrawHandleClick`（zr 点击取点；
    水平线一次成线、趋势线两次成线、无法转换时保持模式不造点）、`klineDrawClear`
    （清空全部并回基础序列）、`klineDrawOnKeydown`（Esc 取消）、`klineDrawApply`
    （基础序列+画线 replaceMerge，不动数据与布局）。
  - 重播边界：`setKlineToolsEnabled(false)` 取消画线模式与未落点；画线按钮随
    KLINE_TOOL_KINDS 禁用；重播 option 由 mountKlineReplay 独立构建，画线不进入
    重播帧；退出重播 renderKline 重建后按状态恢复画线。
  - 模式提示写在既有 `#kline-ohlc` 信息区（klineSetInfo），不新增元素。
- 测试：
  - `tests/test_saas_static_kline_tv.py`：harness 增加 `convertFromPixel`/`getZr`
    （zrHandlers 顶层单例）与 `refreshButton` 无关的 `zrHandlers` 暴露；新增
    `TestSourceContract` 3 例（工具按钮 DOM/helper 声明/颜色 token）与
    `TestKlineDrawing` 3 例（像素转换含全部降级路径、series 配置、点击流：
    水平线/趋势线/Esc/清除/降级不造点）。
  - `tests/test_saas_replay_tv.py`：`_EXIT_SCENARIO` 补画线断言（进入重播取消模式、
    三按钮禁用、退出恢复、重播帧无画线序列）。

### 验证结果

- RED：7 个新测试先失败（无按钮/无 helper/无交互/重播不禁用）。
- `uv run pytest tests/test_saas_static_kline_tv.py tests/test_saas_replay_tv.py tests/test_saas_replay_boundaries.py tests/test_gui_saas_pages.py -q`
  → 131 passed。
- `uv run pytest tests/ -q` → 见交付说明（全量结果）。

### 已知限制 / 遗留

- 画线不持久化（刷新/重渲染后按当次会话状态恢复；chip 切换与退出重播会恢复，
  页面刷新丢失）——CR 明确不做持久化。
- 未做缩放窗口联动重算：画线按日期+价格存储，dataZoom 缩放后 ECharts 自动跟随
  类别轴渲染，不会泄露未来数据（数据本就在全量静态序列内）。
- 未跑浏览器实机；建议主 Agent 部署后在 1280/375 目视确认趋势线两点拖拽观感
  与 Night Mode 下画线可读性。
- 测试抽取范围（`_render_kline_source()`）截断画线函数定义，`bindKlineTools` 内
  对画线函数调用加了 `typeof` 守卫；真实页面为同一脚本全量求值，行为不受影响。
