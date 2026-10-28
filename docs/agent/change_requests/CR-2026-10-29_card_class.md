# CR-2026-10-29 小数据卡统一「白底紫框」并收敛为单一权威文件

状态：已实施，未 commit/push（等用户验收）
关联：`CR-2026-10-28_card_unify.md`（上一轮改紫底，本轮按用户要求推翻）、
`CR-2026-10-28_card_frosted_glass.md`（磨砂玻璃卡族）

## 1. 需求（用户 2026-10-29 定稿）

1. **取消所有紫底的小 div**，全部改为**白底**；
2. 中性数据（日期、暴露度等）设计为**紫色**；
3. 有盈亏属性的数据：正收益率**红色**、亏损**绿色**；
4. 回测首页、个股回测详情里**顶部小 div、重播 div 小 div、交易磨损、风险分析**四类，
   本版仍白紫混搭，要求**统一作为一类**，便于未来统一改风格；现统一为**白底紫框**。

## 2. 根因：规则散在三处，改一处漏两处

这类卡**一律由 `.metric-card` 渲染**，但样式规则分散在三处：

| 位置 | 规则 | 结果 |
|---|---|---|
| `base.html` 内联 | `.metric-card{background:#fff;border:1px solid var(--line)}` | 白底灰框 |
| `base.html` 内联（上一轮） | 六条指标条 ID 覆盖 `--tint` 紫底 | 指标条紫底 |
| `lab-theme.css` | `.metric-strip .metric-card{...var(--line)}` | 白底灰框（后加载赢 base） |
| `lab-theme.css` | `.risk-cards .metric-card{border-color:#F0CACA;background:#FFFBFB}` | **粉底粉框** |
| 模板 `wc()` | `<div class="m-value flat" style="color:var(--lav-deep)">` | **内联强制紫**，压过一切 CSS |

上一轮（CR-2026-10-28）只把六条指标条并进紫底名单，**漏了 `.wear-cards`（交易磨损）与
`.risk-cards`（风险分析）**，后者还吃着 lab-theme 的粉底粉框 → 用户看到的白/紫/粉混搭。

## 3. 修复

### 3.1 新建 `static/card-class.css` —— 这类卡的唯一权威

在 `lab-theme.css` / `night-mode.css` **之后**加载（同特异性下后加载胜出，这是它能压住
lab-theme 粉底粉框的唯一机制）。文件头用注释写死「一类卡」的定义与全部落点：

- **基类（白底紫框）**：`.metric-strip .metric-card, .wear-cards .metric-card,
  .risk-cards .metric-card, .metric-card{background:#fff;border:1px solid var(--lav);
  border-radius:10px}`
  （用容器类选择器把特异性提到与 lab-theme 同级，靠后加载胜出；裸 `.metric-card` 兜底）
- **数值色**：`.metric-card .m-value{color:var(--lav-deep)}`（中性紫）；
  `.metric-card .m-value.pos{color:var(--pos)}` / `.neg{color:var(--neg)}`
  —— **必须用 0,3,0 显式提级**，否则会被 0,2,0 的 `.metric-card .m-value` 压住，
  盈亏就不再是红绿（RED 验证专门测这条）
- **磨损条盈亏值**：`.wb-val.pos` / `.wb-val.neg`（同理，lab-theme 的 `.wb-val{color:var(--ink)}`
  同特异性但先加载）
- **磨损/风险条收回**：`.wear-cards .metric-card, .risk-cards .metric-card
  {background:#fff;border-color:var(--lav)}`
- **布局**：六条小卡条 flex 自适应（密集条 min 130px，简介/ra 条 min 250px）——沿用上轮实测值

### 3.2 `base.html`

- 末尾加 `<link rel="stylesheet" href="/static/card-class.css">`
- **删掉**上一轮加在内联里的六条指标条紫底 + flex 规则，只留 `.metric-strip` /
  `.metric-card` 基类兜底（card-class.css 未加载时页面仍可用，退回白底灰框）

### 3.3 `job.html` / `symbol.html`

- 两个 `wc()`（磨损卡渲染）去掉内联 `style="color:var(--lav-deep)"` —— 内联样式压过一切
  CSS，是「统一风格」最大的漏洞
