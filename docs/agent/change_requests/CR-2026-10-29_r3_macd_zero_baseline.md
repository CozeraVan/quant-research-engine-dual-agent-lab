# CR-2026-10-29 · R3-1 MACD pane 视觉闭环（零基线 + 单 pane 高度 25%）

> 任务书：`docs/agent/TV_ROUND3_TASKS_2026-10-29.md` §2
> 优先级 P0，0.5–1 人日。实施：Kimi。

---

## 1. 背景（为什么做）

用户原始投诉：「MACD 的 dea、dif、hist 又是各自的坐标系」。

ROUND2 已用判据**定量证明是同坐标系**（`yAxisIndex=2` 全同、`px 476.4` 全同、
probe 三者同一 y 映射），错觉机理也定量了：该 pane 是 auto scale，量程取三 series
并集 `[-2.95, +2.87]`，而 HIST 自身跨度只占 pane 高 **~44%**、DIF/DEA 占满 100%——
柱子看起来"贴在一把小得多的尺上"。

逆向侧 ROUND3 裁定：**不拆独立轴**（TV 原版 MACD 也是三线共轴共量程，拆轴会偏离
TV 行为且重新引入真问题）。剩余差距是三个视觉项，本 CR 做其中两个代码项。

---

## 2. 改动

### 2.1 HIST 家族 pane 画零基线

`src/quant_research_engine/gui/static/factor-layout.js::paneSeries`

- **静态路径**：HIST 系列（`type:'bar'`）直接挂 `markLine`：

```js
var zeroLine = { silent: true, symbol: 'none',
  lineStyle: { type: 'dashed', width: 1, color: '#8B7FBE' },
  data: [{ yAxis: 0 }] };
```

  - `silent: true` —— 不吞鼠标事件（tooltip/十字光标不受影响）；
  - 中性色 `#8B7FBE` 与既有阈值线同色，**不引新色相**，浅色/夜间均可读；
  - 阈值线逻辑不变（仍只挂同面板第一条线，不被零基线顶替）。

- **重播路径**：`paneSeries` 的 replay 规格给 HIST 系列打 `hist: true` 标记
  （注意 `zeroBase` 已被"窗口内归零"占用，不能复用），由调用方的 `markLineFor`
  钩子分流。

`src/quant_research_engine/gui/saas/templates/symbol.html::mountKlineReplay` 的
`markLineFor` 从"只处理价格系列"扩展为按 series 类型分流：

```js
markLineFor: (s, idx, s0) => {
  if (s.hist) {                       // ① HIST → 零基线
    return { silent: true, symbol: 'none',
      lineStyle: { type: 'dashed', width: 1, color: '#8B7FBE' },
      data: [{ yAxis: 0 }] };
  }
  if (!s.mark || typeof QREPriceScale === 'undefined') return null;   // ② 价格 → 末价标签
  ...原末价标签逻辑逐字节不变...
}
```

`replay.js` 本身**零改动**（`markLineFor` 钩子 T2 就已预留，R3-1 只是扩展了它的
分流职责）。

### 2.2 单因子 pane 高度 20.25% → 25%

`factor-layout.js::paneGrids`：

```js
var paneH = (n === 1) ? 25 : (step * 0.75);
```

只有 `n === 1` 时提高度；多 pane 仍 `step*0.75`，避免互相挤压。

### 2.3 顺手收敛一处会造成漂移的重复实现

`symbol.html::klineGridSpec` 原先是 `paneGrids` 的**逐行复制第二份**（两边逻辑
"逐字节同"靠注释维持）。本次若只改 `paneGrids`，`klineGridSpec` 不会跟着变——
正是这类漂移让单 pane 高度规则漏过一轮。现 `klineGridSpec` 改为签名适配壳：

```js
function klineGridSpec(showVol, paneCount, showFct){
  return QREFactorLayout.paneGrids(paneCount, { showVol: showVol, showFct: showFct });
}
```

布局实现只剩一份。所有跑 `renderKline` 的 Node harness 都已注入真实
`factor-layout.js`（T1 时统一过），委派不会炸。

---

## 3. 测试

### 3.1 新增（`tests/test_kline_pane_option.py::TestR3MacdZeroBaseline`，5 例）

| 用例 | 锁什么 |
|---|---|
| `test_single_pane_height_is_25_percent` | 单 pane `height === '25%'`；**3 pane 仍 `6.75%`**（不被顺手改坏） |
| `test_hist_series_gets_zero_baseline_static` | 静态 option 的 HIST 带 `markLine`，`silent===true`、`symbol==='none'`、虚线、`data===[{yAxis:0}]`；MACD 阈值线仍在 |
| `test_hist_series_flagged_in_replay_spec` | replay 规格恰好 1 个 `hist:true` 且为 `bar`；**非 bar 系列不得被误打标**（否则末价标签会被零基线顶掉） |
| `test_symbol_html_markline_for_splits_hist_and_price` | `markLineFor` 先分流 `s.hist`；末价标签逻辑未被顶掉 |
| `test_kline_grid_spec_delegates_to_shared_layer` | `klineGridSpec` 委派 `paneGrids` 且**不再内联布局字面量**；`paneGrids` 全库唯一实现 |

