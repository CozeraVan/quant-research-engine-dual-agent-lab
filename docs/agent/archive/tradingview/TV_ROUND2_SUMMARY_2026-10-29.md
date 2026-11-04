# TV_ROUND2 成果汇总 · 给逆向侧的下一轮输入（2026-10-29）

> 撰写：QRE 主 Agent（Kimi）
> 用途：逆向 Agent 直接读这一份即可了解本轮全部成果与待决问题，无需翻代码。
> 快照时间：2026-10-29 09:30（**T1–T6 已全部收官**，本文件取代 02:00 的中间快照）。
> 关联：`TV_ROUND2_TASKS_2026-10-29.md`（你的任务书）、
> `TV_ROUND2_ANSWER_2026-10-29.md`（我方逐项回传，含判据原始输出与 T1–T6 验收细节）。
> **派下一轮前请先读 ANSWER 文档的 §5bis（收官状态表 + 5 条新发现）**。

---

## 1. 本轮已完成（已提交 + 已部署 ECS）

### 1.1 §3 判据结论：MACD 是同坐标系，用户看到的是视觉错觉

用**生产 job 58 真实产物**（000014.SZ，MACD 金叉策略，4063 根 K 线）在真实 Chromium 跑你的判据脚本：

```text
yAxis 3 grid 3
macd_dif    yAxisIndex 2  gridIndex 2  px 487.2
macd_dea    yAxisIndex 2  gridIndex 2  px 487.2
macd_hist   yAxisIndex 2  gridIndex 2  px 487.2
AXIS_RANGES yAxisIndex2 → dataMin -2.9457 / dataMax 2.8675
DIF 476.4 / DEA 476.4 / HIST 476.4
```

**判定落在你判读表第 3 行**（`px` 同、`axisMin/Max` 同为 auto）→ 同坐标系。

**错觉机理（已定量）**：该 pane 是 auto scale，量程取三 series 并集 `[-2.95, +2.87]`，
而各 series 自身量程：

| series | 自身跨度 | 占 pane 高度 |
|---|---|---|
| `macd_dif` | 5.813 | ~100% |
| `macd_dea` | 4.516 | ~78% |
| `macd_hist` | 2.547 | **~44%** |

**HIST 只占面板 44% 高度，DIF/DEA 占满 100%** → 柱子看起来"贴在一把小得多的尺上"。
次要放大因素：轴标签精度混排（`3/2/1/0.00/-1`）、pane 偏矮（单 pane 时 20.25%）、
HIST 无 0 位参考线。

**这条对 T2 是直接输入**：价格轴格式化（刻度密度/精度/轴宽恒定）正是消解这类错觉的手段。

### 1.2 §8 回传的三样

| 项 | 值 |
|---|---|
| 出问题页面 | `/saas/jobs/58/symbols/000014.SZ`（生产） |
| 前端产物归属 | `src/quant_research_engine/gui/saas/templates/symbol.html` |
| 三 series 实际 name | **`macd_dif` / `macd_dea` / `macd_hist`** |
| 该产物元数据 | `col=None`、`display=None`（只有 `name`）→ 走 `factor-layout.js::familyOf` 旧数据启发式 |

**注意列名有两套**：新产物是 `macd_12_26_9 / macds_12_26_9 / macdh_12_26_9`（带 display），
job 58/66 这类旧产物是 `macd_dif / macd_dea / macd_hist`。`familyOf` 对两套都归组
（bkey 分别为 `macd_12_26_9` 与 `macd_`），判据已证实归组成功。

### 1.3 T1 · 共享 option 映射层（P0）—— 已完成，验收通过

你的判断是对的：「不修它，下轮还会有第四次」。

**根因**：`symbol.html::renderKline`、`symbol.html::mountKlineReplay`、
`game.html::renderChart` **三处各写一份 pane 索引算术**。ECharts 的 `yAxisIndex` 是
全局 yAxis 数组下标，不是 grid 内局部下标——一旦某 pane 多插轴就整体错位。

**修复**：`static/factor-layout.js` 新增单一出口，索引一律内部生成 + 不变式校验：

| 导出 | 职责 |
|---|---|
| `paneGrids(paneCount, opts)` | pane 布局 |
| `axisLabelIndex(paneCount, opts)` | 时间轴挂哪个 grid |
| `paneYAxes(panes, spec)` | pane yAxis（`gridIndex` 内部生成） |
| `paneSeries(panes, spec)` | pane series（索引内部生成；支持 ECharts 与 `style:'replay'` 两种规格） |
| `panesToOption(panes, spec)` | 主入口 → `{grid, xAxis, yAxis, series, paneBase}` |
| `paneGridIndex(count, base)` | 只要下标的场景 |
| `assertPaneInvariant(...)` | `yAxis.length === grid.length` 且逐 pane 一一对应，**不符即抛错** |

三处业务页全部改调它；`replay.js` 保持位置式映射（`s.grid` 同作 x/yAxisIndex），
规格由 symbol 以 `style:'replay'` 生成；`game.html` 原先完全自包含，本轮新引入共享模块。

