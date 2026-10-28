# CR-2026-10-28 K 线双引擎互斥（切 TradingView 视图叠加）

状态：已实施 + 已部署 ECS（MainPID 542952），未 commit/push（等用户验收）
关联：`CR-2026-10-28_lwc_kline_pilot.md`（B 路阶段 2 引入双引擎开关）、`12_UI_STYLE_GUIDE.md` §3.16、`23_KLINE_IMPLEMENTATION.md`

## 1. 现象（用户验收时发现）

个股详情里点「试用 TradingView 图表」切到 LWC 视图后，新图**叠在旧 ECharts 图之上**。

## 2. 根因

`#chart-kline` 是同一个容器，ECharts 与 LWC 各自只清自己创建的 DOM：

- `renderKlineLwc()` 只调 `lwcDispose()`（只摘 LWC 自己的节点），**从不清 ECharts 实例**；
- `LWC.createChart(el)` 往同一容器再插一套 canvas → 两个图并存。
- 反向（lwc → echarts）当时没暴露，只是因为引擎开关处理器里手工补了一次 `lwcDispose()`；
  `renderKline` 本身仍然只 `dispose` echarts，其它重渲染路径一律会残留 LWC。

真实浏览器实测（Chromium + 生产同款 echarts/LWC，`renderEcharts()` → `renderLwc()`）：

| 版本 | 容器子元素 | scrollHeight |
| --- | --- | --- |
| 修复前 | **2**（echarts DIV + LWC DIV） | **800**（高度翻倍） |
| 修复后 | 1 | 400 |

反复切换 8 轮（lwc/echarts 交替）修复后恒为 1 个子元素、零 pageerror。

## 3. 修复

新增 `klineDisposeEngines()`（`symbol.html`，紧邻 `lwcDispose`）：

- `echarts.getInstanceByDom(el)` → `dispose()`（清 ECharts 实例）
- `while (el.firstChild) el.removeChild(el.firstChild)`（兜底清残留 canvas；该容器模板内即为空 div，专供 K 线图）
- `symbolKlineChart = null`
- 再调 `lwcDispose()`（清 LWC 实例）

三个调用点全部改走它：

1. `renderKlineLwc()`（原 `lwcDispose()`）——**本次 bug 的直接根因**
2. `renderKline()`（原只 dispose echarts）
3. 引擎开关处理器（原 `lwcDispose()`）

重播路径不变：`mountKlineReplay` 恒为 echarts，replay.js 自身已 `getInstanceByDom` + `dispose`；
进入/退出重播前的 `lwcDispose()` 保留，退出后重建走 `renderKlineDispatch` → 现在也会双清。

## 4. 测试

新增 `tests/test_lwc_kline_adapter.py::TestKlineEngineExclusive`：

- `test_dispose_tears_down_both_engines`：Node vm 跑真实 `klineDisposeEngines` 源码，
  断言 ECharts 实例被 dispose、容器被清空、LWC 实例被 remove、引用清掉。
  **已做 RED 验证**：把函数体改回"只清 LWC"该测试立即失败。
- `test_both_render_paths_and_switch_use_exclusive_dispose`：源码合同，两个渲染入口与
  引擎开关都必须出现 `klineDisposeEngines()`，且引擎开关里不得再出现裸 `lwcDispose();`。

四个既有 harness 的源码抽取区同步扩展（`klineDisposeEngines` 定义在 `klineResizeBound`
之前，原抽取区不含它，会 ReferenceError）：`test_saas_static_kline_tv.py`、
`test_saas_replay_tv.py`、`test_saas_chart_a_fix.py`、`test_gui_saas_pages.py`；
并为 `makeEl`/`el` 桩补 `firstChild` / `removeChild`（DOM 保真）。

全量 `uv run pytest tests/ -q` → `3011 passed, 24 skipped`。

## 5. 过程教训

`_DRAW_BLOCK` 类模块级常量在构造 page 时就把 `%SOURCE%` 替换掉了，导致"再替换一次"静默失效——
RED 检查第一版因此测了个假绿灯。**教训：RED 检查必须确认替换真的发生了**（打印替换前后长度）。

浏览器级证据：`.tmp/engine-excl/`（page.html + run.py + shot-old.png + shot-engine-excl.png）。
