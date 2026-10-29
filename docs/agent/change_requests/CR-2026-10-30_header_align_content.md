# CR-2026-10-30 · 2.2 header 主要内容与页面整体 width 对齐

> 任务书：`docs/agent/change_requests/TASK-2026-10-30_deepseek_ui_round4.md` §2.2
> 实施：DeepSeek 子 agent / 复核：Kimi
> 改动文件：`src/quant_research_engine/gui/saas/templates/base.html`（仅内联 `<style>`）

---

## 1. 改前实测（真实浏览器，改前基线）

测量脚本 `.tmp/ds-round4/measure.py`（Chromium 1248，每视口独立 context，
`service_workers="block"`），结果落 `.tmp/ds-round4/measure-before.json`。

| 视口 | `header.topbar` padL | `.brand` left | `.mainnav` right | `.container`/`.wrap` padL · maxW |
|---|---|---|---|---|
| 1920 | **180px** | **180** | **1740** | 16px · 1920px |
| 1440 | **20px** | 20 | 1420 | 16px · 1920px |
| 375 | 12px | 12 | 363 | 12px · 1920px |

→ 1920 下 LOGO 与内容左缘差 **164px**，右侧同理；1440 下差 4px（不易察觉但同源）。
light / dark 数值完全一致（主题只改色，不改几何）。

## 2. 根因（三问逐条回答任务书）

1. **`.topbar-inner` 在 SaaS 侧根本不存在。** 任务书说「`.topbar-inner` max-width 已是 1920px」，
   那是 lab 页（`templates/base.html`）的版式；SaaS 的 `header.topbar` 是 `<body>` 的直接
   子元素，没有 inner 包裹层（实测 `document.querySelector('.topbar-inner') === null`，
   `.tmp/ds-round4/measure-*.json` 里 `topbarInner: null`）。所以对齐对象是
   `.container`（job 页）/`.wrap`（symbol 页），**不是** `.topbar-inner`。
2. **padding 不一致才是根因。** `static/lab-theme.css:417` 给 `.topbar` 写的是
   `padding:0 max(20px,calc((100% - 1600px)/2 + 20px))` —— 这是给 **1600px** 内容区配的公式；
   SaaS 内容列是 **1920px + 16px**（`base.html:81` 的 `.container`、`lab-theme.css:49` 的 `.wrap`）。
   公式不同 → 宽屏越宽偏得越多（1920 偏 164px，2560 将偏更多）。
3. **LOGO 宽度没有推偏内容**：`.brand` 的 `clientWidth` 三视口恒为 123/123/64px，且是 flex 首项，
   不产生位移。

## 3. 改法（未动 `lab-theme.css`）

`lab-theme.css` 的 `.topbar{...1600px...}` 同时被 lab 页（`templates/base.html`，
确有 `.topbar-inner`、内容 1600px）使用，改公式会破 lab 页版式。故只在 SaaS 的
`base.html` 内联样式里用**已有惯例**的 `header.topbar` 前缀（特异性 0,1,1 > `.topbar` 的 0,1,0）
覆盖 padding：

```css
/* 左右留白与内容列（.container/.wrap 的 max-width:1920px + 16px）逐像素对齐：
   大屏时随内容列一起居中，不再沿用 lab-theme 的 1600px 公式。 */
header.topbar{...;padding:0 max(16px,calc((100% - 1920px)/2 + 16px))}
```

断点同步（内容列在 ≤768px 收 12px）：

```css
@media (max-width:960px){ header.topbar{padding:0 16px} ... }   /* 原 12px → 16px */
@media (max-width:768px){ header.topbar{padding:0 12px} }        /* 新增：内容列也在此收 12px */
@media (max-width:400px){ header.topbar{padding:0 12px} ... }    /* 保持，与上一档同值 */
```

> 769–960px 区间的旧行为（顶栏 12px / 内容 16px，方向相反地错 4px）一并修正为 16/16。

## 4. 改后实测（真实浏览器）

| 视口 | `header.topbar` padL | `.brand` left | `.mainnav` right | 内容列 padL | 对齐判定 |
|---|---|---|---|---|---|
| 1920 | 16px | 16 | 1904 | 16 | ✅ 左缘 16=16，右缘 1920-16 |
| 1440 | 16px | 16 | 1424 | 16 | ✅ 16=16 |
| 375 | 12px | 12 | 363 | 12 | ✅ 12=12 |
| 2560（公式推算） | (2560-1920)/2+16 = 336 | 336 | 2224 | 336 | ✅ |

