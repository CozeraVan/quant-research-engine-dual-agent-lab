# DeepSeek 任务书：QRE UI 第四轮——持续后台改进（2026-10-30）

> 派发人：Kimi（主 Agent）
> 执行人：DeepSeek 子 agent（**后台运行**，不阻塞主对话）
> 批准人：用户（2026-10-30）

---

## 0. 先读

1. `docs/agent/12_UI_STYLE_GUIDE.md`（UI 长期标准）
2. `AGENTS.md`（项目总规则；**本轮起新增了三条 UI/证据纪律，必读**）
3. `docs/agent/change_requests/TASK-2026-10-29_deepseek_ui_round3.md`（上一轮，边界延续）

## 1. 当前基线（2026-10-30 线上实测）

- body **19px** / line-height 1.65（**line-height 冻结，不许改**）
- table **16px** / `.tbl th` 16px / `.chart-title` 18.5px + mb 18px
- `.metric-card` label 16px / value 21px / `.page-head h1` 32px
- `.page-head` margin-bottom **28px**、`.chart-box` padding 26/28 + mb 32px、
  `.metric-strip` gap 18px + mb 28px
- `.wrap` / `.container` / `.topbar-inner` max-width **1920px**
- 夜间模式：`night-mode.css` + `qre-theme` localStorage + 顶部切换按钮（当前显示中）

---

## 2. 五项任务

### 2.1 「夜间模式」按钮不显示，但功能全部保留（暂不启用）

- **隐藏**顶部的夜间模式切换按钮（不删除功能代码）。
- **保留**：`night-mode.css` 全部规则、`qre-theme` localStorage 持久化、
  系统偏好跟随（`prefers-color-scheme`）、防 FOUC、ECharts 主题联动——
  **一行逻辑都不许删**。
- 实现要求：用 CSS 隐藏（如 `.theme-toggle{display:none}`），不要删 JS；
  在 CSS 规则处写清「按钮暂不启用，功能保留，恢复只需删这条规则」。
- 已手动切过 dark 的用户（localStorage 有 `qre-theme=dark`）**行为不变**，
  不得把他们弹回浅色。

### 2.2 header 主要内容与页面整体 width 一致

当前 `.topbar-inner` max-width 已是 1920px，但用户反馈 header 的
LOGO + 顶部菜单栏与页面主体 width **没对齐**。

- 用真实浏览器量 `.topbar-inner` 与 `.wrap`/`.container` 的
  `clientWidth` 和 `getBoundingClientRect().left`，**报出实际差值**；
- 找出根因（padding 不一致？topbar 有额外包裹层？LOGO 宽度把内容推偏？）；
- 修到两者 `clientWidth` 相等、`left` 相等；
- 375px 不得因对齐改动产生横向溢出。

### 2.3 增大个股交易详情页 K 线的 height

当前 `symbol.html` 的 `#chart-kline` 太扁。

- 找到当前高度值（含 `QREReplay.klineHeightForPanes()` 与
  `QRELwcAdapter.klineHeight` 两条路径——**注意 LWC 已整体移除**，
  只需改 ECharts 路径）；
- 适度增大（用户原话「太扁」），同时保证：
  - 有因子 pane 与无因子 pane 两种情况都协调；
  - 重播进入/退出后高度一致（`klineHeightForPanes` 与静态路径同源）；
  - 375px 不溢出、不把下方交易表挤出首屏太多。
- **不要**顺手改 pane 的相对比例（那是 R3-1 刚定的 25%/42%/10%）。

### 2.4 个股 FRM 模块 7 个小 div 的排版优化

当前 7 个卡排成「第一排 6 个、第二排 1 个」，很别扭。

- 位置：`symbol.html` 的 FRM 卡（VaR/ES 那一组，`.metric-strip` 或类似容器）；
- 目标：改成均衡排版。可选方向（自己判断哪个最合适，**在 CR 里说明取舍**）：
  - 7 个改 `grid-template-columns` 自适应（如 `repeat(auto-fit, minmax(150px,1fr))`）；
  - 或按语义分两组（如「尾部风险 4 + 波动/夏普 3」）；
  - 或调成 4+3 两排。
