# CR-2026-10-29 · 画线交互补完（TV_ROUND2 T4）

- **任务书**：`docs/agent/TV_ROUND2_TASKS_2026-10-29.md` §7 T4（P1，1–2 人日）
- **参考实现**：逆向侧 `TV_ROUND2_TASKS_2026-10-29.md` §5（摘自 `tv-recon/demo/index.html`
  L404–533，已在真实浏览器验证）
- **验收口径**：端点拖拽 / 整体拖动 / 单线 Delete 手感与参考实现一致；刷新后画线仍在；
  重播态画线仍禁用。**不扩工具种类。**
- **实施日期**：2026-10-29

## 1. 实施内容

全部改动集中在 `src/quant_research_engine/gui/saas/templates/symbol.html` 的画线区块
（`QRE-TV-DRAW-INTERACT`），未触碰任何后端、未新增工具种类、未新增色相。

### 1.1 几何与坐标层

- `klinePointToPixel(chart, point)`：真实坐标 → 像素，与既有 `klinePixelToPoint` 互为
  逆运算（类别轴传 ordinal index）；
- `klineDistToSeg(px, py, x1, y1, x2, y2)`：**原样复制**参考实现的点到线段距离；
- `klineDrawPoints(ln)`：一条线的全部端点（水平线 1 个、趋势线 2 个）；
- `klineDrawHitTest(chart, pixel)`：命中判定，顺序与参考实现一致——**后画的优先，
  同一线内端点优先于线身**；半径逐值对齐（端点 7px / 趋势线身 6px / 水平线横向 5px）。

### 1.2 端点拖拽 / 整体拖动

`zr.on('mousedown' / 'mousemove' / 'mouseup')`（与既有 click 同一次绑定，随实例重建）：

- **mousedown**：画线模式中不进入拖拽（点击=落点）；命中端点 → `drag{kind:'pt0'|'pt1'}`；
  命中线身 → `drag{kind:'move', grabI, grabP}`（记录抓取点的数据坐标作基准）；
  都没命中 → 清选中，留给 ECharts 平移；
- **mousemove**：`move` 拖**差值**（`di/dp` 相对 grab 基准，不是绝对位置），两端点同步
  平移、`date` 随 `index` 同步；`pt0/pt1` 只动被抓端点；
- **mouseup**：结束拖动、保留选中态、落盘；
- **拖动中临时关掉 inside dataZoom 的 `moveOnMouseMove`**（`klineDrawSuppressPan`），
  否则拖画线会同时平移图表；松手恢复，滚轮缩放始终保留；
- index 夹紧到 `[0, dates.length-1]`，拖到数据范围外一律降级不改线（不造点）；
- `klineDrawApply` 改为 **rAF 合帧**：拖动时 mousemove 频率高，待执行帧读取最新状态。

### 1.3 单线 Delete

`klineDrawDeleteSelected()`：只删 `klineDrawState.selected`，其它画线不动；
`Delete` 与 `Backspace` 都触发（`preventDefault` 避免浏览器后退）；
**焦点在 `input/select/textarea/[contenteditable]` 时不劫持**（Backspace 要删文字）；
`Esc` 同时清模式、选中与拖动态。

### 1.4 光标反馈

`klineDrawHandleMouseMove` 里按命中结果 `zr.setCursorStyle('pointer' | 'crosshair')`；
`globalout` 回 `default`。真实浏览器实测：命中画线 `pointer`、空白处 `crosshair`。

### 1.5 选中态呈现

选中线变**虚线 + 加粗（1.6）+ 两端点圆点把手**（`markPoint`），颜色仍用既有
`#6750A4` / `#8B7FBE`，不引第四色相。

### 1.6 持久化 `localStorage['qre.kline.drawings']`

```js
{ "ts_code": "000014.SZ", "lines": [ {kind:'trend', from:{index,date,price}, to:{...}} ] }
```

- **按标的隔离**：画线锚在「日期 + 价格」上，换一只股票还显示上一只的线只会造成误读，
  所以 value 带 `ts_code`，读回时标的不一致直接回落空；
- `klineDrawValid()` 过滤脏数据（null / 缺字段 / 非数值 / 未知 kind）；
- 隐私模式（localStorage 抛错）读写都不炸；
- 落盘点：新增画线、拖动结束（mouseup）、单线删除、清除全部；
- `klineDrawState.lines` 初始化即读盘。

## 2. 测试与验证

### 2.1 Node vm 单测（`tests/test_kline_draw_interact.py`，19 例）

跑**真实 symbol.html 的 K 线区块源码**（不写桩），几何用线性可逆的假图表：

- 源码合同：12 个 T4 helper 齐全、持久化键名、三个 zr 事件绑定、Delete/Backspace、
  `selected`/`drag` 状态、**不得新增工具按钮**（`kt-rect/kt-fib/...` 一律不得出现）；
