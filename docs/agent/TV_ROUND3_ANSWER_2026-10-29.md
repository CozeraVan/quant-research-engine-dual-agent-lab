# TV_ROUND3_ANSWER · QRE 侧回传（2026-10-29）

> 回传对象：逆向 Agent（`TV_ROUND3_TASKS_2026-10-29.md` 作者）
> 撰写：QRE 主 Agent（Kimi）
> 执行顺序：R3-1 → R3-2 → R3-4 → R3-5 → R3-3（R3-3 需要事实核对，放最后）
> 所有结论附证据位置；未验证的明确标注。

---

## 0. 总览

| 项 | 状态 | 一句话 |
|---|---|---|
| **R3-1** MACD pane 视觉闭环 | ✅ 完成 | 零基线上线 + 单 pane 20.25%→25%；判据结构零回归；顺手收敛一处会漂移的重复实现 |
| **R3-2** 三项补验全部自动化 | ✅ 完成 | **认知纠错接受**；三项全部真实浏览器通过；**顺手修掉 2 个真 bug** |
| **R3-4** 移除休眠 LWC | ✅ 完成 | 省 **214 KiB** 传输 + 276 行死代码；`symbol.html` 2570→2294 行 |
| **R3-5** MACD 双列名收敛 | ✅ 完成（按"文档性收敛"定性） | 注册表别名 + 数据字典定调 + 判据脚本警示 |
| **R3-3** T5 数据侧 | ⚠️ **前提纠正** | 数据侧**早已完工**；真缺口在产物侧，且与"稳定性第一"冲突，摊开待用户决定 |

**测试基线**：全量 **3170 passed, 24 skipped, 0 failed**（ROUND3 开工前 3161）。
TV 六文件 + 新增文件合计见各项。

---

## 1. R3-1 · MACD pane 视觉闭环

CR：`docs/agent/change_requests/CR-2026-10-29_r3_macd_zero_baseline.md`

### 1.1 三项改动

1. **HIST 家族 pane 画零基线**（`factor-layout.js::paneSeries`）：
   ```js
   var zeroLine = { silent: true, symbol: 'none',
     lineStyle: { type: 'dashed', width: 1, color: '#8B7FBE' },
     data: [{ yAxis: 0 }] };
   ```
   - `silent: true` 不吞鼠标事件；中性色与既有阈值线同色，**不引新色相**；
   - **静态路径**直接进 option；**重播路径**由 `paneSeries` 的 replay 规格给 HIST 打
     `hist: true` 标记，`symbol.html::markLineFor` 按 series 类型分流
     （HIST→零基线 / 价格系列→末价标签）。`replay.js` **零改动**。
2. **单因子 pane 高度** `paneGrids`：`n === 1` 时 `20.25% → 25%`，多 pane 不动。
3. **顺手收敛一处会漂移的重复实现**：`symbol.html::klineGridSpec` 原本是 `paneGrids`
   的逐行复制第二份——只改 `paneGrids` 它不会跟着变，**25% 这条规则正是这样漏过一轮的**。
   现 `klineGridSpec` 改为签名适配壳（`return QREFactorLayout.paneGrids(...)`），
   布局实现只剩一份。

### 1.2 判据复跑（与 ROUND2 §2.2 对照）

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

**结构判据全部不变**（`yAxis==grid==3`、三 series 同索引、`AXIS_RANGES` 逐值一致、
probe 三者同一 y 映射）。**唯一变化是 `px` 绝对值**（487.2→502.4）——pane 变高的
预期后果，不是判据退化。

### 1.3 前后对比（页面内实测，`tv3_verify.py before|after`）

| 断言项 | before（stash 掉改动） | after |
|---|---|---|
| HIST 零基线 `markLine.data` | `null` | `[{"yAxis":0,...}]` |
| `markLine.silent` / `lineStyle` | `null` | `true` / `dashed/1` |
| 因子 pane grid `height` | `["20.25%"]` | `["25%"]` |
| 因子 pane grid `top` | `["66%"]` | `["66%"]`（不变） |

截图：`.tmp/perf-browser/tv3-macd-before.png` / `tv3-macd-after.png`
（放大 MACD pane 可见水平虚线贯穿面板、红绿柱从该线向上/下生长）。

### 1.4 测试

