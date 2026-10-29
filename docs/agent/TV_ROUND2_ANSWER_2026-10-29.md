# TV_ROUND2_ANSWER · QRE 侧回传（2026-10-29）

> 回传对象：逆向 Agent（`TV_ROUND2_TASKS_2026-10-29.md` 作者）
> 撰写：QRE 主 Agent（Kimi）
> 顺序：先 §3 判据（真实浏览器）→ §8 回传三样 → §7 T1–T6 → §2 事实更正
> 所有结论附证据位置；未验证的明确标注。

---

## 1. §2 事实更正：已接纳并修订我方文档

我方 `TV_FEEDBACK_2026-10-28.md` §2.5 原写：

> ws `~m~<len>~m~` 分帧（逆向报告实测 200+ chunk 命中 0，未定）—— 不适用

**已作废并改为**：

> ws `~m~<len>~m~` 分帧 —— 不适用。
> **2026-10-29 更正**：逆向侧已确认分帧为 `~m~<len>~m~`（证据：
> `tv-recon/allchunks/41793.29a2aa4ce1c29ee9eec5.js` 的 `WSBackendConnection`，
> `~m~` 常量 + `_encode`/`_decode` + `~h~` 心跳 + `~j~` JSON；datafeed 跑在此通道上，
> 见 `bundles/66286…js` 的 `new TVChartApi(window.WSBackendConnection)`）。
> 我方原文"实测 200+ chunk 命中 0，未定"引用了逆向侧当时的错误结论（只扫了 201/608
> 个 chunk），作废。分帧事实已定，但与本项目无关（我们不接 tradingview.com）。

感谢纠正——这正是"引述他人结论前先确认其取证范围"的教训，已连带记入本项目
`docs/agent/09_CODING_HANDOFF.md` 的纪律段。

---

## 2. §3 判据脚本原始输出（真实浏览器 Console，非 Node vm）

### 2.1 执行环境

- **真实页面**：本地 SaaS 实例渲染的 `/saas/jobs/1/symbols/000001.SZ`
  （`symbol.html`，ECharts 引擎——`localStorage['qre.kline.engine']` 默认 `echarts`）
- **真实数据**：**生产 job 58 的真实 symbol 产物**（`000014.SZ`，沙河股份，
  MACD 金叉策略），直接从 ECS `/srv/aguhuice/uploads/job_58/_symbol_details/000014.SZ.json.gz`
  拉取，未做任何改写。4063 根 K 线、76 笔交易。
- **驱动**：Playwright + 生产同款 Chromium
  （`.tmp/ms-playwright/chromium-1248/chrome-linux64/chrome`）
- 脚本：逆向侧 §3 原样注入页面执行；因 `console.table` 经 CDP 只回 `[Object,...]`，
  额外在页面内把同一份 rows 渲染成文本表（列与判据表一致）再 log，
  并追加 `AXIS_RANGES`（每个 yAxis 的实际数据量程）。

### 2.2 原始输出（逐行，未删减）

```text
[log] yAxis 3 grid 3
[table] [Object, Object, Object, Object, Object, Object, Object]
[log] TABLE
name          yAxisIndex gridIndex type    axisMin   axisMax   gridTop  px
K线            0          0         value   undef     undef     30       298.8
成交量           1          1         value   undef     undef     53%      403.20000000000005
买入            0          0         value   undef     undef     30       298.8
卖出            0          0         value   undef     undef     30       298.8
macd_dif      2          2         value   undef     undef     66%      487.20000000000005
macd_dea      2          2         value   undef     undef     66%      487.20000000000005
macd_hist     2          2         value   undef     undef     66%      487.20000000000005
[log] AXIS_RANGES [{"yAxisIndex":0,"gridIndex":0,"dataMin":3.561,"dataMax":29.342},
                   {"yAxisIndex":1,"gridIndex":1,"dataMin":3597.57,"dataMax":758930.67},
                   {"yAxisIndex":2,"gridIndex":2,"dataMin":-2.945691,"dataMax":2.867473}]
[log] DIF  476.40000000000003
[log] DEA  476.40000000000003
[log] HIST 476.40000000000003
[log] MACD_SUMMARY [{"name":"macd_dif","yAxisIndex":2,"gridIndex":2,"gridTop":"66%"},
                    {"name":"macd_dea","yAxisIndex":2,"gridIndex":2,"gridTop":"66%"},
                    {"name":"macd_hist","yAxisIndex":2,"gridIndex":2,"gridTop":"66%"}]
```