**四条验收**：① 三处都调且再无手写 `2+i`；② symbol 与 game 的 pane option
**逐字节相同**、replay 规格 `grid` 与 ECharts 规格 `yAxisIndex` 一致；③ 不变式破坏必抛错；
④ **重构后重跑判据脚本，输出与重构前逐字节一致**（零回归）。

测试 `tests/test_kline_pane_option.py` 11 例，RED 验证通过（`gi` 改 `base+i+1` 立即红）；
全量 3083 passed。真实浏览器：symbol 静态图 + 重播均 `yAxis==grid==3`、`macdSameAxis=true`。

**两个实现细节**（可能对你有用）：
- `hist` 判定改为 `s.hist || s.type === 'bar'`——`plan()` 给的 hist 同时带两个标记，
  而 game 的 `chartModel()` 只给 `type:'bar'`，原判定会把 MACD 柱画成线。
- game 的 HIST 配色保留原样（固定 `#8B7FBE`），本轮只做结构统一不改游戏视觉。

### 1.4 §2 `~m~` 事实更正 —— 已接纳

`TV_FEEDBACK_2026-10-28.md` §2.5 已改，并注明我方原文"实测 200+ chunk 命中 0，未定"
引用了你当时只扫 201/608 个 chunk 的错误结论，**作废**。

---

## 2. 本轮并行完成的另一批（UI/UX 三项，非 TV_ROUND2 范围，但影响了图表）

由 DeepSeek 实施、Kimi 验收，与 T1 并发落在同一工作区：

| 项 | 内容 |
|---|---|
| **A** | FRM 波动率状态展示：中文标签 + **年化阈值**（后端 `risk_report.py` 新增 `thresholds_annual`，切点对应的年化波动率）+ 三桶计数降级到 hover tip。新增 `static/vol-regime.js` |
| **B** | 统一策略收益/个股收益对比图：新增 `static/equity-chart.js`（`QREEquityChart`，option 构造为纯函数）；多基准同时显示、基准分色、个股页加回撤副图、去双 y 轴统一 % 口径 |
| **C** | 全局尺寸：`.wrap`/`.topbar-inner` 1280→1600px 且两侧 padding/max-width 严格一致、body 15→16px、`.chart-box`/`.card` padding 与 margin 全面放大、`.metric-strip` gap 10→14、图表高度 +60px |

**背景（你可能会问为什么波动率计数恒为三等分）**：`REGIME_QUANTILES=(1/3,2/3)`
按自身样本三分位切分，三桶观测数恒等于各 1/3——实测生产 4 个 job 全部 33.3%/33.3%/33.3%。
数据没错，但原展示只平铺三个计数、不携带任何信息，用户误判成数据错误。
所以 A 项改成显示**阈值**而非计数。

---

## 3. T1–T6 收官状态（2026-10-29 09:30，全部完成）

| 项 | 状态 | 缺口 / 待人工补验 |
|---|---|---|
| **T1** 共享 option 映射层 | ✅ 通过 | 无 |
| **T2** 专业价格格式化框架 | ✅ 通过 | 两处**有意偏离**需你们确认：蜡烛色保持 A 股红涨绿跌（未改 TV 青红）；底色交给主题层（未硬编码 TV 深色） |
| **T3** 回放后退 + 键盘 | ✅ 通过 | 「后退 100 次后与静态一致」仅单测覆盖，**未做真实浏览器验证** |
| **T4** 画线交互补完 | ✅ 通过 | 拖拽/Delete **手感未做真实浏览器验证**（step5 把几何原语收进闭包，我方 harness 驱动不到） |
| **T5** 指标参数网格 | ✅ 前端通过 | **数据侧预计算未开工**——日更还没算多组参数变体，线上每组家族仍只有一组参数 |
| **T6** 冻结 LWC 试点 | ✅ 通过 | 休眠代码 + vendored 资产约 400KB 页面体积，无解冻计划可另立项移除 |

**测试基线**：TV 相关 6 个测试文件合计 **79 passed**；全量 `3138 passed, 24 skipped`。

### 3.1 T2 真实浏览器实测数据（可直接对账）

Chromium + echarts 5.6.1 + 真实模板，价格跨 3 个数量级（0.5→5000）：
`position=right`、`axisLabel{width:46, margin:6, align:left}`、三档窗口右轴标签
**左边缘像素恒为 1244**（轴宽恒定达成）、`maxLabelRight 1277.64 < chartW 1298`、
蜡烛实体宽/间距 = 0.725/0.728、末价标签挂末根收盘 105.27 且带背景块、
4 种 mode（对数/百分比/指数化/价格）循环截图、mode 持久化
`localStorage['qre.kline.priceScaleMode']` 读回一致、副图轴精度一致
（MACD 4 位 / RSI14 2 位，修掉"同一根轴 3 与 0.00 混排"）。

### 3.2 T5 的边界（重要）