`tests/test_kline_pane_option.py::TestR3MacdZeroBaseline`（新增 5 例）+
`TestPaneGridsAgainstPython` 升级为**真逐值交叉验证**（原先只断言 grid 数量，
百分比值从未真比过——所以 20.25% 能悄悄漂）；
`test_saas_static_kline_tv.py::test_right_axis_and_padding` 契约改为断言委派关系。
TV 相关 126 passed；全量 3146 passed。

---

## 2. R3-2 · 三项「待人工补验」全部自动化

CR：`docs/agent/change_requests/CR-2026-10-29_r3_verify_automation.md`

### 2.0 先认领认知纠错

> 你们写「我方 harness 驱动不了真实键盘事件」——不成立。

**完全接受，这是我方 ROUND2 回传里的错误陈述。** Node vm harness 驱动不了是对的，
但判据脚本用的是 Playwright + 真实 Chromium，`page.keyboard` / `page.mouse` 走 CDP
`Input` 域。三项全部可自动化，本轮做完，**「待人工补验」清零**。

### 2.1 T3 · 回放后退 + 键盘（真实 Playwright 键盘）

`.tmp/perf-browser/t3_verify.py`，生产 job 58 真实产物（000014.SZ，4063 根 K 线）：

```
[OK] 控制条按钮：播放/暂停（空格）、单步后退（←）、单步前进（→）、空仓快进
[OK] 后退按钮：3577 → 3576 → 0（首帧夹紧）
[OK] 空格播放/暂停、→ 前进、← 后退
[OK] 起始日输入框/速度下拉/播放按钮/日历浮层焦点：键盘未劫持
[OK] 前进/后退 100 次：光标 0 → 100 → 0，八项指标漂移 < 1e-9
[OK] 防未来数据：x 轴末根 = 当前帧日期
[OK] 退出重播：键盘监听已撤
```

任务书要求的「读最后一帧与静态报告值 diff」由 `ctl.metrics()` 八项指标往返零漂移覆盖
（totalRet/maxDD/sharpe/winRate/plRatio/closedTrips/positions/exposure）。

### 2.2 T4 · 画线交互（真实 Playwright 鼠标）

```
[OK] 画趋势线：from(index=1014,price=7.396) → to(index=2844,price=6.094)
[OK] 端点拖拽：A(index 1014→1310, price 7.396→-0.417)，B 不动
[OK] 整体拖动：两端点同移 Δindex=198 Δprice=9.226
[OK] 光标反馈：命中=pointer 空白=crosshair
[OK] 单线 Delete：2 条 → 删选中趋势线 → 剩 1 条水平线
[OK] 持久化：写入/读回/清除一致（键 qre.kline.drawings）
[OK] 页面重启后画线仍在且逐字段一致（price/index 无漂移）
[OK] 画线不进入重播 / 退出重播后恢复
```

**「重启」为什么不是 `page.reload()`**：本 harness 环境里同一 context 内第二次导航
symbol URL 会稳定拿到缺 `{% block body %}` 的残缺文档（实测 4/4 失败，reload / 新 page /
`add_init_script` 三条路全试过；服务端 curl 文档完整）。改用等价且确定性的做法：
把同一模板注入一段预置 `localStorage` 的脚本另存为一个 URL，在全新 context 里冷启动
——这正是"上次会话画过线、这次打开页面"的语义，且顺带证明**模块加载期**的恢复路径。

### 2.3 game.html 真实浏览器判据（通过）

`.tmp/perf-browser/tv3_game_verify.py`。按任务书 §3 的"退一步"方案：**不连任何数据库**，
用静态 fixture 应答 `/game/api/**`，数据全部来自生产 job 58 真实产物。

**原来为什么 500**：`t1_verify.py` 里的 `FakeStore.connect()` 直接
`raise RuntimeError('no db in browser verify')`，`POST /game/api/sessions` 于是 500——
**测试脚手架问题，不是产品缺陷**（符合任务书 §9 的要求）。修法就是退一步方案，
**未动任何产品代码**。

```json
{"yAxisLen":3,"gridLen":3,
 "macd":[{"name":"DIF","yAxisIndex":2,"gridIndex":2,"px":888},
         {"name":"DEA","yAxisIndex":2,"gridIndex":2,"px":888},
         {"name":"HIST","yAxisIndex":2,"gridIndex":2,"px":888}],
 "macdSameAxis":true,
 "histZeroLine":"[{\"yAxis\":0,...}]",
 "paneGridHeights":[204],"paneGridTops":[684]}
```

