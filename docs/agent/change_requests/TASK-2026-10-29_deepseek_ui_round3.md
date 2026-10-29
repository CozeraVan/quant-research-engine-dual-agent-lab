# DeepSeek 任务书：QRE UI 第三轮——全局字号 +2px 与间距系统放大（2026-10-29）

> 派发人：Kimi（主 Agent）
> 执行人：DeepSeek 子 agent（**后台运行**，不阻塞主对话）
> 批准人：用户（2026-10-29）
> 前置：第 2 轮（`TASK-2026-10-29_deepseek_ui_round2.md`）已由 Kimi 复核验收，
> 本轮是它的直接延续。

---

## 0. 先读这三份

1. `docs/agent/change_requests/TASK-2026-10-29_deepseek_ui_round2.md`（上一轮任务书，边界与纪律）
2. `docs/agent/12_UI_STYLE_GUIDE.md`（UI 长期标准）
3. `AGENTS.md` 必读清单里与 UI 相关的条目（R-UI-001、规则 12、规则 13）

---

## 1. 当前基线（Kimi 已实测线上，2026-10-29 12:00，1920 视口）

| 项 | 现值 |
|---|---|
| `body` font-size / line-height | **17px / 1.65** |
| `.chart-title` | 16.5px / margin-bottom 14px |
| `table` | **14px** |
| `.tbl th` / `.tbl td` | 14px / 继承 14px |
| `.metric-card .m-label` / `.m-value` | 14px / 19px |
| `.muted` / `label` / `details summary` / `.chart-empty` / `.bench-bar` / `.tag-tabs button` / `.btn-sm` | 13px / 13.5px（上一轮刚放大过） |
| `.label-inline` / `.wz-factsel select` | 13.5px / 12.5px |
| `.wrap` / `.container` max-width | 1920px |
| `.chart-box` | padding 22px 24px / margin-bottom 28px |
| `.card` | padding 26px 28px / margin-bottom 28px |
| `.metric-strip` | gap 14px / margin-bottom 22px |
| `.metric-card` | padding 16px 18px |
| `.page-head p` | 15.5px |
| `.fct-chip` / `.fct-chip-reset` | 12px / 12px |

---

## 2. 任务 A：所有字号再 +2px（用户原话：「所有字号再大2PX」）

### A1. 目标值

| 目标 | 现值 → 新值 |
|---|---|
| `body` | 17px → **19px** |
| `.chart-title` | 16.5px → **18.5px** |
| `table` / `.tbl th` / `.tbl td` | 14px → **16px** |
| `.detail-table` / `.detail-table th` | 14px → **16px** |
| `.metric-card .m-label` | 14px → **16px** |
| `.metric-card .m-value` | 19px → **21px** |
| `#sum-strip/#ra-strip` 的 m-value | 17.5px → **19.5px** |
| `.page-head p` | 15.5px → **17.5px** |
| `.muted` / `label` / `details summary` / `.chart-empty` / `.bench-bar` / `.tag-tabs button` / `.btn-sm` / `.label-inline` | 13 / 13.5px → **15 / 15.5px** |
| `.fct-chip` / `.fct-chip-reset` | 12px → **14px** |
| `.mainnav a` | 14px → **16px** |
| `h1` / `h2` | 18px / 15px → **20px / 17px** |
| 其它散落 px 字号 | 一律 **+2px**（逐个 grep，不要漏） |

### A2. 硬约束

1. **不改 `font-family`、`font-weight`、`line-height` 比例**。用户明确「行间距暂不推进」——
   `line-height` 一律保持原值（含无单位的 1.65 / 1.7 等倍数），**不得改成绝对值、
   不得改倍数**。字号变大后行盒会自然变高，这是允许的；改比例不允许。
2. **只放大，不放小**；只改 px 数值。
3. `.opt` / 提示类弱化层级同样 +2px，**不得小于 14px**（原下限 12px 随基数上移）。
4. 放大后**必须逐页检查文字裁切与换行错位**：表格列多（成交表/持股表/交易表），
   16px 可能撑宽或把列头挤成两行。ECharts 的 `grid.left/right` 也要复查
   （轴标签更宽会被裁——`test_gui_risk_report.py::TestStressAxisLabels` 记过这个坑）。
5. `@media` 断点阈值**不变**（仍按视口宽度），但 960 档的 `flex:1 1 45%` 之类
   要复查是否因字号变大而需要调。

---

## 3. 任务 B：间距系统放大（用户原话 + 具体举例）

### B1. 用户点名的第一现场：页面头部与主体 DIV 之间**完全没有间距**

以 `/saas/help`（使用说明）为例，当前结构：

```html
<div class="page-head">
  <h1>使用说明</h1>
  <p>o</p>          <!-- 这句备注文字 -->
</div>
<div class="...">   <!-- 主体 DIV，紧跟其后，中间 0 间距 -->
```

**要求**：`.page-head` 的 `h1` 上间距、`h1` 与 `p` 之间、`p` 与主体 DIV 之间
都要有明确间距。这是用户说的"画面整体感觉逼辙"的最直接来源。

### B2. 要求逐一扩大的位置（不限于此，举一反三）

