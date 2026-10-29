# CR-2026-10-29 密集文本字号补齐（表格 14px / 密集控件 13.5px）

状态：已实施，未 commit/push/部署（等 Kimi 复核与用户验收）
关联：`docs/agent/change_requests/TASK-2026-10-29_deepseek_ui_round2.md` A 项；
同一任务的 B 项见 `CR-2026-10-29_public_ui_audit.md`

## 1. 需求

用户 28 寸屏 + MacBook 观感「字小」。上一轮已把 `body` 提到 17px、`.chart-title` 16.5px、
`.metric-card` 数值 19px；本轮补最后两档：

- `table` 13px → **14px**（全站最大的一处断层：body 17px vs 表格 13px）
- `label` / `.muted` / `details summary` / `.chart-empty` / `.bench-bar` /
  `.tag-tabs button` / `.btn-sm` 由 12.5–13px → **13.5px**
- 下限：任何字号不得低于 12px（`.opt` 12.5px 保留不动）

不引入新字号档位，只在既有「14 / 13.5」两档上收敛；不改字体家族、不改色板、
不改圆角/玻璃/夜间机制、不加动效。

## 2. 改动（16 行，两个文件）

### 2.1 `src/quant_research_engine/gui/saas/templates/base.html`（内联 `<style>`，8 行）

| 行 | 选择器 | 原值 | 新值 |
|---|---|---|---|
| 59 | `.btn-sm` | 13px | 13.5px |
| 63 | `label` | 13px | 13.5px |
| 64 | `.muted` | 13px | 13.5px |
| 70 | `table` | 13px | **14px** |
| 112 | `summary` | 13px | 13.5px |
| 134 | `.chart-empty` | 13px | 13.5px |
| 135 | `.bench-bar` | 13px | 13.5px |
| 139 | `.tag-tabs button` | 13px | 13.5px |

### 2.2 `src/quant_research_engine/gui/static/lab-theme.css`（8 行）

| 行 | 选择器 | 原值 | 新值 |
|---|---|---|---|
| 69 | `.btn-sm` | 12.5px | 13.5px |
| 121 | `.label-inline` | 12.5px | 13.5px |
| 174 | `table.tbl` | **14.5px** | **14px** |
| 175 | `.tbl th` | 13.5px | **14px** |
| 250 | `.chart-empty` | 13px | 13.5px |
| 388 | `.chart-empty` | 13px | 13.5px |
| 403 | `.detail-table` | 13.5px | **14px** |
| 404 | `.detail-table th` | 13px | **14px** |

## 3. 四个必须解释的判断

### 3.1 `table.tbl` 原值是 14.5px，不是任务书以为的 13px —— 所以是**缩小**到 14px

任务书 A1 表把 `table.tbl` 记作 13px，实测 `lab-theme.css:174` 原值为 **14.5px**。
14.5 会让 A4 的硬断言①（`table` 计算字号 = 14px）直接失败；更要紧的是
`.tbl th` 当时是 13.5px，14.5 的表体配 13.5 的表头是**倒挂**（表头比表体小），
视觉上表头被压扁。两处一起统一到 14/14，既不倒挂，也和 `base.html` 的 `table`
14px 对齐。

### 3.2 `.detail-table` / `.detail-table th` 同样统一 14/14

原 13.5 / 13 也是表头倒挂。`.detail-table` 与 `table.tbl` 在 `lab-theme.css:582`
是同一条中性化规则的对象（`table.tbl,.syms-table,.detail-table{margin:0;background:transparent}`），
同属一个视觉族，字号保持同档。

### 3.3 `.label-inline` 12.5 → 13.5 是**被真实调用点**逼出来的

它有两个活调用点，都不是死样式：

- `saas/templates/new.html:739` —— JS 动态创建 `label.className='label-inline'`（固定阈值输入）
- `saas/templates/strategy.html:60` —— `<label class="label-inline">启用每日扫描</label>`

12.5px 是页面里最小的可交互文本，低于本轮下限目标，且与同排 `<input>`（14px）落差明显。

### 3.4 `summary` 是**裸选择器**，不是 `details summary`

`base.html:112` 写作 `details{margin-top:10px}summary{...}`。裸 `summary` 会命中
页面上所有 `<summary>`，包括不在 `<details>` 内的（若有）。改这一处等于全站折叠头
一起动 0.5px；本轮只调字号、不重写选择器结构（避免行为面扩大）。

### 3.5 没有覆盖层把 14px 打回去