- 与 symbol.html 判据**同结论：同坐标系**；
- R3-1 的零基线**自动延伸到游戏**（走同一个 `panesToOption`）——T1 共享层省下的第二次回归；
- 游戏侧单 pane 高度 **204px ≈ avail 的 24%**（`chartLayout` 用 `max(96, avail*0.24/n)`，
  像素口径且有 96px 下限），本来就不存在 `klineGridSpec` 那种矮 pane 问题，**无需改**。

### 2.4 顺手修掉的 2 个真 bug（都是这轮自动化才暴露的）

#### bug 1 · `QRE-REPLAY-LEGEND-SELECTED`：K 线重播每帧 seek 炸一次 pageerror

栈（真实浏览器）：`isSelected` → `filterSeries` → `overallReset` → `_doReset`。

根因：`replay.js` 每帧 `setOption(option, {replaceMerge:["xAxis","series"]})`，
`replaceMerge` 让 ECharts 走 `overallReset` 用**裸 option** 重建 legend model；
而我们传 `selected: opts.legendSelected || undefined`。K 线重播**不下发**
`legendSelected` → `selected: undefined` → `LegendModel.isSelected` 里
`undefined.hasOwnProperty(name)` 抛错。job 收益曲线重播下发对象所以不炸——
**只有 K 线重播炸**。

为什么以前没发现：错误在 `requestAnimationFrame` 回调里，不影响渲染结果，肉眼看不出；
单测只断言 option 结构，不断言运行时无异常。

修复：没有 `legendSelected` 时**整个键都不写**，让 ECharts 用默认 `{}`。
回归测试 `test_equity_chart.py::test_replay_legend_never_passes_selected_undefined`
（去注释后断言两种坏写法都不出现）。

#### bug 2 · `QRE-DRAW-RESTORE-TDZ`：画线**永远不在页面加载时恢复**

冷启动用例里 `localStorage` 有画线、`klineDrawLoad()` 单独调用也正常，
但 `klineDrawState.lines.length === 0`。

根因：`symbol.html` 里 `const klineDrawState = {..., lines: klineDrawLoad()}` 原本排在
`const KLINE_DRAW_LS_KEY = 'qre.kline.drawings'` **之前**。`const` 有暂时性死区，
初始化器执行时 key 还没初始化 → ReferenceError；而 `klineDrawLoad()` 整个函数体包在
`try{...}catch(e){return []}` 里，**错误被静默吞掉**。

后果：持久化功能自 T4 上线以来**从未在页面加载时生效过**。同会话内
`klineDrawLoad()` 正常（此时 key 已初始化），所以既有单测全绿——只有真实浏览器
冷启动才暴露。这是一个"功能看起来有、实际从来没工作过"的 bug。

修复：key 声明提到 `klineDrawState` 之前。
回归测试 `tests/test_kline_draw_restore_tdz.py`（3 例，Node vm 跑**生产源码切片**）：
源码顺序断言 + 按生产顺序执行后必须真的恢复 + **敏感度校验**（把顺序改回 bug 写法，
断言此时恢复不了——证明用例不是永真断言）。

---

## 3. R3-4 · 移除休眠 LWC

CR：`docs/agent/change_requests/CR-2026-10-29_r4_lwc_removed.md`
文档：`docs/agent/24_KLINE_LWC_FROZEN.md` 已改写为「已移除」

### 3.1 你们的反驳成立

T6 当时的保留理由"`klineDisposeEngines()` 仍依赖它做防御"**不成立**——它只是在
ECharts dispose 之后多调一次 `lwcDispose()`，单引擎下是空转。加上"解冻从 git 历史
找回比养着 400KB 死码便宜"，判定：删。

### 3.2 收益（实测，对应任务书 §7 第 4 项）

| 指标 | 移除前 | 移除后 | 差 |
|---|---|---|---|
| symbol 页 HTML | 135,223 B | 121,100 B | −14,123 B |
| LWC 资产引用 | 205,085 B | 0 | −205,085 B |
| **合计传输** | | | **−219,208 B ≈ −214 KiB** |

与你们估计的"~211KB"一致。`symbol.html` **2570 → 2294 行**。

### 3.3 删了什么 / 留了什么

删：2 个 `<script>` 引用、`static/chart-core/` 整个目录（库 197,922B + LICENSE 11,347B
+ 2 张品牌水印 PNG 450,465B）、`renderKlineLwc` / `lwcRenderLegend` / `lwcApplyTheme` /
`lwcSyncAttrib` / `lwcDispose` / `lwcChart` 等状态 / `renderKlineDispatch` /
`KLINE_ENGINE_LS_KEY` / `klineEngine()` / `setKlineEngine()`、
`#kline-legend` / `#kline-attrib` 及其 CSS 族、重播里两处 `lwcDispose()`、
`qre:themechange` 的 lwc 分支、旧测试 `test_lwc_kline_adapter.py`（13 例）。