| 位置 | 现状 | 要求 |
|---|---|---|
| `.page-head` 内部 `h1` / `p` 上下间距 | 极小/无 | 明确分层间距 |
| `.page-head` 与主体第一个 DIV 之间 | **0** | 明确间距（与 `.chart-box` 的 28px 同族或略小） |
| **回测详情页**（`job.html`）各 `.chart-box` 之间 | 28px（已有） | 保持或略增；**重点查 box 内部 title→正文** |
| **个股交易行情**（`symbol.html`）各 DIV 之间 | 部分 0 | 逐一补：K 线 box / 交易表 / FRM 卡 / 收益图之间 |
| `.chart-box` 内部 `.chart-title` → 正文 | 14px | **≥ 18px** |
| `.metric-strip` 与上下元素 | gap 14 / mb 22 | gap **≥ 18** / mb **≥ 28** |
| `.metric-card` 内边距 | 16px 18px | **≥ 20px 22px** |
| `.card` 内边距 | 26px 28px | **≥ 30px 32px** |
| `.chart-box` 内边距 | 22px 24px | **≥ 26px 28px** |
| `.risk-cards` / `.risk-grid` / `.wear-cards` 内部 gap | 10–14px | 同步放大 |
| `.tbl` 行高（`td` padding） | 10px 12px | **≥ 13px 14px**（行与行之间要能呼吸） |
| `.fct-chips` 与相邻元素 | margin-left 10px | 同步放大 |
| 表单行（`.form-grid` gap、`label` margin） | 12px 16px / 10px 0 4px | 同步放大 |
| `.entry-grid` / `.entry-card` | gap 16px / padding 20px | 同步放大 |
| 使用说明页侧边栏与右侧正文 | — | 间距明确，不得贴边 |

### B3. 方法要求

- **先测量再改**：用真实浏览器把九页（`/saas`、`/saas/new`、`/saas/jobs/<id>`、
  `/saas/jobs/<id>/symbols/<code>`、`/saas/showcase`、`/saas/profile`、
  `/saas/help`、`/saas/signals`、`/saas/strategies/<id>`）相邻 DIV 的
  `getBoundingClientRect().top - prev.bottom` 全量打出来，**列出所有 ≤ 8px 的间隔**，
  按页面归档进 CR。用户明确要求"逐一扩大"，所以要有一张"改前改后对照表"。
- 间距增量要**成体系**（同一族用同一个增量），不要每处拍一个不同数字。

---

## 4. 验收（必做）

在 **1920 / 1440 / 375** 三个视口 × **light/dark** 两主题 = 6 组合，真实 Chromium：

1. 字号：`body == 19px`、`table == 16px`、`.chart-title == 18.5px`、
   `.m-label == 16px`、`.m-value == 21px`；`line-height` **逐项与改前相同**
   （这是硬门禁，写进断言）。
2. 间距：`.page-head` 与主体 DIV 间距 **> 0 且 ≥ 16px**；`.chart-title`
   margin-bottom **≥ 18px**；`.metric-strip` gap **≥ 18px**；
   `.metric-card` / `.chart-box` / `.card` padding 达到 B2 表目标值。
3. 九页全部 `document.documentElement.scrollWidth <= innerWidth`（**无横向溢出**）。
4. 文本裁切 **0 处**（表格列头/单元格无省略号截断、无换行错位）；
   ECharts 轴标签完整可见。
5. `console.error` / `pageerror` **全 0**。
6. 每页一张全页截图，人工看：无重叠、无挤成一团。

---

## 5. 纪律（与上轮相同，违反即打回）

1. **只改前端**（模板 + `/static/` 下 CSS/JS）。不得改后端 Python、数据库、schema。
2. **不得引外部依赖**（禁 CDN）。
3. **不得新增灰色小字备注**（R-UI-001）；要解释用 `tip-trigger` + `data-tip`。
4. **不改 `font-family` / `font-weight` / `line-height`**。
5. **不改色板、圆角、玻璃/夜间机制**，不加新动效。
6. 每完成一项跑 `uv run pytest tests/ -q`，全绿才进入下一项。
7. 新增/改动的共享模块必须配 Node vm 测试（参照 `tests/test_perf_metrics.py`），
   并做 **RED 验证**。
8. **改完必须真实浏览器验证**——VM 全绿但生产炸的教训已多次。
9. `node -e` 单参数上限 128KB，脚本超 100KB 一律写临时文件跑。
10. 全量测试有**已知负载型 flake**（不同测试在不同轮次各挂一次，单独跑均过）。
    判定方法：单独跑 + 复跑一次，**不要当回归乱改**。
11. 每完成一项，CR 写进 `docs/agent/change_requests/CR-2026-10-29_*.md`，
    并追加 `05_PROGRESS.md` / `09_CODING_HANDOFF.md` / `11_AGENT_STATE.md`。
12. **不要 commit / push / 部署 ECS**——完成后报告 Kimi，由 Kimi 复核。

---

## 6. 明确不做

- 改 `line-height`（用户明确暂不推进）
- 改 `font-family` / `font-weight`
- 改色板、圆角、玻璃/夜间机制
- 移动端 / App 专门适配（用户挂起；但 375 不得横溢）
- 《我不是股神》游戏页（等用户试玩反馈）
- TradingView 化（逆向 agent 负责）
- 9090 管理台
- 后端 / 数据库 / worker

---

## 7. 建议顺序

```
B1 先测量（产出"零间距清单"）→ A 字号（机械）→ B 其余间距（按清单逐处）→ 验收
```

理由：先测量才能知道"逐一扩大"到底有哪些处；字号变大本身会改变行盒高度，
先定字号再定间距，避免同一处反复改。

---

## 8. 汇报格式

按项列出：
- 改动文件清单（路径 + 一句话）
- **零间距清单**（改前 page → 元素 → 实测间隔 → 改后间隔）
- 字号改前改后对照表（含 `line-height` 逐项未变的证据）
- 测试结果（含 RED 验证、全量通过数）
- 真实浏览器验证证据（6 组合、截图路径、断言值）
- 发现但**未改**的问题（附理由）
- 遗留待办
