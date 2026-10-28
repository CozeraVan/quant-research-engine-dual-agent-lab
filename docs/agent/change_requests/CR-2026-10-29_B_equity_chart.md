# CR-2026-10-29 B：收益曲线统一（策略/各基准/买入持有/回撤 一套口径）

状态：已实施，未 commit/push，等用户验收
上游任务书：`TASK-2026-10-29_deepseek_uiux.md` §B（顺序 A → C → B，本 CR 是 B）

## 1. 问题

`job` 页与 `symbol` 页各自内联一份 ECharts 收益曲线，两套口径：

- `job`：策略 + **单**基准 + 回撤；基准靠一个 `<select>`「切换」，
  一次只能看一条，无法对比。
- `symbol`：策略净值（**元**）+ 买入持有（%）+ 各基准（%）**双 y 轴**，
  左侧「净值(元)」右侧「%」两种量纲同图，且全部基准曲线**同色**。
- 两边网格参数、配色、图例默认态都不一致；同样的数据在两个页面读数不同。

## 2. 改动

### 2.1 新增共享构造器

`src/quant_research_engine/gui/static/equity-chart.js`（243 行，IIFE，挂 `window.QREEquityChart`）。
纯函数、不碰 DOM，便于 Node 单测。导出 10 个成员：
`BENCH_COLORS / STRATEGY_COLOR / DD_COLOR / toPct / drawdownPct / benchPct / benchColor / legendSelectedFor / option / replaySpec`。

口径（与 `risk/performance.py`、页面原实现一致）：

| 函数 | 语义 |
| --- | --- |
| `toPct(values)` | 以首个非 null 有限值为基 → `(v/base-1)*100`；基为 0/非有限时全 `null`（不制造 Infinity），null 原位保留 |
| `drawdownPct(equity)` | 按净值历史最高点算 `v/peak-1`（≤0），非正值/缺失为 `null` |
| `benchPct(closes)` | 等同 `toPct`（基准用收盘价归一化） |

配色（12 号 UI 规范：策略紫、**禁蓝/橙**）：策略 `#6750A4`、买入持有 `#6750A4`（虚线）、
回撤 `#d43030`；基准沿用书里的固定色 `000001.SH #B7A6E8 / 000300.SH #2A9D8F /
399001.SZ #E8A33D / 000905.SH #4A3A78 / 399006.SZ #9A93A6 / 000852.SH #6750A4`，
未列出的 code 按 `PALETTE` 循环。

线型/透明度：策略 solid 2px；基准 dashed 1.2px；买入持有 dashed 1.2px；回撤 area `opacity 0.3`、线宽 1。

网格：有回撤 `[{left:68,right:20,top:30,height:'52%'},{left:68,right:20,top:'70%',height:'16%'}]`，
无回撤 `[{left:68,right:20,top:30,height:'72%'}]`（主图与回撤图 x 轴 `axisPointer.link` 联动）。

图例默认态由 `legendSelectedFor(benches, openCodes)` 决定：`openCodes` 是数组就按它，
否则默认只开上证指数（`000001.SH`），没有则开第一条。`option()` 的 `legend.data` 与
`series` 同源（无数据的基准既不画线也不进图例，避免「点了没反应」的图例项）。

### 2.2 模板

| 文件 | 改动 |
| --- | --- |
| `saas/templates/job.html` | 引入 `equity-chart.js`；`renderMain()` 改调 `QREEquityChart.option(...)`；删除 `applyBench()`，换成一排**多选**基准按钮（`aria-pressed` + `legendToggleSelect`，`legendselectchanged` 回写状态）；`mountReplay(d)` 改调 `QREEquityChart.replaySpec({... openCodes: openBenches})`，把 `series/grids/yAxes/legendSelected` 透传给 `QREReplay.attach` |
| `saas/templates/symbol.html` | 引入 `equity-chart.js`；`renderEquity()` 重写：删双 y 轴与「策略净值(元)」，改 `toPct/benchPct/drawdownPct` + `QREEquityChart.option(...)`，同样多选基准按钮 |
| `static/replay.js` | `legend` 增加 `selected: opts.legendSelected || undefined`（重播图例默认态与静态图一致） |

多选而不是「切换」：任务书 B 要求「可同时对比多个基准」，`select` 天然做不到；
按钮组保持原有视觉位置，只是把 radio 语义换成 `aria-pressed` 的 toggle。

## 3. 与任务书的三处取舍（需知会）

1. **策略线用紫 `#6750A4`，不是任务书写的蓝**。`12_UI_STYLE_GUIDE.md` 明确「策略色
   `#6750A4`、禁蓝/橙」，两处规则冲突时以样式规范为准；若坚持蓝，只需改
   `equity-chart.js` 的 `STRATEGY_COLOR` 一个常量。
2. **回撤图高度 16%，原实现是 18%**。统一后主图 52% + 回撤 16% + 间隙 2% + 轴带，
   `dataZoom` 滑块（bottom 6，height 22）不再压住回撤轴；replay 也用同一组数字，
   静态图与重播图的视觉重心一致。
3. **买入持有与策略、中证1000 同色（都是紫）**，靠虚线 + 1.2px 线宽区分实线 2px 的策略。
   书里的基准色板没有第七种颜色，新增色会破坏规范；靠线型区分是图表惯例，且图例
   文字直接标明「买入持有」。