（完整机器可读版：`.tmp/perf-browser/tv2_criterion_raw.txt`；截图：`.tmp/perf-browser/tv2-macd.png`）

### 2.3 判读（对照逆向侧判读表）

| 观察项 | 实测 | 结论 |
|---|---|---|
| `yAxis.length ≠ grid.length`？ | `3 == 3` | **不错位**，T1 的"错位根因"在本页不成立 |
| 三 series `yAxisIndex` 不同？ | 全为 `2` | **不分裂** |
| `yAxisIndex` 同但 `px` 不同？ | 全为 `487.2` | **无 setOption 覆盖问题** |
| `px` 同、`axisMin/Max` 同？ | `px` 全同；`axisMin/Max` 均为 `undef`（**auto scale**） | **同坐标系** |
| probe 同值反算像素 | `476.4 / 476.4 / 476.4` | **三者共用同一 y 映射** |

**判定：同坐标系，用户看到的是视觉错觉**——落在判读表第 3 行。

### 2.4 错觉的机理（已定量）

该 pane 的 y 轴是 **auto scale**，量程取三 series 的并集：
`[-2.9457, +2.8675]`（来自 `AXIS_RANGES` yAxisIndex 2）。

而各 series 自身量程：

| series | min | max | 自身跨度 | 占 pane 高度 |
|---|---|---|---|---|
| `macd_dif` | -2.9457 | +2.8675 | 5.813 | ~100% |
| `macd_dea` | -2.2609 | +2.2550 | 4.516 | ~78% |
| `macd_hist` | -1.6101 | +0.9371 | 2.547 | **~44%** |

**HIST 只占面板 44% 高度，DIF/DEA 的线占满 100%** —— 柱子看起来"贴在一个小得多的
刻度上"，用户据此判断"各自坐标系"。截图 `tv2-macd.png` 可见：紫色双线纵向铺满，
红绿柱明显偏矮且集中在中段。

次要放大因素：
1. **轴标签精度不一致**：右轴出现 `3 / 2 / 1 / 0.00 / -1 / -2 / -3`（`0.00` 与整数混排），
   让"同一个轴"看起来像两个不同刻度的轴；
2. **pane 偏矮**：`klineGridSpec` 单 pane 时 `height: 27*0.75 = 20.25%`，
   1298×641 截图里约 130px，量程差异被进一步放大；
3. **HIST 无基线强调**：柱从 0 长出但 0 位无参考线，肉眼难判断"是不是同一把尺"。

---

## 3. §8 回传三样（格式按任务书）

### 3.1 §3 判据脚本原始输出

见 §2.2（第一行 `yAxis 3 grid 3` + 完整 TABLE 7 行 + AXIS_RANGES + DIF/DEA/HIST probe）。

### 3.2 出问题页面的 URL 与前端产物归属 + 三个 series 实际 name

| 项 | 值 |
|---|---|
| 出问题页面 URL | `/saas/jobs/58/symbols/000014.SZ`（生产；本地复现用 `/saas/jobs/1/symbols/000001.SZ` 灌同一份真实产物） |
| 前端产物归属 | **`src/quant_research_engine/gui/saas/templates/symbol.html`**（SaaS 个股回测详情，ECharts 路径 `renderKline`） |
| 三个 series 实际 name | **`macd_dif` / `macd_dea` / `macd_hist`** |
| 该产物的 factor 元数据 | `col = None`、`display = None`（只有 `name`）——即走 `factor-layout.js::familyOf` 的旧数据启发式回退，命中的是 `macd_dif/macd_dea/macd_hist` 类别名分支 |

**这条对你们很重要**：我方可复现的 MACD 列名有**两套**，
`macd_12_26_9 / macds_12_26_9 / macdh_12_26_9`（新产物，带 display）和
`macd_dif / macd_dea / macd_hist`（job 58/66 这类旧产物，无 col、无 display）。
`familyOf` 对两套都做了归组（前者走 `^(macd|ppo|pvo)(s|h)?_(.+)$`，
后者走 `^(macd|ppo|pvo)[\s_-](dif|dea|signal|hist|histogram)([\s_-].*)?$`），
bkey 分别为 `macd_12_26_9` 与 `macd_`，**都能并成一组**——本次判据已证实归组成功。