已逐条确认 `.tbl td`（`lab-theme.css:178`）与 `.detail-table td`（:406）**没有**
`font-size` 声明，继承表格 14px。浏览器实测 `thFont` 与 `tables` 统计完全一致（见 §5），
证明无覆盖。

## 4. 有意不动的项

- `textarea.code` 13px、`.error` 13px —— 代码/错误块，维持等宽小字
- `.bench-bar button` 12px —— 时间轴刻度钮，受条宽约束
- `.opt` 12.5px —— 本轮只保证 ≥12px，不再放大（避免灰字重新变显眼，与 R-UI-001 方向一致）
- `.fct-chip-reset{font-size:11.5px}` —— **不是本 CR 的改动**，是工作区里他人未提交的新增
  （chip 三态可辨识改造），低于 12px 下限，已作为遗留项上报（见 B 项 CR §7.6）

## 5. 测试

### 5.1 新增单测 `tests/test_ui_dense_font_scale.py`（11 用例）

先写断言、跑出 RED（改 CSS 前 11 条全挂），再改样式转绿。

| 类 | 用例 | 断言 |
|---|---|---|
| `TestBaseInlineScale` | `test_table_font_is_14px` | `base.html` 的 `table{...}` 含 `font-size:14px` |
| | `test_th_did_not_override_below_14` | 无 `th` 字号 < 14px 的声明 |
| | `test_helper_scale_is_13_5px` | `label` / `.muted` / `summary` / `.chart-empty` / `.bench-bar` / `.tag-tabs button` / `.btn-sm` 均 13.5px |
| | `test_old_13px_helper_scale_gone` | 上述选择器不再出现 13px |
| `TestLabThemeScale` | `test_table_tbl_is_14px` | `table.tbl` = 14px（含防回退到 14.5） |
| | `test_tbl_th_is_14px` | `.tbl th` = 14px |
| | `test_detail_table_is_14px` | `.detail-table` 与 `.detail-table th` = 14px |
| | `test_btn_sm_not_shrinking_base` | `.btn-sm` 13.5px（不小于 base） |
| | `test_label_inline_is_13_5px` | `.label-inline` = 13.5px |
| | `test_chart_empty_is_13_5px_in_both_places` | 两处 `.chart-empty`（:250 / :388）都 13.5px |
| `TestOptFloor` | `test_no_opt_declaration_below_12px` | 任何 `.opt` 字号不低于 12px |

结果：`11 passed`。

### 5.2 全量

`uv run pytest tests/ -q` → **3158 passed, 24 skipped, 4 warnings in 158.93s**（exit 0，
跑在 `profile.html` 改动之后，即 A+B 两项都落地后的绿灯）。

文档收尾时又复跑一次（工作区已混入并行 TV agent 新增的 3 条测试）：
**3161 passed, 24 skipped in 155.60s**（exit 0）。

## 6. 真实浏览器验证（Chromium，8 页 × 3 视口 × 2 主题 = 48 组合）

脚本 `.tmp/ui-round2/verify_a.py` → `.tmp/ui-round2/result_a.json`
（页面 home / new / job / symbol / symbols / showcase / profile / help；
视口 1920x1080 / 1440x900 / 375x812；主题 light / dark；截图 `shot_{theme}_{w}_{page}.png`）。

| 项 | 实测值 |
|---|---|
| `failures` | `[]`（0） |
| 表格计算字号（`class:font-size` 计数） | `{('tbl','14px'):84, ('(none)','14px'):18, ('detail-table','14px'):6}` |
| 表头计算字号（`thFont`） | **完全相同**：`{('tbl','14px'):84, ('(none)','14px'):18, ('detail-table','14px'):6}` |
| 文本裁切 `clipped` | 48 组合全部 `[]`（0 处） |
| 横向溢出 `scrollWidth - innerWidth` | 48 组合全部 `0` |
| console error + pageerror | **0** |
| 采样最小字号 `minFonts` | `.muted` 13.5px、`details summary` 13.5px、`.btn-sm` 13.5px |

表头与表体字号计数逐项相同，是「无 th 覆盖」的直接证据；48 组合零裁切零横溢，
说明 14px 没有把行高/列宽撑破（375px 窄屏同样 0）。

## 7. 影响面

- 只改两个纯样式文件：`saas/templates/base.html`（内联 style 段）与
  `static/lab-theme.css`。
- `lab-theme.css` 是**实验室 8081 与 SaaS 共用**的样式表，8081 侧表格/密集控件同步
  放大 0.5–1px（同一套视觉，属预期）。
- 未改任何 Python、模板结构、DB、schema、依赖；未新增灰字（R-UI-001）。
- 未 commit / push / 部署 ECS（任务书边界）。