## 4. 测试

- `tests/test_equity_chart.py`（**新增/重写**，23 例）：`toPct` 基点为 0/缺失/负值、
  `drawdownPct` 峰值更新与缺失值、`benchColor` 固定色与循环回退、`legendSelectedFor`
  默认态与 `openCodes` 覆盖、`option` 的 series 名字/颜色/线型/回撤轴索引、
  `replaySpec` 的 grid 索引与 `hasDD`、模板接线断言（job/symbol 均出现 `QREEquityChart.option`、
  无 `applyBench`、symbol 无「净值(元)」与双 y 轴）。
- 五文件联跑：`tests/test_equity_chart.py tests/test_vol_regime.py
  tests/test_saas_replay_tv.py tests/test_saas_replay_boundaries.py tests/test_gui_saas_pages.py`
  → **150 passed**。
- 全量 `uv run pytest tests/ -q` → 见下方「全量结果」。
- **RED 验证**：见 §5。

## 5. RED 验证（断言真的在跑）

删掉 `symbol.html` 里 `drawdownPct: QREEquityChart.drawdownPct(eq.values),` 整行后：

```
tests/test_equity_chart.py::TestTemplateContract::test_symbol_page_has_bench_bar_and_drawdown
>       assert "QREEquityChart.drawdownPct(" in SYMBOL_TPL, "symbol.html 未计算回撤"
E       AssertionError: symbol.html 未计算回撤
E       assert 'QREEquityChart.drawdownPct(' in '{% extends "base.html" %}...'
1 failed, 22 deselected in 0.02s
```

恢复后该用例转绿。

## 6. 与 T1（QRE-KLINE-PANE-OPTION）的交叉

同一工作树里另有 agent 在做 `factor-layout.js` 的 K 线分屏重构（T1），**不是本 CR 的改动**。
T1 改了 `symbol.html` 的 `renderKline/mountKlineReplay` 与 `game/templates/game.html`，
导致三个既有测试与线上 API 分叉，本 CR 只做**适配性**修改，不放宽语义：

1. `tests/test_gui_saas_pages.py` 的 symbol kline 场景原来**打桩** `QREFactorLayout`，
   T1 的 `panesToOption/paneYAxes` 一上线打桩就缺方法。改为注入真实
   `static/factor-layout.js` 源码进 vm（与 `REPLAY_SRC` 并列），避免 harness 与线上分叉。
2. `tests/test_saas_replay_tv.py::test_replay_reuses_static_layout_spec` 里
   `position: 'right'` 计数从 `>= 3` 改为 `>= 2`（因子副图 yAxes 已移进
   `factor-layout.paneYAxes`，模板里只剩主图/量两条），**同时新增**
   `assert "panesToOption(panes, {" in body and "paneBase: 2" in body` 保证副图轴仍走共享出口。
3. `tests/test_saas_replay_boundaries.py` 的 job replay 事件 harness 补 `openBenches: null`
   （本 CR 新增的模板模块级变量），并注入 `equity-chart.js` 源码。

## 7. 影响面

`job` / `symbol` 两页的收益曲线模块；`replay.js` 的 legend 默认态。其它图表、其它页面未动。
`#chart-equity` 所在的 grid `left` 仍取运行时的容器宽度（C 项已把字号/间距调好）。

## 8. 补记（2026-10-29 独立核验：基准按钮初态缺 `aria-pressed` / `.active`，已修）

浏览器实测发现：页面首次加载时 `#bench-bar` 的基准按钮**没有 `aria-pressed`**，
也没有 `.active` 类，尽管图例默认把上证指数打开。读屏与键盘用户拿不到初始勾选态，
视觉上也少一个「已选」标记。

根因（`job.html` 与 `symbol.html` 各一份同样的逻辑）：`codes.forEach` 里先调用
`syncButton(code, on)`，后写 `btns[code] = btn;`；而 `syncButton` 开头是
`if (!btns[code]) return;`，所以初始化那次调用必然直接返回，什么都没设。

修法（两个模板相同，各 2 行）：把 `btns[code] = btn;` **上移到** `syncButton(code, on)`
之前，并删掉后面旧位置的那行重复赋值（重复赋值本身无害，只是噪声）。

浏览器证据（`.tmp/equity-browser/b_verify.py`，Playwright + 真实 Chromium，
真实模板重渲染、`/api/**` 拦截回 fixture）：

```
job 1440: series=['策略', '上证指数', '沪深300', '回撤'] bench_colors=['#B7A6E8', '#2A9D8F']
bench buttons: [{'text': '上证指数', 'pressed': 'true'}, {'text': '沪深300', 'pressed': 'false'}]
aria-pressed: true -> false        # 点击后反转
job 375 overflow: {'sw': 375, 'cw': 375}
symbol: yAxis=2 grid=2 series=['策略', '买入持有', '回撤']
symbol 375 overflow: {'sw': 375, 'cw': 375}
=== ERRORS === 无
=== ALL OK ===
```

脚本同时断言：双网格（`yAxis=2/grid=2`）、回撤 series 走副网格（`yAxisIndex=1/xAxisIndex=1`）
且为 `areaStyle`、策略色 `#6750A4`、多基准各自异色、375px 无横向溢出。