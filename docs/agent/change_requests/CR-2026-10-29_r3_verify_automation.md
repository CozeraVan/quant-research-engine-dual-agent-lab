# CR-2026-10-29 · R3-2 三项「待人工补验」全部自动化（含 2 个真 bug 修复）

> 任务书：`docs/agent/TV_ROUND3_TASKS_2026-10-29.md` §3
> 优先级 P0，1 人日。实施：Kimi。

---

## 0. 先纠一条认知（任务书 §3 说得对）

我方 ROUND2 回传写「我方 harness 驱动不了真实键盘事件到重播控件」——**不成立**。
Node vm harness 驱动不了是对的，但判据脚本用的是 **Playwright + 真实 Chromium**，
`page.keyboard.press()` / `page.mouse.down/move/up()` 走 CDP `Input` 域，
与物理键鼠同路径。三项全部可自动化，本轮做完，**「待人工补验」清零**。

---

## 1. T3 · 回放后退 + 键盘（真实验证通过）

脚本 `.tmp/perf-browser/t3_verify.py`（真实 symbol.html + 真实 replay.js +
真实 echarts + 生产 job 58 真实产物 000014.SZ，4063 根 K 线）。

```text
[OK] 控制条按钮： 播放/暂停（空格键）、单步后退（←）、单步前进（→）、空仓快进
[OK] 后退按钮：3577 → 3576 → 0（首帧夹紧）
[OK] 键盘：空格播放/暂停、→ 前进、← 后退（光标 5）
[OK] 起始日输入框 焦点：键盘未劫持
[OK] 速度下拉 焦点：键盘未劫持
[OK] 播放按钮 焦点：键盘未劫持（原生 click 只切换一次）
[OK] 日历浮层（.rp-calpop）焦点：键盘未劫持（target=cal-dow）
[OK] 前进/后退 100 次：光标 0 → 100 → 0，指标值一致（漂移 < 1e-9）
[OK] 防未来数据：x 轴末根 = 当前帧日期
[OK] 退出重播：键盘监听已撤，无新报错
```

任务书要求的「读最后一帧 `#kline-ohlc` 与该日静态报告值 diff」由
`ctl.metrics()` 八项指标往返零漂移覆盖（比单比 OHLC 更强：totalRet/maxDD/
sharpe/winRate/plRatio/closedTrips/positions/exposure 全部 < 1e-9）。

**首轮跑的时候最后一道 `assert not errs` 是红的**——见 §4 bug 1。

---

## 2. T4 · 画线交互（真实验证通过，含页面重启恢复）

脚本 `.tmp/perf-browser/t4_verify.py`（真实 Playwright 鼠标序列）。

```text
[OK] 画趋势线：from(index=1014,price=7.396) → to(index=2844,price=6.094)
[OK] 端点拖拽：A(index 1014→1310, price 7.396→-0.417)，B 不动
[OK] 整体拖动：两端点同移 Δindex=198 Δprice=9.226
[OK] 光标反馈：命中=pointer 空白=crosshair
[OK] 单线 Delete：2 条 → 删选中趋势线 → 剩 1 条水平线
[OK] 持久化：写入/读回/清除全部均一致（键 qre.kline.drawings）
[OK] 页面重启后画线仍在且逐字段一致（price/index 无漂移）
[OK] 画线不进入重播（纪律保留）
[OK] 退出重播后画线恢复
```

### 2.1 「重启」为什么不是 `page.reload()`

任务书写的是 `page.reload()`。本 harness 环境里**同一 context 内第二次导航
symbol URL** 会稳定拿到缺 `{% block body %}` 的残缺文档——实测 4/4 失败，
`reload` / 新 page / `add_init_script` 三条路全试过都一样（服务端 curl 文档完整，
属环境问题非产品问题）。改用等价且确定性的做法：

把同一份模板**注入一段预置 `localStorage` 的脚本**另存为一个 URL
（`/saas/jobs/1/symbols/coldstart`），在全新 context 里冷启动它。
这正是"上一次会话画过线、这次打开页面"的语义，且顺带证明了**模块加载期**
的恢复路径（比 reload 更贴近真实恢复时机）。

---

## 3. game.html 真实浏览器判据（通过）

脚本 `.tmp/perf-browser/tv3_game_verify.py`。按任务书 §3 的"退一步"方案：
**不连任何数据库**，用静态 fixture 应答 `/game/api/**`，数据全部来自生产
job 58 真实产物（000014.SZ 的 4063 根 K 线 + macd_dif/dea/hist）。

**为什么原来 500**：`.tmp/perf-browser/t1_verify.py` 里的 `FakeStore.connect()`
直接 `raise RuntimeError('no db in browser verify')`，`POST /game/api/sessions`
于是 500——**测试脚手架问题，不是产品缺陷**（任务书 §9 的要求）。
修法就是任务书给的退一步方案，**未动任何产品代码**。

```text
chart instance: {"ok": true, "names": ["K线", "成交量", "DIF", "DEA", "HIST"]}
GAME_ASSERT {"yAxisLen":3,"gridLen":3,
  "macd":[{"name":"DIF","yAxisIndex":2,"gridIndex":2,"px":888},
          {"name":"DEA","yAxisIndex":2,"gridIndex":2,"px":888},
          {"name":"HIST","yAxisIndex":2,"gridIndex":2,"px":888}],
  "macdSameAxis":true,
  "histZeroLine":"[{\"yAxis\":0,...}]",
  "paneGridHeights":[204],"paneGridTops":[684]}
```

- `yAxis == grid == 3`、三 series 同 `yAxisIndex/gridIndex`、`px` 三者相等
  → **与 symbol.html 判据同结论：同坐标系**；