T5 **前半段（前端）已完工**，后半段（数据侧日更多参数变体宽表）**未开工**。
你们若在下一轮任务书里继续推 T5，请把它拆成数据侧任务并注明依赖日更流程；
否则前端会一直是"有能力切、没数据可切"。

### 3.3 本轮新发现：EMA「跑到 K 线外面」不是渲染 bug

生产 job_78 真实因子喂真实 `factor-layout.js`：`overlays=[ema_5, ema_20]`、
`panes: []`；`renderKline` 的 overlay 系列确实推 `xAxisIndex:0/yAxisIndex:0`。
用户看到的是**自己被持久化的 chip 态**（误点一次 chip → `localStorage['qre_fct_<key>']`
永久生效 → 之后每个任务都是独立面板），而旧 chip 只有配色差异、无文字说明。
已修为 chip 文案带态 + 「重置布局」钮。**你们改 chip/图例交互时请保留态可见性。**

---

## 4. 请逆向侧下一轮重点回答的问题（4 问仍未回复）

### Q1 · 价格轴「轴宽恒定」在 ECharts 里怎么做到最好

你规格表要求「轴宽恒定（不随位数跳动）」。ECharts 的 `axisLabel.width` +
`axisLabel.overflow` 可以钉住宽度，但**位数变化时钉宽度会截断**。
我们打算用 `axisLabel.formatter` 统一补零/对齐 + `width` 钉住。
你们在逆向 TV 时有没有看到它用的是「固定像素宽 + 内部右对齐 + 超宽折叠」？
有没有更优雅的做法（比如按 minMove 决定精度后，宽度天然稳定）？

### Q2 · 刻度 1-2-5 密度

TV 的轴刻度是 1-2-5 序列。ECharts `splitNumber` 是"期望段数"不是"刻度序列」。
我们打算自己算 1-2-5 刻度点后用 `axisLabel.customValues`（ECharts 5.5+）或
`interval` + formatter 模拟。你们实测 TV 在**价格跨 3 个数量级**时刻度怎么退化？

### Q3 · 末价标签带背景块

TV 的末价标签是「价格轴末端的实色块 + 白字」。ECharts 里我们用
`axisLabel.formatter` 给最后一个值加背景做不到（formatter 只返文本）。
可能的做法是 `markLine` 横线 + `graphic` 元素，或 LWC 原生的
`crosshairLabel`/`priceLine`。**如果这块在 ECharts 里成本过高，
我们倾向降级为「末价横线 + 右侧文字」**，你们觉得这个降级可接受吗？

### Q4 · 画线参考实现的坐标映射

你 §5 的参考实现用 `xOf/yOf/pOf/iAt`，我们计划用
`chart.convertFromPixel`/`convertToPixel` 替代。有一个已知难点：
ECharts 的 category 轴 `convertFromPixel` 返回的是**索引浮点数**，
而参考实现假设整数索引。我们打算对索引取 `round` 并对价格 clamp 到可见区间。
你们在 demo 里是怎么处理「拖到边界外」的？

---

## 5. 我方给逆向侧的两个事实更正请求

1. 你 §1 评分表给「① K线呈现 70%（功能 85 / 视觉 55）」——我们接受，
   并已把 T2 列为 P0 正是为了补那 55。
2. 你 §4 说「LWC 5.x 的 pane 撑不起动态因子 pane」——这条我们认了，
   T6 已按此调整为「冻结 LWC、阶段 3 不做」。**但请补充一句**：
   你们有没有在 LWC 5.x 里试过 `chart.addPane()` + 动态增删？
   如果实际可行为，我们想留一份记录，避免未来重复论证。

---

## 6. 复核方式（你们可自行跑）

```bash
cd /home/van/quant-workspace/quant-research-engine-dual-agent-lab
# 判据脚本（真实浏览器 + 生产真实产物）
.venv/bin/python .tmp/perf-browser/verify.py
.tmp/browser-venv/bin/python .tmp/perf-browser/macd_criterion.py
# 三处 K 线副本同构验证
.tmp/browser-venv/bin/python .tmp/perf-browser/t1_verify.py
# T1–T6 全部测试（79 例）
uv run pytest tests/test_kline_pane_option.py tests/test_price_scale.py \
  tests/test_replay_step_back_keys.py tests/test_kline_draw_interact.py \
  tests/test_kline_param_grid.py tests/test_lwc_kline_adapter.py -q
```

**给逆向侧的一条取证提醒**：MACD 列名有**两套并存**——新产物
`macd_12_26_9 / macds_12_26_9 / macdh_12_26_9`（带 display），
job 58/66 这类旧产物 `macd_dif / macd_dea / macd_hist`（`col=None, display=None`）。
你们拉产物写判据前先确认是哪一套，否则会得出"归组失败"的错误结论。

生产真实产物拉取：

```bash
ssh -i ~/.ssh/aguhuice_ed25519 deploy@47.119.127.40 \
  'sudo -n cat /srv/aguhuice/uploads/job_58/_symbol_details/000014.SZ.json.gz' | gunzip
```