- `docW == scrollW == bodyScrollW`：1920/1920、1440/1440、375/375 —— **三视口均无横向溢出**。
- `pageerror` / `console.error`：**0**（`.tmp/ds-round4/log-after2.2.txt` 末尾 `=== PAGEERRORS ===` → `(none)`）。
- 截图：`.tmp/ds-round4/after2.2-{1920,1440,375}-{light,dark}-{job,sym}-{top,risk}.png`（共 24 张），
  改前对照 `before-*` 同名。

## 5. 验证

- `uv run pytest tests/ -q`：**全绿**（见 `.tmp/ds-round4/pytest-2.2.log`）。
- `node --check`：`base.html` 全部 4 个内联 script 通过（`.tmp/ds-round4/nodecheck.py`）。
- 未改 `font-family`/`font-weight`/`line-height`、未改色板、未加动效、未引 CDN。

## 6. 遗留 / 说明

- `lab-theme.css:415` 的 `.topbar` 规则（1600px 公式 + `height:60px`）在 SaaS 侧仍是
  「被覆盖的候选」，未删——它服务于 lab 页，删了会破 lab。已在 `base.html` 注释里写明覆盖关系。
- `.topbar-inner` 在 SaaS DOM 中不存在，属死代码（`lab-theme.css:37` 仍定义，供 lab 页使用）。
---

## 7. Kimi 复核补记（2026-10-30）

**独立复核结论**：本 CR 的两项改动成立，可以提交。
（更正：DeepSeek 本轮**实际完成五项里的四项**——除本 CR 的 2.1/2.2 外，
还做了 2.3（K 线高度 520→620px，含 `replay.js::klineHeightForPanes` 公式同步
抬到 `560 + panes*180`，静态与重播同源）与 2.4（`card-class.css` 新增
`#risk-body .metric-strip` 四列网格，7 卡从 6+1 变 4+3，≤960px 两列且末卡跨两列）。
这两项没有单独 CR，见下方补记；**2.5 策略详情 FRM 波动率显示未做**。）

已独立验证：
- **对齐**：Kimi 用自己写的探针（`.tmp/perf-browser` 渲染 + 三视口）复测，
  `brandLeft` 与内容列内容左缘（`.wrap` left + paddingLeft）在
  1920/1440/375 三视口**全部相等**（16/16/12px），零 pageerror、零横向溢出。
  （Kimi 首版探针误比 `.wrap` 的 border-box left = 0，报过一次假 MISALIGNED，
  已修正为内容左缘——教训：量对齐要量**内容**左缘，不是容器边框左缘。）
- **夜间模式功能保留**：`git diff --stat` 确认 `night-mode.css` 与 `night-mode.js`
  **零改动`；`qre-theme` 持久化、系统偏好跟随、防 FOUC、ECharts 主题联动均在。
- **全量测试**：`.tmp/ds-round4/pytest-2.2.log` = 3208 passed, 34 skipped。
- **`node --check`**：28 个 inline script 块 0 错。

**未完成的一项**（任务书 §2.5）：**策略详情 FRM 波动率显示优化**——
`job.html::renderRiskVol` 未改，仍是「一行状态文字 + `#chart-risk-vol` display:none」。
用户明确说「依然是简陋的当前波动率状况」，这项**待下一轮**。

**2.3/2.4 补记（无单独 CR，Kimi 复核确认）**：
- 2.3 `symbol.html:116` `#chart-kline` height 520→620px；`replay.js::klineHeightForPanes`
  无副图 520→620、有副图 `480+n*160`→`560+n*180`（1 副图 740、3 副图 1100），
  静态与重播共用同一公式未漂移；`tests/test_saas_replay_tv.py` 与
  `test_saas_replay_boundaries.py` 的高度断言同步更新。
- 2.4 `card-class.css` 新增 `#risk-body .metric-strip` 四列网格（特异性压过
  lab-theme 的 `repeat(6,1fr)`），≤960px 两列且 `.metric-card:last-child{grid-column:span 2}`
  消孤行；未引新色相、未加动效。

**待部署后验证的一项**：`header.topbar .tt-btn{display:none}` 的隐藏效果。
Kimi 本地 harness 探针出现一次自相矛盾（按钮在 DOM、CSS 规则也在页面，
但 `querySelector('header.topbar .tt-btn')` 返回 null），未能定位到根因；
部署后需在线上确认按钮确实不可见、且**不会**因 night-mode.js 的
「页面无 .tt-btn 则注入 `.tt-btn.tt-float` 悬浮钮」逻辑而冒出悬浮钮
（DeepSeek 的注释已预警这条路径）。