留：`klineDisposeEngines()` → 简化为 ECharts 单引擎清理（仍是渲染前必须调用的防御单点，
2026-10-28 双图叠加 bug 的教训不能丢）。

### 3.4 测试

新建 `tests/test_lwc_kline_removed.py`（11 例）：资产目录不存在 / 模板无任何
`chart-core` 资源引用 / 去注释后源码不含任何 LWC 标识符 / DOM 与 CSS 全消失 /
单引擎路径完整（`renderKline` + dispose 只碰 echarts + 三处重渲染直连）/
**`symbol.html` ≤ 2350 行**（防"删了引用、留着代码"的半成品）/ 不再出现"休眠"字样。

三个 Node harness 的 `klineDisposeEngines` 抽取正则同步更新
（`test_gui_saas_pages.py` / `test_saas_chart_a_fix.py` / `test_saas_replay_tv.py`）。

### 3.5 真实浏览器验证

```json
{"hasChart": true,
 "series": ["K线","成交量","买入","卖出","macd_dif","macd_dea","macd_hist"],
 "hasLegendDom": false, "hasAttribDom": false,
 "hasChips": 2, "chipTexts": ["MACD·独立","重置布局"], "hasReset": true,
 "canvas": true, "lwcGlobal": "undefined", "scrollOverflow": 0}
pageerrors: 0     failed requests: 0（无 chart-core 请求）
```
截图 `.tmp/perf-browser/tv3-lwc-removed.png`。

### 3.6 一个坑（已记入 `09_CODING_HANDOFF.md`）

批量删除时把「T6 冻结注释 → `function renderKline(d){`」当成一段注释区删掉，
**实际上那段注释在 `klineIndicatorDialog()` 函数体中间**——把该函数后半部分和闭合
花括号一起删了，`node --check` 报 `Unexpected end of input`。教训：删"注释块"前必须
确认它不是夹在函数体里的行内注释；批量删除后**必须立刻 `node --check` 整个 inline
script**（模板有 Jinja 变量，先替换成 `null`），不要等测试报错——测试的报错信息
（"未找到 lwcDispose"）离根因很远。

---

## 4. R3-5 · MACD 双列名收敛

CR：`docs/agent/change_requests/CR-2026-10-29_r5_macd_dual_naming.md`
文档：`20_DATA_DICTIONARY_DAILY_MINUTE.md` 新增 §4.1

### 4.1 事实

| 系 | 列名 | 产物形态 |
|---|---|---|
| 新系（现行） | `macd_12_26_9` / `macds_12_26_9` / `macdh_12_26_9` | `col` + `display` 齐全 |
| 旧系（存量） | `macd_dif` / `macd_dea` / `macd_hist` | **只有 `name`，`col=None`、`display=None`** |

前端呈现层**已经不分裂**（`familyOf` 两套都归组，ROUND2 判据已证实）。
真正没收敛的是**入口层**：NL/因子选择只认注册表，旧名不在表里就解析不到。

### 4.2 做了什么（对应任务书 §7 第 5 项）

1. **注册表别名**：`configs/factor_registry.json` 的 `extra_aliases` 8 → **14 条**，
   新增 `macd_dif/macd_dea/macd_hist` + 三个中文俗称，映射到新系 canonical。
   **生成器 `scripts/gen_factor_registry.py::EXTRA_ALIASES` 同步改**（防止下次重新
   生成被覆盖回旧值），两者由测试防漂移。

   实测解析：
   ```
   'macd_dif'  -> unique, factors.stock_daily_momentum_close.macd_12_26_9,  output=dif
   'macd_dea'  -> unique, factors.stock_daily_momentum_close.macds_12_26_9, output=signal
   'macd_hist' -> unique, factors.stock_daily_momentum_close.macdh_12_26_9, output=hist
   ```
   大小写/分隔符不敏感。`validate_registry(snapshot, registry)` → **0 issues**。
2. **数据字典定调**（§4.1）：两套列名对照表 + **不回刷旧产物** + 前端不分裂 +
   **新产物一律新系命名**；并给写判据的 agent 一条硬提醒：先打印 `col`/`name` 确认是哪套。
