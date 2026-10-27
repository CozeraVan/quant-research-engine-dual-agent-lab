# CR-2026-10-27 重播遗留清理：tooltip 口径、高度与 375 信息区

## 背景

K 线重播 TV 化首片已完成，但遗留三类体验问题：

1. `replay.js` 顶部 tooltip 统一 `valueFormatter` 给所有值加 `%`，导致价格/成交量/因子轴出现 `19.70%` 这类错误单位。
2. 重播容器高度与静态 K 线高度公式存在重复/漂移风险。
3. 375px 下顶部 OHLC/因子信息区仍是 `nowrap + ellipsis`，只看到日期，看不到完整 OHLC/因子值。

本 CR 只清理这三项遗留，不引入画线工具、指标设置弹层或第二套 K 线模块。

## 目标

1. 重播 tooltip 按序列类型显示正确单位：
   - K 线显示 OHLC 原始数值；
   - 成交量显示万手；
   - 因子/收益曲线按原值或百分比，按序列声明，不统一加 `%`。
2. `job.html` 收益曲线重播保持原有百分比口径，不回归。
3. 重播与静态 K 线高度公式统一为同一 helper，避免两处漂移。
4. 375px 信息区不截断关键 OHLC/因子值；不允许页面横向溢出。
5. Night Mode、红涨绿跌、因子 display 合同、防未来数据规则不变。

## 边界

- 只改 `src/quant_research_engine/gui/static/replay.js`、`src/quant_research_engine/gui/saas/templates/symbol.html` 及必要测试。
- 不改 `job.html` 的现有重播行为；不改游戏、worker、引擎、schema、因子注册表。
- 不新增依赖、不引 CDN、不引入 Lightweight Charts。
- 不跑回测、不部署 ECS（主 Agent 复核后部署）、未 commit/push。

## 实施要求

### 1. tooltip 口径

- `replay.js` 将“统一加 %”改为可选/按序列声明：
  - 默认路径不传时不改变 job 收益曲线行为；
  - K 线重播传 `tooltipPercent: false` 或等价开关；
  - 每个 series 可带 `tooltipValueFormatter` 或 `tooltip.unit`，由 `renderFrame()` 透传。
- candlestick 的 tooltip value 可能是数组，必须兼容，不能出现 `NaN%`。
- 成交量、因子、价格轴不得统一加 `%`。

### 2. 高度统一

- 提取 `klineHeightForPanes(paneCount)` 或等价 helper；静态 `renderKline()` 与重播 `mountKlineReplay()` 共用。
- 默认高度公式与当前静态一致：无副图 460px，有副图 `420 + panes*160`。

### 3. 375 信息区

- 窄屏允许 `.kline-ohlc` 换行或移除 ellipsis，保证首屏能看到日期与 OHLC；不得横向溢出。
- 不新增灰色小字备注。

## 测试与验收

- TDD：先补失败测试，再实现。
- 新增/更新测试至少覆盖：
  - 重播 tooltip 不再对价格/量/因子统一加 `%`；
  - candlestick 数组值格式化不产生 `NaN%`；
  - job 默认路径仍加 `%`；
  - 静态/重播高度 helper 一致；
  - 375 CSS 不截断且无横向溢出相关静态断言。
- 命令：
```bash
uv run pytest tests/test_saas_replay_tv.py tests/test_saas_replay_boundaries.py tests/test_saas_static_kline_tv.py tests/test_gui_saas_pages.py -q
uv run pytest tests/ -q
```

## 发布

- 测试通过后由主 Agent 部署 ECS，仅同步实际改动文件并重启 qre-saas；用户验收前不 commit/push。

## 实现记录（2026-10-27，TDD：先 RED 6 例后 GREEN）

### 改动文件

- `src/quant_research_engine/gui/static/replay.js`：
  - 新增 `formatTooltipValue(v, unit)`（入 `QREReplay.core`）：数组（candlestick
    [开,收,低,高]）显示「开/收/低/高」标签化 OHLC，绝不产生 `NaN%`；标量按 unit
    声明，默认原值不加单位；`unit==='percent'` 才加 %。
  - 新增 `klineHeightForPanes(paneCount)`（入 `QREReplay.core` 并暴露
    `QREReplay.klineHeightForPanes`）：无副图 460px，有副图 420 + panes*160。
  - `renderFrame()` tooltip 增加 `opts.tooltipPercent` 开关：不传（默认）时
    valueFormatter 与旧版逐字节一致（job 收益曲线 `%` 口径不变）；传 `false` 时
    走原值口径，`opts.tooltipUnit` 可给标量加单位。
- `src/quant_research_engine/gui/saas/templates/symbol.html`：
  - `renderKline()` 与 `mountKlineReplay()` 高度统一为
    `QREReplay.klineHeightForPanes(panes.length) + 'px'`，删除两处内联公式。
  - 重播 attach 传 `tooltipPercent: false`；成交量 series 经 `extra` 透传
    series 级 `tooltip.valueFormatter`（万手，echarts 5.6.1 axis-trigger 支持
    series 级优先于全局）；K 线数组走全局 OHLC 格式化；因子按原值。
  - 375/640 断点新增 `.kline-ohlc{white-space:normal;overflow:visible;text-overflow:clip}`，
    窄屏换行显示完整 OHLC/因子值，不再 ellipsis 截断；无新增灰色小字备注。
- 测试（必要 harness 适配，均为真实页面依赖）：
  - `tests/test_saas_replay_tv.py`：新增 `TestTooltipUnitCleanup` 5 例（tooltip
    无 %、candlestick 无 NaN%、成交量万手、tooltipPercent 开关、高度 helper 共用
    + 公式场景），job 默认场景补 tooltip 断言，exit 场景补高度断言。
  - `tests/test_saas_replay_boundaries.py`：symbol 事件场景改加载真实 replay.js
    （helper 不复制公式），补 `tooltipPercent:false`、460px、万手断言。
  - `tests/test_saas_static_kline_tv.py`：harness 预加载真实 replay.js；新增
    `test_narrow_info_bar_no_truncation`（media 块花括号配平抽取，断言换行/
    无 ellipsis/min-width:0 防溢出/无 muted 灰字）。
  - `tests/test_gui_saas_pages.py`：`_run_symbol_script_js` 暴露 `REPLAY_SRC`，
    两个跑真实 renderKline 的场景预加载 replay.js。

### 验证结果

- RED：新增 6 例先失败（tooltip 19.70% / 数组 NaN% / 无 helper / 无断点覆盖）。
- `uv run pytest tests/test_saas_replay_tv.py tests/test_saas_replay_boundaries.py tests/test_saas_static_kline_tv.py tests/test_gui_saas_pages.py -q`
  → 120 passed。
- `uv run pytest tests/ -q` → 见交付说明（全量结果）。

### 未覆盖/风险

- 浏览器实机（1280/375）未跑；tooltip series 级 valueFormatter 依赖 echarts
  5.6.1 的 axis-trigger 行为（已核对 `echarts.min.js` 源码 `TV([p],i).get("valueFormatter")`），
  建议主 Agent 部署后目视确认成交量 tooltip「万」与 K 线 OHLC 标签。
- 上一片遗留的 `#kreplay-note`（`.opt` 灰字备注）不在本 CR 范围，未处理。
