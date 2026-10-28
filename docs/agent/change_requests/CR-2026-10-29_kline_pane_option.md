# CR-2026-10-29 K 线 pane option 共享映射层（T1）

状态：已实施，未 commit/push
关联：`TV_ROUND2_TASKS_2026-10-29.md` §7 T1、`TV_ROUND2_ANSWER_2026-10-29.md`

## 1. 缘起

逆向侧把「共享 option 映射层」从原 P2 提到 **P0**，理由是我方自己写了
"同类问题已复发三次"，而 MACD 坐标轴问题极可能长在这一层。

## 2. 根因

`symbol.html::renderKline`、`symbol.html::mountKlineReplay`、`game.html::renderChart`
**三处各写一份 pane 索引算术**（`2 + i` / `paneIndex + 2` / `model.panes[index - 2]`）。
ECharts 的 `yAxisIndex` 是**全局 yAxis 数组下标**（不是 grid 内局部下标），
一旦某个 pane 多插轴就整体错位——用户看到的"各自坐标系"正是这类错位的表现。

TV_ROUND2 §3 判据（真实浏览器 + 生产 job 58 真实产物）证实本次是**视觉错觉**
（三 series 同 `yAxisIndex=2`、同 `gridIndex=2`、同值反算像素 476.4/476.4/476.4），
但错位机制成立，且三份副本意味着下次还会犯。

## 3. 修复

`static/factor-layout.js` 新增单一出口，索引一律内部生成并带不变式校验：

| 函数 | 职责 |
|---|---|
| `paneGrids(paneCount, opts)` | pane 布局（从 symbol.html 的 `klineGridSpec` 原样抽出） |
| `axisLabelIndex(paneCount, opts)` | 时间轴挂哪个 grid |
| `paneYAxes(panes, spec)` | pane 的 yAxis 声明（`gridIndex` 内部生成） |
| `paneSeries(panes, spec)` | pane 的 series 声明（索引内部生成；支持 ECharts 与 `style:'replay'` 两种规格） |
| `panesToOption(panes, spec)` | 主入口，返回 `{grid, xAxis, yAxis, series, paneBase}` |
| `paneGridIndex(count, base)` | 只要下标的场景 |
| `assertPaneInvariant(...)` | `yAxis.length === grid.length` 且逐 pane 一一对应，**不符即抛错** |

三处业务页全部改调它；`replay.js` 本身保持位置式映射（`s.grid` 同时作
x/yAxisIndex），其规格由 symbol 以 `style:'replay'` 生成。
`game.html` 原先完全自包含，本轮**新引入** `factor-layout.js`。

### 3.1 两个实现细节

1. **`hist` 判定改为 `s.hist || s.type === 'bar'`**：`plan()` 给的 hist 同时带
   `hist:true` 和 `type:'bar'`，而 game 的 `chartModel()` 只给 `type:'bar'`——
   原判定会把 game 的 MACD 柱画成线。
2. **game 的 HIST 配色保留原样**（固定 `#8B7FBE`）：本轮只做结构统一，
   不改游戏视觉；如后续要统一成红绿，单独提 CR。

## 4. 测试

新建 `tests/test_kline_pane_option.py` 11 例：

- `TestThreeCallSites`：三处都调、且三处再无手写 pane 索引
- `TestSharedOptionMapping`：symbol 与 game 的 pane option 逐字节相同；
  replay 规格的 `grid` 与 ECharts 规格的 `yAxisIndex` 一致；MACD 三 series 同轴；
  HIST 是 bar、DIF/DEA 是 line；不变式被破坏必须抛错
- `TestPaneGridsAgainstPython`：`paneGrids` / `axisLabelIndex` 与 Python 等价实现一致
- `TestSourceContract`：导出齐全；四文件不得再出现手写 pane 索引

**RED 验证**：把 `paneSeries` 的 `gi` 改成 `base + i + 1` →
`test_macd_three_series_share_one_axis` 立即红。

### 4.1 连带修的三处测试脚手架（都是"桩窄于依赖"）

1. `test_saas_static_kline_tv.py`：`QREFactorLayout` 桩只有 `plan()`/`COLORS`，
   改为在 harness 定义处注入**真实 factor-layout.js 原始源码**（不是 json.dumps
   的字符串字面量——那不会执行，第一版就栽在这）。
2. `test_saas_chart_a_fix.py`：同样改为注入真实源码。
3. `test_trading_game_web.py`：原断言 `factor-layout.js not in template` 与新设计
   冲突，改为断言"不得用共享 chip/plan UI（游戏有自己的因子选择），但必须走
   panesToOption"。

## 5. 验证

- `tests/test_kline_pane_option.py` 11 passed
- 全量 `uv run pytest tests/ -q -p no:randomly` → **3083 passed, 24 skipped**
- §3 判据脚本重构后重跑，输出与重构前**逐字节一致**（零回归）
- 真实浏览器（`.tmp/perf-browser/t1_verify.py`，生产 job 58 真实产物 000014.SZ）：
  symbol 静态图与重播两条路径均 `yAxis==grid==3`、`macdSameAxis=true`

## 6. 遗留

`game.html` 未跑真实浏览器（本地起的游戏 Flask 服务开局 500，`FakeStore` 连库问题，
属测试脚手架缺陷）。其 pane 映射已由单测覆盖，但**真实浏览器验证待补**——
下次跑游戏端到端时一并补上。