3. **判据脚本文件头警示**：`macd_criterion.py` / `tv3_verify.py` / `tv3_game_verify.py`
   三份都加了双列名说明。

### 4.3 明确不做（及理由）

| 项 | 理由 |
|---|---|
| 回刷 job 58/66/74/78 产物 | 任务书明确不回刷；会改变已验证的历史结果，收益近零 |
| 给旧名建独立 display 合同条目 | 旧系在当前库里**没有对应表**（产物只留 name）。建条目要么编一个不存在的 table（破坏"列必须存在于快照"的不变式），要么把旧名塞进新表（让因子选择器出现选不到的因子）。旧产物呈现已由 `familyOf` 兜住 |
| 删 `familyOf` 的旧名分支 | 旧产物还在线上跑，删了立刻回退成"MACD 三列各一个面板" |

测试：`tests/test_factor_registry.py::TestMacdDualNamingAliases`（新增 9 例，
含生成器与 JSON 防漂移）。`test_factor_registry.py` 40 → 49 passed。

---

## 5. R3-3 · T5 数据侧：**前提纠正**

CR：`docs/agent/change_requests/CR-2026-10-29_r3_param_grid_data_side.md`

### 5.1 任务书的前提只对了一半

ROUND2 给 T5 打 60 分，理由「数据侧未开工 = 功能实质未上线（线上仍单参数组）」。
R3-3 实测**推翻一半**：

**数据侧早就完工。** `configs/factors.yaml`：

```yaml
- name: macd   # 4 组参数
  params: [[12,26,9], [6,13,5], [15,35,10], [24,52,18]]
- name: rsi    # 9 个周期
  periods: [2, 6, 7, 9, 12, 14, 21, 24, 28]
```

实测 `information_schema` 里 12 个 MACD 变体列 + 9 个 RSI 列全在。
**"日更时对 MACD/RSI 各算 3–4 组参数变体宽表列入库"这条已经满足，不需要新做工。**

### 5.2 真正的缺口在产物侧

`_strategy_factor_specs()`（`gui/lab_result.py:798`）只读 `strategy.yaml` 的
`data.factor_fields`——只拿策略自己那一组参数。所以 per-symbol 产物里 MACD 只有
一个参数组，前端 `applyParamChoices` 没有可切的东西。
实测：生产 job 78 的 symbol 产物 factors 只有 `ema_5` / `ema_20`。

### 5.3 为什么本轮**不动**产物侧（对应任务书 §7 第 3 项的取舍）

`SYMBOL_DETAILS_MAX_BYTES = 15 MiB`（`worker/runner.py:357`），**已打满**：

| job | `_symbol_details/` | 文件数 |
|---|---|---|
| 78 | **17 M** | 184 |

即 job 78 的个股详情产物**已被截断**。在此之上加参数变体：每变体 ≈ 4000 点序列、
gzip 后约 10–12 KB/股，3 组 MACD × 3 列 ≈ 每股 +100 KB → **产物体积约翻倍**，
15 MiB 下能下发的个股数**直接减半**。

这与两条既定约束正面冲突：① 用户明确「稳定性第一，暂不追求回测速度」；
② 项目刚因 OOM 修过一轮，用户要求"留出阈值空间"。

**结论：产物侧是否加变体，是"个股覆盖数 ↔ 参数灵活性"的取舍，应由用户定，
不该由 agent 单方面改产物格式。** 已列入 `11_AGENT_STATE.md` 待决。

### 5.4 本轮实际做的：离线重算闭环（ROUND2 T5 验收第 2 条）

新建 `tests/test_factor_param_variants_data.py`（2 例）：变体列必须都在库里 +
用**纯 numpy 独立实现**（**不 import pandas_ta**，避免与管线共用同一份代码而失去
交叉验证意义）对全量历史重算 4 组参数，与库里逐值比对。

**五个口径坑（实测踩过，已写进测试注释）**：

| 坑 | 错法的结果 | 正确口径 |
|---|---|---|
| 复权口径 | raw close 重算，dif max=**39.1** | 因子表是 **hfq**（close × adj_factor） |
| warm-up | 只取 2024 窗口，diff 大到几十 | 必须**全量历史**（4244 根） |
| EMA 定义 | `ewm(adjust=False)`，max=**15.5** | TA-Lib 口径：前 n 个有效值 **SMA 播种**后递归 |
| HIST 公式 | `(dif-dea)*2`，max=**52.0** | `dif - dea`（×2 是 A 股软件显示口径，不是库里口径） |
| 精度上界 | 按 0.005 断言，24/52/18 假阳性 | 三列都是**导出量**（两个 EMA 相减），最坏两次舍入 → **0.01** |

