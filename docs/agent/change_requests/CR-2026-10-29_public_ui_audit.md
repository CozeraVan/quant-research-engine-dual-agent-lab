# CR-2026-10-29 公网 UI 标准符合性审计与收尾

状态：已实施（1 处真实修复），未 commit/push/部署（等 Kimi 复核与用户验收）
关联：`docs/agent/change_requests/TASK-2026-10-29_deepseek_ui_round2.md` B 项；
权威标准 `docs/agent/12_UI_STYLE_GUIDE.md`、`AGENTS.md` 的 R-UI-001；
同一任务 A 项见 `CR-2026-10-29_dense_font_scale.md`

## 1. 做法

按 B3 九页 × B4 八条逐页核。九页：`/saas`（home）、`/saas/new`、`/saas/jobs/<id>`（job）、
`/saas/jobs/<id>/symbols/<code>`（symbol）、`/saas/showcase`、`/saas/profile`、
`/saas/help`、`/saas/signals`、`/saas/strategies/<id>`（strategy）。

只改**真实**违反标准的问题（「还能更好」的没动，避免 churn）。八条里只有 1 条命中真实缺陷：
`/saas/profile` 的一整段灰色小字备注 → 改 `data-tip`。

证据脚本（均在 `.tmp/ui-round2/`，不入库）：

| 脚本 | 产出 | 口径 |
|---|---|---|
| `audit_b.py` | `audit_b.json` | 9 页 × 2 主题 × 2 视口（1440x900 / 375x812）= 36 条；统计 `.opt` 数、`tip-trigger`/`data-tip` 数、表格数、玻璃卡数、文本对比度分布、横向溢出、console/pageerror |
| `probe_tips_real.py` | `probe_tips_real.json` | 7 页 × 2 主题 = 134 条**真实**交互：真实 `hover()` / 真实 `Tab` focus，逐条比对弹出文本与 `data-tip` |
| `probe_chip.py` | `probe_chip.json` | 规则 8：注入两条合成 panel 驱动真实 `renderFactorChips()`，点状态机 + 重置钮 + localStorage |
| `probe_profile.py` | `probe_profile.json` | 修复后 `profile` 四组合（light/dark × 375/1440）hover + focus |
| `probe_profile_count.py` | — | `profile` 的 `.opt` 元素数前后对比 |

## 2. 逐页结论

`light` / 1440x900 实测（`audit_b.json`）：

| 页面 | `.opt` 元素 | 其中成段灰字备注 | tip 触发点 | 表格 | 玻璃卡 | 结论 |
|---|---|---|---|---|---|---|
| home | 9 | 0（合法小标签：入口提示/计数） | 1 | 3 | 1 | 通过 |
| new | 7 | 0（示例填入提示/阈值说明） | 24 | 0 | 3 | 通过 |
| job | 10 | 0（任务号/只读标记/热力图标题） | 21 | 2 | 1 | 通过 |
| symbol | 3 | 0（行情读数/图例） | 22 | 1 | 1 | 通过 |
| showcase | 0 | 0 | 2 | 1 | 2 | 通过 |
| profile | **10 → 9**（本轮修） | **1（已修）** | 1→2 | 3 | 2 | **已修复** |
| help | 1 | 0（数据来源说明，单行标签） | 0 | 7 | 3 | 通过 |
| signals | 1 | 0 | 0 | 1 | 1 | 通过 |
| strategy | 12 | 0（状态标记/参数小标签） | 1 | 2 | 2 | 通过 |

合计 36 条取证记录，`failures=[]`，36 页次 console error 与 pageerror 均为 **0**。

## 3. 八条标准逐条结论

### 3.1 规则 1（R-UI-001，成段灰色小字备注）—— 1 处真实缺陷，已修

`profile.html:31` 的分享卡下面原来有一整段 44 字的灰字：

```html
<p class="opt" style="font-size:12.5px;margin:0 0 10px">分享链接只读、可撤销；接收方无需登录即可在有效期内查看对应结果。链接只在创建时显示一次。</p>
```

这是「成段解释性备注」，正是 R-UI-001 禁的形态（既不是计数也不是状态标记）。
改为标题上的 tip：

```html
<h2>我的分享 <button type="button" class="tip-trigger" data-tip="分享链接只读、可撤销；接收方无需登录即可在有效期内查看对应结果。链接只在创建时显示一次。" aria-label="我的分享说明">?</button></h2>
```

文案一字未删（只是从常驻小字搬到悬停说明），未新增任何灰字。

