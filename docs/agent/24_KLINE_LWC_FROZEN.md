# 24_KLINE_LWC_FROZEN.md — LWC 引擎试点：已移除（原冻结说明，2026-10-29 R3-4 结案）

> 状态：**已整体移除**（2026-10-29，TV_ROUND3 R3-4）
> 决策来源：逆向 Agent `TV_ROUND3_TASKS_2026-10-29.md` §5
> 历史：T6（TV_ROUND2 §4）先冻结入口 → R3-4（TV_ROUND3 §5）按"解冻从 git 历史
> 找回比养着 400KB 死码便宜"的判断整体删除。本文保留决策记录，便于未来复盘。

---

## 1. 移除范围（R3-4 实际删了什么）

| 项 | 处置 |
|---|---|
| 模板 `<script>` 引用 | **删除 2 个**：`chart-core/vendor/lightweight-charts.standalone.production.js`、`chart-core/kline-lwc.js` |
| vendored 资产目录 | **`static/chart-core/` 整个删除**（库 js 197,922B + LICENSE 11,347B + 两张品牌水印 PNG 450,465B） |
| `symbol.html` 死代码 | **删除 276 行**：`renderKlineLwc` / `lwcRenderLegend` / `lwcApplyTheme` / `lwcSyncAttrib` / `lwcDispose` / `lwcChart` 等状态 / `renderKlineDispatch` / `KLINE_ENGINE_LS_KEY` / `klineEngine()` / `setKlineEngine()` |
| LWC 专属 DOM | **删除**：`#kline-legend`（DOM 图例）、`#kline-attrib`（品牌水印 + TradingView 链接）及其 CSS 规则族 |
| `klineDisposeEngines()` | **保留但简化为 ECharts 单引擎清理**（仍是渲染前必须调用的防御单点） |
| 测试 | `tests/test_lwc_kline_adapter.py`（13 例）→ 改写为 `tests/test_lwc_kline_removed.py`（11 例），断言资产**不再被引用/加载** |
| 重播 LWC adapter（阶段 3） | 从未做，仍不做 |

`symbol.html` 行数：**2570 → 2294**。

## 2. 收益（实测）

| 指标 | 移除前 | 移除后 | 差 |
|---|---|---|---|
| symbol 页 HTML | 135,223 B | 121,100 B | **−14,123 B** |
| LWC 资产引用 | 205,085 B | 0 | **−205,085 B** |
| **合计传输** | — | — | **−219,208 B ≈ −214 KiB** |

（HTML 体量 = 模板 UTF-8 字节；资产体量 = `<script src>` 指向文件的实际大小。
与逆向侧估计的"~211KB 传输"一致。）

## 3. 为什么最终是删而不是留（决策记录）

T6 当时判断"保留休眠态，`klineDisposeEngines()` 仍依赖它做防御"，把移除列为
"若确认无解冻计划可另立项"。R3-4 逆向侧反驳了这个判断，理由成立：

1. **`klineDisposeEngines()` 并不真的依赖 LWC**——它只是在 ECharts dispose 之后
   多调一次 `lwcDispose()`；单引擎下这段是空转。
2. **死代码有真实成本**：约 214 KiB 传输 + 276 行需要阅读理解与测试维护，
   而且每次改 K 线都要在脑子里排除 LWC 分支。
3. **"以后可能解冻"不构成保留理由**——git 历史能完整找回（提交历史里有 vendored
   资产与全部代码），恢复成本是一次 `git checkout`。

**教训（已写进 `09_CODING_HANDOFF.md`）**：休眠代码不是免费的。要么删，
要么给它一个明确的、有期限的复活条件；"先留着以后可能用"最后都会变成
没人敢动的化石代码。

## 4. 什么情况下重新引入（若要）

1. 出现**无因子单图**场景（分享卡 / 缩略图 / 游戏页），不需要动态 pane；
2. 该场景明确要求 TV 原生交互（如原生 crosshair label）。

步骤：`git log` 找回 vendored 资产与适配层 → 为该场景**单独写渲染路径**
（不要复用 symbol.html 的因子 pane 逻辑）→ 补双引擎互斥测试 →
重新评估 Apache-2.0 attribution 合规（原方案是"默认文本链接 + 自绘品牌水印"）。

## 5. 对使用者的影响

**无**。默认引擎本就是 echarts；移除后行为不变，且页面传输少了约 214 KiB。
试点期间手动切到过 LWC 的用户，其 `localStorage['qre.kline.engine']` 值现已
无人读取（`klineEngine()` 已删除），残留值完全惰性，不会有报错或白屏。

## 6. 相关代码位置（移除后）

| 内容 | 位置 |
|---|---|
| 唯一渲染入口 `renderKline(d)` | `gui/saas/templates/symbol.html` |
| 单引擎清理 `klineDisposeEngines()` | `gui/saas/templates/symbol.html`（`klineIsDark()` 之后） |
| K 线布局（共享层唯一实现） | `gui/static/factor-layout.js::paneGrids` |
| 移除态合同测试 | `tests/test_lwc_kline_removed.py`（11 例） |
| 实施 CR | `docs/agent/change_requests/CR-2026-10-29_r4_lwc_removed.md` |

## 7. 遗留

- 若未来重新引入 LWC， vendored 版本锁定信息（5.2.1，sha256
  `e21cc5caa0226ef30bd8549c50b9ef926615f2a4ee6b4e486353477a55f598cf`）
  需从 git 历史取回并重跑 Spike 基准——**不要凭记忆选版本**。
- 品牌资产（`/home/van/logo/A股回测台-brand-assets/`）仍在用户机器上，
  未随代码删除；重新引入时可直接复用。
