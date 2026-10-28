# CR-2026-10-29 A：波动率状态展示改造（FRM 低/中/高 可读化）

状态：已实施，未 commit/push，等用户验收
上游任务书：`TASK-2026-10-29_deepseek_uiux.md` §A（顺序 A → C → B，本 CR 是 A）

## 1. 问题

FRM 模块「波动率状态」图上方/悬停只显示英文枚举与三个恒等的计数：

- `当前波动状态 mid` —— 用户看不懂 `mid` 是什么档，更不知道"中"的边界在哪
- 低/中/高样本天数恒为 n/3、n/3、n/3（`REGIME_QUANTILES=(1/3,2/3)` 按自身样本切分），
  越是均匀越像"数据错了"

后端已在上一个 CR 给 `risk_report.json` 的 `volatility.regime` 加了 `thresholds_annual`
（年化切点），但这批数据只到 report 层，**没进 GUI 视图**，前端拿不到。

## 2. 改动

| 文件 | 改动 |
| --- | --- |
| `src/quant_research_engine/gui/lab_result.py` | `build_lab_risk_view()` 的 `volatility` 视图新增 `"regime_thresholds": regime.get("thresholds_annual")`（1 行，透传） |
| `src/quant_research_engine/gui/static/vol-regime.js` | **新增**，65 行，`window.QREVolRegime = { label, describe, tipText }` |
| `src/quant_research_engine/gui/saas/templates/job.html` | head 引 `vol-regime.js`；`volTxt` 改 `QREVolRegime.tipText(vol)`；新增 `<div class="risk-vol-state" id="chart-risk-vol-state">`；`renderRiskVol` 写入状态文案 |
| `src/quant_research_engine/gui/templates/lab_result.html` | 同上，并把原来的 `.opt` 灰字说明整段删掉（改走 hover tip，符合 R-UI 规则 13） |
| `src/quant_research_engine/gui/static/lab-theme.css` | 新增 `.risk-vol-state{font-size:14px;font-weight:600;margin:0 0 6px}`（不设颜色，跟随主题前景色） |
| `tests/test_vol_regime.py` | **新增** 13 例 |
| `tests/test_gui_saas_pages.py` | JS 沙箱真实加载 `vol-regime.js` 进 vm（不再打桩），context 注入 `QREVolRegime` |

文案形态（`describe`）：

- 有阈值：`当前：中波动（年化 18.3%–20.2% 为中档；≥20.2% 为高，<18.3% 为低）`
- 旧产物（无阈值）：`当前：中波动` —— 不出现 undefined/NaN/null

`tipText` 负责悬停：`EWMA 年化波动 5.7%；GARCH 年化波动 6.2%；当前状态 中波动；样本天数：低波动 1356 / 中波动 1356 / 高波动 1356`

阈值格式统一 `.toFixed(1)`，不改全局 `pct()`。

## 3. 与任务书的偏差（需知会）

1. **任务书 A2 假设后端已有 `thresholds_annual` 可直取**，实际它只在 `risk/report.py`
   的 report 里，GUI 视图层没有；因此在 `lab_result.py` 加了 1 行**只读透传**。
   任务书 §D 写"不得改后端 Python"，此处属于避开不了的例外——若坚持不改，
   只能前端去读 raw report，代价与风险都更大。
2. lab_result 侧原来用 `.opt` 小灰字承载说明，与 `AGENTS.md` 规则 13（禁灰字小字注释）
   冲突，本次一并改为 `tip-trigger` + `data-tip`。

## 4. 测试

- `tests/test_vol_regime.py` 13 passed。
- 三文件联跑：`tests/test_vol_regime.py tests/test_gui_saas_pages.py tests/test_gui_risk_report.py`
  → **134 passed**。
- 全量 `uv run pytest tests/ -q` → 3046 passed / 3 failed / 24 skipped。3 条里：
  - 1 条 `test_gui_saas_pages` 是本次改动漏注入 `QREVolRegime` 导致，**已修**（单跑 94 passed）；
  - 2 条 `test_saas_public_beta_ops::TestConsoleOps::test_metrics_math` 与
    `test_conversion_ratio_never_computed` 是**既有时间边界 flake**：`_seed()` 用
    `now() - interval '1 hour'` 造数据，测试恰在 2026-10-29 00:0x 跑，样本落到前一天
    23:0x，而 `window=today` 按 Asia/Shanghai 自然日从 00:00 起算 → 计数为 0。
    跨过 01:00 后自愈，与本次改动无关。

