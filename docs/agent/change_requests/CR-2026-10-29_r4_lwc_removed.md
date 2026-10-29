# CR-2026-10-29 · R3-4 移除休眠 LWC 试点（省 ~214 KiB 传输 + 276 行死代码）

> 任务书：`docs/agent/TV_ROUND3_TASKS_2026-10-29.md` §5
> 优先级 P1，0.5–1 人日。实施：Kimi。

---

## 1. 逆向侧的反驳为什么成立

T6（ROUND2）把移除列为"若确认无解冻计划可另立项"，理由是
"`klineDisposeEngines()` 仍依赖它做防御"。R3-4 逆向侧指出这个理由不成立：
`klineDisposeEngines()` 只是在 ECharts dispose 之后多调一次 `lwcDispose()`，
单引擎下是空转——**并不构成依赖**。

加上两条：死代码有真实成本（214 KiB 传输 + 276 行阅读理解 + 每次改 K 线都要在
脑子里排除 LWC 分支），而"以后可能解冻"不构成保留理由（git 历史能完整找回）。
判定：删。

## 2. 删了什么

| 项 | 明细 |
|---|---|
| 模板 `<script>` 引用 | 2 个（vendored 库 + 适配层） |
| vendored 资产 | `static/chart-core/` 整个目录（js 197,922B + LICENSE 11,347B + 2 张品牌水印 PNG 450,465B） |
| `symbol.html` 死代码 | **276 行**（2570 → 2294）：`renderKlineLwc` / `lwcRenderLegend` / `lwcApplyTheme` / `lwcSyncAttrib` / `lwcDispose` / `lwcChart·lwcMarkers·lwcThresholds·lwcHover` / `renderKlineDispatch` / `KLINE_ENGINE_LS_KEY` / `klineEngine()` / `setKlineEngine()` |
| LWC 专属 DOM + CSS | `#kline-legend`（DOM 图例）、`#kline-attrib`（品牌水印 + TradingView 链接）及 `.kline-legend*` / `.kline-attrib*` 规则族、夜间还原规则 |
| 重播里的 LWC 分支 | `mountKlineReplay` 进出两处 `lwcDispose()`、`qre:themechange` 监听的 lwc 分支 |
| 旧测试 | `tests/test_lwc_kline_adapter.py`（13 例）删除 |

**保留并简化**：`klineDisposeEngines()` → ECharts 单引擎清理（仍是渲染前必须调用的
防御单点，2026-10-28 双图叠加 bug 的教训不能丢）。

## 3. 收益（实测）

| 指标 | 前 | 后 | 差 |
|---|---|---|---|
| symbol 页 HTML | 135,223 B | 121,100 B | −14,123 B |
| LWC 资产引用 | 205,085 B | 0 | −205,085 B |
| **合计传输** | | | **−219,208 B ≈ −214 KiB** |

与逆向侧估计的"~211KB"一致。

## 4. 测试

新建 `tests/test_lwc_kline_removed.py`（11 例，全部 Node/源码合同，无浏览器依赖）：

| 类 | 锁什么 |
|---|---|
| `TestLwcAssetsRemoved` | `static/chart-core/` 不存在；模板无任何 `chart-core` / `lightweight-charts` / `kline-lwc` 资源引用；去掉注释后源码不含任何 LWC 标识符；`#kline-legend` / `#kline-attrib` / `.kline-legend` / `.kline-attrib` 全消失 |
| `TestSingleEngineRemains` | `renderKline` / `klineDisposeEngines` 仍在；dispose 只碰 echarts；三处重渲染点直连 `renderKline`；R3-1 的 `klineGridSpec → paneGrids` 委派没被带坏 |
| `TestPageShrank` | `symbol.html` ≤ 2350 行（防"删了引用、留着代码"的半成品）；模板不再出现"休眠"字样 |

三个 Node harness 的 `klineDisposeEngines` 抽取正则同步更新
（`test_gui_saas_pages.py` / `test_saas_chart_a_fix.py` / `test_saas_replay_tv.py`）——
旧正则锚在 `let lwcChart = null`，删除后必然失效。

**全量：3159 passed, 24 skipped, 0 failed。**

## 5. 真实浏览器验证（`.tmp/perf-browser/` + 本地 harness）

`tv3-lwc-removed.png` + 断言输出：

```json
{
 "hasChart": true,
 "series": ["K线","成交量","买入","卖出","macd_dif","macd_dea","macd_hist"],
 "hasLegendDom": false, "hasAttribDom": false,
 "hasChips": 2, "chipTexts": ["MACD·独立","重置布局"], "hasReset": true,
 "canvas": true, "lwcGlobal": "undefined",
 "scrollOverflow": 0
}
pageerrors: 0     failed requests: 0（无 chart-core 请求）
```

即：K 线图完整渲染、chip 带态 + 重置钮在、`window.LightweightCharts` 未定义、
零 pageerror、375/1440 无横向溢出。

## 6. 过程中踩的一个坑（已记入 `09_CODING_HANDOFF.md`）

批量删除时把「T6 冻结注释 → `function renderKline(d){`」当成一段注释区删掉，
**实际上那段注释在 `klineIndicatorDialog()` 函数体中间**——结果把该函数后半部分
和闭合花括号一起删了，`node --check` 报 `Unexpected end of input`。

**教训**：删"注释块"前必须确认它不是夹在函数体里的行内注释。批量删除后
**必须立刻 `node --check` 整个 inline script**（模板有 Jinja 变量，先替换成 `null`），
不要等测试报错——测试的报错信息（"未找到 lwcDispose"）离根因很远。

## 7. 文档

- `docs/agent/24_KLINE_LWC_FROZEN.md` 改写为「已移除」：移除清单、收益表、
  决策记录、重新引入的条件与步骤、版本锁定信息指向 git 历史。
- `AGENTS.md` 必读清单里该条目的描述同步更新。

未 commit / 未 push / 未部署 ECS（按派单约束）。