### 3.2 改造（`TestPaneGridsAgainstPython::test_pane_grids_match_python`）

原用例只断言 grid **数量**，百分比值从未真比过（所以 20.25% 这种数值可以悄悄漂）。
现改为**真交叉验证**：Python 侧等价实现算期望 → 注入 JS → JS 逐值 `JSON.stringify`
比对，不一致即抛错。顺带修了 Python 镜像的两处格式化问题（`True` 键大小写、
`66.0%` vs JS 的 `66%`——`%g` 会把 69.66666666666667 截成 69.6667，改用最短往返
表示 + 去尾 `.0`）。

### 3.3 改造（`tests/test_saas_static_kline_tv.py::test_right_axis_and_padding`）

原断言 `"left: 16, right: 56" in renderKline 源码`——布局字面量上移后失效。
改为断言「`klineGridSpec` 委派共享层」+「共享层产出右留白」，比数字面量更防漂移。

### 3.4 结果

- TV 六文件：**126 passed**（R3-1 前 121，新增 5）
- 全量：**3146 passed, 24 skipped, 0 failed**（基线 3138，+8 = 新 5 + 上轮 chip 3）

---

## 4. 真实浏览器验证（`.tmp/perf-browser/tv3_verify.py`）

数据 = **生产 job 58 真实产物**（000014.SZ，4063 根 K 线，MACD 金叉策略），
Chromium + 真实模板，非 Node vm。

### 4.1 R3-1 断言（页面内实测）

| 断言项 | before（stash 掉本次改动） | after |
|---|---|---|
| HIST 零基线 `markLine.data` | `null` | `[{"yAxis":0,...}]` |
| `markLine.silent` | `null` | `true` |
| `markLine.lineStyle` | `null` | `dashed/1` |
| 因子 pane grid `height` | `["20.25%"]` | `["25%"]` |
| 因子 pane grid `top` | `["66%"]` | `["66%"]`（不变） |

### 4.2 判据复跑（与 ROUND2 §2.2 对照）

```
[log] yAxis 3 grid 3
name          yAxisIndex gridIndex type    axisMin   axisMax   gridTop  px
K线            0          0         value   undef     undef     30       298.8
成交量           1          1         value   undef     undef     53%      403.2
买入            0          0         value   undef     undef     30       298.8
卖出            0          0         value   undef     undef     30       298.8
macd_dif      2          2         value   undef     undef     66%      502.4
macd_dea      2          2         value   undef     undef     66%      502.4
macd_hist     2          2         value   undef     undef     66%      502.4
AXIS_RANGES yAxisIndex2 → dataMin -2.945691 / dataMax 2.867473
DIF 489.0666666666667 / DEA 489.0666666666667 / HIST 489.0666666666667
```

**结构判据全部不变**：`yAxis==grid==3`、三 series 全 `yAxisIndex:2/gridIndex:2`、
`px` 三者相等、`AXIS_RANGES` 与 ROUND2 逐值一致、DIF/DEA/HIST 同一 y 映射。

**唯一变化是 `px` 绝对值**（487.2 → 502.4，DIF/DEA/HIST 476.4 → 489.07）——
这是 pane 变高的**预期后果**（同一 y 值在更高的 pane 里映射到不同像素），
不是判据退化。判据的语义（三线共轴）完全保持。

### 4.3 截图

- `.tmp/perf-browser/tv3-macd-before.png`（无零基线、pane 20.25%）
- `.tmp/perf-browser/tv3-macd-after.png`（有零基线、pane 25%）

放大 MACD pane 可见：水平虚线贯穿整个面板，红绿柱从该线向上/下生长——
"同一把尺"不再需要解释。

---

## 5. 明确不做 / 遗留

- **不拆 MACD 独立轴**（逆向侧 ROUND3 明令，TV 原版也是共轴共量程）。
- `game.html` 走同一个 `paneSeries`，自动获得零基线与 25% 单 pane 规则；
  未单独跑 game 真实浏览器（进 R3-2）。
- 重播路径的零基线**未做真实浏览器录屏验证**（静态路径已证；重播的
  `markLineFor` 分流由单测覆盖 + R3-2 的键盘/鼠标驱动会顺带覆盖到）。

未 commit / 未 push / 未部署 ECS（按派单约束）。