其余八页的 `.opt` 全部是**单行标签/计数/状态**（job 的「任务 #58」「经典策略展示 · 只读」、
new 的「没思路？点一个示例填入：」「约 695 只」、help 的单行来源说明等），
不构成「成段备注」，按任务书 B2 的结论维持原状。

**口径提示**：`audit_b.json` 里 profile 的 `optCount=10` 是**修复前**的值——那次审计跑在
8097 服务的模板缓存上（模板已加载，改动看不到）。修复后单独在 8098 用
`probe_profile_count.py` 复测：`.opt` 元素 **10 → 9**、`shareOptCount=0`、`shareP=0`。
不要拿 `audit_b.json` 的 10 当作修复后的数字。

### 3.2 规则 2（tip 可达性）—— 通过（134 条真实交互，0 失败）

`probe_tips_real.py` 用 Playwright 真实 `locator.hover()` 与真实键盘 `Tab`（不是合成事件），
7 页 × 2 主题共 **134 条**，`failures=[]`。每页触发点：
home 1 / new 24 / job 21 / symbol 22 / showcase 2 / profile 2 / strategy 1。耗时约 140s。
覆盖了三条要求：hover 弹、连续两次 hover 都弹（无「只弹一次」回归）、focus 弹。

同时记录了修复后 profile 的细节（`probe_profile.json`，4 个组合，`fails: []`）：
`pOptCount=0`、`tipTriggerExists=true`、`dataTip` 即原文案、
`hoverPopVisible=true`、`hoverPopText` 原文案、`popHiddenAfterMoveOut=true`、
`focusPopVisible=true`、`aria-describedby=qre-help-tip`、`aria-label=我的分享说明`。

**必须写明的假阳性**：`audit_b.json` 里 job 的 `tipHover.first=null` 与 3 处 `tipFocus` 异常，
**全部是探针口径问题，不是缺陷**：

- 旧探针 `TIP_HOVER_JS` / `TIP_FOCUS_JS` 用 `dispatchEvent(new MouseEvent('mouseover'))`
  合成事件，绕过了真实的 hover 链，`sameText` 又是整串严格比 → 误报；
- `disabled` 元素本来就不应该响应 focus，弹不出来是正确行为；
- `new` 页有大量 `label[data-tip]` 位于**折叠区**（祖先 `clientHeight=0` + `overflow:hidden`，
  `sec-body` / `sec-inner`），旧探针的 `loc.is_visible()` 对裁剪元素会误判 true，
  真实探针改用 `BRING` 检查祖先并判为 `collapsed-section` 后跳过——不是缺陷。

因此本 CR **只认 `probe_tips_real.py` 的 134 条 0 失败**，不认合成事件探针的结果。

### 3.3 规则 3（死按钮/死链）—— **未逐点核**，证据强度弱，如实标注

本轮只做了**弱证据**核验：九页 × 4 组合（36 条）加 tips 探针的 7 页次，
console error 与 pageerror 全为 0，即「没有因点击/绑定失败抛错的按钮」。

**没有**逐页逐按钮真实点击一遍（尤其 job 的结果操作卡、symbol 的 toolbar、
strategy 的每日扫描开关）。这条按「未验证」记录，不计入通过。若需强证据，建议后续
单独立项做一次「全员按钮点击回归」（点击 → 断言响应 DOM/toast/网络请求）。

### 3.4 规则 4（375px 无横向溢出）—— 通过

`audit_b.json` 里 375px 视口共 18 条记录（9 页 × 2 主题），
全部 `scrollWidth == innerWidth == 375`。修复后的 profile 亦单独复核：
`docScrollW=375`、`cardScrollW=cardClientW=349`、`h2ScrollW=h2ClientW=293`、
`h2Right=334 < cardRight=363`（tip 按钮没有撑破标题行）。

### 3.5 规则 5（夜间模式）—— 通过

dark 主题下所有页 `low<4.5` 计数均为 **0**（暗底上 muted 色达标），
红涨绿跌语义保留（沿用既有 token，本轮未动色板）。36 条记录 error 全 0。

`light` 侧存在 muted `rgb(154,147,166)` 对白底 **2.82–2.89:1**（低于 AA 4.5）：
这是**色板冻结**范围内的既有值（任务书明令不改色板），白底 muted 天然偏低，
本轮**未改**，作为已知项记录，不在本 CR 处理。

### 3.6 规则 6（玻璃卡一致性）—— 主体通过，2 处判定记录

- 通过：`.metric-card` / 磨损卡 / 风险卡 / sum-strip / ra-strip 的玻璃五要素
  （`backdrop-filter: blur(28px) saturate(140%)`、白 45–60% 透明、1px 半透明白描边、
  顶部内侧高光、24px 圆角、紫阴影）在 light 下逐项一致（九页玻璃卡计数见 §2 表）。