- 硬要求：1920 / 1440 / 375 三视口都不溢出、不出现单卡孤行；
  与策略详情页（job.html）同族卡片风格保持一致。

### 2.5 策略详情 FRM 的波动率显示继续优化

现状（用户原话「依然是简陋的当前波动率状况」）：删掉三等分柱状图后，
那一列只有一行文字「当前：中波动（年化 18.3%–20.2% 为中档；≥20.2% 为高，<18.3% 为低）」，
`#chart-risk-vol` 容器被 `display:none`。

- 先读 `job.html::renderRiskVol` 与 `static/vol-regime.js` 的现状；
- 设计一个**有信息量**的呈现，可考虑方向（自己判断，CR 里说明）：
  - 波动率时序曲线（EWMA/GARCH 年化波动随时间）+ 三档阈值的水平参考线；
  - 当前值在历史分布中的位置（分位数标记）；
  - 三桶计数以**堆叠条/占比条**呈现（不是三个相等数字）。
- 硬约束：
  - **不得把三等分柱状图改回来**（用户明确否掉过）；
  - 不得引新色相（用既有 token）；不得新增灰色小字备注（R-UI-001）；
  - 数据只来自 `d.volatility`（`ewma_annual` / `garch_annual` / `regime_counts` /
    `latest_regime` / `regime_thresholds`），**没有的字段不许编**；
  - 旧产物（job 58/66，无 `thresholds_annual`）必须优雅降级，不出现
    `undefined`/`NaN`；
  - 真实浏览器验证（job 58 有真实 risk_report.json 可灌）。

---

## 3. 硬边界（违反即打回）

1. **只改前端**（模板 + `/static/`）。不得改后端 Python、数据库、schema。
2. **不得引外部依赖**（禁 CDN）。
3. **不得新增灰色小字备注**（R-UI-001）；要解释用 `tip-trigger` + `data-tip`。
4. **不得改 `font-family` / `font-weight` / `line-height`**（用户明确冻结行距）。
5. **不得改色板、圆角、玻璃/夜间机制**，不加新动效（除 2.5 新增图表本身的
   必要交互）。
6. **静默 catch 必须带理由注释**（AGENTS.md 新纪律，测试强制）。
7. **条件键缺就不写键**；存量「键在值为 undefined」按**消费方是否不解引用**
   判定去留——`markLine: undefined` 实测不炸，**不许改**（防无 bug churn）。
8. 每完成一项跑 `uv run pytest tests/ -q`，全绿才进入下一项。
9. 新增/改动的共享模块必须配 Node vm 测试 + **RED 验证**。
10. **改完必须真实浏览器验证**（Chromium + `.tmp/browser-venv/bin/python`），
    1920/1440/375 × light/dark。
11. 模板改完必须 `node --check` 所有 inline script（先替换 Jinja）。
12. **不要 commit / push / 部署 ECS**——完成后报告 Kimi。
13. 每完成一项，CR 写进 `docs/agent/change_requests/CR-2026-10-30_*.md`，
    并追加 `05_PROGRESS.md` / `09_CODING_HANDOFF.md` / `11_AGENT_STATE.md`。

---

## 4. 明确不做

- 改 `line-height` / `font-family` / `font-weight`
- 改色板、圆角、玻璃/夜间机制
- 恢复夜间模式按钮（本轮是**隐藏**，不是删除，更不是恢复）
- 动 R3-1 定的 pane 比例（25%/42%/10%）
- 把三等分柱状图改回来
- 后端 / 数据库 / worker
- TV 化（已收官）

---

## 5. 建议顺序

```
2.2 header 对齐（最小，先量再改）→ 2.1 夜间模式按钮隐藏（一行 CSS）
→ 2.3 K 线高度 → 2.4 FRM 7 卡排版 → 2.5 波动率显示（最复杂，留最后）
```

---

## 6. 汇报格式

按项列出：改动文件清单 / 测试结果（含 RED）/ 真实浏览器证据（6 组合、截图路径、
断言值）/ 发现但未改的问题（附理由）/ 遗留待办。
2.2 必须附 `.topbar-inner` 与 `.wrap` 的改前改后实测值；
2.5 必须附 job 58 真实数据的渲染结果。
