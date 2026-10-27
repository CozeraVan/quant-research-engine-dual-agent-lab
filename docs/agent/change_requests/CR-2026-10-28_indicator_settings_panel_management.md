# CR-2026-10-28 TradingView 化：指标设置与面板管理

## 背景

TradingView 化按 `CR-2026-10-27_tv_chart_core_spike.md` 的工作流推进。本轮先做
**证据核查**，再落地仍缺的用户可见能力。

### A 路性能切片核查结论（实测，不再盲目优化）

Spike §8 A 路切片 2 要求把重播每帧 `replaceMerge:['xAxis','series']` 改为
**增量 append**。用真实生产文件做了受控基准
（`.tmp/replay-bench/bench.py`，Playwright route 把 `/static/*` 指向仓库真实
`echarts.min.js` + `replay.js`，4000 点 / 3 grid / 6 series，200 帧）：

| 指标 | 数值 |
| --- | --- |
| `setOption` 调用次数 | 201（首帧 + 200 帧） |
| 单帧 `setOption` 均值 | **2.03 ms** |
| p50 / p95 | 1.80 / 2.80 ms |
| max（首帧建图） | 22.8 ms |
| `windowDisplayData` 每帧 | 0.022 ms |
| `frameMetrics` 每帧 | 0.007 ms |

Spike 记录的 40.7ms/帧是**未加 `visibleWindow` 视口裁剪前**的全量重绘口径；
裁剪上线后单帧总成本已降到 ~2ms，相对 16.7ms（60fps）预算有 8× 余量。
**结论：增量 append 的可得收益 ≤ 2ms/帧，却要改重播热路径，风险收益比不成立，
本轮不做**；该结论写入长期文档，避免后续重复立项。

### 仍缺的用户可见能力

现有 K 线只有因子 chip（三态循环）与图例开关，没有 TradingView 式的
**指标设置**与**面板管理**：

- 无法一眼看到全部因子的当前呈现方式并集中切换；
- 无法调整副图顺序（面板顺序恒等于因子分组顺序）；
- 无法单独收起某个副图（只能整块开关因子面板）。

## 目标

1. 工具栏新增「指标」入口，弹出**指标设置面板**：集中列出本策略全部因子，
   可搜索、可切换「叠加 K 线 / 独立面板 / 隐藏」。
2. **面板管理**：副图可上移/下移调整顺序、可单独收起；顺序本地记忆。
3. 复用在既有的 chip 状态机与 `localStorage` 机制，不引入第二套状态源。
4. 遵守 R-UI-001：不新增灰色小字备注，说明一律走 `data-tip`。

## 边界

- 只改 `factor-layout.js`、`saas/templates/symbol.html` 及必要测试。
- **不支持新增任意因子**：ECS 无行情库，个股详情因子来自 worker 回传产物，
  本面板只管理产物内已有因子。要做「任意指标」需先解决云端取数，另立项。
- 不动 `lab_symbol.html`、游戏、`replay.js` 渲染核心、因子注册表、schema。
- 不改 `plan()` 既有签名语义（新增第三参为可选，缺省行为逐字节不变）。

## 测试与验收

- TDD：先 RED 后 GREEN。
- 覆盖：
  - `plan(factors, states, paneOrder)` 第三参可选；缺省/空/未知键/重复键/
    含隐藏键时行为与现状一致或明确降级；
  - `kt-ind` 按钮 DOM 合同（`.kline-tool`、aria-label、data-tip、SVG）；
  - 面板顺序持久化与「单独收起副图」的状态写入；
  - 现有 chip / 画线 / 重播测试不回归。
- 命令：
```bash
uv run pytest tests/test_factor_display_contract.py tests/test_saas_static_kline_tv.py tests/test_saas_replay_tv.py -q
uv run pytest tests/ -q
```
- 浏览器：真实页面打开面板、搜索、切态、移动面板、收起副图，K 线按预期重排。

## 实现记录（2026-10-28，TDD：先 RED 后 GREEN）

### 改动文件

- `src/quant_research_engine/gui/static/factor-layout.js`
  - `plan(factors, states, paneOrder)` 新增可选第三参：列出的副图键前置（去重、
    忽略未知/非字符串），未列出的保持相对顺序置后；只影响 `panes`，不动
    `overlays` / `chips` / `paneCount`；缺省/空数组/null/非数组时行为逐字节不变。
- `src/quant_research_engine/gui/saas/templates/symbol.html`
  - 工具栏新增 `kt-ind`（指标）按钮，复用 `.kline-tool` + `aria-label` + `data-tip`。
  - 新增 `paneOrder()` / `setPaneOrder()` / `movePane()` / `hidePane()` /
    `klineRerenderAfterSetting()` / `klineIndicatorDialog()`。
  - 副图顺序持久化在单一 localStorage 键 `qre_pane_order`（JSON 数组），
    非法输入一律降级空数组，不抛错。
  - `renderKline` 与 `mountKlineReplay` 的 `plan()` 调用都传入 `paneOrder()`，
    静态图与重播遵守同一副图顺序。
  - `KLINE_TOOL_KINDS` 加入 `ind`（重播接管时自动禁用）。
  - 新增 `.ind-mask` / `.ind-dialog` 等样式，全部复用主题 token。

### 测试

- `tests/test_factor_display_contract.py`：`plan()` 第三参 6 组断言（缺省不变 /
  显式重排 / 空与 null / 未知键 / 重复键去重 / 不动 overlay 与 chips / hidden
  不参与排序）。
- `tests/test_saas_static_kline_tv.py::TestIndicatorSettings`：源码 DOM 合同 +
  Node harness 跑持久化、越界、未知键、hidePane、`plan` 第三参透传。
- harness 同步补 `localStorage` 与 `setChipState`（两者都在 kline 块之外）。
- 命令与结果：
  - `uv run pytest tests/test_factor_display_contract.py tests/test_saas_static_kline_tv.py -q`
  - 相关 6 文件 162 passed；**全量 2964 passed, 24 skipped**。

### 生产验证（真实浏览器）

- 部署 `symbol.html` + `factor-layout.js`，MainPID 512078，回滚副本
  `/tmp/qre-deploy-20261027T175206Z.bak`。
- job58/920832.BJ：页面正常渲染、无「加载失败」；点 `kt-ind` 弹出
  `role=dialog` / `aria-modal=true` 面板，含「指标」「面板」两节。
- 交互：MACD 由「独立面板」切到「隐藏」→ 面板节显示空态、chip 记 hidden；
  点「恢复默认」→ 偏好清空、K 线重建；Esc 关闭。全程零 pageerror / console error。
- 回归：job58/920832.BJ、job58/301308、job66/300308.SZ 均 200 正常渲染。
- **过程教训（已修复）**：移动函数区块时误删 `renderFactorChips` 的
  `const slot = $('#kline-chips');`，导致 `ReferenceError` 被 `load()` catch 吞成
  「加载失败」。Node 单测全绿但生产炸——因为 VM harness 从不跑 `renderFactorChips`。
  已在生产浏览器逐段复现并定位；后续对模板的机械移动必须跑一次真实页面渲染。

## 发布

- 已按长期指令直接部署 ECS；未 commit / 未 push，待用户验收。
