# DeepSeek 任务书：QRE UI 收尾与标准符合性审计（第 2 轮，2026-10-29）

> 派发人：Kimi（主 Agent，负责主线推进 + bug 检查与复核）
> 执行人：DeepSeek 子 agent（**后台运行**，不阻塞主对话）
> 批准人：用户（2026-10-29）
>
> **背景**：上一轮 A/B/C 三项（波动率展示 / 收益图统一 / 全局尺寸）已由 Kimi 验收，
> 其中 C 项由 Kimi 追加收尾（width 1600→1920、body 17px、chart-title 16.5px、
> div 内部 header→正文间距 6→14px、删三等分柱状图）。用户接下来要推公网，
> UI 是最高优先级之一，故派第 2 轮：**补实测缺口 + 按长期标准做一次彻底审计**。
>
> **边界（与上轮相同，违反即打回）**：
> - 只改**前端**（模板 / `/static/` 下 CSS/JS）。**不得改任何后端 Python、不得改数据库、不得改 schema**。
> - 不得引入外部依赖（禁 CDN），所有 JS/CSS 走 `/static/`。
> - 不得新增灰色小字备注（R-UI-001）；要解释用 `tip-trigger` + `data-tip` + `LabUI.helpTips`。
> - 不改字体家族、不改色板、不改圆角/玻璃/夜间机制、不加新动效。
> - **不要 commit / push / 部署 ECS**——完成后报告 Kimi，由 Kimi 复核后再走部署。
> - 每完成一项必须自测并通过 `uv run pytest tests/ -q` 全绿，再进入下一项。

---

## A. 密集文本字号补齐（Kimi 已量出缺口，用户 28 寸 + MacBook 观感「字小」的最后一处）

### A1. 已量化的现状（Kimi 2026-10-29 真实浏览器实测线上）

| 目标 | 现值 | 说明 |
|---|---|---|
| `body` font-size | **17px** | 上一轮已到位，不用动 |
| `.chart-title` | 16.5px / mb 14px | 已到位，不用动 |
| `.metric-card .m-label` | 14px | 已到位，不用动 |
| `.metric-card .m-value` | 19px | 已到位，不用动 |
| **`table`** | **13px** | ← **本轮唯一明显落后项** |
| `.tbl th` | 13.5px | 与 `table` 13px 不一致，同属落后 |
| `label` / `.muted` / `details summary` / `.chart-empty` / `.bench-bar` / `.tag-tabs button` / `.btn-sm` | 13px | 密集控件，需小幅跟进 |

`table` 仍是 13px 而 body 已 17px，是当前全站最大的一处字号断层（实测线上
`/saas/jobs/58`：`body 17px` vs `table 13px`）。

### A2. 目标值

| 目标 | 现值 → 新值 |
|---|---|
| `table`（`saas/templates/base.html:70`） | `13px` → **`14px`** |
| `.tbl th`（`static/lab-theme.css`） | `13.5px` → **`14px`** |
| `.tbl td` | 不写字号（继承 table 的 14px），确认没有被别处覆盖 |
| `label` / `.muted` / `details summary` / `.chart-empty` / `.bench-bar` / `.tag-tabs button` / `.btn-sm` | `13px` → **`13.5px`**（密集控件只微加，避免挤版） |

### A3. 硬约束

1. **只放大，不放小**；只改 px 数值，不改 `font-family` / `font-weight` / `line-height` 比例。
2. `.opt` / 提示类弱化层级**不在本项放大**（B 项统一处理），但不得小于 12px。
3. `lab-theme.css` 是 8081 lab 与 SaaS **共用**的，改它会同时影响两边——这正是要的
   「所有页面一致」，但改前先 `grep` 确认没有依赖 13px 的硬编码布局。
4. 表格放大后**必须检查轴标签与表格列不裁切**：成交表/持股表列多，14px 可能撑宽。
   验收要求见 A4。

### A4. 验收（必做，用户用 28 寸 + MacBook 看）

在 **1920 / 1440 / 375** 三个视口，用真实 Chromium 断言并截图：

1. `getComputedStyle(document.querySelector('table')).fontSize === '14px'`
2. 三个视口 `document.documentElement.scrollWidth <= innerWidth`（**无横向溢出**）
3. 回测详情页的成交表/持股表、个股详情的交易表：**所有列头与单元格文字完整可见，
   无省略号截断、无换行错位**
4. 首页 / 新建策略 / 回测结果 / 个股详情 / 使用说明 / 经典策略 / 个人信息 七页各一张全页图
5. 夜间模式下同样 1–4 通过

---

## B. 公网 UI 标准符合性审计与收尾（按长期标准逐页核，修**真实**问题）

### B1. 先读这两份（权威标准，不是我的转述）

- `docs/agent/12_UI_STYLE_GUIDE.md`（色板/组件/交互/禁项全套）
- `AGENTS.md` 里的 **R-UI-001**（禁灰色小字备注）与「新 UI 不得出现灰色小字号备注」标准

### B2. Kimi 已做的前置测量（2026-10-29 线上实测，你可直接引用，不必重测）

| 页面 | `.metric-card` 数 | 其中带 `data-tip` | `.opt` 元素数 | `.opt` 采样 |
|---|---|---|---|---|
| `/saas/jobs/58` | 26 | **26（100%）** | 11 | 「任务 #58」「经典策略展示 · 只读」… |
| `/saas/new` | 0 | — | 7 | 「没思路？点一个示例填入：」「约 695 只」… |
| `/saas/help` | 0 | — | 1 | 「所有指标均来自真实回测产物…」 |

