# 24_KLINE_LWC_FROZEN.md — LWC 引擎试点冻结说明（T6）

> 状态：**已冻结**（2026-10-29，TV_ROUND2 T6）
> 决策来源：逆向 Agent `TV_ROUND2_TASKS_2026-10-29.md` §4（Q2 决策）
> 本文说明冻结范围、理由、以及什么情况下可以解冻。

---

## 1. 冻结范围

| 项 | 处置 |
|---|---|
| 用户可见的引擎切换入口 | **已移除**（原在「指标设置」模态底部的「试用 TradingView 图表 / 切回 ECharts」按钮） |
| `klineEngine()` | 恒返回 `'echarts'`；读取时若发现存量 `'lwc'` 值**一次性 removeItem 收回** |
| `setKlineEngine()` | 保留但冻结期不应有调用点（测试断言无调用） |
| LWC 代码（`kline-lwc.js` / `renderKlineLwc` / `lwcRenderLegend` / `lwcApplyTheme` 等） | **保留为休眠态**，不删 |
| vendored 资产（`lightweight-charts.standalone.production.js`、品牌水印、LICENSE） | **保留** |
| `klineDisposeEngines()` | **保留且仍必需**——它是 ECharts/LWC 双引擎互斥的防御性单点 |
| 阶段 3（重播 LWC adapter） | **明确不做** |

## 2. 为什么冻结（两条硬理由）

### 2.1 LWC 5.x 的 pane 撑不住本项目的动态因子 pane

因子 pane 是**动态**的，需要支持：

- 叠加 K 线 / 独立面板 / 隐藏 三态切换
- 副图上移 / 下移
- 单独收起
- `qre_pane_order` 持久化

ECharts 用声明式 `grid[] / yAxis[]` 改 option 即生效；LWC 要**逐 pane 管生命周期**，
还要与同容器的 ECharts 互斥——这正是本项目「难点 #3：双轨维护成本」的来源。
试点期间已经为此付出过真实 bug 代价（切引擎双图叠加、图例开关死锁）。

### 2.2「像 TV」的差距 80% 在样式规格，不在引擎

TV 视觉签名（右置价格轴、轴宽恒定、1-2-5 刻度、末价标签背景块、只画水平网格线、
蜡烛实体宽 0.7×间距、十字光标 1px 虚线）**在 ECharts 里全部做得到**。
换引擎买不到这 80%——T2（专业价格格式化框架）已经在 ECharts 上把这些落下来了。

## 3. 什么情况下可以解冻

只有同时满足以下两条才重新评估：

1. 出现**无因子单图**场景（分享卡 / 缩略图 / 游戏页），不需要动态 pane；
2. 该场景明确要求 TV 原生交互（如原生 crosshair label）。

解冻步骤：恢复入口按钮 → 让 `klineEngine()` 读回 localStorage → 为该场景单独写
渲染路径（不要复用 symbol.html 的因子 pane 逻辑）→ 补双引擎互斥测试。

## 4. 对使用者的影响

- **无**。默认引擎本就是 echarts，切换入口移除后行为不变。
- 唯一例外：试点期间手动切到过 LWC 的用户，下次打开会被一次性切回 echarts
  （localStorage 值被收回），不会有报错或白屏。

## 5. 相关代码位置

| 内容 | 位置 |
|---|---|
| 冻结后的 `klineEngine()` / `setKlineEngine()` | `gui/saas/templates/symbol.html` 约 565 行 |
| 双引擎互斥单点 `klineDisposeEngines()` | `gui/saas/templates/symbol.html` 约 576 行 |
| 休眠的 LWC 渲染路径 | `gui/saas/templates/symbol.html` `renderKlineLwc()` 及 `static/chart-core/kline-lwc.js` |
| 冻结态测试 | `tests/test_lwc_kline_adapter.py::TestLwcSourceContract::test_lwc_frozen_no_switch_entry` |
| 双引擎互斥测试 | `tests/test_lwc_kline_adapter.py::TestKlineEngineExclusive`、`TestLwcLegendToggle` |

## 6. 遗留（不在本轮范围）

- `renderKlineLwc()` 及其依赖在冻结期成为死代码，随 vendored 资产一起占用约 400KB
  页面体积。若后续确认无解冻计划，可再立项移除（需同步删测试与资产，属独立 CR）。
- 阶段 3（重播 LWC adapter）不做；重播继续走 ECharts，与静态图共用
  `QREFactorLayout.panesToOption` 输出。