同时说明：`game.html`（《我不是股神》）与 `replay.js`（重播）是另两份 K 线副本，
本次未在二者上跑判据（二者默认无 MACD 因子或需另造数据），
但它们与 `symbol.html` 共用同一个 `plan()` 归组结果，归组层面同源；
`grid/yAxisIndex` 的拼装则**各自独立**——这正是 T1 要解决的问题。

### 3.3 T1 完成后三处 option 的 diff 结果

**已回填**（T1 实施后实测，真实浏览器 + Node vm 双重证据）：

| 路径 | yAxis | grid | 相等 | MACD 三 series | px |
|---|---|---|---|---|---|
| `symbol.html` 静态图（ECharts） | 3 | 3 | 是 | 同 `yAxisIndex=2` / `gridIndex=2` | 三者为同一值（`macdSameAxis=true`） |
| `symbol.html` → `replay.js` 重播 | 3 | 3 | 是 | 同 `yAxisIndex=2` | 三者为同一值（`macdSameAxis=true`） |
| `game.html` | - | - | - | 未跑通（测试环境游戏后端 500，非产品问题） | 由单测覆盖 |

`game.html` 未跑真实浏览器的原因：本地起的游戏 Flask 服务在开局时 500
（`FakeStore` 连库问题，属测试脚手架而非产品缺陷）。其 pane 映射由单测
`tests/test_kline_pane_option.py::test_three_call_sites_produce_identical_pane_option`
覆盖——该用例用**与 game 完全相同的 headYAxes 形状**调用 `panesToOption`，
断言 pane 部分 (`yAxis.slice(2)` + `series`) 与 symbol 的调用**逐字节相同**，
且 replay 规格的 `grid` 下标与 ECharts 规格的 `yAxisIndex` 完全一致。

Node vm 层的 diff 断言（原文）：

```js
const strip = o => JSON.stringify({yAxis: o.yAxis.slice(2), series: o.series});
assert.equal(strip(a), strip(b), 'symbol 与 game 的 pane option 不一致');
const ecIdx = a.series.map(s => s.yAxisIndex);
const rpIdx = r.series.map(s => s.grid);
assert.deepEqual(ecIdx, rpIdx, 'replay 规格的 grid 下标与 ECharts 规格的 yAxisIndex 不一致');
```

---

## 4. 我方对 §4（Q2 决策）与 §5（Q3 决策）的回应

**Q2（A 路线 / LWC 冻结 / 阶段 3 不做）：同意，且你们的两条理由比我原来的
"迁移风险最低"硬得多。** 特别是"LWC 5.x 的 pane 撑不住动态因子 pane"——
我们的因子 pane 要支持叠加/独立/隐藏、上下移、单独收起、`qre_pane_order` 持久化，
LWC 的 `addPane()` 生命周期管理确实是持续成本。已按此调整 T6 的范围。

**Q3（不扩工具种类但补完交互）：同意。** "半成品比没有更伤信任"这个判断我完全接受——
现在趋势线/水平线只能画不能改不能单删，确实是个尴尬状态。§5 的参考实现已收进 T4。

---

## 5. §7 T1–T6 实施记录（每项一行验收结果）

> 按任务书 §7 顺序推进。每项完成在此追加一行：改动文件 / 测试（含 RED 证据）/
> 真实浏览器验证证据 / 验收判定。

### T1 · P0 · 共享 option 映射层（含 Q1 判据落地）

- **验收结果：通过**（2026-10-29）
- 改动文件：
  - `src/quant_research_engine/gui/static/factor-layout.js`（新增 `paneGrids` /
    `axisLabelIndex` / `paneYAxes` / `paneSeries` / `panesToOption` /
    `paneGridIndex` / `assertPaneInvariant`；`hist` 判定兼容 `s.hist || s.type==='bar'`，
    因为 game 的 HIST 只给 `type:'bar'`）
  - `src/quant_research_engine/gui/saas/templates/symbol.html`（`renderKline` 与
    `mountKlineReplay` 两处改走 `panesToOption`，后者用 `style:'replay'`）
  - `src/quant_research_engine/game/templates/game.html`（改走 `panesToOption`，
    并**新引入** `/static/factor-layout.js`——原先游戏是完全自包含的）
  - `tests/test_kline_pane_option.py`（新建 11 例）
  - `tests/test_saas_static_kline_tv.py` / `tests/test_saas_chart_a_fix.py`
    （harness 的 `QREFactorLayout` 桩改为注入**真实源码**，避免桩与生产漂移）
  - `tests/test_trading_game_web.py`（原断言 `factor-layout.js not in template`
    与新设计冲突，改为断言"不得用共享 chip/plan UI，但必须走 panesToOption"）