- 磨损条毛/净收益值（`.wb-val`）按盈亏加 `pos`/`neg` 类（共 6 处：两模板各 3 条路径）

## 4. 测试

`tests/test_perf_metrics.py::TestMetricStripStyleContract` 重写为 8 例：

1. `test_card_class_css_is_loaded_last` —— 加载顺序 lab → night → card-class
2. `test_base_no_longer_overrides_card_background` —— base 内联不得再出现
   `.metric-card` 的 `--tint` 规则或按 ID 的覆盖（只挑含 `.metric-card` 的规则检查，
   不误伤 `.sidenav`/`.wb-track` 等本就该用 `--tint` 的元素）
3. `test_all_cards_white_bg_purple_border` —— 基类含 `.wear-cards`/`.risk-cards`
   （防再漏），且显式收回粉底粉框
4. `test_value_colors_neutral_purple_pnl_red_green` —— 中性紫 + `.pos`/`.neg` 提级
5. `test_dense_strips_fit_seven_in_one_row` —— 密集条 min ≤130px
6. `test_summary_and_ra_strips_use_wider_basis` —— 简介/ra 条 min 250px
7. `test_no_leftover_grid_rules_for_these_strips` —— 无 grid 死代码
8. `test_wear_renderers_do_not_force_inline_color` —— 模板不得内联强制色 + 磨损条必须上色

**RED 验证**：① 把 `.wear-cards`/`.risk-cards` 从基类选择器里删掉 → 例 3 红；
② 删掉 `.m-value.pos`/`.neg` 提级规则 → 例 4 红。恢复后 18 passed。

## 5. 真实浏览器验证（Chromium，`.tmp/perf-browser/verify.py`）

fixture 补齐 `wear` / `risk` / `fees_summary` / `risk_analysis`，对 job/symbol 两页
× 1440/1024/375 六个组合 + 磨损/风险条，断言**白底 + 紫框 + 数值色三分 + 行内等宽 +
非末行填满 + 无溢出**：

| 位置 | 卡数 | 背景 | 边框 | 数值色 |
|---|---|---|---|---|
| job `#metric-strip` 1440/1024 | 7（一行） | 白 | 紫 `#6750A4` | 紫/红/绿 |
| job `#ra-strip` | 3（撑满） | 白 | 紫 | 红/紫 |
| job `#fees-body`（磨损） | 5 | 白 | 紫 | 全中性紫 |
| job `#risk-body`（风险） | 4 | 白 | 紫 | **全绿**（VaR/ES 是损失） |
| symbol `#sum-strip` 1440 | **4+4** | 白 | 紫 | 紫/红 |
| symbol `#ra-strip` | 3（撑满） | 白 | 紫 | 红/紫 |
| symbol `#wear-body`（磨损） | 5 | 白 | 紫 | 全中性紫 |
| symbol `#risk-body`（风险） | 7 | 白 | 紫 | 全中性紫 |
| 375px（两页各条） | 正常换行 | 白 | 紫 | — |

同时复验：α=12.00% / β=0.89 / IR=0.78（与 Python `performance_summary` 一致）、
平均持股周期 45.3/48.7 天、LWC 图例 5 pill 往返全通。**零 pageerror。**

截图 `.tmp/perf-browser/symbol-cards.png`：可见 4+4+3 全白底紫框，中性值紫、盈亏值红。

## 6. 过程中抓到的两个真问题

1. **`--lav-deep` 是 `#4A3A78` = rgb(74, 58, 120)**，我期望值一度写成 `rgb(74,60,120)`
   （#4A3C78）→ 断言红。这类断言必须用真实计算值，不能手写猜。
2. **`loadRisk()` 要求 payload 带 `has_report: true`**，否则整块隐藏——fixture 第一次没带，
   job 风险条被 skip。补上后 4 张卡才渲染出来。

## 7. 影响面

- 新增 `static/card-class.css`（需随部署上传）
- 改 `base.html`（加 link + 删旧规则）、`job.html`、`symbol.html`（去内联色 + 磨损条上色）
- lab（8081）页面不用这些容器类，不受影响；`.metric-card` 的玻璃/夜间规则未动
- **未来改这类卡的风格只改 `card-class.css` 一个文件**；新增小卡条只需把容器 ID 加进
  它的 flex 规则，背景/边框/数值色由基类自动继承