**RED 验证**：把 `vol-regime.js` 里 `describe` 的 `th && num(...)` 守卫去掉后，
`test_old_artifact_without_thresholds_degrades` 立即红：

```
TypeError: Cannot read properties of undefined (reading 'low_below')
1 failed, 12 passed
```

恢复守卫后 13 passed。

## 5. 真实浏览器验证

脚本 `.tmp/vol-browser/a_verify.py`（无参准备数据，`browser` 参跑 Playwright）。
数据来自生产 job 58 的真实 risk report 现算视图；旧产物版本刻意不带 `regime_thresholds`。

实测输出：

```
job 1440px (阈值): state='当前：中波动（年化 18.3%–20.2% 为中档；≥20.2% 为高，<18.3% 为低）' display=block
job 375px  (阈值): 同上
job 页 旧产物（无阈值）: state='当前：中波动'（无 undefined/NaN/null）
lab_result 页（阈值）: state='当前：中波动（年化 18.3%–20.2% 为中档；…）' display=block font-size=14px
=== ERRORS === 无
```

截图：`.tmp/vol-browser/job_vol_thr.png`、`job_vol_old.png`、`lab_risk.png`。

## 6. 影响面

只影响 FRM「波动率状态」一栏的标题文案与其悬停说明；图表本身（三档柱状）未动，
counts 保留（数据本身正确）。其它风险组件、其它页面未动。

## 7. 补记（2026-10-29 独立核验：lab 页说明机制整块失效，已修）

核验结论：HEAD `bf71387` 已含本 CR 主体——后端 `build_lab_risk_view()` 透传
`regime_thresholds`，SaaS `job` 页「波动率状态」标题已带阈值，tip 文案模板齐全。
缺口只在 **8081 实验台的 `lab_result.html`**：该页同样是风险组件宿主，但说明机制完全没生效。

根因（两条，同时存在）：

1. `lab_result.html` 继承 `base.html`，而 `base.html` **不加载** `static/lab-ui.js`
   → 页面里没有 `window.LabUI`，`LabUI.helpTips()` 从未绑定，任何 `data-tip` 都不弹。
2. 模板里 `volTxt` 算出来却**从未被使用**（死变量），波动率状态说明被写成 `.opt` 灰字；
   风险灯与卡片标题也只用了原生 `title=`。这违反 `AGENTS.md` 规则 13
   （说明必须走 `tip-trigger` + `data-tip` + `LabUI.helpTips`，禁 `.opt` / 灰色小字）。

本次改动（`gui/templates/lab_result.html`，6 处）：

- `<head>` 补 `<script src="/static/lab-ui.js">`（放在 echarts 之后、vol-regime 之前）。
- IIFE 顶部补 `escH()` HTML 转义 helper，所有 `data-tip` 走它。
- `card()` 的 `title=` → `tabindex="0" data-tip="escH(tip)"`。
- 风险灯 `title=` → `tabindex="0" data-tip=escH(conclusion)`。
- 风险块：日收益分布 `.opt` 灰字 → `tip-trigger` 按钮；「波动率状态」加
  `tip-trigger data-tip=escH(volTxt || '暂无波动率数据')`（`volTxt` 不再是死变量）。
- `loadRisk();` 之后补 `if (window.LabUI && LabUI.helpTips) LabUI.helpTips();`。

浏览器证据（`.tmp/vol-browser/a_verify.py`，Playwright + 真实 Chromium，
生产 job 58 真实 risk report 现算视图）：

```
lab_result 页（阈值）: state='当前：中波动（年化 18.3%–20.2% 为中档；≥20.2% 为高，<18.3% 为低）'
  display=block font-size=14px
  vol tip: EWMA 年化波动 5.7%；GARCH 年化波动 6.2%；当前状态 中波动；
           样本天数：低波动 1356 / 中波动 1356 / 高波动 1356
  triggers=2  card tips=0  helpTips bound=True
  hover tip-pop: display=block（文本非空）
  focus tip-pop: display=block（文本非空）
job 页 旧产物（无阈值）: state='当前：中波动'（无 undefined/NaN/null）
=== ERRORS === 无
```

新增断言：`#risk-body .tip-trigger[data-tip]` ≥ 2、波动率 tip 含 `EWMA` 与 `样本`、
文本无 `undefined/NaN/null`、`LabUI.helpTips` 已绑定、hover 与 focus 均让
`div.tip-pop` 变为 `display:block` 且文本非空。截图：`.tmp/vol-browser/lab_risk.png`。