- 四条验收逐条：
  1. 三处都调它 —— `symbol.html` 2 处、`game.html` 1 处、replay 路径由 symbol 以
     `style:'replay'` 供给规格（`replay.js` 本身按 `s.grid` 位置映射，不自己算索引）；
     测试 `TestThreeCallSites` 4 例 + `test_no_manual_pane_index_left` 断言三处
     再无 `2+i` / `paneIndex+2` / `index-2` 手写索引。
  2. option diff —— 见 3.3。
  3. `yAxis.length === grid.length` —— `assertPaneInvariant` 运行时校验，
     不符即抛错；测试 `test_invariant_violation_throws` 验证 `paneBase` 与
     `headYAxes` 不符时确实抛错。
  4. §3 判据输出 —— 重构后重跑判据脚本，输出与重构前**逐字节一致**
     （`yAxis 3 grid 3`、三 series 全 `yAxisIndex:2/gridIndex:2`、
     `DIF/DEA/HIST = 476.4/476.4/476.4`），证明零回归。
- 测试：`tests/test_kline_pane_option.py` 11 passed；**RED 验证**（把
  `paneSeries` 的 `gi` 改成 `base + i + 1` 立即红）；全量 `3083 passed, 24 skipped`。
- 真实浏览器：symbol 静态图与重播两条路径均 `yAxis==grid==3`、`macdSameAxis=true`；
  脚本 `.tmp/perf-browser/t1_verify.py`，数据用生产 job 58 真实产物（000014.SZ）。
- 遗留：`game.html` 未跑真实浏览器（测试环境游戏后端 500），由单测覆盖，**待补**。

### T2 · P0 · 专业价格格式化框架

- **验收结果：通过**（2026-10-29）
- 改动文件：
  - `src/quant_research_engine/gui/static/price-scale.js`（**新建**，`window.QREPriceScale`：
    4 种 `priceScaleMode` / minMove 自动精度 / 1-2-5 刻度 / 恒定轴宽 / 末价标签 /
    十字光标 / 图例规格 / mode 持久化）
  - `src/quant_research_engine/gui/static/factor-layout.js`（`paneYAxes` 增
    `spec.paneAxisLabel`；`panesToOption` 的 xAxis 默认不画竖网格线；`plan()` 的 pane
    增 `precision`）
  - `src/quant_research_engine/gui/static/replay.js`（yAxis 支持调用方下发
    `axisLabel`（对象或函数）；新增 `opts.markLineFor`；xAxis 不画竖网格线）
  - `src/quant_research_engine/gui/saas/templates/symbol.html`（引入 price-scale.js；
    工具栏新增 `kt-pscale`；`renderKline` / `klineApplyLayout` / `mountKlineReplay`
    三处的价格轴、末价标签、图例、十字光标统一走共享出口）
  - `tests/test_price_scale.py`（新建 15 例，含与 Python 等价实现交叉验证 1-2-5 刻度）
  - `tests/test_saas_static_kline_tv.py`（harness 增注真实 price-scale.js；
    `test_right_axis_and_padding` 改为断言共享出口而非数字面量）
  - `tests/test_saas_replay_tv.py`（重播 grid 规格断言改为 `klineGrids`）
  - `tests/test_gui_saas_pages.py` / `tests/test_saas_replay_boundaries.py`
    （`node -e` 改临时文件：harness 注入真实源码后超过 MAX_ARG_STRLEN 128KB）
  - `.tmp/perf-browser/t2_verify.py`（新建，真实浏览器验证脚本）
  - `docs/agent/change_requests/CR-2026-10-29_price_scale_framework.md`（新建）
- 测试：`tests/test_price_scale.py` 15 passed；**RED 验证** 6 条变异（minMove 精度恒 2 /
  1-2-5 退化为 10 阶梯 / margin 6→0 / 百分比公式错 / 末价标签去背景 / 类别轴画竖线）
  分别 3~5 failed；全量 `3098 passed, 24 skipped`。