- **判定一（记发现项，不改）**：暗色下 job / symbol 的
  `#metric-strip / #sum-strip / #range-strip .metric-card` 是实色 `#3A3170`，
  来自 `static/night-mode.css:51-54`，`git blame` = **b4d785e8 (2026-10-27)**，
  **早于**磨砂玻璃统一轮。即「暗色这几条卡从来不是玻璃」，属既有不一致、
  不是本轮回归。建议后续单独立项（暗色玻璃覆盖名单补齐），本轮不动，避免扩大改动面。
- **判定二（设计如此，通过）**：profile 的 `.metric-card` 浅色是实色 `#F1EDF8`，
  来源是模板 L14/17/20/23 的**内联** `background:var(--tint,#F1EDF8)`，
  light/dark 表现一致，是个人页刻意的浅紫底，不判违反。

### 3.7 规则 7（图表轴标签完整）—— 通过（含一处探针口径说明）

job 的 `chart-main`：**x 轴 `show=false` 是刻意设计**（时间轴由下方另置的
`xAxis[1]` 承载且有数据），不是被裁；y 轴 `width 40/44` + `overflow:'truncate'` +
`align:'left'`，实测轴标签完整可见。

`audit_b.json` 中的 `xLabel.maxW=0` **是探针口径问题（取了被隐藏的 x 轴），不要引用**。

### 3.8 规则 8（K 线因子呈现）—— 通过（注入验证）

`probe_chip.py` 用 `page.route` 注入两条合成 factor panel，驱动页面**真实的**
`renderFactorChips()`，避免碰后端：

- 初始 chip 文案：`['EMA5·叠加', 'RSI14·独立', '重置布局']`
- 连点 EMA5 三次状态：`独立 → 隐藏 → 叠加`，localStorage `qre_fct_ema_5` 依次
  `pane / hidden / overlay`（态与持久化同步）
- 点 `#kline-chips-reset` 后 localStorage 全清、文案回到默认态
- console/pageerror 0；截图 `chip_{theme}_{initial|after_reset}.png`

**真实环境限制**：当前服务返回 `factors=None`、`factor_basis=qfq_anchor_v1`
（缺因子表，不是回归），所以 chip 真实链路走不到因子，只能用注入验证 DOM 状态机。
这一点如实记录，后续因子表恢复后应补一次真数据回归。

## 4. 范围外但已记录的数量

- **`admin.html` 管理台**：`src/quant_research_engine/gui/templates/admin.html` 模板中
  `class="opt"` **99 处**（与任务书一致），`lab.html` 39 处。
  9090 隧道当前指向的是公网站点（`curl -sL 127.0.0.1:9090/` → 200，
  最终 URL `http://127.0.0.1:9090/saas/`，仅 8 处 `.opt`），**管理台本身未做浏览器审计，
  未测渲染后的可见性**。按 B5 本轮不做，只记录模板数量留待后续。
- **`.fct-chip-reset{font-size:11.5px}`**（`lab-theme.css:583-586`）：
  **不是本 CR 的改动**，是工作区里他人未提交的 chip 三态可辨识改造。
  11.5px 低于 A 项的 12px 下限，属于遗留项，本轮不改（避免和他人改动冲突）。

## 5. 测试与验证汇总

| 项 | 结果 |
|---|---|
| 全量 `uv run pytest tests/ -q` | **3158 passed, 24 skipped, 4 warnings in 158.93s**（exit 0，A+B 都落地后）；文档收尾复跑（含并行 TV agent 新增 3 条）**3161 passed, 24 skipped in 155.60s** |
| 新增 `tests/test_ui_dense_font_scale.py` | 11 passed（先 RED 后绿，见 A 项 CR） |
| `tests/test_fct_chip_state_visible.py` + `tests/test_kline_pane_option.py`（规则 8 相关） | **19 passed** |
| 审计 36 条 | `failures=[]`，error 0 |
| tips 真实探针 134 条 | `failures=[]` |
| profile 修复 4 组合 | `fails: []`，error 0 |

## 6. 影响面

只改 1 个模板文件 `src/quant_research_engine/gui/saas/templates/profile.html`（分享卡标题行，
`<p class="opt">` → `<h2>` 内 `tip-trigger`）。未改 CSS / JS / 后端 / DB / schema / 依赖，
未新增灰字，treatment 与全站既有 tip 机制同构（`LabUI.helpTips`，复用 `qre-help-tip` 弹层）。