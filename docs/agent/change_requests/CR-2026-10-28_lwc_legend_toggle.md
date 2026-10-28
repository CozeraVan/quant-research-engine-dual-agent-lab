# CR-2026-10-28 LWC 图例开关两个 bug（TradingView 视图下因子/成交量只能藏不能回）

状态：已实施 + 已部署 ECS，未 commit/push（等用户验收）
关联：`CR-2026-10-28_lwc_kline_pilot.md`（B 路阶段 2 引入 LWC 引擎与 DOM 图例）

## 1. 现象（用户实测，TradingView 视图下）

个股详情 K 线 div 顶部的图例（成交量 / 买卖点 / 技术指标因子）：

1. **成交量、买卖点默认开启，点一次藏起来后再也点不回来**；
2. **技术因子点「取消显示」后，该选项从图例里彻底消失，无法再选择**。

（ECharts 视图无此问题——它的 chip 走 `renderFactorChips`，从 `plan.chips` 建且用
`c.states[(idx+1) % len]` 正确循环。所以这是 LWC 专属回归。）

## 2. 根因（`symbol.html::lwcRenderLegend`）

### 2.1 bug①：restore 态回读了自身

```js
// 旧代码
setChipState(key, on ? 'hidden' : (states[key] || 'pane'));
```

`states[key]` 在已隐藏时**就是 `'hidden'`**，于是"显示"分支又写回 `'hidden'`——
`__vol__` / `__marks__` 一旦藏了永久出不来（死锁）。

### 2.2 bug②：图例从「可见序列」建，隐藏组没有 pill

```js
// 旧代码
(plan.overlays || []).forEach(...)     // overlay pill
if ((plan.panes || []).length){ ... }  // 副图行
```

而 `factor-layout.js::plan()` 对隐藏组是 `if (st === "hidden") return;`——
**不入 `overlays` / `panes` 数组**。于是因子一藏，图例里连 pill 都没有，副图行
（判据是"有可见 pane"）也可能整行消失，用户无处点回。

## 3. 修复

1. `pill()` 增加第 5 参 `restore`（该组第一个非隐藏态）；
   点击时 `setChipState(key, hiddenNow ? restore : 'hidden')`，二者互斥。
2. **点击时实时读状态**（`chipStates()[key] === 'hidden'`）而非用闭包捕获的 `on`——
   万一某条支路（如无 K 线数据时 `renderKlineLwc` 提前 return）没重建图例，
   陈旧闭包也不会又写回 hidden。
3. 图例改为从 **`plan.chips`** 建（含全部组及其 state，与 ECharts 路径的
   `renderFactorChips` 同源）；副图行判据改为「有 pane 类 chip」而非「有可见 pane」。
4. `__vol__` / `__marks__` 的 restore 传 `'on'`；overlay chip 传 `c.states[0]`（= `'overlay'`），
   pane chip 传 `c.states[0]`（= `'pane'`）。
5. overlay pill 的 key 由 `o.f.col || o.f.name` 改为 `c.key`——
   而 `fkey(f) === f.col || f.name`，取值等价，且与 ECharts chip 完全同键。

## 4. 测试

新增 `tests/test_lwc_kline_adapter.py::TestLwcLegendToggle` 3 例：

- `test_pill_restores_with_explicit_state_not_stale_hidden`：源码合同，禁止旧死锁写法
- `test_legend_built_from_chips_not_visible_series`：源码合同，禁止从 overlays/panes 建图例
- `test_toggle_roundtrip_in_vm`：Node vm 跑真实 `lwcRenderLegend`，
  断言 ① 成交量藏→pill 不消失→再点回 `'on'`；② MACD 藏→pill 不消失→再点回 `'pane'`；
  ③ overlay 再点回 `'overlay'`；④ 唯一 pane 被藏后副图行仍存在；
  ⑤ **不重建图例时同一陈旧 pill 也能正确往返**（实时读状态）

**RED 验证**：把源码改回旧写法，3 例全红；恢复后 13 passed。

## 5. 真实浏览器验证（Chromium）

`.tmp/perf-browser/verify.py` 追加 LWC 引擎端到端（切 `qre.kline.engine=lwc` → 调真实
`renderKlineLwc` → 点真实 pill → 读 localStorage 与 DOM）：

| 断言 | 结果 |
|---|---|
| 图例 pill 数 | **5**（成交量 / 买卖点 / EMA5 / EMA200 / MACD） |
| 成交量默认 | `aria-pressed=true` |
| 点一次 | `qre_fct___vol__ = hidden`，**pill 仍在**，`aria-pressed=false` |
| 再点一次 | `qre_fct___vol__ = on`（**回来**；旧代码卡在 hidden） |
| EMA5 点一次 | `ema_5 = hidden`，**pill 数仍为 5**（旧代码掉到 3） |
| EMA5 再点 | `ema_5 = overlay` |
| MACD 点一次 | `macd_12_26_9 = hidden`，**pill 仍在** |
| MACD 再点 | `macd_12_26_9 = pane` |
| pageerror / console error | **0** |

## 6. 影响面

只改 `lwcRenderLegend`（LWC 引擎专属）。ECharts 路径、`renderFactorChips`、
`factor-layout.js`、指标设置模态均未动。