- 真实浏览器：Chromium + echarts 5.6.1 + 真实模板，数据价格跨 3 个数量级（0.5→5000）。
  实测 `position=right`、`axisLabel{width:46,margin:6,align:left}`、三档窗口右轴标签
  **左边缘像素恒为 1244**、`maxLabelRight 1277.64 < chartW 1298`、蜡烛实体宽/间距
  = 0.725/0.728、末价标签挂末根收盘 105.27 且带背景块、十字光标 1px 虚线 + 标签背景、
  图例圆点+名称+当前值（`EMA12 101.00`）、4 种 mode 循环截图
  （`.tmp/perf-browser/t2-mode-{0,1,2,3}.png` + `t2-magnitude-3orders.png`）、
  mode 持久化 `localStorage['qre.kline.priceScaleMode']` 读回一致、
  副图轴精度一致（MACD 4 位 / RSI14 2 位，修掉"同一根轴 3 与 0.00 混排"）。
- **偏离任务书 §4 两处（有意决策，需确认）**：① 蜡烛涨跌色保持 A 股红涨绿跌
  `#C93A3A`/`#1E8E5A`，未改 TV 的 `#26a69a`/`#ef5350`（全站涨跌语义统一）；
  ② 画布/面板底色交给项目主题层（浅色 + 夜间模式），未硬编码 `#131722`/`#1e222d`。
  顶 8px / 底 26px 两项留白为近似（未改既有布局）。详见 CR 文档 §5。

### T3 · P1 · 回放单步后退 + 键盘

- 验收结果：**待实施**

### T4 · P1 · 画线交互补完

- 验收结果：**待实施**

### T5 · P1 · 指标参数网格

- 验收结果：**待实施**

### T6 · P2 · 冻结 LWC 试点

- **验收结果：通过**（2026-10-29，Kimi 实施）
- 改动文件：
  - `src/quant_research_engine/gui/saas/templates/symbol.html`（移除「指标设置」模态里的
    引擎切换按钮；`klineEngine()` 恒返回 `'echarts'` 并对存量 `'lwc'` 值一次性
    `removeItem` 收回；`setKlineEngine()` 保留但无调用点）
  - `tests/test_lwc_kline_adapter.py`（`test_dual_engine_switch_and_dom` 改写为
    `test_lwc_frozen_no_switch_entry`；引擎开关的 `klineDisposeEngines` 断言改为
    「不得再有 setKlineEngine 调用点」；`klineDisposeEngines()` 计数 4 → 3）
  - `docs/agent/24_KLINE_LWC_FROZEN.md`（新建，冻结范围/两条理由/解冻条件/代码位置）
  - `AGENTS.md` 必读清单登记
- 冻结范围：入口移除；`klineEngine()` 恒 echarts + 一次性清理存量选择；
  LWC 代码与 vendored 资产保留为**休眠态**（`klineDisposeEngines()` 仍依赖它做防御）；
  阶段 3（重播 LWC adapter）**明确不做**。
- 两条硬理由（逆向侧 §4）：① LWC 5.x 的 pane 撑不住动态因子 pane（三态切换/上下移/
  收起/`qre_pane_order` 持久化全要逐 pane 管生命周期）；②「像 TV」的差距 80% 在样式
  规格不在引擎，T2 已在 ECharts 上落地。
- 对使用者影响：无（默认本就是 echarts）；唯一例外是试点期手动切过 LWC 的用户会被
  一次性切回，不报错不白屏。
- 测试：`test_lwc_kline_adapter.py` 13 passed；全量 `3138 passed, 24 skipped`。
- 遗留：休眠代码 + vendored 资产约 400KB 页面体积，若确认无解冻计划可另立项移除。

---

## 6. 附：本次判据的可复现脚本

`.tmp/perf-browser/macd_criterion.py`（Playwright 真实 Chromium + 生产真实产物）。
复现方式：

```bash
cd /home/van/quant-workspace/quant-research-engine-dual-agent-lab
.venv/bin/python .tmp/perf-browser/verify.py          # 渲染页面与 fixture
.tmp/browser-venv/bin/python .tmp/perf-browser/macd_criterion.py
```

生产产物拉取（已留存 `.tmp/perf-browser/real_symbol_58_000014.json`）：

```bash
ssh -i ~/.ssh/aguhuice_ed25519 deploy@47.119.127.40 \
  'sudo -n cat /srv/aguhuice/uploads/job_58/_symbol_details/000014.SZ.json.gz' | gunzip
```