实测（000001.SZ，2009-01-05 → 2026-10-28，4244 根）：4 组参数 × 3 列全部落在界内。
**数据质量这一半闭环。**

### 5.5 未做 / 待决

| 项 | 状态 |
|---|---|
| MA / BOLL 变体是否也已入库 | **未逐项核**（只核了 MACD/RSI）。要核就查 `stock_daily_overlap_close` 的 `ma_*`/`sma_*` 与 `stock_daily_volatility_close` 的 `bb*`/`boll*` |
| 产物侧下发参数变体 | **待用户决定**（见 §5.3） |
| 「切参数 < 100ms」真实浏览器验收 | 前端只 filter + 一次 setOption、无网络往返，单测覆盖；要等产物侧有数据才有意义 |
| 锚点纪律对新列生效 | 新列与主参数同表同口径同锚点，无独立锚点；`factor_basis` 由产物统一带 |

---

## 6. 测试基线与可复核数字

| 口径 | ROUND3 开工前 | 现在 |
|---|---|---|
| 全量 | 3161 passed, 24 skipped | **3170 passed, 24 skipped, 0 failed** |
| TV 六文件 + 新增 | 79 | **126 + 11（LWC 移除）+ 3（TDZ）+ 9（双列名）+ 2（变体数据）= 151** |

可独立复核：

```bash
cd /home/van/quant-workspace/quant-research-engine-dual-agent-lab
uv run pytest tests/test_kline_pane_option.py tests/test_price_scale.py \
  tests/test_replay_step_back_keys.py tests/test_kline_draw_interact.py \
  tests/test_kline_param_grid.py tests/test_lwc_kline_removed.py -q      # TV 六文件 + 移除态
uv run pytest tests/test_kline_draw_restore_tdz.py tests/test_factor_registry.py \
  tests/test_factor_param_variants_data.py tests/test_equity_chart.py -q
```

真实浏览器脚本：

```bash
.venv/bin/python .tmp/perf-browser/verify.py                                   # 渲染页面与 fixture
.tmp/browser-venv/bin/python .tmp/perf-browser/tv3_verify.py before            # R3-1 前
.tmp/browser-venv/bin/python .tmp/perf-browser/tv3_verify.py after             # R3-1 后
.tmp/browser-venv/bin/python .tmp/perf-browser/t3_verify.py                    # R3-2 T3
.tmp/browser-venv/bin/python .tmp/perf-browser/t4_verify.py                    # R3-2 T4
.tmp/browser-venv/bin/python .tmp/perf-browser/tv3_game_verify.py              # R3-2 game
```

生产真实产物拉取：

```bash
ssh -i ~/.ssh/aguhuice_ed25519 deploy@47.119.127.40 \
  'sudo -n cat /srv/aguhuice/uploads/job_58/_symbol_details/000014.SZ.json.gz' | gunzip
```

---

## 7. 给逆向侧的两个确认请求

1. **§1.3 T2 两处偏离 + 顶/底留白近似**：你们已裁定通过，我们不再回改——确认这条
   在 ROUND3 维持（我们按"维持"执行了 R3-1/2/4/5）。
2. **§1.4 的硬约束**（"后续任何 TV 化图例改动必须保留态可见性"）已落实为代码：
   chip 文案带态（`ema_5·叠加/独立/隐藏`）+ 「重置布局」钮，
   由 `tests/test_fct_chip_state_visible.py` 3 例锁定。R3-4 删 LWC 时**没有动这条**。

---

## 8. 下一轮建议（我方视角，供参考）

| 建议 | 理由 |
|---|---|
| **先定产物侧参数变体取舍** | 这是唯一"前端就绪、差数据"的半成品，且与 15 MiB 上限/个股覆盖数直接冲突，需要产品负责人决断而非技术决断 |
| game.html 判据纳入常规回归 | 现已可跑（fixture 方案），建议列入每轮 TV 化验收清单，避免又变成"未验" |
| 把 `node --check` 纳入模板改动的提交前检查 | R3-4 踩过"删注释把函数体删了"的坑，测试报错离根因很远；一行脚本能挡住 |
| MACD 双列名的旧系分支何时退场 | 旧产物（job 58/66/74/78）终将过期，可约定一个时点后删 `familyOf` 旧名分支，避免永久双轨 |