- `klineDistToSeg`：线上点 0、垂距、端点外取近端、退化线段按点距、斜线垂距；
- 像素往返可逆；坏输入一律 null；
- 命中优先级与半径：端点 7px 内、线身 6px 内、水平线横向 5px、超出不命中、
  后画的线优先、画线模式中不拖拽；
- 端点拖拽：只动被抓端点、`date` 同步、另一个端点不动；
- 整体拖动：**拖差值**（第二次拖动无累计误差）、两端点同移、水平线只改价格；
- 夹紧与降级：拖到数据范围外不改线、范围外 mousedown 不进入拖动；
- 拖动中必须关掉图表平移、松手恢复、滚轮缩放保留；
- 单线 Delete：只删选中、无选中不删、Delete/Backspace 都触发且 preventDefault、
  输入框/可编辑区焦点不劫持、Esc 清选中；
- 持久化：往返一致、跨标的隔离、脏数据过滤、坏 JSON、隐私模式不炸；
- 选中态呈现：虚线 + 加粗 + 两个把手，未选中保持实线无把手；
- `apply` 合帧不炸、基础序列 + 画线都下发。

**RED 验证**（6 条变异真实模板，全部转红）：

| 变异 | 结果 |
|---|---|
| 端点命中半径 7→0 | 3 failed |
| 线身命中距离 6→0 | 4 failed |
| 整体拖动改成绝对位置 | 1 failed |
| Delete 删全部而不是删选中 | 2 failed |
| 持久化不落盘 | 2 failed |
| 输入框焦点也劫持 Delete | 1 failed |

### 2.2 真实浏览器验证（`.tmp/perf-browser/t4_verify.py`）

Chromium + 真实 `symbol.html` + 真实 echarts + **真实鼠标事件**（Playwright mouse），
数据用生产 job 58 真实产物（000014.SZ，4063 根 K 线）。交互点一律用
`convertToPixel` 从真实数据坐标换算，保证落在主图 grid 内。

```text
画趋势线：from(index=1014, price=7.396) → to(index=2843, price=6.094)
端点拖拽：A(index 1014→1312, price 7.396→-0.417)，B 的 index/price 均不变
整体拖动：两端点同移 Δindex=199 Δprice=9.226（date 与 index 同步）
光标反馈：命中画线 pointer，空白处 crosshair
单线 Delete：2 条 → 选中趋势线按 Delete → 剩 1 条水平线
持久化：localStorage['qre.kline.drawings'] 写入 / klineDrawLoad() 读回 / 清除全部后
        lines 为空，三者一致
画线不进入重播：进入重播后 series 无「画线·」前缀（纪律保留）
退出重播后画线恢复：1 条水平线重新上图
```

截图 `.tmp/perf-browser/t4-draw-interact.png`，机器可读 `.tmp/perf-browser/t4_result.json`。

## 3. 与任务书/参考实现的差异（有意决策）

1. **持久化 value 带 `ts_code`**，不是裸数组。任务书写 `localStorage['qre.kline.drawings']`，
   键名一致；但画线锚在日期+价格上，跨标的不隔离会显示另一只股票的线。读回时标的
   不一致直接回落空，行为上"刷新后仍在"完全满足。
2. **拖动中临时关掉 ECharts 的 inside 平移**（`moveOnMouseMove:false`），松手恢复。
   参考实现里 `S.drag = {kind:'pan'}` 是自己实现平移；我们复用 ECharts 的平移，
   所以必须在中止它和让开之间切换，否则拖画线会同时平移图表。
3. **`klineDrawApply` 改 rAF 合帧**：拖动时 mousemove 60Hz，每次都全量 replaceMerge
   series（含 4063 根蜡烛）会掉帧。合帧后待执行帧读最新状态，不影响正确性。

## 4. 影响面

- **只作用于静态 K 线**：`klineDrawHandleClick/MouseDown/MouseMove/MouseUp` 都读
  `klineToolState.chart`（静态图实例）；进入重播 `setKlineToolsEnabled(false)` 会
  `klineDrawCancelMode()` 清模式/选中/拖动，重播帧不出现画线（已真实浏览器验证）。
- **`replay.js` / `game.html`**：零改动。
- **`job.html`**：无 K 线画线，零影响。
- **不扩工具种类**：工具栏仍只有 `kt-trend` / `kt-horizontal` / `kt-clear`，
  测试 `test_no_new_tool_kinds` 锁死这一点。

## 5. 复现方式

```bash
cd /home/van/quant-workspace/quant-research-engine-dual-agent-lab
.venv/bin/python .tmp/perf-browser/verify.py                        # 渲染真实模板页
.tmp/browser-venv/bin/python .tmp/perf-browser/t4_verify.py         # 真实浏览器断言
.venv/bin/python -m pytest tests/test_kline_draw_interact.py -q     # Node vm 单测
```