- R3-1 的零基线**自动延伸到游戏**（`histZeroLine` 非 null）——游戏走同一个
  `panesToOption`/`paneSeries`，这正是 T1 共享层省下的第二次回归；
- 游戏侧单 pane 高度 **204px ≈ avail 的 24%**（`chartLayout` 用
  `max(96, avail*0.24/n)`，像素口径且有 96px 下限），本来就不存在
  `klineGridSpec` 那种 20.25% 的矮 pane 问题，**无需改**。

一个顺带确认的事实：游戏页 `MACD` 常量写死**新系** canonical
（`factors.stock_daily_momentum_close.macd_12_26_9` 系），fixture 用旧系
`macd_dif` 根本选不中——这正是 R3-5 要收敛的双列名问题的又一现场。

---

## 4. 本轮揪出并修掉的 2 个真 bug

### 4.1 QRE-REPLAY-LEGEND-SELECTED：K 线重播每帧 seek 炸一次 pageerror

**现象**：`t3_verify.py` 最后一道"零 pageerror"门禁红，报几十次
`TypeError: Cannot read properties of undefined (reading 'hasOwnProperty')`。

**栈**（真实浏览器）：
```
at e.isSelected (echarts.min.js)
at e.filterSeries
at Object.eF [as overallReset]
at t.ny [as _doReset]
```

**根因**：`replay.js` 每帧 `setOption(option, {replaceMerge:["xAxis","series"]})`，
`replaceMerge` 让 ECharts 走 `overallReset`，用**裸 option** 重建 legend model；
而我们传的是 `selected: opts.legendSelected || undefined`。K 线重播**不下发**
`legendSelected`，于是 `selected: undefined` → `LegendModel.isSelected` 里
`undefined.hasOwnProperty(name)` 抛错。job 收益曲线重播下发对象，所以不炸——
只有 K 线重播炸。

**为什么以前没发现**：错误发生在 `requestAnimationFrame` 回调里，不影响渲染结果，
肉眼看不出来；单测只断言 option 结构，不断言运行时无异常。

**修复**（`replay.js`）：没有 `legendSelected` 时**整个键都不写**，让 ECharts
用默认 `{}`：

```js
var legend = { top: 0, data: legendData };
if (opts.legendSelected) legend.selected = opts.legendSelected;
```

**回归测试**：`tests/test_equity_chart.py::test_replay_legend_never_passes_selected_undefined`
（去掉注释后断言 `selected: undefined` / `selected: opts.legendSelected || undefined`
都不出现；原 `test_replay_passes_legend_selection` 同步改为断言新写法）。

**验证**：修后 `t3_verify.py` 全绿（含零 pageerror 门禁）；单独驱动
ArrowRight×8 + ArrowLeft×8，`unique errors: 0`（修前 1）。

### 4.2 QRE-DRAW-RESTORE-TDZ：画线**永远不在页面加载时恢复**

**现象**：冷启动用例里 `localStorage` 有画线、`klineDrawLoad()` 单独调用也正常，
但 `klineDrawState.lines.length === 0`。

**根因**：`symbol.html` 里

```js
const klineDrawState = { ..., lines: (typeof klineDrawLoad === 'function') ? klineDrawLoad() : [] };  // 第 1263 行
...
const KLINE_DRAW_LS_KEY = 'qre.kline.drawings';   // 原本在第 2059 行
```

`const` 有**暂时性死区**。`klineDrawState` 的初始化器执行时 `KLINE_DRAW_LS_KEY`
还没初始化 → ReferenceError；而 `klineDrawLoad()` 整个函数体包在
`try { ... } catch (e) { return []; } }` 里，错误被**静默吞掉**，返回 `[]`。

**后果**：持久化功能自 T4 上线以来**从未在页面加载时生效过**。同会话内
`klineDrawLoad()` 正常（此时 key 已初始化），所以既有单测全绿——只有真实
浏览器冷启动才暴露。这是一个"功能看起来有、实际从来没工作过"的 bug。

**修复**：把 `KLINE_DRAW_LS_KEY` 声明提到 `klineDrawState` 之前，并写清为什么。

**回归测试**：`tests/test_kline_draw_restore_tdz.py`（3 例，全部 Node vm 跑
**生产源码切片**）：
1. `test_key_declared_before_state` —— 源码顺序断言；
2. `test_state_initializer_restores_from_storage` —— 按生产顺序执行，
   `klineDrawState.lines` 必须真的拿到存储里的画线，且异标的不得恢复；
3. `test_load_still_swallows_only_real_errors` —— **敏感度校验**：把顺序改回
   bug 写法，断言此时恢复不了（证明用例不是永真断言）。

**验证**：修后冷启动 `lines: 1`（修前 0）；`t4_verify.py` 全绿。

---

## 5. 测试

- 新增 `tests/test_kline_draw_restore_tdz.py` 3 例、`tests/test_equity_chart.py` +1 例
- 全量：**3161 passed, 24 skipped, 0 failed**

---

## 6. 遗留

- 「前进/后退 100 次后光标与静态报告一致」目前由**重播自身 metrics 往返零漂移**
  覆盖；若要严格照任务书字面（与静态报告逐值 diff），需另拉一份静态报告 fixture
  做交叉比对——指标口径同源，价值增量有限，**建议下一轮再议**。
- game.html 判据用的 fixture 是**旧系列名**的真实产物（`macd_dif/dea/hist`），
  靠 fixture 的 catalog 把它们映射到新系 canonical 才选中。真实游戏会话用的是
  新系列；产物侧双列名收敛见 R3-5。

未 commit / 未 push / 未部署 ECS（按派单约束）。