**结论：灰字备注问题已基本解决**，`grep -c 'class="opt"'` 的高数字（admin.html 99、
lab.html 39）大部分是**隐藏 DOM** 与**合法小标签**（计数、状态、入口提示），
不是用户抱怨的「大段灰色备注」。悬停 tip 机制健康：连续两次 hover 同一 trigger，
`.tip-pop` 两次都 `display:block` 且内容正确（40 个 trigger，job 页零 JS error）。

**所以 B 项不是「把 `.opt` 清零」——那是噪音。** B 项是：按标准逐页找**真实**缺陷。

### B3. 审计范围（公网用户可见面，按优先级）

1. `/saas`（首页，三入口）
2. `/saas/new`（新建策略，三入口 + 回测参数区）
3. `/saas/jobs/<id>`（回测详情：指标条/收益图/归因热力图/FRM/重播/结果操作卡）
4. `/saas/jobs/<id>/symbols/<code>`（个股详情：K 线/toolbar/chip/交易表/FRM）
5. `/saas/showcase`（经典策略）
6. `/saas/profile`（个人信息：回测记录/策略库）
7. `/saas/help`（使用说明，含侧边栏）
8. `/saas/signals`（信号中心）
9. `/saas/strategies/<id>`（策略详情）

### B4. 每页按这八条核，发现问题才改

1. **R-UI-001**：是否存在**成段的**灰色小字备注（不是单个小标签/计数/状态）。
   存在则：删（冗余）/ 移 `data-tip`（需解释）/ 改为正常可读色 `--ink` 且 ≥13px。
2. **悬停 tip 可达性**：每个 `tip-trigger` 与带 `data-tip` 的元素，hover 与
   keyboard focus（Tab）**都必须**弹出；连续两次 hover 都要弹（已知修复过
   「只有第一次弹」的 bug，确认无回归）。
3. **死按钮/死链**：所有按钮链接必须有真实响应；未实现能力给 toast 或说明。
4. **375px 无横向溢出**：`scrollWidth <= innerWidth`，无元素超出视口。
5. **夜间模式**：九页在 `data-theme="dark"` 下无可读性问题（对比度、边框消失、
   图表主题不联动等）。红涨绿跌语义保留。
6. **玻璃卡一致性**：`.metric-card` / 磨损卡 / 风险卡 / sum-strip / ra-strip 必须都是
   磨砂玻璃规格（`backdrop-filter: blur(28px) saturate(140%)`、白色 45–60% 透明、
   1px 半透明白描边、顶部内侧细高光、圆角 24px、大而柔的紫阴影）。
   已知这条曾经白底/紫底混搭，已统一；**确认无回退**。
7. **图表轴标签完整**：字号放大后 ECharts 的 `grid.left/right` 是否仍够
   （轴标签被裁是已知坑，`test_gui_risk_report.py::TestStressAxisLabels`
  记过这个教训）。
8. **K 线因子呈现**：EMA/MA/BOLL 类 overlay 因子必须叠加在 K 线主图
   （`xAxisIndex:0/yAxisIndex:0`），MACD/RSI 类独立副图。chip 必须带态
   （`ema_5·叠加` / `·独立` / `·隐藏`）且有「重置布局」钮——
   **这是 Kimi 本轮刚修的，不得回退**。

### B5. 输出要求

- 每页一份结论（通过 / 问题清单），问题清单按「页面 → 元素 → 现状 → 改法」列。
- **只改真实问题**；「看起来还能更好」但不违反标准的**不要动**（避免无意义 churn）。
- 9090 管理台（`admin.html` 99 处 `.opt`）**本轮不做**（内网 SSH 隧道访问，
  用户看不到），但要在 CR 里记录数量，留待后续。

---

## C. 纪律与交付

1. **不新增灰色小字备注**（R-UI-001）。
2. **不引外部依赖**（禁 CDN）。
3. 每完成一项跑 `uv run pytest tests/ -q`，全绿才进入下一项。
4. 新增/改动的共享模块必须配 Node vm 测试（参照 `tests/test_perf_metrics.py`），
   并做 **RED 验证**（把改动改坏，确认测试红）。
5. **改完必须真实浏览器验证**（Chromium + `.tmp/browser-venv/bin/python`）——
   VM 全绿但生产炸的教训已多次。
6. 涉及 `node -e` 的测试：脚本超 100KB 改写临时文件跑（`symbol.html` 已 107KB+，
   Linux 单参数上限 128KB）。
7. 全量测试有**已知负载型 flake**（不同测试在不同轮次各挂一次，单独跑均过）。
   判定方法：单独跑 + 复跑一次，**不要当成回归去乱改**。
8. 每完成一项，CR 写进 `docs/agent/change_requests/CR-2026-10-29_*.md`，
   并追加 `05_PROGRESS.md` / `09_CODING_HANDOFF.md` / `11_AGENT_STATE.md`。
9. **不要 commit / push / 部署 ECS**——完成后报告 Kimi。

---

## D. 明确不做（本轮范围外，勿越界）

- 移动端 / App 深化（用户已明确挂起）
- 《我不是股神》游戏（等用户试玩反馈）
- TradingView 化（逆向 agent 负责，见 `docs/agent/TV_ROUND2_*`）
- 后端 / 数据库 / schema /  worker
- 任何新色相、新组件、新动效

---

## E. 建议顺序

```
A（字号，机械且有明确数值）→ B（审计，发现驱动）
```

理由：A 会改变表格与密集文本尺寸，可能引发轴标签裁切等连带问题；
先把 A 定下来再做 B 的审计，避免同一处反复改。
